""""""

__all__ = [
  'Space',
  'System',
  'bind',
  'Entity',
  'EntityId',
  'Query',
  'subclasses',
  'strict_subclasses',
  'key_functions',
  'set_key',
  'tagclass',
  'first',
]

from collections.abc import (
  Generator as _Generator,
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


_get_subclasses = type.__subclasses__

def subclasses(cls: _TypeT, /) -> _Generator[_TypeT, None, _TypeT]:
  """Generator of the class and all of the class's subclasses.

  Metaclasses also work.
  There may be duplicates in the case of multiple inheritance.
  Note: overridden implementations of __subclasses__ are ignored
  because type.__subclasses__ is used, which also prevents cycles.

  The order the classes are returned is not specified, however:
  It is guaranteed that the cls passed in is the first class yielded.
  For a tree inheritance structure (single inheritance only), a subclass
  will never be yielded before any of its superclasses.

  'Return' the cls passed in. (This value is accessible through
  the StopIteration that is raised).
  """
  yield cls
  get_subclasses = _get_subclasses
  stack = get_subclasses(cls)
  pop = stack.pop
  while stack:
    subclass = pop()
    yield subclass
    stack += get_subclasses(subclass)
  return cls


def strict_subclasses(cls: _TypeT, /) -> _Generator[_TypeT, None, _TypeT]:
  """Same as subclasses, but does not yield the original class."""
  get_subclasses = _get_subclasses
  stack = get_subclasses(cls)
  pop = stack.pop
  while stack:
    subclass = pop()
    yield subclass
    stack += get_subclasses(subclass)
  return cls


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


def first(arg: _T, *args: _Any) -> _T:  # noqa: ARG001
  return arg


class _Sentinel(_Enum):
  SENTINEL = 1

_SENTINEL: _Sentinel = _Sentinel.SENTINEL


# circular imports
from pyriak.bind import bind  # noqa: E402
from pyriak.entity import Entity, EntityId  # noqa: E402
from pyriak.eventkey import key_functions, set_key  # noqa: E402
from pyriak.query import Query  # noqa: E402
from pyriak.space import Space  # noqa: E402


# cleanup namespace
del _MutableSequence, _Enum, _TypeVar, _weakref
