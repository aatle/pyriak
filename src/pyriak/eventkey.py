__all__ = ['key_functions', 'set_key', 'NoKey', 'NoKeyType', 'KeyFunction']

from collections.abc import Callable, Hashable, Iterator, Mapping
from typing import Any, TypeAlias, TypeVar, overload
from weakref import WeakKeyDictionary

from pyriak import _SENTINEL


_T = TypeVar('_T')
_D = TypeVar('_D')

del TypeVar


class NoKeyType:
  __slots__ = ()

  def __new__(cls, /):
    return NoKey

  def __repr__(self, /):
    return 'NoKey'

  def __init_subclass__(cls, /, **kwargs):
    raise TypeError(f"cannot subclass type '{cls.__name__}'")


NoKey: NoKeyType = object.__new__(NoKeyType)


# if return value is NoKey, then no key, else if it is iterator (especially generator),
# it is multiple hashable keys, else it is the key itself (must be hashable)
KeyFunction: TypeAlias = Callable[[_T], Hashable | Iterator[Hashable] | NoKeyType]


class EventKeyFunctions:
  """A weakkey dict of event types to key functions or None."""

  __slots__ = ('_data',)

  def __init__(
    self, dict: Mapping[type, KeyFunction[Any] | None] | None = None
  ):
    self._data: WeakKeyDictionary[type, KeyFunction[Any] | None]
    self._data = WeakKeyDictionary()
    if dict is not None:
      self.update(dict)

  @overload
  def __call__(self, event_type: type[_T]) -> KeyFunction[_T]: ...
  @overload
  def __call__(self, event_type: type[_T], default: _D) -> KeyFunction[_T] | _D: ...
  def __call__(self, event_type, default=_SENTINEL):
    """Return the key function for event_type.

    A key function is used to extract a key from an event of type event_type.

    Each type in the event_type's method resolution order (__mro__) is checked until
    a specific key function is found and is not None,
    in which case the key function is returned.
    If no key function is found that is not None, default is returned if it is provided,
    otherwise a KeyError is raised.
    This is the only method that considers superclasses, other than the exists method.
    """
    get = self._data.get
    for cls in event_type.__mro__:
      key_function = get(cls)
      if key_function is not None:
        return key_function
    if default is _SENTINEL:
      raise KeyError(event_type)
    return default

  def exists(self, event_type: type) -> bool:
    """Return True if there is a key function for event_type that is not None."""
    return self(event_type, None) is not None

  def __getitem__(self, event_type: type[_T]) -> KeyFunction[_T] | None:
    """Return the specific key function for an event_type, ignoring superclasses."""
    return self._data[event_type]

  def __setitem__(self, event_type: type[_T], key: KeyFunction[_T] | None):
    data = self._data
    if event_type in data:
      raise KeyError(f'cannot reassign event type key: {event_type!r}')
    if key is NoKey:
      raise TypeError(f'do not use {NoKey} to denote no key function, use None instead')
    data[event_type] = key

  @overload
  def get(self, event_type: type[_T]) -> KeyFunction[_T] | None: ...
  @overload
  def get(self, event_type: type[_T], default: _D) -> KeyFunction[_T] | _D: ...
  def get(self, event_type, default=None):
    try:
      return self._data[event_type]
    except KeyError:
      return default

  def setdefault(
    self, event_type: type[_T], default: KeyFunction[_T] | None = None
  ) -> KeyFunction[_T] | None:
    data = self._data
    if event_type in data:
      return data[event_type]
    self[event_type] = default
    return default

  def update(self, other: Mapping[type, KeyFunction[Any] | None]) -> None:
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

  def __or__(self, other: Mapping[type, KeyFunction[Any] | None]):
    return self._data | other

  def __ror__(self, other: Mapping[type, KeyFunction[Any] | None]):
    return other | self._data

  def __ior__(self, other: Mapping[type, KeyFunction[Any] | None]):
    self.update(other)
    return self

  __copy__ = None  # type: ignore

  def copy(self):
    return self._data.copy()

  def keyrefs(self):
    return self._data.keyrefs()


key_functions = EventKeyFunctions()
key_functions[object] = None


def set_key(key: KeyFunction[_T] | None, /) -> Callable[[type[_T]], type[_T]]:
  """Assign a key function (permanently) to an event type.

  Convenience decorator to assign a key function (or None) to an event class definition.

  The operator module has useful functions for creating key functions, e.g. attrgetter.
  """
  def decorator(cls: type[_T]) -> type[_T]:
    key_functions[cls] = key
    return cls
  return decorator
