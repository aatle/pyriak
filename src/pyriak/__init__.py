# ----------------------------------------------------------------------------
# pyriak
# Copyright (c) 2024 aatle

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# ----------------------------------------------------------------------------

"""Pyriak is a framework for ECS architecture.

This implementation also implements event-driven architecture.
The package is written in pure python and has no dependencies.

This module is the top-level module of the package and contains
most of the things necessary to use this package.
"""

__all__ = [
    "bind",
    "Space",
    "Entity",
    "EntityId",
    "System",
    "EventQueue",
    "key_functions",
    "set_key",
]

from collections.abc import Hashable as _Hashable, MutableSequence as _MutableSequence
from enum import Enum as _Enum
from typing import (
    Any as _Any,
    Final as _Final,
    Literal as _Literal,
    TypeAlias as _TypeAlias,
)
from weakref import ref as _weakref

System: _TypeAlias = _Hashable


EventQueue: _TypeAlias = _MutableSequence[object]


dead_weakref: _Final[_weakref[_Any]] = _weakref(set())


class _Sentinel(_Enum):
    SENTINEL = 1


_SENTINEL: _Final[_Literal[_Sentinel.SENTINEL]] = _Sentinel.SENTINEL


# circular imports
from pyriak.bind import bind  # noqa: E402
from pyriak.entity import Entity, EntityId  # noqa: E402
from pyriak.entity_manager import QueryResult as QueryResult  # noqa: E402
from pyriak.eventkey import key_functions, set_key  # noqa: E402
from pyriak.space import Space  # noqa: E402

NULL_ID: _Final[EntityId] = EntityId(0)


# cleanup namespace
del _Hashable, _MutableSequence, _Enum, _weakref
