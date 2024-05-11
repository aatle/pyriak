__all__ = [
  'Query',
  'QueryResult',
  'ComponentQueryResult',
  'EntityQueryResult',
  'IdQueryResult',
]

from abc import ABC, abstractmethod
from collections.abc import Iterator, KeysView, ValuesView
from typing import Any, Callable, NoReturn, TypeVar, overload

from pyriak.entity import Entity, EntityId


_T = TypeVar('_T')


class Query:
  __slots__ = '_types', '_merge'

  @overload
  def __init__(self, *, merge: Callable[..., set] = set.intersection) -> NoReturn: ...
  @overload
  def __init__(
    self, *component_types: type, merge: Callable[..., set] = set.intersection
  ): ...
  def __init__(self, *component_types, merge=set.intersection):
    if not component_types:
      raise TypeError('expected at least one component type')
    self._types = component_types
    self._merge = merge

  @property
  def types(self) -> tuple[type, ...]:
    return self._types

  @property
  def merge(self):
    return self._merge

  def count(self, value: type, /):
    return self._types.count(value)

  def index(self, *args):
    return self._types.index(*args)

  def __getitem__(self, key, /):
    return self._types[key]

  def __iter__(self):
    return iter(self._types)

  def __len__(self):
    return len(self._types)

  def __contains__(self, obj: object, /):
    return obj in self._types

  def __eq__(self, other: object, /):
    if not isinstance(other, Query):
      return NotImplemented
    # TODO: investigate unusual problem with type narrowing
    return self._types == other._types and self._merge == other._merge  # type: ignore

  def __hash__(self):
    return hash((self._types,self._merge))

  def __repr__(self):
    return (
      f'{type(self).__name__}'
      f'({", ".join(repr(t) for t in self._types)}, merge={self._merge!r})'
    )


class QueryResult(ABC):
  __slots__ = '_entities', '_types', '_merge'

  def __init__(self, _entities, _types, _merge, /):
    self._entities = _entities
    self._types = _types
    self._merge = _merge

  @property
  def ids(self) -> KeysView[EntityId]:
    return self._entities.keys()

  @property
  def entities(self) -> ValuesView[Entity]:
    return self._entities.values()

  @property
  def types(self) -> tuple[type, ...]:
    return self._types

  @property
  def merge(self) -> Callable[..., set]:
    return self._merge

  def query(self) -> Query:
    """Return a new Query object that describes self."""
    return Query(*self.types, merge=self.merge)

  @overload
  def __call__(self) -> Iterator[Any]: ...
  @overload
  def __call__(self, *component_types: type[_T]) -> Iterator[_T]: ...
  def __call__(self, *component_types):  # type: ignore
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
  def __getitem__(self, key, /):  # type: ignore
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
