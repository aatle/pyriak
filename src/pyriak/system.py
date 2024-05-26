__all__ = ['bind', 'System', 'BindingWrapper', 'Binding']

from collections.abc import Callable, Hashable, Iterable
from functools import update_wrapper
from typing import TYPE_CHECKING, Any, NamedTuple, TypeAlias, TypeVar, overload

from pyriak import _SENTINEL
from pyriak.eventkey import key_functions


if TYPE_CHECKING:
  from pyriak.space import Space


_T = TypeVar('_T')
_R = TypeVar('_R')

_Callback: TypeAlias = Callable[['Space', _T], _R]


class Binding(NamedTuple):
  event_type: type
  priority: Any
  keys: frozenset[Hashable]


System: TypeAlias = Hashable


class BindingWrapper:
  """A wrapper for the event handler callback which holds the bindings."""

  __wrapped__: Callable

  def __init__(self, wrapped: Callable, bindings: tuple[Binding, ...], /):
    self.__bindings__ = bindings
    update_wrapper(self, wrapped)

  def __call__(self, /, *args, **kwargs):
    return self.__wrapped__(*args, **kwargs)

  def __get__(self, obj, objtype=None):
    wrapped = self.__wrapped__
    try:
      descr_get = type(wrapped).__get__  # type: ignore[attr-defined]
    except AttributeError:
      return wrapped
    return descr_get(wrapped, obj, objtype)


@overload
def bind(
  event_type: type[_T], priority: Any, /
) -> Callable[[_Callback[_T, _R]], _Callback[_T, _R]]: ...
@overload
def bind(
  event_type: type[_T], priority: Any, /, *, key: Hashable
) -> Callable[[_Callback[_T, _R]], _Callback[_T, _R]]: ...
@overload
def bind(
  event_type: type[_T], priority: Any, /, *, keys: Iterable[Hashable]
) -> Callable[[_Callback[_T, _R]], _Callback[_T, _R]]: ...
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
    keys = frozenset(keys) if keys is not _SENTINEL else frozenset()
  if keys and not key_functions.exists(event_type):
    raise ValueError(
      f'bind(): keys were provided but no key function exists for {event_type!r}'
    )
  def decorator(callback: _Callback[_T, _R], /) -> _Callback[_T, _R]:
    if not isinstance(callback, BindingWrapper):
      return BindingWrapper(callback, (Binding(event_type, priority, keys),))
    for binding in callback.__bindings__:
      if event_type is binding.event_type:
        raise ValueError(
          f'{event_type!r} is already bound to event handler {callback._callback_!r}'
        )
    callback.__bindings__ += (Binding(event_type, priority, keys),)
    return callback
  return decorator
