"""This module implements some features for tag components.

Tag components are used in query operations as another way of selecting entities.
"""

__all__ = ["tag", "tag_types"]

from collections.abc import Hashable, Set as AbstractSet
from typing import TypeVar
from weakref import WeakSet

_H = TypeVar("_H", bound=Hashable)

tag_types: AbstractSet[type[Hashable]] = WeakSet()
"""The global read-only set of tag types.

Once a type is added, it cannot be removed.

This uses WeakSet meaning that types are not kept alive by
the set. This is necessary in case types are dynamically defined.
Note: In CPython, type objects have reference cycles, so only the garbage
collector can delete them, not reference counting.
"""


def tag(cls: type[_H], /) -> type[_H]:
    """Register a component type as a tag type.

    This can be used either as a decorator or a normal function.

    The component must be hashable.
    It typically holds no data other than what is used for hashing.
    Features such as dataclass(frozen=True), NamedTuple, and Enum
    are common ways to define tag types.
    An empty class can also be useful as a tag type.

    Args:
        cls: The component type to register.

    Returns:
        The cls passed in, to allow use as a decorator.

    Raises:
        ValueError: If the type is already a tag type.

    Example:
        @tag
        @dataclass(frozen=True)
        class Leader:
            id: EntityId
    """
    if cls in tag_types:
        raise ValueError(f"component type {cls!r} is already a tag type")
    tag_types.add(cls)  # type: ignore[attr-defined]
    return cls
