__all__ = ['EntityManager', 'QueryResult']

from collections.abc import Collection, Iterable, Iterator, KeysView, Set as AbstractSet
from typing import Any, Callable, TypeVar, overload
from weakref import ref as weakref

from pyriak import _SENTINEL, EventQueue, dead_weakref
from pyriak.entity import Entity, EntityId
from pyriak.events import ComponentAdded, ComponentRemoved, EntityAdded, EntityRemoved


_T = TypeVar('_T')


class QueryResult:
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
    return self._entities.keys()

  @property
  def entities(self) -> Collection[Entity]:
    return self._entities.values()

  @property
  def types(self) -> tuple[type, ...]:
    return self._types

  @property
  def merge(self) -> Callable[..., set]:
    return self._merge

  def __call__(self, component_type: type[_T], /) -> Iterator[_T]:
    return (entity[component_type] for entity in self.entities)

  @overload
  def zip(self) -> Iterator[tuple[Any, ...]]: ...
  @overload
  def zip(self, *component_types: type[_T]) -> Iterator[tuple[_T, ...]]: ...
  def zip(self, *component_types):
    if not component_types:
      component_types = self.types
    return (
      tuple([ent[comp_type] for comp_type in component_types]) for ent in self.entities
    )

  @overload
  def zip_entity(self) -> Iterator[tuple[Any, ...]]: ...
  @overload
  def zip_entity(
    self, *component_types: type[_T]
  ) -> Iterator[tuple[Entity | _T, ...]]: ...
  def zip_entity(self, *component_types):
    if not component_types:
      component_types = self.types
    return (
      (ent, *[ent[comp_type] for comp_type in component_types]) for ent in self.entities
    )

  __iter__ = __hash__ = None  # type: ignore


class _Components:
  """The components attribute of an EntityManager instance, exposes more functionality.

  If the EntityManager has been garbage collected, all methods
  raise TypeError.
  """

  __slots__ = ('_manager',)

  _manager: Callable[[], 'EntityManager']

  def __call__(self, component_type: type[_T], /) -> Iterator[_T]:
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
  __slots__ = '_entities', '_component_types', 'components', 'event_queue', '__weakref__'

  def __init__(
    self, entities: Iterable[Entity] = (), /, event_queue: EventQueue | None = None
  ):
    self.event_queue = event_queue
    self.components = _Components()
    self.components._manager = weakref(self)  # type: ignore
    self._entities: dict[EntityId, Entity] = {}
    self._component_types: dict[type, set[EntityId]] = {}
    self.add(*entities)

  def add(self, *entities: Entity) -> None:
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
    """Create an Entity with the given components, add it to self, and return it.

    The returned Entity can, of course, be directly modified.
    """
    entity: Entity = Entity(components)
    self.add(entity)
    return entity

  def remove(self, *entities: Entity) -> None:
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
    """"""
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
    """Return a generator of all entities in self that contain component_type."""
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

    If no component type is given, then
    return a set-like view of all entity ids in self instead.
    """
    if component_type is None:
      return self._entities.keys()
    return set(self._component_types.get(component_type, ()))

  def __iter__(self):
    """Return an iterator of all Entities in self.

    The least recently added Entities are first.
    """
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
