__all__ = ['SystemManager']

from collections.abc import Hashable, Iterable, Iterator
from inspect import getattr_static
from types import ModuleType
from typing import TYPE_CHECKING, Any, NamedTuple
from weakref import ref as weakref

from pyriak import EventQueue, System, dead_weakref
from pyriak.bind import BindingWrapper, _Callback
from pyriak.eventkey import key_functions
from pyriak.events import (
  EventHandlerAdded,
  EventHandlerRemoved,
  SystemAdded,
  SystemRemoved,
)


if TYPE_CHECKING:
  from pyriak.space import Space


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

  event_queue: EventQueue | None

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

  def process(self, event: object, /) -> bool:
    """Handle an event. Callbacks of the event are passed space and event.

    If the Event type has no binds, do nothing.
    If a callback returns a truthy value, the
    rest of the callbacks are skipped and True is returned, else False.
    """
    space = self.space
    if space is None:
      raise TypeError("process() missing 'space'")
    for handler in self._get_handlers(event):  # noqa: SIM110
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
      if event_queue is not None:
        event_queue.extend([SystemAdded(system), *events])
      if space is not None:
        try:
          added = system._added_  # type: ignore[attr-defined]
        except AttributeError:
          continue
        added(space)

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
      if event_queue is not None:
        event_queue.extend([SystemRemoved(system), *events])
      if space is not None:
        try:
          removed = system._removed_  # type: ignore[attr-defined]
        except AttributeError:
          continue
        removed(space)

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
    """Return whether obj is a system added to self."""
    return obj in self._systems

  def clear(self) -> None:
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

    Sorts by: highest priority, then oldest in manager
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
        return other_priority < handler_priority  # type: ignore[no-any-return]
      system = handler.system
      other_system = other_handler.system
      if system != other_system:
        for s in self.systems:
          if s == system:
            return True
          if s == other_system:
            return False
        raise ValueError
      name = handler.name
      other_name = other_handler.name
      if type(system) is not ModuleType:
        return name < other_name
      for n in system.__dict__:
        if other_name == n:
          return False
        if name == n:
          return True
      raise ValueError

  def _sort_handlers(
    self, handlers: Iterable[_EventHandler], /
  ) -> list[_EventHandler]:
    """Return a sorted list of handlers.

    Sorts by, in order:
    - highest priority
    - least recently added system
    - (same system) order the handlers were added in
      - if system is module instance, then order created
      - otherwise, alphabetical names
    """
    SortKey = self._SortKey
    systems = self._systems
    # Uses dict to remove duplicates while preserving some order
    return sorted(dict.fromkeys(handlers), key=lambda h: SortKey(h, systems))

  def _get_handlers(self, event: object, /) -> list[_EventHandler]:
    event_type = type(event)
    try:
      handlers = self._handlers[event_type]
    except KeyError:
      return []
    if event_type not in key_functions:
      return handlers[:]
    try:
      key_handlers = self._key_handlers[event_type]
    except KeyError:
      # A key function was added late
      self._key_handlers[event_type] = {}
      return handlers[:]
    key = key_functions[event_type](event)
    if not isinstance(key, Iterator):
      return (key_handlers.get(key, handlers))[:]
    keys = {k for k in key if k in key_handlers}
    if len(keys) > 1:
      return self._sort_handlers(
        [handler for key in keys for handler in key_handlers[key]]
      )
    return (key_handlers.get(keys.pop(), handlers) if keys else handlers)[:]

  @staticmethod
  def _get_bindings(system: System):
    if type(system) is ModuleType:
      return [
        (name, wrapper.__bindings__, wrapper.__wrapped__)
        for name, wrapper in system.__dict__.items()
        if isinstance(wrapper, BindingWrapper)
      ]
    return [
      (
        name, wrapper.__bindings__,
        c if (c:=getattr(system, name)) is not wrapper else wrapper.__wrapped__
      )
      for name in dict.fromkeys(dir(system))
      if isinstance((wrapper:=getattr_static(system, name)), BindingWrapper)
    ]

  def _bind(self, system: System, /) -> list[EventHandlerAdded]:
    """Bind a system's handlers so that they can process events.

    Bindings of an event type are sorted by highest priority,
    then oldest system, then first one bound in system.
    """
    all_handlers = self._handlers
    all_key_handlers = self._key_handlers
    insert_handler = self._insert_handler
    events: list[EventHandlerAdded] = []
    for name, bindings, callback in self._get_bindings(system):
      for binding in bindings:
        event_type = binding.event_type
        keys = binding.keys
        handler = _EventHandler(system, callback, name, binding.priority)
        events.append(EventHandlerAdded(handler, event_type, keys))
        if not keys:
          try:
            insert_handler(all_handlers[event_type], handler)
          except KeyError:
            all_handlers[event_type] = [handler]
          if event_type in key_functions:
            try:
              for handlers in all_key_handlers[event_type].values():
                insert_handler(handlers, handler)
            except KeyError:
              all_key_handlers[event_type] = {}
          continue
        try:
          handlers = all_handlers[event_type]
        except KeyError:
          handlers = all_handlers[event_type] = []
        if event_type not in all_key_handlers:
          handlers = handlers[:]
          insert_handler(handlers, handler)
          all_key_handlers[event_type] = {key: handlers[:] for key in keys}
          continue
        key_handlers = all_key_handlers[event_type]
        for key in keys:
          if key not in key_handlers:
            key_handlers[key] = handlers[:]
          insert_handler(key_handlers[key], handler)
    return events

  def _unbind(self, system: System, /) -> list[EventHandlerRemoved]:
    """Remove all handlers that belong to system from self.

    If an event type no longer has any handlers, it is removed.
    This also applies to keys with handlers.
    """
    all_handlers = self._handlers
    all_key_handlers = self._key_handlers
    events: list[EventHandlerRemoved] = []
    for name, bindings, callback in self._get_bindings(system):
      for binding in bindings:
        event_type = binding.event_type
        handlers = all_handlers[event_type]
        handlers[:] = [
          handler for handler in handlers if handler.system != system
        ]
        if not handlers:
          del all_handlers[event_type]
        if event_type not in all_key_handlers:
          continue
        key_handlers = all_key_handlers[event_type]
        for key, handlers in key_handlers.items():
          handlers[:] = [
            handler for handler in handlers if handler.system != system
          ]
          if not handlers:
            del key_handlers[key]
        if not key_handlers:
          del all_key_handlers[event_type]
        events.append(EventHandlerRemoved(
          system, callback, name, binding.priority, event_type, binding.keys
        ))
    return events
