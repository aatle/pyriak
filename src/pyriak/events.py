"""This module contains built-in events.

The managers automatically generate these events when
something is added or removed from them, if they have an event queue.
Entities added to an EntityManager also generate events for components.

Most of these events have key functions to help narrow down which events
to receive, since they are generated in large volumes and very generally.
"""

__all__ = [
    "ComponentAdded",
    "ComponentRemoved",
    "EntityAdded",
    "EntityRemoved",
    "SystemAdded",
    "SystemRemoved",
    "EventHandlerAdded",
    "EventHandlerRemoved",
    "StateAdded",
    "StateRemoved",
]

from collections.abc import Hashable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pyriak.event_key import set_key as _set_key

if TYPE_CHECKING:
    from pyriak import System
    from pyriak.bind import Binding, _Callback
    from pyriak.entity import Entity
    from pyriak.system_manager import _EventHandler


_T = TypeVar("_T")


@dataclass
class EntityAdded:
    """An event for when an Entity is added to the EntityManager.

    Attributes:
        entity: The entity added to the manager.
    """

    entity: "Entity"


@dataclass
class EntityRemoved:
    """An event for when an Entity is removed from the EntityManager.

    Attributes:
        entity: The entity removed from the manager.
    """

    entity: "Entity"


def _component_type_key(event: "ComponentAdded | ComponentRemoved") -> type:
    return type(event.component)


@_set_key(_component_type_key)
@dataclass
class ComponentAdded(Generic[_T]):
    """An event for when a component is added to the EntityManager.

    Either, a component is added to an entity that is in the manager,
    or an entity with existing components is added to the manager.

    The event key is the type of the component.

    Attributes:
        entity: The entity that the component is in.
        component: The component added.
    """

    entity: "Entity"
    component: _T


@_set_key(_component_type_key)
@dataclass
class ComponentRemoved(Generic[_T]):
    """An event for when a component is removed from the EntityManager.

    Either, a component is removed from an entity that is in the manager,
    or an entity with components is removed from the manager.
    For the latter case, the component may still be on the entity.

    The event key is the type of the component.

    Attributes:
        entity: The entity that the component was in.
        component: The component removed.
    """

    entity: "Entity"
    component: _T


def _system_key(event: "SystemAdded | SystemRemoved") -> "System":
    return event.system


@_set_key(_system_key)
@dataclass
class SystemAdded:
    """An event for when a system is added to the SystemManager.

    The event key is the system itself.

    Attributes:
        system: The system added to the manager.
    """

    system: "System"


@_set_key(_system_key)
@dataclass
class SystemRemoved:
    """An event for when a system is removed from the SystemManager.

    The event key is the system itself.

    Attributes:
        system: The system removed from the manager.
    """

    system: "System"


def _state_type_key(event: "StateAdded | StateRemoved") -> type:
    return type(event.state)


@_set_key(_state_type_key)
@dataclass
class StateAdded(Generic[_T]):
    """An event for when a state is added to the StateManager.

    The event key is the type of the state.

    Attributes:
        state: The state added to the manager.
    """

    state: _T


@_set_key(_state_type_key)
@dataclass
class StateRemoved(Generic[_T]):
    """An event for when a state is removed from the StateManager.

    The event key is the type of the state.

    Attributes:
        state: The state removed from the manager.
    """

    state: _T


def _handler_key(event: "EventHandlerAdded | EventHandlerRemoved") -> type:
    return event.event_type


@dataclass
class _EventHandlerEvent(Generic[_T]):
    _binding: "Binding[_T, Any]"
    _handler: "_EventHandler[_T]"

    @property
    def system(self) -> "System":
        return self._handler.system

    @property
    def callback(self) -> "_Callback[_T, Any]":
        return self._handler.callback

    @property
    def name(self) -> str:
        return self._handler.name

    @property
    def priority(self) -> Any:
        return self._binding._priority_

    @property
    def event_type(self) -> type[_T]:
        return self._binding._event_type_

    @property
    def keys(self) -> frozenset[Hashable]:
        return self._binding._keys_

    @property
    def key(self) -> Hashable:
        """The single key of the event handler, if applicable.

        Often, a key event handler only binds a single key.
        Raises ValueError if there is not exactly 1 key in keys.
        """
        [key] = self.keys
        return key


@_set_key(_handler_key)
class EventHandlerAdded(_EventHandlerEvent[_T]):
    """An event for when a single event handler is added.

    When a system is added to the SystemManager, it may have bindings.
    For each binding, an event handler is created on the manager.

    The event key is the event type of the handler.

    Attributes:
        system: The system of the event handler.
        callback: The callback of the event handler.
        name: The attribute name of the binding on the system.
        priority: The priority of the event handler.
        event_type: The event type of the event handler.
        keys: The keys of the event handler. May be empty.
    """


@_set_key(_handler_key)
class EventHandlerRemoved(_EventHandlerEvent[_T]):
    """An event for when a single event handler is removed.

    A system removed from the SystemManager may own event
    handlers that need to be removed.

    The event key is the event type of the handler.

    Attributes:
        system: The system of the event handler.
        callback: The callback of the event handler.
        name: The attribute name of the binding on the system.
        priority: The priority of the event handler.
        event_type: The event type of the event handler.
        keys: The keys of the event handler. May be empty.
    """
