__all__ = ['bind', 'System']

from collections.abc import Callable, Hashable, Iterable
from types import MappingProxyType, ModuleType
from typing import TYPE_CHECKING, Any, TypeAlias, TypeVar, overload

from pyriak import _SENTINEL
from pyriak.eventkey import key_functions


if TYPE_CHECKING:
  from pyriak.space import Space


_T = TypeVar('_T')
_R = TypeVar('_R')

_Callback: TypeAlias = Callable[['Space', _T], _R]


class _Binding:  #= public when expose event handlers
  __slots__ = 'priority', 'keys'

  def __init__(self, priority: Any, keys: frozenset[Hashable], /):
    self.priority = priority
    self.keys = keys


class _BindingWrapper:
  """Transitory object created by bind decorator."""

  __slots__ = '_callback_', '_bindings_'

  def __init__(
    self, callback: _Callback, bindings: dict[type, _Binding], /
  ):
    self._callback_ = callback
    self._bindings_ = bindings

  def __call__(self, /, *args, **kwargs):
    return self._callback_(*args, **kwargs)

  def __getattr__(self, name, /):
    return getattr(self._callback_, name)


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
    if not isinstance(callback, _BindingWrapper):
      return _BindingWrapper(callback, {event_type: _Binding(priority, keys)})
    bindings = callback._bindings_
    if event_type in bindings:
      raise ValueError(
        f'{event_type!r} is already bound to system event handler {callback._callback_!r}'
      )
    bindings[event_type] = _Binding(priority, keys)
    return callback
  return decorator


class _SystemInfo:
  """Transitory object for initializing a system.

  Currently, this holds no configuration in the System constructor.
  (may later include specific class to allow subclassing System)
  """

  __slots__ = ()

  def __init__(self, /):
    ...

  __hash__ = None  # type: ignore

  def __repr__(self, /):
    return '<unitialized system module>'

  def __getattribute__(self, name, /):
    raise RuntimeError(
      'cannot use uninitialized system (do not use _system_ in top-level code)'
    )


class System(ModuleType):
  """A singleton behaviour of a space.

  Holds basically no data (only constants and possibly caches).
  Systems are modules.
  Usage:
  In a module, set a top-level '_system_' variable to a call to System().
  After the entire module has been initialized (from an import),
  _system_ is set to the module but with its class changed to System.
  """

  _system_: 'System'  #= use 3.11 typing.Self
  _bindings_: MappingProxyType[str, MappingProxyType[type, _Binding]]

  def __new__(cls, /) -> 'System':  #= use self
    """Return a _SystemInfo for _system_ variable.

    The _SystemInfo instance will be used to initialize the module into a System.
    The _system_ variable will be set to the module after initialization.

    Warning: you must import/load pyriak before importing a system module,
    or the module will not be turned into a system.
    This means that a system run as the main file is not initialized automatically.
    """
    return _SystemInfo()  # type: ignore

  def __init__(self, /):
    raise TypeError(
      f'do not call __init__ method of {type(self)!r}, did you mean init?'
    )

  @classmethod
  def init(cls, module: ModuleType, /):
    system = module._system_
    if isinstance(module, System):
      raise RuntimeError(
        f'cannot apply system initialization on same module twice: {module!r}'
      )
    if not isinstance(system, _SystemInfo):
      raise TypeError(
        f'module _system_ should be a call to System(), not: {system!r}, in {module!r}'
      )
    bindings = {}
    for name, attr in module.__dict__.items():
      if not isinstance(attr, _SystemInfo) and isinstance(attr, _BindingWrapper):
        setattr(module, name, attr._callback_)
        bindings[name] = MappingProxyType(attr._bindings_)
    module.__class__ = cls
    assert isinstance(module, System)
    module._system_ = module
    module._bindings_ = MappingProxyType(bindings)
    return module

  def __repr__(self, /):
    return super().__repr__().replace('module', 'system', 1)

  @staticmethod
  def _added_(space: 'Space', /):
    """Automatically invoked with the manager's space passed in.

    Invoked right after self is added to the manager,
    but before SystemAdded event is triggered.
    Can be manually invoked if needed.
    Return value is not used by SystemManager.
    """

  @staticmethod
  def _removed_(space: 'Space', /):
    """Automatically invoked with the manager's space passed in.

    Invoked right after self is removed from the manager,
    but before SystemRemoved event is triggered.
    Can be manually invoked if needed.
    Return value is not used by SystemManager.
    """
