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
  MutableSequence as _MutableSequence,
)
from enum import Enum as _Enum
from typing import (
  Any as _Any,
  Literal as _Literal,
  TypeAlias as _TypeAlias,
  TypeVar as _TypeVar,
  overload as _overload,
)
from weakref import ref as _weakref


_TypeT = _TypeVar('_TypeT', bound=type)
_T = _TypeVar('_T')
_D = _TypeVar('_D')


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


@_overload
def tagclass(cls: _TypeT, /) -> _TypeT: ...
@_overload
def tagclass(
  name: str, bases: tuple[type, ...] = (), namespace: dict[str, _Any] = ..., /
) -> type: ...
def tagclass(*args) -> type:
  """Make a tag class.

  A tag class has instances that are all equal and carry no mutable/instance data.
  These instances serve as tags, or markers, which can be useful in component queries.

  Ways to use tag:
  - plain decorator: mutates class inplace
  - call with cls arg: same as plain decorator
  - call with type signature, creates class

  This is useful for dataless events and 'tag' components.
  """

  try:
    first = args[0]
  except IndexError:
    raise TypeError('tag must have at least one argument') from None
  def __eq__(self, other):  # noqa: ARG001
    return isinstance(other, cls)
  def __hash__(self):  # noqa: ARG001
    return hash((cls,))  # does not hash subclass: only uses the decorated class
  if isinstance(first, type):
    if len(args) != 1:
      raise TypeError(
        'tag() takes exactly one argument when first argument is a type '
        f'({len(args)} given)'
      )
    cls = first
    cls.__eq__ = __eq__  # type: ignore
    cls.__hash__ = __hash__  # type: ignore
    return cls
  num_args = len(args)
  namespace = {'__slots__': (), '__eq__': __eq__, '__hash__': __hash__}
  if num_args < 3:
    bases = () if num_args == 1 else args[1]
  elif num_args == 3:
    bases = args[1]
    if not isinstance(args[2], dict):
      raise TypeError(args[2])
    namespace.update(args[2])
  else:
    raise TypeError('tag() takes at most 3 arguments')
  cls = type(first, bases, namespace)  # required variable so dunder methods know cls
  return cls  # noqa: RET504


def first(arg: _T, *args: _Any) -> _T:  # noqa: ARG001
  return arg


class _Sentinel(_Enum):
  SENTINEL = 1

_SENTINEL: _Sentinel = _Sentinel.SENTINEL


# circular imports
from pyriak.entity import Entity, EntityId  # noqa: E402
from pyriak.eventkey import key_functions, set_key  # noqa: E402
from pyriak.query import Query  # noqa: E402
from pyriak.space import Space  # noqa: E402
from pyriak.system import System, bind  # noqa: E402


# cleanup namespace
del _MutableSequence, _Enum, _Literal, _TypeVar, _weakref
