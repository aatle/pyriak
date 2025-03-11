"""This module implements the SystemManager class."""

__all__ = ["SystemManager"]

from collections.abc import Hashable, Iterable, Iterator
from functools import cmp_to_key
from inspect import getattr_static
from reprlib import recursive_repr
from types import ModuleType
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

    A function on a system can be bound to event types.
    This creates a 'binding' on the system.
    There may be multiple event handlers per binding, each bound to
    different event types and having separate priority and keys.
    The function becomes the event handler callback for each of those handlers.
    Most commonly, a binding only has one event handler.
    Conceptually, an event handler consists of its event type, keys, priority,
    callback, system, and name, and is in a manager listening for events.
    The system, name, and callback are all shared
    in a single binding.
    However, this internal object only stores some of that data,
    as other data is implied by its location in data structures.

    This object is used for invoking, sorting, and storing the event handler.
    It is implemented as a NamedTuple, with equality and hash based on only
    name and system.

    Attributes:
        system: The system the event handler belongs to.
        callback: The event handler callback to be invoked.
        name: The attribute name of the binding on the system.
        priority: The priority of the event handler given in bind().
    """

    system: System
    callback: _Callback[_T, Any]
    name: str
    priority: Any

    def __call__(self, space: "Space", event: _T, /) -> Any:
        return self.callback(space, event)

    def __eq__(self, other: object) -> bool:
        if self is other:
            return True
        if isinstance(other, _EventHandler):
            return self.name == other.name and self.system == other.system
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.name, self.system))


del NamedTuple


class SystemManager:
    """A manager and container of systems.

    The SystemManager stores the systems of a space and is in charge of invoking
    their event handlers.
    Event processing and other system callbacks require a reference to the space,
    so the SystemManager holds a weak reference to one.

    A system is any hashable object, but it must have certain things to make it
    useful. Defining _added_ and _removed_ functions or attributes on the system
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

    def process(self, event: object, /) -> bool:
        """Invoke system event handlers for an event.

        Event handlers listen for events of a specific type.
        Optionally, they can require event keys.
        Each event handler callback is called in order of priority.

        The SystemManager's space attribute must not be None.

        If the event type has no event handlers, nothing happens.

        If a callback returns a truthy value, the rest of the callbacks
        are skipped and True is returned.
        If no callback returns a truthy value, False is returned.

        Args:
            event: The event to process.

        Returns:
            True if event processing was stopped by a callback, False otherwise.

        Raises:
            RuntimeError: If self's space is None or deleted.
        """
        space = self.space
        if space is None:
            raise RuntimeError("cannot process event, space is None or deleted")
        for handler in self._get_handlers(event):
            if handler.callback(space, event):
                return True
        return False

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
                    added = system._added_  # type: ignore[attr-defined]
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
                    removed = system._removed_  # type: ignore[attr-defined]
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

    @staticmethod
    def _insert_handler(
        lst: list[_EventHandler[_T]], handler: _EventHandler[_T], /
    ) -> None:
        """Insert a handler into a list of other handlers.

        Sorts by: highest priority, then oldest in manager.

        Args:
            lst: The list of handlers to add the handlers to.
            handler: The handler to be inserted into the list.
        """
        priority = handler.priority
        lo = 0
        hi = len(lst)
        while lo < hi:
            mid = (lo + hi) // 2
            if lst[mid].priority < priority:
                hi = mid
            else:
                lo = mid + 1
        lst.insert(lo, handler)

    def _handler_cmp(  # noqa: PLR0911
        self, handler1: _EventHandler[Any], handler2: _EventHandler[Any], /
    ) -> int:
        priority1, priority2 = handler1.priority, handler2.priority
        if priority1 != priority2:
            return -1 if priority2 < priority1 else 1
        system1, system2 = handler1.system, handler2.system
        if system1 != system2:
            for system in self._systems:
                if system == system1:
                    return -1
                if system == system2:
                    return 1
            raise ValueError
        name1, name2 = handler1.name, handler2.name
        if name1 == name2:
            return 0
        if type(system1) is not ModuleType:
            return -1 if name1 < name2 else 1
        for name in system1.__dict__:
            if name == name1:
                return -1
            if name == name2:
                return 1
        raise ValueError

    def _sort_handlers(
        self, handlers: Iterable[_EventHandler[_T]], /
    ) -> list[_EventHandler[_T]]:
        """Sort and return an iterable of handlers.

        Duplicate handlers are removed before sorting.

        This method merely emulates the behavior of _bind().
        Event handlers are typically inserted one at a time into the correct position.

        Sorts by, in order:
        - highest priority
        - least recently added system
        - (same system) order the handlers were added in:
            - if system is module instance, then order created
            - otherwise, alphabetical names

        Args:
            handlers: The iterable of event handlers to be sorted.

        Returns:
            A new list of sorted handlers from the original handlers.
        """
        # Uses dict to remove duplicates while preserving some order
        return sorted(dict.fromkeys(handlers), key=cmp_to_key(self._handler_cmp))

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
    def _get_bindings(system: System) -> list[tuple[Binding, _EventHandler[Any]]]:
        if type(system) is ModuleType:
            return [
                (
                    binding,
                    _EventHandler(system, binding._callback_, name, binding._priority_),
                )
                for name, binding in system.__dict__.items()
                if isinstance(binding, Binding)
            ]
        return [
            (
                binding,
                _EventHandler(
                    system,
                    c
                    if (c := getattr(system, name)) is not binding
                    else binding._callback_,
                    name,
                    binding._priority_,
                ),
            )
            for name in dict.fromkeys(dir(system))  # remove duplicates
            if isinstance(binding := getattr_static(system, name), Binding)
        ]

    def _bind(self, system: System, /) -> list[EventHandlerAdded]:
        """Create handlers to process events for a system's bindings.

        Handlers of one event type are sorted by highest priority,
        then oldest system, then first one created in manager.

        Args:
            system: The system that was added, and to create handlers from.

        Returns:
            A list of EventHandlerAdded events to be posted.
        """
        all_handlers = self._handlers
        all_key_handlers = self._key_handlers
        insert_handler = self._insert_handler
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
                insert_handler(all_handlers[event_type], handler)
                if event_type in all_key_handlers:
                    for handlers in all_key_handlers[event_type].values():
                        insert_handler(handlers, handler)
            else:
                handlers = all_handlers[event_type]
                key_handlers = all_key_handlers[event_type]
                for key in keys:
                    if key not in key_handlers:
                        key_handlers[key] = handlers[:]
                    insert_handler(key_handlers[key], handler)
            events.append(EventHandlerAdded(binding, handler))
        return events

    def _unbind(self, system: System, /) -> list[EventHandlerRemoved]:
        """Remove all handlers that belong to system from self.

        If an event type no longer has any handlers, it is removed.
        This also applies to keys with handlers.

        Args:
            system: The system that was removed, to remove handlers for.

        Returns:
            A list of EventHandlerRemoved events to be posted.
        """
        all_handlers = self._handlers
        all_key_handlers = self._key_handlers
        events: list[EventHandlerRemoved] = []
        seen: dict[type, frozenset[Hashable]] = {}
        for binding, handler in self._get_bindings(system):
            event_type = binding._event_type_
            keys = binding._keys_
            if event_type not in seen:
                handlers = all_handlers[event_type]
                handlers[:] = [
                    handler for handler in handlers if handler.system != system
                ]
                if not handlers:
                    if event_type not in all_key_handlers:
                        del all_handlers[event_type]
                    elif not all_key_handlers[event_type]:
                        del all_handlers[event_type], all_key_handlers[event_type]
                seen[event_type] = unseen_keys = keys
            else:
                unseen_keys = keys - seen[event_type]
                seen[event_type] |= unseen_keys
            if unseen_keys:
                key_handlers = all_key_handlers[event_type]
                for key in unseen_keys:
                    handlers = key_handlers[key]
                    handlers[:] = [
                        handler for handler in handlers if handler.system != system
                    ]
                    if not handlers:
                        del key_handlers[key]
                if not key_handlers:
                    del all_key_handlers[event_type]
                    if not all_handlers[event_type]:
                        del all_handlers[event_type]
            events.append(EventHandlerRemoved(binding, handler))
        return events
