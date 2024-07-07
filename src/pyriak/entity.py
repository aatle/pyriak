__all__ = ['Entity', 'EntityId']

from collections.abc import Iterable
from typing import TYPE_CHECKING, NewType, TypeVar, overload
from uuid import uuid4

from pyriak import _SENTINEL, dead_weakref


if TYPE_CHECKING:
  from weakref import ref as weakref

  from pyriak.managers import EntityManager


EntityId = NewType('EntityId', int)


_T = TypeVar('_T')
_D = TypeVar('_D')


class Entity:
  __slots__ = 'id', '_components', '_manager'

  def __init__(self, components: Iterable[object] = (), /):
    self.id: EntityId = self.new_id()
    self._manager: weakref[EntityManager] = dead_weakref
    comp_dict: dict[type, object] = {}
    for comp in components:
      comp_type = type(comp)
      if comp_type in comp_dict and (
          (other := comp_dict[comp_type]) is comp or other == comp):
        continue
      comp_dict[comp_type] = comp
    self._components: dict[type, object] = comp_dict

  def add(self, *components: object) -> None:
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

  def __getitem__(self, component_type: type[_T], /) -> _T:
    return self._components[component_type]  # type: ignore[return-value]

  def __delitem__(self, component_type: type, /):
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

  def types(self):
    return self._components.keys()

  def __iter__(self):
    return iter(self._components.values())

  def __reversed__(self):
    return reversed(self._components.values())

  def __len__(self):
    return len(self._components)

  def __contains__(self, obj: object, /):
    return obj in self._components

  def __eq__(self, other: object, /):
    if self is other:
      return True
    if isinstance(other, Entity):
      return self._components == other._components
    return NotImplemented

  def clear(self) -> None:
    """Remove all components from self."""
    self.remove(*self)

  @staticmethod
  def new_id() -> EntityId:
    return uuid4().int  # type: ignore[return-value]
