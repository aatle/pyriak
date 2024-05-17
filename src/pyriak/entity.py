__all__ = ['Entity']

from collections.abc import Iterable
from typing import TYPE_CHECKING, NewType, TypeVar, overload
from uuid import uuid4

from pyriak import _SENTINEL, dead_weakref, strict_subclasses, subclasses
from pyriak.events import ComponentAdded, ComponentRemoved


if TYPE_CHECKING:
  from weakref import ref as weakref

  from pyriak.managers import EntityManager


EntityId = NewType('EntityId', int)


_T = TypeVar('_T')
_D = TypeVar('_D')


class Entity:
  __slots__ = 'id', '_components', '_manager', '__weakref__'

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
    events: list[ComponentAdded | ComponentRemoved] = []
    append_event = events.append
    for component in components:
      component_type = type(component)
      if component_type in self_components:
        other_component = self_components[component_type]
        if other_component is component or other_component == component:
          continue
        append_event(ComponentRemoved(self, other_component))
      self_components[component_type] = component
      append_event(ComponentAdded(self, component))
    manager = self._manager()
    if manager is not None:
      manager._components_added(self.id, components, events)

  def remove(self, *components: object) -> None:
    self_components = self._components
    manager = self._manager()
    for i, component in enumerate(components):
      component_type = type(component)
      try:
        other_component = self_components[component_type]
      except KeyError:
        pass
      else:
        if other_component is component or other_component == component:
          del self_components[component_type]
          continue
      if manager is not None:
        manager._components_removed(self, components[:i])
      raise ValueError(component)
    if manager is not None:
      manager._components_removed(self, components)

  def __call__(self, *component_types: type[_T]) -> list[_T]:
    components = self._components
    return [
      components[component_type]  # type: ignore
      for component_type in {
        comp_type: None for cls in component_types for comp_type in subclasses(cls)
      }  # dict instead of set to guarantee stable ordering while still removing dupes
      if component_type in components
    ]

  def __getitem__(self, component_type: type[_T], /) -> _T:
    try:
      return self._components[component_type]  # type: ignore[return-value]
    except KeyError:
      components = self._components
      for cls in strict_subclasses(component_type):
        if cls in components:
          return components[cls]  # type: ignore[return-value]
      raise

  def __setitem__(self, component_type: type[_T], component: _T, /):
    self.remove(*self(component_type))
    self.add(component)

  def __delitem__(self, component_type: type, /):
    self.remove(self[component_type])

  @overload
  def get(self, component_type: type[_T], /) -> _T | None: ...
  @overload
  def get(self, component_type: type[_T], default: _D, /) -> _T | _D: ...
  def get(self, component_type, default=None, /):
    try:
      return self._components[component_type]
    except KeyError:
      pass
    components = self._components
    for cls in strict_subclasses(component_type):
      if cls in components:
        return components[cls]
    return default

  @overload
  def pop(self, component_type: type[_T], /) -> _T: ...
  @overload
  def pop(self, component_type: type[_T], default: _D, /) -> _T | _D: ...
  def pop(self, component_type, default=_SENTINEL, /):
    try:
      component = self[component_type]
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
    if obj in self._components:
      return True
    if isinstance(obj, type):
      components = self._components
      for cls in strict_subclasses(obj):
        if cls in components:
          return True
    return False

  def __eq__(self, other: object, /):
    if self is other:
      return True
    if isinstance(other, Entity):
      return self._components == other._components
    return NotImplemented

  def clear(self):
    """Remove all components from self."""
    self.remove(*self)

  @staticmethod
  def new_id() -> EntityId:
    return uuid4().int  # type: ignore
