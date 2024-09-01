"""This module contains the implementation for binding event handlers."""

__all__ = ['bind', 'Binding']

from collections.abc import Callable, Hashable, Iterable
from functools import update_wrapper
from typing import (
  TYPE_CHECKING,
  Any,
  Generic,
  TypeAlias,
  TypeVar,
  overload,
)

from pyriak import _SENTINEL
from pyriak.eventkey import key_functions


if TYPE_CHECKING:
  from pyriak.space import Space


_T = TypeVar('_T')
_R_co = TypeVar('_R_co', covariant=True)

_Callback: TypeAlias = Callable[['Space', _T], _R_co]


_empty_frozenset: frozenset[object] = frozenset()


class Binding(Generic[_T, _R_co]):
  """A Binding wraps the event handler callback with handler info.

  bind() returns a Binding. When a system is added to a SystemManager,
  it searches the system for attributes of type Binding.
  An event handler is then created for each binding on the system.

  Binding forwards calls to the internal callback.
  Binding supports descriptor access by redirecting it to the internal
  callback. This is to allow instance methods to be properly invoked as a
  bound method (for the self argument), if the callback was a function
  in a class.

  Attributes:
    _callback_: The event handler callback wrapped by the Binding.
    _event_type_: The event type bound to the handler.
    _priority_: The priority of the handler for this event type.
    _keys_: The frozenset of event keys that the handler be triggered by.
      Often empty, or only containing one key.
  """

  __wrapped__: _Callback[_T, _R_co]

  def __init__(
    self,
    callback: _Callback[_T, _R_co],
    event_type: type[_T],
    priority: Any,
    keys: frozenset[Hashable],
  ):
    update_wrapper(self, callback)
    self._event_type_ = event_type
    self._priority_ = priority
    self._keys_ = keys

  @property
  def _callback_(self) -> _Callback[_T, _R_co]:
    return self.__wrapped__

  def __call__(self, space: 'Space', event: _T, /) -> _R_co:
    return self._callback_(space, event)

  def __get__(self, obj, objtype=None):
    callback = self._callback_
    try:
      descr_get = type(callback).__get__  # type: ignore[attr-defined]
    except AttributeError:
      return callback
    return descr_get(callback, obj, objtype)


@overload
def bind(
  event_type: type[_T], priority: Any, /
) -> Callable[[_Callback[_T, _R_co]], Binding[_T, _R_co]]: ...
@overload
def bind(
  event_type: type[_T], priority: Any, /, *, key: Hashable
) -> Callable[[_Callback[_T, _R_co]], Binding[_T, _R_co]]: ...
@overload
def bind(
  event_type: type[_T], priority: Any, /, *, keys: Iterable[Hashable]
) -> Callable[[_Callback[_T, _R_co]], Binding[_T, _R_co]]: ...
def bind(event_type, priority, /, *, key=_SENTINEL, keys=_SENTINEL):
  """Bind a callback to an event type.

  To use, define a function that takes two arguments, space and event.
  Then, decorate it with a call to bind(), passing in the necessary info.

  This creates a binding. When the system is added to the space's SystemManager,
  an event handler will be created for this binding, which means that when an event
  of the correct type is processed by the SystemManager, the callback is invoked.
  This does not include subclasses of the event type. The types must be exact.

  The priority determines the order in which callbacks are invoked if there
  are multiple systems or event handlers for that event.

  The optional key or keys further narrow which events are handled.
  The event must give at least one key that matches the binding,
  if the binding has any keys.
  This is only valid for event types with key functions.

  bind() should only be used on attributes directly on the system.
  bind() cannot be used multiple times on the same object.

  bind() works on any callable, but the signature should be correct.
  It can be manually invoked with two calls instead of using as a decorator,
  if necessary.
  The most common place where bind() is used is on a module top-level function,
  where the module object is the system.

  Args:
    event_type: The type of events that the handler will be triggered by.
    priority: The object the handler will be sorted by for invocation.
    key: Defaults to no key. The key that events must have for the handler.
    keys: Defaults to no keys. The keys that events must have any of.

  Returns:
    A Binding instance that allows SystemManager to recognize bindings.

  Raises:
    TypeError: If the argument types or function call signature are incorrect.
      If `event_type` is not a type object and hashable.
      If key(s) were provided but the event type doesn't have a key function.
      If both `key` and `keys` keyword arguments are passed in.
      If any of the keys provided are not hashable.
      In the decorator, if the object is already a binding.

  Example:
    Typical usage of bind() decorator::

      @bind(UpdateGame, 500)
      def update_physics(space: Space, event: UpdateGame):
        ...
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
    raise TypeError(
      f'bind(): keys were provided but no key function exists for {event_type!r}'
    )
  def decorator(callback, /):
    if isinstance(callback, Binding):
      raise TypeError('cannot bind same object multiple times')
    return Binding(callback, event_type, priority, keys)
  return decorator
