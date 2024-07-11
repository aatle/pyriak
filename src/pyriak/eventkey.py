"""This module implements the functionality responsible for keyed event types.

Along with the event type, a bound event handler can further narrow down
what events it receives with an event key or keys.
An event's key, determined by the key function of the event type,
must match at least one of the bound keys.

A key function takes one argument, the event,
and returns either one key or an iterator of any number of keys.
Keys must be hashable.

Binding keys only available for event types with key functions,
but are not required. If no keys are bound, the event handler
acts as normal, ignoring event keys.

An event type either has or doesn't have a key function, and
this is global across the entire python process.
A key function cannot be removed once set.

To set a key function on an event type, either use the
key_functions variable as a mapping to do it manually,
or use the set_key() function/decorator on the class (preferred).

The operator module has useful functions for
creating key functions, e.g. attrgetter.
"""

__all__ = ['key_functions', 'set_key', 'KeyFunction']

from collections.abc import Callable, Hashable, Iterator, Mapping
from typing import Any, TypeAlias, TypeVar, overload
from weakref import WeakKeyDictionary


_T = TypeVar('_T')
_D = TypeVar('_D')

del TypeVar


KeyFunction: TypeAlias = Callable[[_T], Hashable | Iterator[Hashable]]
"""Type alias for a valid key function for a specified event type.

If the return type is an iterator (especially generator), the event keys
are what the iterator yields. Otherwise, the event key is the return value.
All keys must be hashable.
"""


class EventKeyFunctions:
  """A dictionary of event types to key functions.

  Once a key function is set for an event type, it cannot be
  deleted or replaced.
  Currently, there is only one key function mapping per process,
  accessible as pyriak.key_functions.

  Internally, EventKeyFunctions is implemented using a WeakKeyDictionary,
  meaning that event types are not kept alive just because they
  have a key function. Since type objects usually don't get deleted,
  this feature may rarely be used.
  Note: In CPython, type objects have reference cycles, so only the garbage
  collector can delete them, not reference counting.
  """

  __slots__ = ('_data',)

  def __init__(
    self, dict: Mapping[type, KeyFunction[Any]] | None = None
  ):
    self._data: WeakKeyDictionary[type, KeyFunction[Any]]
    self._data = WeakKeyDictionary()
    if dict is not None:
      self.update(dict)

  def __getitem__(self, event_type: type[_T]) -> KeyFunction[_T]:
    return self._data[event_type]

  def __setitem__(self, event_type: type[_T], key: KeyFunction[_T]):
    """Set a key function for an event type.

    Raises:
      KeyError: If the event type already has a key function set.
    """
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
  """Assign a key function to an event type.

  Use as a decorator to assign a key function to an event class definition.

  Args:
    key: The key function to be assigned.

  Returns:
    A decorator that sets the key function on its argument
    and then returns the argument.
    This decorator raises KeyError if the type already has a key function.
  """
  def decorator(cls: type[_T]) -> type[_T]:
    key_functions[cls] = key
    return cls
  return decorator
