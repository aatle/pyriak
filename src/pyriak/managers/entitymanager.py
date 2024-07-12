"""This module implements the EntityManager and its helper classes."""

__all__ = ['EntityManager', 'QueryResult']

from collections.abc import Collection, Iterable, Iterator, KeysView, Set as AbstractSet
from typing import Any, Callable, TypeVar, overload
from weakref import ref as weakref

from pyriak import _SENTINEL, EventQueue, dead_weakref
from pyriak.entity import Entity, EntityId
from pyriak.events import ComponentAdded, ComponentRemoved, EntityAdded, EntityRemoved


_T = TypeVar('_T')


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

  __slots__ = '_entities', '_types', '_merge'

  def __init__(
    self, _entities: dict[EntityId, Entity],
    _types: tuple[type, ...],
    _merge: Callable[..., set], /
  ):
    self._entities = _entities
    self._types = _types
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
  def merge(self) -> Callable[..., set]:
    """The merge function passed to the query call.

    The default query merge function is set.intersection.
    """
    return self._merge

  def __call__(self, component_type: type[_T], /) -> Iterator[_T]:
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
      Typical usage of zip() method::

        for sprite, position in space.query(Sprite, Position).zip():
          render(sprite, position)
    """
    if not component_types:
      component_types = self.types
    return (
      tuple([ent[comp_type] for comp_type in component_types]) for ent in self.entities
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
      Typical usage of zip_entity() method::

        for entity, lifetime in space.query(Lifetime).zip_entity():
          if lifetime.timer < 0:
            space.post(KillEntity(entity))
    """
    if not component_types:
      component_types = self.types
    return (
      (ent, *[ent[comp_type] for comp_type in component_types]) for ent in self.entities
    )

  __hash__ = None  # type: ignore[assignment]


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

  __slots__ = ('_manager',)

  _manager: Callable[[], 'EntityManager']

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
      for entity_id in manager._component_types.get(component_type, ())
    )

  def types(self) -> KeysView[type]:
    return self._manager()._component_types.keys()

  def __iter__(self) -> Iterator[object]:
    for entity in self._manager():
      yield from entity

  def __reversed__(self) -> Iterator[object]:
    for entity in reversed(self._manager()):
      yield from reversed(entity)

  def __len__(self):
    return sum([len(entity) for entity in self._manager()])

  def __contains__(self, obj: object, /):
    return obj in self._manager()._component_types


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

  __slots__ = '_entities', '_component_types', 'components', 'event_queue', '__weakref__'

  def __init__(
    self, entities: Iterable[Entity] = (), /, event_queue: EventQueue | None = None
  ):
    """Initialize the EntityManager with the given entities and event queue.

    By default, the EntityManager is initialized with no entities and
    event queue as None.

    Also initializes the components attribute of the manager.

    Args:
      entities: The iterable of initial entities. Defaults to no entities.
      event_queue: The event queue to post to. Defaults to None.
    """
    self.event_queue = event_queue
    self.components = _Components()
    self.components._manager = weakref(self)  # type: ignore[assignment]
    self._entities: dict[EntityId, Entity] = {}
    self._component_types: dict[type, set[EntityId]] = {}
    self.add(*entities)

  def add(self, *entities: Entity) -> None:
    """Add an arbitrary number of entities to self.

    Each entity is stored by its unique id.

    If self already has the entity being added, it is skipped.

    If self's event queue is not None, each entity added generates
    an EntityAdded event, and then a ComponentAdded event for each
    component in the entity.

    An entity may only added to at most one manager.

    Args:
      *entities: The entities to be added.

    Raises:
      RuntimeError: If one of the entities is added to another manager.
    """
    component_types = self._component_types
    self_entities = self._entities
    self_weakref: weakref[EntityManager] = weakref(self)
    event_queue = self.event_queue
    for entity in entities:
      entity_id = entity.id
      if entity_id in self_entities:
        continue
      if entity._manager() is not None:
        raise RuntimeError(f'{entity!r} already added to another manager')
      self_entities[entity_id] = entity
      entity._manager = self_weakref
      for component_type in entity.types():
        try:
          component_types[component_type].add(entity_id)
        except KeyError:
          component_types[component_type] = {entity_id}
      if event_queue is not None:
        event_queue.extend([
          EntityAdded(entity),
          *[ComponentAdded(entity, component) for component in entity]
        ])

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

    If self's event queue is not None, an EntityRemoved event followed
    by ComponentRemoved events for each component are posted.

    Args:
      *entities: The entities to be removed.

    Raises:
      ValueError: If one of the entities is not in self.
    """
    component_types = self._component_types
    event_queue = self.event_queue
    for entity in entities:
      entity_id = entity.id
      try:
        del self._entities[entity_id]
      except KeyError:
        raise ValueError(entity) from None
      entity._manager = dead_weakref
      for component_type in entity.types():
        component_type_entities = component_types[component_type]
        component_type_entities.remove(entity_id)
        if not component_type_entities:
          del component_types[component_type]
      if event_queue is not None:
        event_queue.extend([
          EntityRemoved(entity),
          *[ComponentRemoved(entity, component) for component in entity]
        ])

  def query(
    self, /, *component_types: type, merge: Callable[..., set] = set.intersection
  ) -> QueryResult:
    """Request specific data from the manager.

    Given an arbitrary non-zero number of types, return bulk data about
    the set of entities corresponding to these types, as a QueryResult.

    Each component type has a set of entities/ids that have it.
    The merge function combines these sets to create the final set of
    entities/ids that are used.

    By default, the merge function is set.intersection, which means the
    result is the entities that have all of the component types.

    The merge function must take a number of sets as arguments, where the
    number is how many component types are passed in, and return a set.
    Preferably, the merge function can take an arbitrary non-zero number of sets.
    The most common merge functions are unbound set methods.

    Args:
      *component_types: The types that are used to generate the set of entities.
      merge: The set merge function used to combine the sets of ids into one.

    Raises:
      TypeError: If exactly zero component types were given.

    Returns:
      A readonly QueryResult object that contains the data and info of the query.
    """
    if not component_types:
      raise TypeError('expected at least one component type')
    self_entities = self._entities
    self_component_types = self._component_types
    return QueryResult(
      {
        id: self_entities[id]
        for id in merge(*[
          self_component_types[typ]  # noqa: SIM401
          if typ in self_component_types else set()
          for typ in component_types
        ])
      },
      component_types,
      merge
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
      entities[entity_id] for entity_id in self._component_types.get(component_type, ())
    )

  def __getitem__(self, entity_id: EntityId, /) -> Entity:
    return self._entities[entity_id]

  def __delitem__(self, entity_id: EntityId, /):
    self.remove(self._entities[entity_id])

  @overload
  def get(self, entity_id: EntityId, /) -> Entity | None: ...
  @overload
  def get(self, entity_id: EntityId, default: _T, /) -> Entity | _T: ...
  def get(self, entity_id, default=None, /):
    return self._entities.get(entity_id, default)

  @overload
  def pop(self, entity_id: EntityId, /) -> Entity: ...
  @overload
  def pop(self, entity_id: EntityId, default: _T, /) -> Entity | _T: ...
  def pop(self, entity_id, default=_SENTINEL, /):
    try:
      entity = self._entities[entity_id]
    except KeyError:
      if default is _SENTINEL:
        raise
      return default
    self.remove(entity)
    return entity

  @overload
  def ids(self, /) -> KeysView[EntityId]: ...
  @overload
  def ids(self, component_type: type, /) -> set[EntityId]: ...
  def ids(self, component_type=None, /):
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
    return set(self._component_types.get(component_type, ()))

  def __iter__(self):
    return iter(self._entities.values())

  def __reversed__(self):
    return reversed(self._entities.values())

  def __len__(self):
    return len(self._entities)

  def __contains__(self, obj: object, /):
    if isinstance(obj, Entity):
      return obj.id in self._entities
    return obj in self._entities

  def clear(self) -> None:
    self.remove(*self)

  def _component_added(self, entity: Entity, component: object, /) -> None:
    try:
      self._component_types[type(component)].add(entity.id)
    except KeyError:
      self._component_types[type(component)] = {entity.id}
    event_queue = self.event_queue
    if event_queue is not None:
      event_queue.append(ComponentAdded(entity, component))

  def _component_removed(self, entity: Entity, component: object, /) -> None:
    entity_ids = self._component_types[type(component)]
    entity_ids.remove(entity.id)
    if not entity_ids:
      del self._component_types[type(component)]
    event_queue = self.event_queue
    if event_queue is not None:
      event_queue.append(ComponentRemoved(entity, component))
