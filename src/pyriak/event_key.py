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

To set a key function on an event type, use the set_key()
as a function or decorator on the class.

The operator module has useful functions for
creating key functions, e.g. attrgetter.
"""

__all__ = ["key_functions", "set_key", "KeyFunction"]

from collections.abc import Callable, Hashable, Iterator, Mapping
from typing import Any, TypeAlias, TypeVar
from weakref import WeakKeyDictionary

_T = TypeVar("_T")
_D = TypeVar("_D")

del TypeVar


KeyFunction: TypeAlias = Callable[[_T], Hashable | Iterator[Hashable]]
"""Type alias for a valid key function for a specified event type.

If the return type is an iterator (especially generator), the event keys
are what the iterator yields. Otherwise, the event key is the return value.
All keys must be hashable.
"""


key_functions: Mapping[type, KeyFunction[Any]] = WeakKeyDictionary()
"""The global read-only mapping of event types to key functions.

Once a key function is set for an event type, it cannot be
deleted or replaced.

This uses WeakKeyDictionary meaning that event types are not kept alive by
the mapping. This is necessary in case types are dynamically defined.
Note: In CPython, type objects have reference cycles, so only the garbage
collector can delete them, not reference counting.
"""


def set_key(key: KeyFunction[_T], /) -> Callable[[type[_T]], type[_T]]:
    """Assign a key function to an event type.

    Use as a decorator to assign a key function to an event class definition.

    Args:
        key: The key function to be assigned.

    Returns:
        A decorator that sets the key function on its argument
        and then returns the argument.
        This decorator raises ValueError if the type already has a key function.
    """

    def decorator(cls: type[_T], /) -> type[_T]:
        key_functions[cls] = key  # type: ignore[index]
        return cls

    return decorator
