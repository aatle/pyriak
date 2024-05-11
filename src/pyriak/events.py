__all__ = [
  'SpaceCallback',
  'SendEvent',
  'ComponentAdded',
  'ComponentRemoved',
  'EntityAdded',
  'EntityRemoved',
  'SystemAdded',
  'SystemRemoved',
  'EventHandlerAdded',
  'EventHandlerRemoved',
  'StateAdded',
  'StateRemoved',
]

from collections.abc import Callable, Hashable, Iterator
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pyriak import (
  NoKey as _NoKey,
  set_key as _set_key,
  subclasses as _subclasses,
)


if TYPE_CHECKING:
  from pyriak import Entity, Space, System
  from pyriak.managers.systemmanager import _EventHandler


_T = TypeVar('_T')


class SpaceCallback(Generic[_T]):
  """A SystemManager automatically calls a SpaceCallback Event when it processes one."""

  # TODO: python 3.11 - callback: Callable[[Space, *_Ts], _T]

  def __init__(self, callback: Callable[..., _T], /, *args: Any, **kwargs: Any):
    self.callback = callback
    self.args = list(args)
    self.kwargs = kwargs

  def __call__(self, space: Space, /) -> _T:
    """Execute self's callback with self's args and kwargs."""
    return self.callback(space, *self.args, **self.kwargs)


class SendEvent:
  """A special built-in Event type for sending Events to specific System(s).

  A SendEvent is basically a wrapper of another Event.
  When a SendEvent is triggered by a SystemManager, only the SendEvent's receivers
  receive the wrapped Event, if they can.

  If a receiver can't receive the Event, it is skipped.
  This can happen if:
  - the system is not in the system manager
  - the system does not have a callback bind to that event type
  Triggering may be slow if the wrapped Event has a lot of binds in the SystemManager.

  The order in which the bound callbacks of the receivers are invoked
  is no different from normal Event triggering,
  where higher priority callbacks are called first.

  The actual SendEvent instance itself is never processed.
  """

  def __init__(self, event: object, *receivers: 'System'):
    self.event = event
    self.receivers = set(receivers)


def _component_type_key(event: 'ComponentAdded | ComponentRemoved') -> Iterator[type]:
  yield from type(event.component).__mro__

@_set_key(_component_type_key)
class ComponentAdded:
  def __init__(self, entity: 'Entity', component: object):
    self.entity = entity
    self.component = component

@_set_key(_component_type_key)
class ComponentRemoved:
  def __init__(self, entity: 'Entity', component: object):
    self.entity = entity
    self.component = component


class EntityAdded:
  def __init__(self, entity: 'Entity'):
    self.entity = entity

class EntityRemoved:
  def __init__(self, entity: 'Entity'):
    self.entity = entity


def _system_key(event: 'SystemAdded | SystemRemoved') -> 'System':
  return event.system

@_set_key(_system_key)
class SystemAdded:
  def __init__(self, system: 'System'):
    self.system = system

@_set_key(_system_key)
class SystemRemoved:
  def __init__(self, system: 'System'):
    self.system = system


def _handler_key(event: '_EventHandlerEvent') -> Iterator[type]:
  yield from _subclasses(event.event_type)

@_set_key(_handler_key)
class _EventHandlerEvent:
  def __init__(
    self, handler: '_EventHandler', event_type: type, keys: frozenset[Hashable]
  ):
    self._handler = handler
    self._event_type = event_type
    self._keys = keys

  @property
  def event_type(self):
    return self._event_type

  @property
  def callback(self):
    return self._handler.callback

  @property
  def system(self):
    return self._handler.system

  @property
  def priority(self):
    return self._handler.priority

  @property
  def name(self):
    return self._handler.name

  @property
  def keys(self):
    return self._keys

  @property
  def key(self):
    keys = self.keys
    if not keys:
      return _NoKey
    [key] = keys
    return key

class EventHandlerAdded(_EventHandlerEvent):
  pass

class EventHandlerRemoved(_EventHandlerEvent):
  pass


def _state_type_key(event: 'StateAdded | StateRemoved') -> Iterator[type]:
  yield from type(event.state).__mro__

@_set_key(_state_type_key)
class StateAdded:
  def __init__(self, state: object):
    self.state = state

@_set_key(_state_type_key)
class StateRemoved:
  def __init__(self, state: object):
    self.state = state
