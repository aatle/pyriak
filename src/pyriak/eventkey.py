__all__ = ['key_functions', 'set_key', 'KeyFunction']

from collections.abc import Callable, Hashable, Iterator, Mapping
from typing import Any, TypeAlias, TypeVar, overload
from weakref import WeakKeyDictionary


_T = TypeVar('_T')
_D = TypeVar('_D')

del TypeVar


# if it is iterator (especially generator), it is multiple
# hashable keys, else it is the key itself (must be hashable)
KeyFunction: TypeAlias = Callable[[_T], Hashable | Iterator[Hashable]]


class EventKeyFunctions:
  """A weakkey dict of event types to key functions or None."""

  __slots__ = ('_data',)

  def __init__(
    self, dict: Mapping[type, KeyFunction[Any]] | None = None
  ):
    self._data: WeakKeyDictionary[type, KeyFunction[Any]]
    self._data = WeakKeyDictionary()
    if dict is not None:
      self.update(dict)

  def __getitem__(self, event_type: type[_T]) -> KeyFunction[_T]:
    """Return the key function for an event_type."""
    return self._data[event_type]

  def __setitem__(self, event_type: type[_T], key: KeyFunction[_T]):
    data = self._data
    if event_type in data:
      raise KeyError(f'cannot reassign event type key: {event_type!r}')
    data[event_type] = key

  @overload
  def get(self, event_type: type[_T]) -> KeyFunction[_T] | None: ...
  @overload
  def get(self, event_type: type[_T], default: _D) -> KeyFunction[_T] | _D: ...
  def get(self, event_type, default=None):
    return self._data.get(event_type, default)

  def setdefault(
    self, event_type: type[_T], default: KeyFunction[_T]
  ) -> KeyFunction[_T]:
    data = self._data
    if event_type in data:
      return data[event_type]
    data[event_type] = default
    return default

  def update(self, other: Mapping[type, KeyFunction[Any]]) -> None:
    for event_type, key in dict(other).items():
      self[event_type] = key

  def keys(self):
    return self._data.keys()

  def values(self):
    return self._data.values()

  def items(self):
    return self._data.items()

  def __len__(self):
    return len(self._data)

  def __contains__(self, event_type: type):
    return event_type in self._data

  def __iter__(self):
    return iter(self._data)

  def __or__(self, other: Mapping[type, KeyFunction[Any]]):
    return self._data | other

  def __ror__(self, other: Mapping[type, KeyFunction[Any]]):
    return other | self._data

  def __ior__(self, other: Mapping[type, KeyFunction[Any]]):
    self.update(other)
    return self

  def copy(self):
    return self._data.copy()

  def keyrefs(self):
    return self._data.keyrefs()


key_functions = EventKeyFunctions()


def set_key(key: KeyFunction[_T], /) -> Callable[[type[_T]], type[_T]]:
  """Assign a key function (permanently) to an event type.

  Convenience decorator to assign a key function (or None) to an event class definition.

  The operator module has useful functions for creating key functions, e.g. attrgetter.
  """
  def decorator(cls: type[_T]) -> type[_T]:
    key_functions[cls] = key
    return cls
  return decorator
