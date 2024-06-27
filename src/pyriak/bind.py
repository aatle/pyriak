__all__ = ['bind', 'BindingWrapper', 'Binding']

from collections.abc import Callable, Hashable, Iterable
from functools import update_wrapper
from typing import (
  TYPE_CHECKING,
  Any,
  Generic,
  NamedTuple,
  Protocol,
  TypeAlias,
  TypeVar,
  overload,
)

from pyriak import _SENTINEL
from pyriak.eventkey import key_functions


if TYPE_CHECKING:
  from pyriak.space import Space


_T = TypeVar('_T')
_R = TypeVar('_R')
_S = TypeVar('_S')

_Callback: TypeAlias = Callable[['Space', _T], _R]


_empty_frozenset: frozenset[object] = frozenset()


class Binding(NamedTuple):
  event_type: type
  priority: Any
  keys: frozenset[Hashable]


class BindingWrapper(Generic[_T, _R]):
  """A wrapper for the event handler callback which holds the bindings."""

  __wrapped__: _Callback[_T, _R]

  def __init__(self, wrapped: _Callback[_T, _R], bindings: tuple[Binding, ...], /):
    self.__bindings__ = bindings
    update_wrapper(self, wrapped)

  def __call__(self, space: 'Space', event: _T, /) -> _R:
    return self.__wrapped__(space, event)

  def __get__(self, obj, objtype=None):
    wrapped = self.__wrapped__
    try:
      descr_get = type(wrapped).__get__  # type: ignore[attr-defined]
    except AttributeError:
      return wrapped
    return descr_get(wrapped, obj, objtype)


class _Decorator(Protocol, Generic[_T]):
  @overload
  def __call__(
    self, callback: BindingWrapper[_S, _R], /
  ) -> BindingWrapper[_S | _T, _R]: ...
  @overload
  def __call__(self, callback: _Callback[_T, _R], /) -> BindingWrapper[_T, _R]: ...


@overload
def bind(
  event_type: type[_T], priority: Any, /
) -> _Decorator[_T]: ...
@overload
def bind(
  event_type: type[_T], priority: Any, /, *, key: Hashable
) -> _Decorator[_T]: ...
@overload
def bind(
  event_type: type[_T], priority: Any, /, *, keys: Iterable[Hashable]
) -> _Decorator[_T]: ...
def bind(event_type, priority, /, *, key=_SENTINEL, keys=_SENTINEL):
  """Bind a callback to an event type.


  """
  if not isinstance(event_type, type):
    raise TypeError(f'{event_type!r} is not a type')
  try:
    hash(event_type)
  except TypeError:
    raise TypeError(f'{event_type!r} is not hashable') from None
  if key is not _SENTINEL:
    if keys is not _SENTINEL:
      raise TypeError("bind() cannot be passed both 'key' and 'keys' kwargs")
    keys = frozenset([key])
  else:
    keys = frozenset(keys) if keys is not _SENTINEL else _empty_frozenset
  if keys and not key_functions.exists(event_type):
    raise ValueError(
      f'bind(): keys were provided but no key function exists for {event_type!r}'
    )
  def decorator(callback, /):
    if not isinstance(callback, BindingWrapper):
      return BindingWrapper(callback, (Binding(event_type, priority, keys),))
    for binding in callback.__bindings__:
      if event_type is binding.event_type:
        raise ValueError(
          f'event handler {callback.__wrapped__!r} already has binding for {event_type!r}'
        )
    callback.__bindings__ += (Binding(event_type, priority, keys),)
    return callback
  return decorator
