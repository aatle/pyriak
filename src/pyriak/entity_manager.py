"""This module implements the EntityManager and its helper classes."""

__all__ = ["EntityManager", "QueryResult"]

from collections.abc import (
    Collection,
    Hashable,
    Iterable,
    Iterator,
    KeysView,
    Set as AbstractSet,
)
from reprlib import recursive_repr
from typing import Any, Callable, TypeVar, overload
from weakref import ref as weakref

from pyriak import _SENTINEL, EventQueue, _Sentinel, dead_weakref
from pyriak.entity import Entity, EntityId
from pyriak.events import ComponentAdded, ComponentRemoved, EntityAdded, EntityRemoved
from pyriak.tag_component import tag_types

_T = TypeVar("_T")


class QueryResult:
    """An object holding the results of the query, with methods to access it.

    Data requested from the EntityManager is exposed in a couple different
    formats, using the QueryResult object.
    It also contains the parameters for the query. The types may be used
    as a default for certain methods.

    Since the data is computed only once, a QueryResult should generally not be
    stored as it may become stale. There is little reason to keep it alive
    outside of the query call expression that created it.
    """

    __slots__ = "_entities", "_types", "_tags", "_merge"

    def __init__(
        self,
        _entities: dict[EntityId, Entity],
        _types: tuple[type, ...],
        _tags: tuple[Hashable, ...],
        _merge: Callable[..., set],
        /,
    ) -> None:
        self._entities = _entities
        self._types = _types
        self._tags = _tags
        self._merge = _merge

    @property
    def ids(self) -> AbstractSet[EntityId]:
        """The ids of the entities of the query."""
        return self._entities.keys()

    @property
    def entities(self) -> Collection[Entity]:
        """The entities of the query."""
        return self._entities.values()

    @property
    def types(self) -> tuple[type, ...]:
        """The component types passed to the query call, in order."""
        return self._types

    @property
    def tags(self) -> tuple[Hashable, ...]:
        """The tags passed to the query call, in order."""
        return self._tags

    @property
    def merge(self) -> Callable[..., set]:
        """The merge function passed to the query call.

        The default query merge function is set.intersection.
        """
        return self._merge

    def __call__(self, component_type: type[_T], /) -> Iterator[_T]:
        """Return an iterator of components of a type.

        For each entity in the query, the component of the given type in it is yielded.
        If an entity does not have the component type, a KeyError is
        raised from the entity when it is reached in the iterator.

        Args:
            component_type: The type of components to get.

        Returns:
            An iterator of components of that type, from the query's entities.
        """
        return (entity[component_type] for entity in self.entities)

    def zip(self, *component_types: type) -> Iterator[tuple[Any, ...]]:
        """Return an iterator of tuples of components.

        For each entity, a tuple is yielded with components corresponding to the
        component types provided. If no component types are given, it defaults
        to the component types passed in for the query call, self.types.

        If the entity doesn't have one of the component types when the entity is
        reached in the iterator, a KeyError is raised from the entity.

        Args:
            *component_types: The types to access from the query's entities.

        Returns:
            An iterator yielding same-length tuples of components.

        Example:
            for sprite, position in space.entities.query(Sprite, Position).zip():
                render(sprite, position)
        """
        if not component_types:
            component_types = self.types
        return (
            tuple([ent[comp_type] for comp_type in component_types])
            for ent in self.entities
        )

    def zip_entity(self, *component_types: type) -> Iterator[tuple[Any, ...]]:
        """Return an iterator of tuples of the entity and its components.

        This method is the same as zip() except that each tuple starts with the
        entity, which is followed by the components.
        The component types default to self.types, the types in the query call,
        if none are provided.

        Args:
            *component_types: The types to access from the query's entities.

        Returns:
            An iterator yielding same-length tuples of the entity and its components.

        Example:
            Typical usage of zip_entity() method

                for entity, lifetime in space.entities.query(Lifetime).zip_entity():
                    if lifetime.timer < 0:
                        space.post(KillEntity(entity))
        """
        if not component_types:
            component_types = self.types
        return (
            (ent, *[ent[comp_type] for comp_type in component_types])
            for ent in self.entities
        )

    __hash__ = None  # type: ignore[assignment]

    def __repr__(self) -> str:
        entities = ", ".join([repr(entity) for entity in self.entities])
        return (
            f"<{type(self).__name__} of "
            f"entities=[{entities}], types={self._types!r}, merge={self._merge!r}>"
        )


class _Components:
    """The components attribute of an EntityManager, exposes more functionality.

    The EntityManager not only manages the entities it holds, but also partially
    manages the components in those entities.
    The components attribute of the EntityManager exposes additional operations for
    the components in the entities, while the entity operations are on the manager.

    Instances are not meant to be independent; they serve as an extension
    to the EntityManager in a syntactically intuitive way, through dot access.
    As such, they are only a proxy for the manager's data.

    If the EntityManager has been deleted and garbage collected, all methods
    raise TypeError. A _Components instance only weakly references its manager.

    Attributes:
        _manager: A weakref to the manager (narrower type annotation to avoid errors).
    """

    __slots__ = ("_manager",)

    _manager: Callable[[], "EntityManager"]

    def __init__(self, manager: "EntityManager", /) -> None:
        self._manager = weakref(manager)  # type: ignore[assignment]

    def __call__(self, component_type: type[_T], /) -> Iterator[_T]:
        """Return an iterator of all components of a type in the manager.

        For each entity that has it, its component is yielded.
        The order of entities/components is not defined.
        The iterator may be empty.

        Since it is an iterator, there are some limitations with it:
        - Raises KeyError if one of the entities is no longer
          in the manager when it is reached in iteration.
        - Raises RuntimeError if the number of entities with
          the component type changes during iteration.
        If necessary, these can be avoided by converting to tuple.

        Args:
            component_type: The type of components to get.

        Returns:
            An iterator of components of that type, from the manager's entities.
        """
        manager = self._manager()
        entities = manager._entities
        return (
            entities[entity_id][component_type]
            for entity_id in manager._type_cache.get(component_type, ())
        )

    def types(self) -> KeysView[type]:
        return self._manager()._type_cache.keys()

    def __iter__(self) -> Iterator[object]:
        for entity in self._manager():
            yield from entity

    def __reversed__(self) -> Iterator[object]:
        for entity in reversed(self._manager()):
            yield from reversed(entity)

    def __len__(self) -> int:
        return sum([len(entity) for entity in self._manager()])

    def __contains__(self, obj: object, /) -> bool:
        return obj in self._manager()._type_cache


class EntityManager:
    """A manager and container of entities.

    The EntityManager stores the entities of a space and provides ways to
    access them and their components.
    Almost all entities instantiated get added to the EntityManager
    so they are accessible from the rest of the space.

    An entity may only be stored in at most one EntityManager at once,
    because entities weakly reference their managers to update caches.

    The manager also has a .components attribute which extends the manager by
    exposing additional (readonly) operations for the components within the entities.

    The EntityManager is owned directly by the Space.
    There is usually only one, accessible via the Space's 'entities' attribute.

    Attributes:
        event_queue: The optional event queue that the EntityManager may post to.
            This is usually assigned the space's event queue.
    """

    __slots__ = (
        "_entities",
        "_type_cache",
        "_tag_cache",
        "components",
        "event_queue",
        "__weakref__",
    )

    def __init__(
        self, entities: Iterable[Entity] = (), /, event_queue: EventQueue | None = None
    ) -> None:
        """Initialize the EntityManager with the given entities and event queue.

        By default, the EntityManager is initialized with no entities and
        event queue as None.

        Also initializes the components attribute of the manager.

        Args:
            entities: The iterable of initial entities. Defaults to no entities.
            event_queue: The event queue to post to. Defaults to None.
        """
        self.event_queue = event_queue
        self.components = _Components(self)
        self._entities: dict[EntityId, Entity] = {}
        self._type_cache: dict[type, set[EntityId]] = {}
        self._tag_cache: dict[Hashable, set[EntityId]] = {}
        self.add(*entities)

    def add(self, *entities: Entity) -> None:
        """Add an arbitrary number of entities to self.

        Each entity is stored by its unique id.

        If self already has the entity being added, an exception is raised.

        If self's event queue is not None, each entity added generates
        an EntityAdded event and then a ComponentAdded event for each
        component in the entity.

        An entity may only added to at most one manager.

        Args:
            *entities: The entities to be added.

        Raises:
            ValueError: If self already has one of the entities.
            RuntimeError: If one of the entities is already added to another manager.
        """
        self_entities = self._entities
        self_weakref: weakref[EntityManager] = weakref(self)
        event_queue = self.event_queue
        for entity in entities:
            entity_id = entity.id
            if entity_id in self_entities:
                raise ValueError(entity)
            if entity._manager() is not None:
                raise RuntimeError(f"{entity!r} already added to another manager")
            self_entities[entity_id] = entity
            entity._manager = self_weakref
            if event_queue is not None:
                event_queue.append(EntityAdded(entity))
            for component in entity:
                self._component_added(entity, component)

    def update(self, *entities: Entity) -> None:
        """Update self with an arbitrary number of entities.

        Same as add(), except that entities that are already in self
        get skipped instead of raising an error.

        Args:
            *entities: The entities to update self with.

        Raises:
            RuntimeError: If one of the entities is in another manager.
        """
        for entity in entities:
            if entity not in self:
                self.add(entity)

    def create(self, *components: object) -> Entity:
        """Create and return a new Entity with components, added to self.

        The entity is instantiated with the given components.
        Then, it is added to self and returned.
        The adding generates EntityAdded and ComponentAdded events.

        Args:
            *components: The components of the new entity.

        Returns:
            The entity created.
        """
        entity: Entity = Entity(components)
        self.add(entity)
        return entity

    def remove(self, *entities: Entity) -> None:
        """Remove an arbitrary number of entities from self.

        If the entity being removed is not in self, a ValueError
        is raised, preventing the rest of the entities from being removed,
        but not affecting the entities already removed.

        If self's event queue is not None, for each entity, a ComponentRemoved
        event is posted for each component followed by an EntityRemoved event.

        Args:
            *entities: The entities to be removed.

        Raises:
            ValueError: If one of the entities is not in self.
        """
        event_queue = self.event_queue
        for entity in entities:
            entity_id = entity.id
            try:
                del self._entities[entity_id]
            except KeyError:
                raise ValueError(entity) from None
            entity._manager = dead_weakref
            for component in entity:
                self._component_removed(entity, component)
            if event_queue is not None:
                event_queue.append(EntityRemoved(entity))

    def discard(self, *entities: Entity) -> None:
        """Remove entities, skipping any not in self.

        This method is the same as remove(), with one difference:
        it does not raise an exception when an entity is missing from self.
        Instead, the entity is skipped.

        See documentation of remove() for more info.

        Args:
            *entities: The entities to be removed if in self.
        """
        self_entities = self._entities
        for entity in entities:
            if entity.id in self_entities:
                self.remove(entity)

    @overload
    def query(
        self, /, *component_types: type, merge: Callable[..., set] = set.intersection
    ) -> QueryResult: ...
    @overload
    def query(
        self,
        /,
        *component_types: type,
        tag: Hashable,
        merge: Callable[..., set] = set.intersection,
    ) -> QueryResult: ...
    @overload
    def query(
        self,
        /,
        *component_types: type,
        tags: Iterable[Hashable],
        merge: Callable[..., set] = set.intersection,
    ) -> QueryResult: ...
    def query(
        self,
        /,
        *component_types: type,
        tag: Hashable | _Sentinel = _SENTINEL,
        tags: Iterable[Hashable] | _Sentinel = _SENTINEL,
        merge: Callable[..., set] = set.intersection,
    ) -> QueryResult:
        """Request specific data from the manager.

        Given an arbitary number of types and tags, return bulk data about
        the set of entities corresponding to these types and tags, as a QueryResult.
        The entities are in an arbitrary order.

        Each component type and each tag has a set of ids of entities that have it.
        The merge function combines these sets to create the final set of entity ids,
        with the sets of the tags passed in first and then the types sets.

        By default, the merge function is set.intersection, which means the
        result is the set of entities that have every component type and tag.

        At least one type or tag must be given.
        The tag kwarg is a shortcut for passing a single tag, and it
        cannot be used with the tags kwarg.

        The merge function must take a number of sets as arguments, where the
        number is how many component types and tags are passed in, and return a set.
        Preferably, the merge function can take an arbitrary non-zero number of sets.
        Typically, merge functions are unbound set methods.

        Args:
            *component_types: Types that are used to generate the set of entities.
            tag: A tag that is used to generate the set of entities. Defaults to no tag.
            tags: An iterable of tags that are used to generate the set of entities.
                Defaults to no tags.
            merge: The set merge function used to combine the sets of ids into one.

        Returns:
            A read-only QueryResult object that contains the data and info of the query.

        Raises:
            TypeError: If exactly zero component types were given.

        Example:
            for sprite, position in space.entities.query(Sprite, Position).zip():
                render(sprite, position)
        """
        type_cache = self._type_cache
        types_ids = [
            type_cache[typ] if typ in type_cache else set()  # noqa: SIM401
            for typ in component_types
        ]
        if tag is not _SENTINEL:
            if tags is not _SENTINEL:
                raise TypeError("query() cannot be passed both 'tag' and 'tags' kwargs")
            tags = (tag,)
            tag_cache = self._tag_cache
            entity_ids = merge(
                (tag_cache[tag] if tag in tag_cache else set()),  # noqa: SIM401
                *types_ids,
            )
        elif tags is not _SENTINEL:
            tags = tuple(tags)
            if not tags and not component_types:
                raise TypeError("expected at least one component type or tag")
            tag_cache = self._tag_cache
            entity_ids = merge(
                *[
                    tag_cache[tag] if tag in tag_cache else set()  # noqa: SIM401
                    for tag in tags
                ],
                *types_ids,
            )
        else:
            if not types_ids:
                raise TypeError("expected at least one component type or tag")
            tags = ()
            entity_ids = merge(*types_ids)
        entities = self._entities
        return QueryResult(
            {entity_id: entities[entity_id] for entity_id in entity_ids},
            component_types,
            tags,
            merge,
        )

    def __call__(self, component_type: type, /) -> Iterator[Entity]:
        """Return an iterator of all entities with component type in the manager.

        For each entity that has a component of the type given, it is yielded.
        The order of entities is not defined. The iterator may be empty.

        Since it is an iterator, there are some limitations with it:
        - Raises KeyError if one of the entities is no longer
          in the manager when it is reached in iteration.
        - Raises RuntimeError if the number of entities with
          the component type changes during iteration.
        If necessary, these can be avoided by converting to tuple.

        Args:
            component_type: The component type to find entities with.

        Returns:
            An iterator of entities that have component_type.
        """
        entities = self._entities
        return (
            entities[entity_id]
            for entity_id in self._type_cache.get(component_type, ())
        )

    @overload
    def ids(self, /) -> KeysView[EntityId]: ...
    @overload
    def ids(self, component_type: type, /) -> set[EntityId]: ...
    def ids(self, component_type: type | None = None, /) -> AbstractSet[EntityId]:
        """Return a set of all entity ids that contain the given component type.

        If no component type is given or is None, then return a readonly set-like
        view of all entity ids in self instead (keys view).

        Args:
            component_type: The type that entities must have. Defaults to None.

        Returns:
            Either a set-like keys view of ids or a set of ids.
        """
        if component_type is None:
            return self._entities.keys()
        return set(self._type_cache.get(component_type, ()))

    def tagged(self, tag: Hashable, /) -> Iterator[Entity]:
        """Return an iterator of all entities with the given tag in the manager.

        For each entity that has the tag, it is yielded.
        The order of entities is not defined. The iterator may be empty.

        Since it is an iterator, there are some limitations with it:
        - Raises KeyError if one of the entities is no longer
          in the manager when it is reached in iteration.
        - Raises RuntimeError if the number of entities with
          the tag changes during iteration.
        If necessary, these can be avoided by converting to tuple.

        Args:
            tag: The tag to find entities with.

        Returns:
            An iterator of entities that have the tag.
        """
        entities = self._entities
        return (entities[entity_id] for entity_id in self._tag_cache.get(tag, ()))

    def tagged_ids(self, tag: Hashable, /) -> set[EntityId]:
        """Return a set of all entity ids that have the given tag.

        Args:
            tag: The tag component that entities must have.

        Returns:
            A new set of ids of entities that contain the given tag.
        """
        return set(self._tag_cache.get(tag, ()))

    def __getitem__(self, entity_id: EntityId, /) -> Entity:
        return self._entities[entity_id]

    def __delitem__(self, entity_id: EntityId, /) -> None:
        self.remove(self._entities[entity_id])

    @overload
    def get(self, entity_id: EntityId, /) -> Entity | None: ...
    @overload
    def get(self, entity_id: EntityId, default: _T, /) -> Entity | _T: ...
    def get(
        self, entity_id: EntityId, default: _T | None = None, /
    ) -> Entity | _T | None:
        return self._entities.get(entity_id, default)

    @overload
    def pop(self, entity_id: EntityId, /) -> Entity: ...
    @overload
    def pop(self, entity_id: EntityId, default: _T, /) -> Entity | _T: ...
    def pop(
        self, entity_id: EntityId, default: _T | _Sentinel = _SENTINEL, /
    ) -> Entity | _T:
        try:
            entity = self._entities[entity_id]
        except KeyError:
            if default is _SENTINEL:
                raise
            return default
        self.remove(entity)
        return entity

    def __iter__(self) -> Iterator[Entity]:
        return iter(self._entities.values())

    def __reversed__(self) -> Iterator[Entity]:
        return reversed(self._entities.values())

    def __len__(self) -> int:
        return len(self._entities)

    def __contains__(self, obj: object, /) -> bool:
        if isinstance(obj, Entity):
            return obj.id in self._entities
        return obj in self._entities

    def __eq__(self, other: object, /) -> bool:
        if self is other:
            return True
        if isinstance(other, EntityManager):
            return self._entities.keys() == other._entities.keys()
        return NotImplemented

    @recursive_repr()
    def __repr__(self) -> str:
        entities = ", ".join([repr(entity) for entity in self])
        return f"{type(self).__name__}([{entities}])"

    def clear(self) -> None:
        self.remove(*self)

    def _component_added(self, entity: Entity, component: object, /) -> None:
        try:
            self._type_cache[type(component)].add(entity.id)
        except KeyError:
            self._type_cache[type(component)] = {entity.id}
        if type(component) in tag_types:
            try:
                self._tag_cache[component].add(entity.id)
            except KeyError:
                self._tag_cache[component] = {entity.id}
        event_queue = self.event_queue
        if event_queue is not None:
            event_queue.append(ComponentAdded(entity, component))

    def _component_removed(self, entity: Entity, component: object, /) -> None:
        type_ids = self._type_cache[type(component)]
        type_ids.remove(entity.id)
        if not type_ids:
            del self._type_cache[type(component)]
        if type(component) in tag_types:
            tag_ids = self._tag_cache[component]
            tag_ids.remove(entity.id)
            if not tag_ids:
                del self._tag_cache[component]
        event_queue = self.event_queue
        if event_queue is not None:
            event_queue.append(ComponentRemoved(entity, component))
