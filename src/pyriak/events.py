__all__ = [
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

from collections.abc import Hashable
from typing import TYPE_CHECKING, Any

from pyriak.eventkey import set_key as _set_key


if TYPE_CHECKING:
  from pyriak import System
  from pyriak.bind import _Callback
  from pyriak.entity import Entity
  from pyriak.managers.systemmanager import _EventHandler


class EntityAdded:
  def __init__(self, entity: 'Entity'):
    self.entity = entity

class EntityRemoved:
  def __init__(self, entity: 'Entity'):
    self.entity = entity


def _component_type_key(event: 'ComponentAdded | ComponentRemoved') -> type:
  return type(event.component)

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


def _state_type_key(event: 'StateAdded | StateRemoved') -> type:
  return type(event.state)

@_set_key(_state_type_key)
class StateAdded:
  def __init__(self, state: object):
    self.state = state

@_set_key(_state_type_key)
class StateRemoved:
  def __init__(self, state: object):
    self.state = state


def _handler_key(event: 'EventHandlerAdded | EventHandlerRemoved') -> type:
  return event.event_type

@_set_key(_handler_key)
class EventHandlerAdded:
  def __init__(
    self, _handler: '_EventHandler', _event_type: type, _keys: frozenset[Hashable]
  ):
    self._handler = _handler
    self.event_type = _event_type
    self.keys = _keys

  @property
  def system(self):
    return self._handler.system

  @property
  def callback(self):
    return self._handler.callback

  @property
  def name(self):
    return self._handler.name

  @property
  def priority(self):
    return self._handler.priority

  @property
  def key(self):
    [key] = self.keys
    return key

@_set_key(_handler_key)
class EventHandlerRemoved:
  def __init__(
    self, _system: 'System', _callback: '_Callback', _name: str, _priority: Any,
    _event_type: type, _keys: frozenset[Hashable]
  ):
    self.system = _system
    self.callback = _callback
    self.name = _name
    self.priority = _priority
    self.event_type = _event_type
    self.keys = _keys

  @property
  def key(self):
    [key] = self.keys
    return key
