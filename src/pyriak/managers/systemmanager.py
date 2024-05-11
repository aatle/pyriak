__all__ = ['SystemManager']

from collections.abc import Generator, Hashable, Iterable
from typing import TYPE_CHECKING, Any, NamedTuple
from weakref import ref as weakref

from pyriak import EventQueue, NoKey, NoKeyType, dead_weakref, key_functions, subclasses
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


# event subhandler dict type alias


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
  __slots__ = '_space', '_systems', '_handlers', '_event_queue', '__weakref__'

  def __init__(
    self,
    systems: Iterable[System] = (),
    /,
    space: 'Space | None' = None,
    event_queue: EventQueue | None = None
  ):
    self.space = space
    self._event_queue = event_queue
    # values aren't used: dict is for insertion order
    self._systems: dict[System, None] = {}
    self._handlers: dict[
      type, list[_EventHandler] | dict[Hashable | NoKeyType, list[_EventHandler]]
    ] = {}
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
    self._systems.clear()

  @property
  def space(self) -> 'Space | None':
    return self._space()

  @space.setter
  def space(self, value: 'Space | None'):
    self._space = dead_weakref if value is None else weakref(value)

  @space.deleter
  def space(self):
    self._space = dead_weakref

  @property
  def event_queue(self) -> EventQueue | None:
    event_queue = self._event_queue
    if event_queue is None:
      space = self.space
      if space is not None:
        return space.event_queue
    return event_queue

  @event_queue.setter
  def event_queue(self, value: EventQueue | None):
    self._event_queue = value

  @event_queue.deleter
  def event_queue(self):
    del self._event_queue

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

  def _sorted_handlers(
    self, handlers: Iterable[_EventHandler], /
  ) -> list[_EventHandler]:
    SortKey = self._SortKey
    systems = self._systems
    return sorted(handlers, key=lambda h: SortKey(h, systems))

  def _get_handlers(self, event: object, /) -> list[_EventHandler]:
    event_type = type(event)
    try:
      handlers = self._handlers[event_type]
    except KeyError:
      handlers = self._lazy_bind(event_type)
    try:
      key_function = key_functions(event_type)
    except KeyError:
      return handlers  # type: ignore
    key = key_function(event)
    if not isinstance(key, Generator):
      try:
        return handlers[key]  # type: ignore
      except KeyError:
        return handlers[NoKey]  # type: ignore
      except TypeError:
        pass
    keys = {k for k in key if k in handlers}  # type: ignore
    if not keys:
      return handlers[NoKey]  # type: ignore
    if len(keys) == 1:
      return handlers[keys.pop()]
    return self._sorted_handlers({
      handler: None for key in keys for handler in handlers[key]
    })  # preserving order slightly by using a dict instead of set

  def _bind(self, system: System, /) -> list[EventHandlerAdded]:
    """Bind a system's handlers so that they can process events.

    If a specified event type does not exist, _lazy_bind is called to find
    bindings for it based on existing superclasses.

    Bindings of an event type are sorted by highest priority,
    then oldest system, then first one bound in system.
    """
    try:
      if not system._bindings_:
        return []
    except AttributeError:
      if isinstance(system, System):
        raise
      raise TypeError(f'{system!r} is not a System') from None
    events: list[EventHandlerAdded] = []
    all_handlers = self._handlers
    insert_handler = self._insert_handler
    for name, bindings in system._bindings_.items():
      callback = getattr(system, name)
      if len(bindings) == 1:
        # the common case of only one event type for a handler (single @bind())
        [(event_type, binding)] = bindings.items()
        handler = _EventHandler(system, callback, name, binding.priority)
        event_handlers = {
          cls: handler for cls in subclasses(event_type) if cls in all_handlers
        }  #= only strict
        event_handlers[event_type] = handler
        keys = binding.keys
        events.append(EventHandlerAdded(handler, event_type, keys))
        if not keys:
          handler_keys = {}
        else:
          keys = dict.fromkeys(keys, handler)
          handler_keys = {
            cls: keys for cls in event_handlers if key_functions.exists(cls)
          }
      else:
        event_handlers = {}
        base_handler_keys = {}
        for event_type, binding in bindings.items():
          keys = binding.keys
          priority = binding.priority
          for other_handler in event_handlers.values():
            if priority is other_handler.priority:
              # saves memory: duplicate handler for different event types that have same
              # priority, is likely because multibinding is usually for similar classes
              event_handlers[event_type] = handler = other_handler
              break
          else:
            event_handlers[event_type] = handler = _EventHandler(
              system, callback, name, priority
            )
          if keys:
            base_handler_keys[event_type] = dict.fromkeys(keys, handler)
          events.append(EventHandlerAdded(handler, event_type, keys))
        handler_keys = {}
        for cls in {
          cls
          for event_type in bindings
          for cls in subclasses(event_type)
          if cls in all_handlers or cls in bindings
        }:
          # The subclasses of a bound event type shall have their keys extended by
          # the bound event type's direct keys, if there exists a key function for it.
          key_function_exists = key_functions.exists(cls)
          for base in cls.__mro__:
            # check each 'base' event type to see if its keys are needed
            if base not in bindings:
              continue
            if cls not in event_handlers:
              # copy the event handler for the subclass if it's not already there
              event_handlers[cls] = event_handlers[base]
            if not (key_function_exists and base in handler_keys):
              continue
            if cls not in handler_keys:
              # copy the keys for the subclass if it's not already there
              handler_keys[cls] = dict(base_handler_keys[base])
              continue
            keys = handler_keys[cls]
            for k, v in base_handler_keys[base].items():
              # keys of the highest in mro will take priority over lower
              if k not in keys:
                # different keys may have different handler priorities because of
                # different event types, so there may be different event handlers
                keys[k] = v

      for event_type, handler in event_handlers.items():
        try:
          handlers = all_handlers[event_type]
        except KeyError:
          if event_type not in bindings:
            continue
          handlers = self._lazy_bind(event_type)
        if not key_functions.exists(event_type):
          insert_handler(handlers, handler)  # type: ignore
          continue
        keys = handler_keys.get(event_type, ())
        if not keys:
          for subhandlers in handlers.values():  # type: ignore
            insert_handler(subhandlers, handler)
          continue
        for key, subhandler in keys.items():
          if key in handlers:
            insert_handler(handlers[key], subhandler)  # type: ignore
          else:
            subhandlers = list(handlers[NoKey])  # type: ignore
            handlers[key] = subhandlers  # type: ignore
            insert_handler(subhandlers, subhandler)
    return events

  def _lazy_bind(
    self, event_type: type, /
  ) -> list[_EventHandler] | dict[Hashable | NoKeyType, list[_EventHandler]]:
    """Find bindings for event_type and bind them and return the handlers.

    Subclass instances of an event_type can be processed by superclass handlers.
    These subclasses are only bound when a subclass is processed. Hence, lazy binding.
    """
    all_handlers = self._handlers
    inherit_handlers = {
      ev_t: all_handlers[ev_t] for ev_t in event_type.__mro__ if ev_t in all_handlers
    }
    if not inherit_handlers:
      event_handlers = (
        [] if not key_functions.exists(event_type) else {NoKey: []}
      )  # type: ignore
      all_handlers[event_type] = event_handlers
      return event_handlers
    # dicts with ignored values are used (instead of lists or sets)
    # to remove duplicate handlers and somewhat preserve ordering,
    # before converting back into sorted list
    if not key_functions.exists(event_type):
      event_handlers = {}
      for ev_t, handlers in inherit_handlers.items():
        if key_functions.exists(ev_t):
          handlers = handlers[NoKey]  # type: ignore
        event_handlers.update(dict.fromkeys(handlers))  # type: ignore
      event_handlers = self._sorted_handlers(event_handlers)  # type: ignore
    else:
      event_handlers: dict[
        Hashable | NoKeyType, list[_EventHandler]
      ] = {NoKey: {}}  # type: ignore
      nokey_handlers_list = []
      for ev_t, handlers in inherit_handlers.items():
        if not key_functions.exists(ev_t):
          nokey_handlers_list.append(dict.fromkeys(handlers))
          continue
        for key, subhandlers in handlers.items():  # type: ignore
          if key is NoKey:
            nokey_handlers_list.append(subhandlers)
            continue
          if key in event_handlers:
            event_handlers[key].update(dict.fromkeys(subhandlers))  # type: ignore
          else:
            event_handlers[key] = dict.fromkeys(subhandlers)  # type: ignore
      inherit_nokey_handlers = {
        h: None for nokey_handlers in nokey_handlers_list for h in nokey_handlers
      }
      for subhandlers in event_handlers.values():
        subhandlers.update(inherit_nokey_handlers)  # type: ignore
      sorted_handlers = self._sorted_handlers
      event_handlers = {k: sorted_handlers(v) for k, v in event_handlers.items()}
    all_handlers[event_type] = event_handlers
    return event_handlers

  def _unbind(self, system: System, /) -> list[EventHandlerRemoved]:
    """Remove all handlers that belong to system from self.

    If an event type no longer has any handlers, it is removed.
    This also applies to keys with subhandlers.
    """
    events: list[EventHandlerRemoved] = []
    all_handlers = self._handlers
    for event_types in system._bindings_.values():
      for cls, binding in event_types.items():
        for event_type in subclasses(cls):
          try:
            handlers = all_handlers[event_type]
          except KeyError:
            continue
          if not key_functions.exists(event_type):
            for handler in handlers[:]:  # type: ignore
              if handler.system is system:
                handlers.remove(handler)  # type: ignore
            if not handlers:
              del all_handlers[event_type]
            continue
          remove_event_type = True
          for key, subhandlers in handlers.items():  # type: ignore
            for handler in subhandlers[:]:
              if handler.system is system:
                subhandlers.remove(handler)
            if subhandlers:
              remove_event_type = False
            elif key is not NoKey:
              del handlers[key]  # type: ignore
          if remove_event_type:
            del all_handlers[event_type]
        # a given bound event type for a handler
        # will always have identical EventHandler objects
        events.append(EventHandlerRemoved(handler, cls, binding.keys))  # type: ignore
    return events
