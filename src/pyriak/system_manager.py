"""This module implements the SystemManager class."""

__all__ = ["SystemManager"]

from bisect import insort_right
from collections.abc import Hashable, Iterable, Iterator
from reprlib import recursive_repr
from types import NotImplementedType
from typing import TYPE_CHECKING, Any, Generic, NamedTuple, TypeVar
from weakref import ref as weakref

from pyriak import EventQueue, System, dead_weakref
from pyriak.bind import Binding, _Callback
from pyriak.event_key import key_functions
from pyriak.events import (
    EventHandlerAdded,
    EventHandlerRemoved,
    SystemAdded,
    SystemRemoved,
)

if TYPE_CHECKING:
    from pyriak.space import Space


_T = TypeVar("_T")


class _EventHandler(NamedTuple, Generic[_T]):
    """Internal object that holds info for a single SystemManager event handler.

    A function on a system can be bound to an event type.
    This creates a 'binding' on the system.
    Conceptually, an event handler consists of its event type, keys, priority,
    callback, system, and name, and is in a manager listening for events.
    However, this internal object only stores some of that data,
    as other data is implied by its location in data structures.

    This object is used for invoking, sorting, and storing the event handler.
    It is implemented as a NamedTuple, with equality and hash based on only
    name and system.

    It also supports comparison based on priority, where if h1 < h2, then h1
    has higher priority.
    Priority comparisons involving equality such as >= are not implemented.

    Attributes:
        callback: The event handler callback to be invoked.
        priority: The priority of the event handler given in bind().
        system: The system the event handler belongs to.
        name: The function variable name of the binding on the system.
    """

    callback: _Callback[_T]
    priority: Any
    system: System
    name: str

    def __call__(self, space: "Space", event: _T, /) -> object:
        return self.callback(space, event)

    def __eq__(self, other: object) -> bool:
        if self is other:
            return True
        if isinstance(other, _EventHandler):
            return self.name == other.name and self.system == other.system
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.name, self.system))

    def __lt__(self, other: object) -> bool:
        if isinstance(other, _EventHandler):
            result: bool = other.priority < self.priority
            return result
        return NotImplemented

    def __gt__(self, other: object) -> bool:
        if isinstance(other, _EventHandler):
            result: bool = self.priority < other.priority
            return result
        return NotImplemented

    def __le__(self, other: object) -> NotImplementedType:
        return NotImplemented

    def __ge__(self, other: object) -> NotImplementedType:
        return NotImplemented


del NamedTuple


class SystemManager:
    """A manager and container of systems.

    The SystemManager stores the systems of a space and is in charge of invoking
    their event handlers.
    Event processing and other system callbacks require a reference to the space,
    so the SystemManager holds a weak reference to one.

    A system is a module object, typically with event handler bindings on it.
    Defining _added_ and _removed_ functions or attributes on the system
    executes code when a system is added or removed.
    Use bind() to create event handlers that listen for certain event types.

    Attributes:
        event_queue: The optional event queue that the SystemManager may post to.
            This is usually assigned the space's event queue.
    """

    __slots__ = (
        "_space",
        "_systems",
        "_handlers",
        "_key_handlers",
        "event_queue",
        "__weakref__",
    )

    def __init__(
        self,
        systems: Iterable[System] = (),
        /,
        space: "Space | None" = None,
        event_queue: EventQueue | None = None,
    ) -> None:
        """Initialize the SystemManager with systems, space, and event queue.

        By default, the SystemManager is initialized with no systems, event queue
        as None, and space as None.

        Args:
            systems: The iterable of initial systems. Defaults to no systems.
            space: The space to use in system callbacks.
            event_queue: The event queue to post to. Defaults to None.
        """
        self.space = space
        self.event_queue = event_queue
        # values aren't used: dict is for insertion order
        self._systems: dict[System, None] = {}
        self._handlers: dict[type, list[_EventHandler[Any]]] = {}
        self._key_handlers: dict[type, dict[Hashable, list[_EventHandler[Any]]]] = {}
        self.add(*systems)

    def process(self, event: object, /) -> None:
        """Invoke system event handlers for an event.

        Event handlers listen for events of a specific type.
        Optionally, they can require event keys.
        Each event handler callback is called in order of priority
        within its event key (or no key).

        If the event has key(s), the key handlers for each key are invoked, one key
        at a time, and then the general handlers are invoked.

        A single event handler may be invoked multiple times if there are multiple
        event keys and either the event handler is bound to multiple keys
        or the event keys contain duplicates.

        The SystemManager's space attribute must not be None.

        If the event type has no event handlers, nothing happens.

        The return value of the callback is ignored.

        Args:
            event: The event to process.

        Raises:
            RuntimeError: If self's space is None or deleted.
        """
        space = self.space
        if space is None:
            raise RuntimeError("cannot process event, space is None or deleted")
        for handler in self._get_handlers(event):
            handler.callback(space, event)

    def add(self, *systems: System) -> None:
        """Add an arbitrary number of systems and their event handlers to self.

        The systems are added one at a time.
        Any hashable object is a valid system.

        If the system is already in self, an exception is raised.

        If self's event queue is not None, a SystemAdded event is generated,
        followed by EventHandlerAdded events for its event handlers.

        If self's space is not None and the system has an _added_ attribute,
        the attribute is called with the space as the only argument.
        This callback can be used to initialize any necessary things for the system.

        Args:
            *systems: The systems to be added.

        Raises:
            ValueError: If self already has one of the systems.
        """
        self_systems = self._systems
        bind = self._bind
        for system in systems:
            if system in self_systems:
                raise ValueError(f"system manager already has system {system!r}")
            self_systems[system] = None
            events = bind(system)
            space = self.space
            event_queue = self.event_queue
            if event_queue is not None:
                event_queue.extend([SystemAdded(system), *events])
            if space is not None:
                try:
                    added = system._added_
                except AttributeError:
                    continue
                added(space)

    def update(self, *systems: System) -> None:
        """Update self with an arbitrary number of systems.

        Same as add(), except that systems that are already in self
        get skipped instead of raising an error.

        Args:
            *systems: The systems to update self with.
        """
        for system in systems:
            if system not in self._systems:
                self.add(system)

    def remove(self, *systems: System) -> None:
        """Remove an arbitrary number of systems and their event handlers from self.

        The systems are removed one at a time.

        If the system is not in self, an exception is raised, preventing the rest
        of the systems from being removed.

        If self's event queue is not None, for each system,
        an EventHandlerRemoved event is posted for each of
        its event handlers followed by a SystemRemoved event.

        If self's space is not None and the system has a _removed_ attribute,
        the attribute is called with the space as the only argument.
        This callback can be used to remove anything tied to the system.

        Args:
            *systems: The systems to be removed.

        Raises:
            ValueError: If one of the systems is not in self.
        """
        self_systems = self._systems
        unbind = self._unbind
        for system in systems:
            try:
                del self_systems[system]
            except KeyError:
                raise ValueError(system) from None
            events = unbind(system)
            space = self.space
            event_queue = self.event_queue
            if event_queue is not None:
                event_queue.extend([*events, SystemRemoved(system)])
            if space is not None:
                try:
                    removed = system._removed_
                except AttributeError:
                    continue
                removed(space)

    def discard(self, *systems: System) -> None:
        """Remove systems, skipping any not in self.

        This method is the same as remove(), with one difference:
        it does not raise an exception when a system is missing from self.
        Instead, the system is skipped.

        See documentation of remove() for more info.

        Args:
            *systems: The systems to be removed if in self.
        """
        self_systems = self._systems
        for system in systems:
            if system in self_systems:
                self.remove(system)

    def __iter__(self) -> Iterator[System]:
        return iter(self._systems)

    def __reversed__(self) -> Iterator[System]:
        return reversed(self._systems)

    def __len__(self) -> int:
        return len(self._systems)

    def __contains__(self, obj: object, /) -> bool:
        return obj in self._systems

    def __eq__(self, other: object, /) -> bool:
        if self is other:
            return True
        if isinstance(other, SystemManager):
            return self._systems.keys() == other._systems.keys()
        return NotImplemented

    @recursive_repr()
    def __repr__(self) -> str:
        systems = ", ".join([repr(system) for system in self])
        return f"{type(self).__name__}([{systems}])"

    def clear(self) -> None:
        """Remove all systems and event handlers from self.

        Does not trigger any events or invoke _removed_ callbacks.
        Does not affect self's space or event_queue.
        """
        self._handlers.clear()
        self._key_handlers.clear()
        self._systems.clear()

    @property
    def space(self) -> "Space | None":
        """The space to be used in system callbacks.

        A weak reference to the space is kept.
        The space may be None, possibly because of a dead weak reference.

        A space is required for processing events.
        A space is needed for _added_ and _removed_ callbacks, which
        are skipped if there is no space available.
        """
        return self._space()

    @space.setter
    def space(self, value: "Space | None") -> None:
        self._space = dead_weakref if value is None else weakref(value)

    def _get_handlers(self, event: _T, /) -> list[_EventHandler[_T]]:
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
        keys = key_functions[event_type](event)
        if not isinstance(keys, Iterator):
            return [*key_handlers.get(keys, ()), *handlers]
        return [
            handler
            for key in keys
            if key in key_handlers
            for handler in key_handlers[key]
        ] + handlers

    @staticmethod
    def _get_bindings(system: System) -> list[tuple[Binding, _EventHandler[object]]]:
        return [
            (
                binding,
                _EventHandler(binding._callback_, binding._priority_, system, name),
            )
            for name, binding in system.__dict__.items()
            if isinstance(binding, Binding)
        ]

    def _bind(self, system: System, /) -> list[EventHandlerAdded]:
        """Create handlers to process events for a system's bindings.

        Handlers of one event type are sorted by highest priority.
        For handlers with the same priority, new handlers are inserted after
        older handlers. This means that equal priority handlers are effectively
        sorted by oldest system, else by order they were returned by _get_bindings().

        Args:
            system: The system that was added, and to create handlers from.

        Returns:
            A list of EventHandlerAdded events to be posted.
        """
        all_handlers = self._handlers
        all_key_handlers = self._key_handlers
        events: list[EventHandlerAdded] = []
        for binding, handler in self._get_bindings(system):
            event_type = binding._event_type_
            keys = binding._keys_
            if event_type not in all_handlers:
                if not keys:
                    all_handlers[event_type] = [handler]
                    if event_type in key_functions:
                        all_key_handlers[event_type] = {}
                else:
                    all_handlers[event_type] = []
                    all_key_handlers[event_type] = {key: [handler] for key in keys}
            elif not keys:
                insort_right(all_handlers[event_type], handler)
            else:
                key_handlers = all_key_handlers[event_type]
                for key in keys:
                    if key in key_handlers:
                        insort_right(key_handlers[key], handler)
                    else:
                        key_handlers[key] = [handler]
            events.append(EventHandlerAdded(binding, handler))
        return events

    def _unbind(self, system: System, /) -> list[EventHandlerRemoved]:
        """Remove all handlers that belong to system from self.

        If an event type no longer has any handlers, it is removed.
        This also applies to key handlers.

        Args:
            system: The system that was removed, to remove handlers for.

        Returns:
            A list of EventHandlerRemoved events to be posted.
        """
        all_handlers = self._handlers
        all_key_handlers = self._key_handlers
        events: list[EventHandlerRemoved] = []
        for binding, handler in self._get_bindings(system):
            event_type = binding._event_type_
            keys = binding._keys_
            if not keys:
                handlers = all_handlers[event_type]
                handlers.remove(handler)
                if not handlers:
                    if event_type not in all_key_handlers:
                        del all_handlers[event_type]
                    elif not all_key_handlers[event_type]:
                        del all_key_handlers[event_type], all_handlers[event_type]
            else:
                key_handlers = all_key_handlers[event_type]
                for key in keys:
                    handlers = key_handlers[key]
                    handlers.remove(handler)
                    if not handlers:
                        del key_handlers[key]
                if not key_handlers and not all_handlers[event_type]:
                    del all_key_handlers[event_type], all_handlers[event_type]
            events.append(EventHandlerRemoved(binding, handler))
        return events
