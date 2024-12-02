"""This module implements the Entity class."""

__all__ = ["Entity", "EntityId"]

from collections.abc import Iterable, Iterator, KeysView
from typing import TYPE_CHECKING, NewType, TypeVar, overload
from uuid import uuid4

from pyriak import _SENTINEL, dead_weakref


if TYPE_CHECKING:
    from weakref import ref as weakref

    from pyriak.entity_manager import EntityManager


EntityId = NewType("EntityId", int)
"""Unique identifier for entities."""


_T = TypeVar("_T")
_D = TypeVar("_D")


class Entity:
    """A mutable collection of components that represents an entity.

    All objects are valid components.

    Entities do not have any behavior on their own. An entity's
    components define its data and systems define their behavior.
    The Entity class should rarely be subclassed because
    functionality is not implemented directly on the Entity class.

    The general purpose of entities is to group together the components
    that make up an object and provide structure to the Space's data.

    Entities are stored in the Space's EntityManager, where they and
    their components are operated on in bulk by the Space's systems.

    An entity's structure is analagous to a set of components
    mixed with a dict of component types to components.
    Components do not need to be hashable.

    Attributes:
        id: A unique integer identifier generated when the entity is created.
            This id can be used to weakly reference and store the entity.
    """

    __slots__ = "id", "_components", "_manager"

    def __init__(self, components: Iterable[object] = (), /) -> None:
        """Initialize the entity with the given components.

        The entity also gets a unique EntityId.
        By default, the entity is initialized with no components.

        Args:
            components: The iterable of initial components. Defaults to no components.
        """
        self.id: EntityId = self.new_id()
        self._manager: weakref[EntityManager] = dead_weakref
        comp_dict: dict[type, object] = {}
        for comp in components:
            comp_type = type(comp)
            if comp_type in comp_dict and (
                (other := comp_dict[comp_type]) is comp or other == comp
            ):
                continue
            comp_dict[comp_type] = comp
        self._components: dict[type, object] = comp_dict

    def add(self, *components: object) -> None:
        """Add an arbitrary number of components to self.

        Each component is stored by its class.

        If self already has a component of the same type, an exception
        is raised, preventing the rest of the components from being added
        but not affecting the ones already added.

        If self is in an EntityManager, a ComponentAdded event is
        posted in the manager event queue for each component added.

        Args:
            *components: The components to be added.

        Raises:
            ValueError: If self already has a component of the same type.
        """
        self_components = self._components
        manager = self._manager()
        for component in components:
            component_type = type(component)
            if component_type in self_components:
                raise ValueError(
                    f"entity already has component of type {component_type}"
                )
            self_components[component_type] = component
            if manager is not None:
                manager._component_added(self, component)

    def update(self, *components: object) -> None:
        """Update self with an arbitrary number of components.

        If self already has an existing component of the exact same type, that
        existing component is removed right before adding the provided component
        This is unless the two components are equivalent or the same object,
        in which case the provided component is skipped without posting events.

        If self is in an EntityManager, each component added and removed
        generates a ComponentAdded and ComponentRemoved event, respectively,
        in the manager event queue.

        Args:
            *components: The components to update self with.
        """
        self_components = self._components
        manager = self._manager()
        for component in components:
            component_type = type(component)
            if component_type in self_components:
                other_component = self_components[component_type]
                if other_component is component or other_component == component:
                    continue
                if manager is not None:
                    manager._component_removed(self, other_component)
            self_components[component_type] = component
            if manager is not None:
                manager._component_added(self, component)

    def remove(self, *components: object) -> None:
        """Remove an arbitrary number of components from self.

        For each provided component, an existing component in self of
        the exact same type is removed. The existing component
        must be equivalent or the same object as the provided component.

        If no such component is found in self, an exception is raised,
        preventing the rest of the components from being removed but
        not affecting the components already removed.

        If self is in an EntityManager, a ComponentRemoved event is
        posted in the manager event queue for each component removed.

        Args:
            *components: The components to be removed.

        Raises:
            ValueError: If one of the components is not found in self.
        """
        self_components = self._components
        manager = self._manager()
        for component in components:
            component_type = type(component)
            try:
                other_component = self_components[component_type]
            except KeyError:
                pass
            else:
                if other_component is component or other_component == component:
                    del self_components[component_type]
                    if manager is not None:
                        manager._component_removed(self, other_component)
                    continue
            raise ValueError(component)

    def discard(self, *components: object) -> None:
        """Remove components, skipping any not in self.

        This method is the same as remove(), with one difference:
        it does not raise an exception when a component is missing from self.
        Instead, the component is skipped.

        See documentation of remove() for more info.

        Args:
            *components: The components to be removed if in self.
        """
        for component in components:
            try:
                self.remove(component)
            except ValueError:
                pass

    def __getitem__(self, component_type: type[_T], /) -> _T:
        return self._components[component_type]  # type: ignore[return-value]

    def __setitem__(self, component_type: type[_T], component: _T) -> None:
        if type(component) is not component_type:
            raise TypeError(component)
        self.update(component)

    def __delitem__(self, component_type: type, /) -> None:
        self.remove(self[component_type])

    @overload
    def get(self, component_type: type[_T], /) -> _T | None: ...
    @overload
    def get(self, component_type: type[_T], default: _D, /) -> _T | _D: ...
    def get(self, component_type, default=None, /):
        return self._components.get(component_type, default)

    @overload
    def pop(self, component_type: type[_T], /) -> _T: ...
    @overload
    def pop(self, component_type: type[_T], default: _D, /) -> _T | _D: ...
    def pop(self, component_type, default=_SENTINEL, /):
        try:
            component = self._components[component_type]
        except KeyError:
            if default is _SENTINEL:
                raise
            return default
        self.remove(component)
        return component

    def types(self) -> KeysView[type]:
        return self._components.keys()

    def __iter__(self) -> Iterator[object]:
        return iter(self._components.values())

    def __reversed__(self) -> Iterator[object]:
        return reversed(self._components.values())

    def __len__(self) -> int:
        return len(self._components)

    def __contains__(self, obj: object, /) -> bool:
        return obj in self._components

    def __eq__(self, other: object, /) -> bool:
        if self is other:
            return True
        if isinstance(other, Entity):
            return self._components == other._components
        return NotImplemented

    def __repr__(self) -> str:
        return f"{type(self).__name__}({list(self)})"

    def clear(self) -> None:
        self.remove(*self)

    @staticmethod
    def new_id() -> EntityId:
        """Return a new unique EntityId int.

        The default implementation uses the `uuid` standard
        library, returning the integer value of `uuid4()` which
        is 128 bits long (16 bytes), the UUID standard.
        Subclasses may implement their own generation method.

        This method is used by the Entity's `__init__()` method
        to generate the `id` attribute.

        Returns:
            A unique integer.
        """
        return uuid4().int  # type: ignore[return-value]
