__all__ = ['SystemManager']

from collections.abc import Hashable, Iterable, Iterator
from typing import TYPE_CHECKING, Any, NamedTuple
from weakref import ref as weakref

from pyriak import EventQueue, dead_weakref, key_functions, subclasses
from pyriak.events import (
  EventHandlerAdded,
  EventHandlerRemoved,
  SendEvent,
  SpaceCallback,
  SystemAdded,
  SystemRemoved,
)
from pyriak.system import System, _Callback


if TYPE_CHECKING:
  from pyriak import Space


class _EventHandler(NamedTuple):
  """Object that holds the info for a single event handler callback in a SystemManager.

  A function on a system can be bound to event types. If a function is bound
  to at least one event type (most common is just one), then it is an event handler
  callback. A binding (of an event type), its info (keys and priority),
  and the callback are considered one event handler.
  There is usually a separate event handler object for event type for each callback.
  However, if a function is bound to multiple event types with the same priority object,
  then the event handler object is shared (implementation detail). Here, keys do
  not affect sharing because it is not kept in the event handler object.
  This is a common case for callbacks with multiple bindings because a callback
  is only a single function, so its event types must usually be very similar and
  therefore their priority is similar. (Otherwise, it would be two separate callbacks.)

  The data stored in this object is used for invoking, sorting, and storing
  the event handler.
  This object stores more data than _Binding because there is less context available.
  """

  system: System
  callback: _Callback
  name: str
  priority: Any

  def __call__(self, /, *args, **kwargs):
    return self.callback(*args, **kwargs)

  def __eq__(self, other: object):
    if self is other:
      return True
    if isinstance(other, _EventHandler):
      return self.name == other.name and self.system == other.system
    return NotImplemented

  def __hash__(self):
    return hash((self.name,self.system))

del NamedTuple


class SystemManager:
  __slots__ = (
    '_space', '_systems', '_handlers', '_key_handlers', 'event_queue', '__weakref__'
  )

  def __init__(
    self,
    systems: Iterable[System] = (),
    /,
    space: 'Space | None' = None,
    event_queue: EventQueue | None = None
  ):
    self.space = space
    self.event_queue = event_queue
    # values aren't used: dict is for insertion order
    self._systems: dict[System, None] = {}
    self._handlers: dict[type, list[_EventHandler]] = {}
    self._key_handlers: dict[type, dict[Hashable, list[_EventHandler]]] = {}
    self.add(*systems)

  def process(self, event: object, space: 'Space | None' = None) -> bool:
    """Handle an event. Callbacks of the event are passed space and event.

    If the Event type has no binds, do nothing.
    If event is an instance of SpaceCallback or SendEvent, it is handled differently.
    If a callback returns a truthy value, the
    rest of the callbacks are skipped and True is returned, else False.
    """
    if space is None:
      space = self.space
      if space is None:
        raise TypeError("process() missing 'space'")
    for handler in self._get_handlers(event)[:]:
      if handler.callback(space, event):
        return True
    if isinstance(event, SpaceCallback) and event(space):
      return True
    if isinstance(event, SendEvent):
      receivers = event.receivers
      event = event.event
      for handler in [
        handler for handler in self._get_handlers(event) if handler.system in receivers
      ]:
        if handler.callback(space, event):
          return True
    return False

  def add(self, *systems: System) -> None:
    """[[Add systems, their priorities, and systems' event binds to self, from objs.

    Each obj in objs can be:
    - an argument to be passed into dict(), to construct a dictionary
      with items of System for key and priority for value.
      Any priorities that are None are replaced with
      its corresponding System's default priority.
    - else (dict construction fails), a System,
      whose priority will be its default priority.

    The order in which the Systems are added is that Systems from the first objs
    are added first.

    Adding or removing a system is expensive because of the
    binding or unbinding of event bind system callbacks.
    This is so that triggering events is fast.
    Any Systems already in self have their priority updated (and event binds rebound),
    and don't trigger SystemAdded event.
    Systems not already in self get their _added_ method
    invoked right after they are added and bound.]]
    """
    self_systems = self._systems
    bind = self._bind
    for system in systems:
      if system in self_systems:
        continue
      self_systems[system] = None
      events = bind(system)
      space = self.space
      event_queue = self.event_queue
      if space is None:
        if event_queue is not None:
          event_queue.extend([
            SpaceCallback(system._added_), SystemAdded(system), *events
          ])
      else:
        if event_queue is not None:
          event_queue.extend([SystemAdded(system), *events])
        system._added_(space)

  def remove(self, *systems: System) -> None:
    """Remove systems and their event handlers from self.

    Removing Systems is expensive (see SystemManager.add method for why).
    Right after a System is removed and unbound, its _removed_ method invoked.
    Raises KeyError if any of the systems are not in self.
    """
    self_systems = self._systems
    unbind = self._unbind
    for system in systems:
      del self_systems[system]
      events = unbind(system)
      space = self.space
      event_queue = self.event_queue
      if space is None:
        if event_queue is not None:
          event_queue.extend([
            SpaceCallback(system._removed_), SystemRemoved(system), *events
          ])
      else:
        if event_queue is not None:
          event_queue.extend([SystemRemoved(system), *events])
        system._removed_(space)

  def discard(self, *systems: System) -> None:
    self_systems = self._systems
    for system in systems:
      if system in self_systems:
        self.remove(system)

  def __iter__(self):
    """Return an iterator of all systems in self, in the order they were added."""
    return iter(self._systems)

  def __reversed__(self):
    return reversed(self._systems)

  def __len__(self):
    return len(self._systems)

  def __contains__(self, obj: object, /):
    """Return whether obj is a system added to self (ignoring subclasses)."""
    return obj in self._systems

  def clear(self):
    """Remove all systems and event handlers from self.

    Does not trigger any events.
    Does not invoke System._removed_ method.
    Does not change self's space or event_queue.
    """
    self._handlers.clear()
    self._key_handlers.clear()
    self._systems.clear()

  @property
  def space(self) -> 'Space | None':
    return self._space()

  @space.setter
  def space(self, value: 'Space | None'):
    self._space = dead_weakref if value is None else weakref(value)

  @staticmethod
  def _insert_handler(list: list[_EventHandler], handler: _EventHandler, /) -> None:
    """Inserts a handler into a list of other handlers.

    Sorts by: highest priority, then oldest handler.
    """
    priority = handler.priority
    lo = 0
    hi = len(list)
    while lo < hi:
      mid = (lo + hi) // 2
      if list[mid].priority < priority:
        hi = mid
      else:
        lo = mid + 1
    list.insert(lo, handler)

  class _SortKey:
    __slots__ = 'handler', 'systems'
    def __init__(self, handler: _EventHandler, systems: Iterable[System], /):
      self.handler = handler
      self.systems = systems
    def __lt__(self, other: 'SystemManager._SortKey', /) -> bool:
      handler = self.handler
      other_handler = other.handler
      other_priority = other_handler.priority
      handler_priority = handler.priority
      if not (other_priority == handler_priority):
        return other_priority < handler_priority
      system = handler.system
      other_system = other_handler.system
      if system is not other_system:
        for s in self.systems:
          if s is system:
            return True
          if s is other_system:
            return False
        raise ValueError
      name = handler.name
      other_name = other_handler.name
      for n in system._handlers_:
        if other_name == n:
          return False
        if name == n:
          return True
      raise ValueError

  def _sort_handlers(
    self, handlers: Iterable[_EventHandler], /
  ) -> list[_EventHandler]:
    SortKey = self._SortKey
    systems = self._systems
    # Uses dict to remove duplicates while preserving some order
    return sorted(dict.fromkeys(handlers), key=lambda h: SortKey(h, systems))

  def _get_handlers(self, event: object, /) -> list[_EventHandler]:
    event_type = type(event)
    try:
      handlers = self._handlers[event_type]
    except KeyError:
      handlers = self._lazy_bind(event_type)
      if not key_functions.exists(event_type):
        return handlers
      key_handlers = self._lazy_key_bind(event_type)
    else:
      if event_type not in self._key_handlers:
        return handlers
      key_handlers = self._key_handlers[event_type]
    key = key_functions(event_type)(event)
    if not isinstance(key, Iterator):
      try:
        return key_handlers[key]
      except KeyError:
        return handlers
    keys = {k for k in key if k in key_handlers}
    if len(keys) > 1:
      return self._sort_handlers(handler for key in keys for handler in key_handlers[key])
    if keys:
      return key_handlers[keys.pop()]
    return handlers

  def _bind(self, system: System, /) -> list[EventHandlerAdded]:
    """Bind a system's handlers so that they can process events.

    If a specified event type does not exist, _lazy_bind is called to find
    bindings for it based on existing superclasses.

    Bindings of an event type are sorted by highest priority,
    then oldest system, then first one bound in system.
    """
    if not isinstance(system, System):
      raise TypeError(f'{system!r} is not a System')
    if not system._bindings_:
      return []
    handler_events: list[EventHandlerAdded] = []
    all_handlers = self._handlers
    all_key_handlers = self._key_handlers
    insert_handler = self._insert_handler
    fromkeys = dict.fromkeys
    for name, bindings in system._bindings_.items():
      callback = getattr(system, name)
      if len(bindings) == 1:
        # the common case of only one event type for a handler (single @bind())
        [(event_type, binding)] = bindings.items()
        handler = _EventHandler(system, callback, name, binding.priority)
        event_handlers = {
          cls: handler for cls in subclasses(event_type) if cls in all_handlers
        }
        key_event_types = event_handlers.keys() & all_key_handlers
        event_handlers[event_type] = handler
        if key_functions.exists(event_type):
          key_event_types.add(event_type)
        binding_keys = binding.keys
        handler_keys = (
          fromkeys(key_event_types, fromkeys(binding_keys, handler))
          if binding_keys else {}
        )
        handler_events.append(EventHandlerAdded(handler, event_type, binding_keys))
      else:
        event_handlers = {}
        base_handler_keys: dict[type, dict[Hashable, _EventHandler]] = {}
        cached_handlers: dict[int, _EventHandler] = {}
        for event_type, binding in bindings.items():
          priority = binding.priority
          priority_id = id(priority)
          if priority_id in cached_handlers:
            handler = cached_handlers[priority_id]
          else:
            handler = cached_handlers[priority_id] = _EventHandler(
              system, callback, name, priority
            )
          binding_keys = binding.keys
          if binding_keys:
            base_handler_keys[event_type] = fromkeys(binding_keys, handler)
          handler_events.append(EventHandlerAdded(handler, event_type, binding_keys))
        del cached_handlers
        # Subclasses of bound event types may also trigger the event handler,
        # and will inherit their binding (keys and priority).
        # In the rare case that a class is the subclass of multiple bound
        # event types, the subclass will try to inherit the bindings of all,
        # but the first bound type in its MRO will take precedence
        # for shared keys (or when the subclass is keyless).
        # A bound event type may be the subclass of other bound event types.
        for cls in {
          cls
          for event_type in bindings
          for cls in subclasses(event_type)
          if cls in all_handlers
        }:
          for base in cls.__mro__:
            if base in bindings:
              event_handlers[cls] = event_handlers[base]
              break
          else:
            raise RuntimeError
        handler_keys = {}
        key_event_types = event_handlers.keys() & all_key_handlers
        key_event_types |= {cls for event_type in bindings if key_functions.exists(cls)}
        for cls in key_event_types:
          inherit_items = [
            item
            for base in cls.__mro__
            if base in bindings and base in base_handler_keys
            for item in base_handler_keys[base].items()
          ]
          # The first bases in the MRO should have their key object: handler pairs
          # take precedence. In a dict, the first keys put in are kept, and the
          # last values put in are kept. So, this accounts for that.
          inherit_handler_keys = dict(reversed(inherit_items))
          handler_keys[cls] = {
            (k:=item[0]): inherit_handler_keys[k] for item in inherit_items
          }

      for event_type, handler in event_handlers.items():
        handlers = (
          all_handlers[event_type] if event_type in all_handlers
          else self._lazy_bind(event_type)
        )
        if event_type not in key_event_types:
          insert_handler(handlers, handler)
          continue
        key_handlers = (
          all_key_handlers[event_type] if event_type in all_key_handlers
          else self._lazy_key_bind(event_type)
        )
        keys = handler_keys.get(event_type, {})
        if not keys:
          insert_handler(handlers, handler)
          for handlers in key_handlers.values():
            insert_handler(handlers, handler)
          continue
        for key, handler in keys.items():
          if key not in key_handlers:
            key_handlers[key] = handlers[:]
          insert_handler(key_handlers[key], handler)
    return handler_events

  def _lazy_bind(self, event_type: type, /) -> list[_EventHandler]:
    """Find bindings for event_type and bind them and return the handlers.

    Subclass instances of an event_type can be processed by superclass handlers.
    These subclasses are only bound when a subclass is processed. Hence, lazy binding.
    """
    all_handlers = self._handlers
    event_handlers = [
      handler
      for ev_t in event_type.__mro__
      if ev_t in all_handlers
      for handler in all_handlers[ev_t]
    ]
    if event_handlers:
      event_handlers = self._sort_handlers(event_handlers)
    all_handlers[event_type] = event_handlers
    return event_handlers

  def _lazy_key_bind(
    self, event_type: type, /
  ) -> dict[Hashable, list[_EventHandler]]:
    all_key_handlers = self._key_handlers
    inherit_key_handlers = [
      item
      for ev_t in event_type.__mro__
      if ev_t in all_key_handlers
      for item in all_key_handlers[ev_t].items()
    ]
    key_handlers: dict[Hashable, list[_EventHandler]] = {}
    if inherit_key_handlers:
      base_handlers = self._handlers[event_type]
      for key, handlers in inherit_key_handlers:
        if key in key_handlers:
          key_handlers[key] += handlers
        else:
          key_handlers[key] = base_handlers[:] + handlers
      sort_handlers = self._sort_handlers
      for handlers in key_handlers.values():
        handlers[:] = sort_handlers(handlers)
    all_key_handlers[event_type] = key_handlers
    return key_handlers

  def _unbind(self, system: System, /) -> list[EventHandlerRemoved]:
    """Remove all handlers that belong to system from self.

    If an event type no longer has any handlers, it is removed.
    This also applies to keys with handlers.
    """
    events: list[EventHandlerRemoved] = []
    all_handlers = self._handlers
    all_key_handlers = self._key_handlers
    for name, event_types in system._bindings_.items():
      for cls, binding in event_types.items():
        for event_type in subclasses(cls):
          try:
            handlers = all_handlers[event_type]
          except KeyError:
            continue
          handlers[:] = [
            handler for handler in handlers if handler.system is not system
          ]
          if not handlers:
            del all_handlers[event_type]
          if event_type not in all_key_handlers:
            continue
          key_handlers = all_key_handlers[event_type]
          for key, handlers in key_handlers.items():
            handlers[:] = [
              handler for handler in handlers if handler.system is not system
            ]
            if not handlers:
              del key_handlers[key]
          if not key_handlers:
            del all_key_handlers[event_type]
        events.append(EventHandlerRemoved(
          system, getattr(system, name), name, binding.priority, cls, binding.keys
        ))
    return events
