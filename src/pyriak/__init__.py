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
  'bind',
  'Space',
  'Entity',
  'EntityId',
  'System',
  'EventQueue',
  'key_functions',
  'set_key',
  'tagclass',
  'first',
]

from collections.abc import (
  Hashable as _Hashable,
  MutableSequence as _MutableSequence,
)
from enum import Enum as _Enum
from typing import (
  Any as _Any,
  TypeAlias as _TypeAlias,
  TypeVar as _TypeVar,
)
from weakref import ref as _weakref


_TypeT = _TypeVar('_TypeT', bound=type)
_T = _TypeVar('_T')
_D = _TypeVar('_D')


System: _TypeAlias = _Hashable


EventQueue: _TypeAlias = _MutableSequence[object]


dead_weakref: _weakref[_Any] = _weakref(set())


def tagclass(cls: type) -> type:
  namespace = dict(cls.__dict__)
  namespace.setdefault('__slots__', ())
  namespace.pop('__dict__', None)
  namespace.pop('__weakref__', None)
  qualname = getattr(cls, '__qualname__', None)
  cls = type(cls)(cls.__name__, cls.__bases__, namespace)
  if qualname is not None:
    cls.__qualname__ = qualname
  def __eq__(self, other):
    if other is self or type(other) is type(self):
      return True
    return NotImplemented
  def __hash__(self):
    return hash((type(self),))
  cls.__eq__ = __eq__  # type: ignore[method-assign, assignment]
  cls.__hash__ = __hash__  # type: ignore[method-assign, assignment]
  return cls


def first(arg: _T, /, *args: _Any) -> _T:  # noqa: ARG001
  return arg


class _Sentinel(_Enum):
  SENTINEL = 1

_SENTINEL: _Sentinel = _Sentinel.SENTINEL


# circular imports
from pyriak.bind import bind  # noqa: E402
from pyriak.entity import Entity, EntityId  # noqa: E402
from pyriak.eventkey import key_functions, set_key  # noqa: E402
from pyriak.managers.entitymanager import QueryResult as QueryResult  # noqa: E402
from pyriak.space import Space  # noqa: E402


# cleanup namespace
del _MutableSequence, _Enum, _TypeVar, _weakref
