"""This module contains the implementation for binding event handlers."""

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
  """A Binding holds info from one call to bind().

  Attributes:
    event_type: The event type bound to the handler.
    priority: The priority of the handler for this event type.
    keys: The frozenset of event keys that the handler be triggered by.
      Often empty, or only containing one key.
  """
  event_type: type
  priority: Any
  keys: frozenset[Hashable]


class BindingWrapper(Generic[_T, _R]):
  """A BindingWrapper wraps the event handler callback with its bindings.

  bind() returns a BindingWrapper. When a system is added to a SystemManager,
  it searches the system for attributes of type BindingWrapper.

  BindingWrapper forwards calls to the internal callback.
  BindingWrapper supports descriptor access by redirecting it to the internal
  callback. This is to allow instance methods to be properly invoked as a
  bound method (for the self argument), if the callback was a function
  in a class.

  Attributes:
    __wrapped__: The event handler callable wrapped by the BindingWrapper.
  """

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

  To use, define a function that takes two arguments, space and event.
  Then, decorate it with a call to bind(), passing in the necessary info.

  This creates a binding, which means that when an event of the correct
  type is processed by the SystemManager, the callback is invoked.
  This does not include subclasses of the event type. The types must be exact.

  The priority determines the order in which callbacks are invoked if there
  are multiple systems or bindings for that event.

  The optional key or keys further narrow which events are handled.
  The event must give at least one key that matches the binding,
  if the binding has any keys.
  This is only valid for event types with key functions.

  bind() should only be used on attributes directly on the system.

  bind() can be used multiple times on the same callback, as long as
  different event types are bound.

  bind() works on any callable, but the signature should be correct.
  It can be manually invoked with two calls instead of using as a decorator.
  The most common place where this is used is on a module top-level function,
  where the module is the system.

  Args:
    event_type: The type of events that the handler will be triggered by.
    priority: The object the handler will be sorted by during invocation.
    key: Defaults to no key. The key that events must have for this handler.
    keys: Defaults to no keys. The keys that events must have any of.

  Returns:
    A BindingWrapper instance that allows SystemManager to recognize bindings.

  Raises:
    TypeError: If the argument types or function call signature are incorrect.
      If `event_type` is not a type object and hashable.
      If both `key` and `keys` keyword arguments are passed in.
      If any of the keys provided are not hashable.
    ValueError: If the argument value is bad.
      If a key or keys were provided but the event type doesn't have a key function.
      In the decorator, if the event type is already bound to this callback.
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
  if keys and event_type not in key_functions:
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
