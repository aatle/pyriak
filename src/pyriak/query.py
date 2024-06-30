__all__ = [
  'QueryResult',
  'ComponentQueryResult',
  'EntityQueryResult',
  'IdQueryResult',
]

from abc import ABC, abstractmethod
from collections.abc import Collection, Iterator, Set as AbstractSet
from typing import Any, Callable, TypeVar, overload

from pyriak.entity import Entity, EntityId


_T = TypeVar('_T')


class QueryResult(ABC):
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

  @overload
  def __call__(self) -> Iterator[Any]: ...
  @overload
  def __call__(self, *component_types: type[_T]) -> Iterator[_T]: ...
  def __call__(self, *component_types):
    if not component_types:
      component_types = self.types
    return (comp for ent in self.entities for comp in ent(*component_types))

  # group method

  @overload
  @abstractmethod
  def __getitem__(self, key: tuple[()], /) -> tuple[Iterator[Any], ...]: ...
  @overload
  @abstractmethod
  def __getitem__(
    self, component_types: tuple[type, ...], /
  ) -> tuple[Iterator[Any], ...]: ...
  @overload
  @abstractmethod
  def __getitem__(
    self, component_type: type[_T], /
  ) -> Iterator[_T] | tuple[Iterator[Any], Iterator[_T]]: ...
  @abstractmethod
  def __getitem__(self, key, /):
    ...

  #= get method?

  @abstractmethod
  def zip(self, *component_types: type) -> Iterator[tuple[Any, ...]]:
    ...

  __iter__ = __hash__ = None  # type: ignore


class ComponentQueryResult(QueryResult):
  @overload
  def __getitem__(self, key: tuple[()], /) -> tuple[Iterator[Any], ...]: ...
  @overload
  def __getitem__(
    self, component_types: tuple[type[_T], ...], /
  ) -> tuple[Iterator[_T], ...]: ...
  @overload
  def __getitem__(self, component_type: type[_T], /) -> Iterator[_T]: ...
  def __getitem__(self, key, /):  # type: ignore
    entities = self.entities
    if isinstance(key, tuple):
      return tuple(
        (ent[comp_type] for ent in entities)
        for comp_type in (key if key else self.types)
      )
    return (ent[key] for ent in entities)

  @overload
  def zip(self) -> Iterator[tuple[Any, ...]]: ...
  @overload
  def zip(self, *component_types: type[_T]) -> Iterator[tuple[_T, ...]]: ...
  def zip(self, *component_types: type):  # type: ignore
    if not component_types:
      component_types = self.types
    return (
      tuple(ent[comp_type] for comp_type in component_types) for ent in self.entities
    )


class EntityQueryResult(QueryResult):
  #@overload
  #def __getitem__(self, key: tuple[()], /) -> tuple[Iterator[Any], ...]: ...
  @overload
  def __getitem__(
    self, component_types: tuple[type, ...], /
  ) -> tuple[Iterator[Any], ...]: ...
  @overload
  def __getitem__(
    self, component_type: type[_T], /
  ) -> tuple[Iterator[Entity], Iterator[_T]]: ...
  def __getitem__(self, key, /):  # type: ignore
    entities = self.entities
    if isinstance(key, tuple):
      types = key if key else self.types
      return (
        iter(entities), *[(ent[comp_type] for ent in entities) for comp_type in types]
      )
    return (iter(entities), (ent[key] for ent in entities))

  def zip(self, *component_types: type) -> Iterator[tuple[Any, ...]]:
    if not component_types:
      component_types = self.types
    return (
      (ent, *[ent[comp_type] for comp_type in component_types]) for ent in self.entities
    )


class IdQueryResult(QueryResult):
  #@overload
  #def __getitem__(self, key: tuple[()], /) -> tuple[Iterator[Any], ...]: ...
  @overload
  def __getitem__(
    self, component_types: tuple[type, ...], /
  ) -> tuple[Iterator[Any], ...]: ...
  @overload
  def __getitem__(
    self, component_type: type[_T], /
  ) -> tuple[Iterator[EntityId], Iterator[_T]]: ...
  def __getitem__(self, key, /):  # type: ignore
    entities = self.entities
    if isinstance(key, tuple):
      types = key if key else self.types
      return (
        iter(self.ids), *[(ent[comp_type] for ent in entities) for comp_type in types]
      )
    return (iter(self.ids), (ent[key] for ent in entities))

  def zip(self, *component_types: type) -> Iterator[tuple[Any, ...]]:
    if not component_types:
      component_types = self.types
    return (
      (ent.id, *[ent[comp_type] for comp_type in component_types])
      for ent in self.entities
    )
