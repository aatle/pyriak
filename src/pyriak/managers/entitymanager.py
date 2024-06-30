__all__ = ['EntityManager']

from collections.abc import Iterable, Iterator, KeysView
from typing import Callable, TypeVar, overload
from weakref import ref as weakref

from pyriak import _SENTINEL, EventQueue, dead_weakref, subclasses
from pyriak.entity import Entity, EntityId
from pyriak.events import ComponentAdded, ComponentRemoved, EntityAdded, EntityRemoved
from pyriak.query import (
  ComponentQueryResult,
  EntityQueryResult,
  IdQueryResult,
  QueryResult,
)


_T = TypeVar('_T')
_Q = TypeVar('_Q', bound=QueryResult)


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
      component
      for entity_id in manager._component_types.get(component_type, ())
      for component in entities[entity_id](component_type)
    )

  def __getitem__(self, component_type: type[_T], /) -> Iterator[_T]:
    manager = self._manager()
    entities = manager._entities
    return (entities[entity_id][component_type]
            for entity_id in manager._component_types.get(component_type, ()))

  def types(self) -> KeysView[type]:
    return self._manager()._component_types.keys()

  def __iter__(self) -> Iterator[object]:
    for entity in self._manager():
      yield from entity

  def __reversed__(self) -> Iterator[object]:
    for entity in reversed(self._manager()):
      yield from reversed(entity)

  def __len__(self):
    return sum(len(entity) for entity in self._manager()._entities.values())

  def __contains__(self, obj: object, /):
    types = self._manager()._component_types
    if isinstance(obj, type):
      for cls in subclasses(obj):
        if cls in types:
          return True
    return False


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
      for component_type in {
        component_type for cls in entity.types() for component_type in cls.__mro__
      }:
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
      for component_type in {
        component_type for cls in entity.types() for component_type in cls.__mro__
      }:
        component_type_entities = component_types[component_type]
        component_type_entities.remove(entity_id)
        if not component_type_entities:
          del component_types[component_type]
      if event_queue is not None:
        event_queue.extend([
          EntityRemoved(entity),
          *[ComponentRemoved(entity, component) for component in entity]
        ])

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

  def query(
    self, /, *component_types: type, merge: Callable[..., set] = set.intersection
  ) -> ComponentQueryResult:
    """"""
    return self._query(ComponentQueryResult, component_types, merge)

  def entity_query(
    self, /, *component_types: type, merge: Callable[..., set] = set.intersection
  ) -> EntityQueryResult:
    """"""
    return self._query(EntityQueryResult, component_types, merge)

  def id_query(
    self, /, *component_types: type, merge: Callable[..., set] = set.intersection
  ) -> IdQueryResult:
    """"""
    return self._query(IdQueryResult, component_types, merge)

  def _query(
    self,
    result_cls: type[_Q],
    component_types: tuple[type, ...],
    merge: Callable[..., set] = set.intersection,
    /
  ) -> _Q:
    """"""
    if not component_types:
      raise TypeError('expected at least one component type')
    self_entities = self._entities
    self_component_types = self._component_types
    return result_cls(
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
    component_types = self._component_types
    if component_type not in component_types:
      return set()
    return set(component_types[component_type])

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

  def clear(self):
    self.remove(*self)

  def _component_added(self, entity: Entity, component: object, /) -> None:
    component_types = self._component_types
    entity_id = entity.id
    for component_type in type(component).__mro__:
      try:
        component_types[component_type].add(entity_id)
      except KeyError:
        component_types[component_type] = {entity_id}
    event_queue = self.event_queue
    if event_queue is not None:
      event_queue.append(ComponentAdded(entity, component))

  def _component_removed(self, entity: Entity, component: object, /) -> None:
    component_types = self._component_types
    entity_id = entity.id
    for component_type in type(component).__mro__:
      if component_type in entity:
        continue
      entity_ids = component_types[component_type]
      entity_ids.remove(entity_id)
      if not entity_ids:
        del component_types[component_type]
    event_queue = self.event_queue
    if event_queue is not None:
      event_queue.append(ComponentRemoved(entity, component))
