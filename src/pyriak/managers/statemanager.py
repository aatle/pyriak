__all__ = ['StateManager']

from collections.abc import Iterable
from typing import TypeVar, overload

from pyriak import _SENTINEL, EventQueue
from pyriak.events import StateAdded, StateRemoved


_T = TypeVar('_T')
_D = TypeVar('_D')


class StateManager:
  """

  StateManager structure is very similar to an Entity.
  """

  __slots__ = '_states', 'event_queue', '__weakref__'

  def __init__(
    self, states: Iterable[object] = (), /, event_queue: EventQueue | None = None
  ):
    self.event_queue = event_queue
    self._states: dict[type, object] = {}
    self.add(*states)

  def add(self, *states: object) -> None:
    self_states = self._states
    event_queue = self.event_queue
    for state in states:
      state_type = type(state)
      if state_type in self_states:
        other_state = self_states[state_type]
        if other_state is state or other_state == state:
          continue
        if event_queue is not None:
          event_queue.append(StateRemoved(other_state))
      self_states[state_type] = state
      if event_queue is not None:
        event_queue.append(StateAdded(state))

  def remove(self, *states: object) -> None:
    self_states = self._states
    event_queue = self.event_queue
    for state in states:
      state_type = type(state)
      try:
        other_state = self_states[state_type]
      except KeyError:
        pass
      else:
        if other_state is state or other_state == state:
          del self_states[state_type]
          if event_queue is not None:
            event_queue.append(StateRemoved(other_state))
          continue
      raise ValueError(state)

  def __getitem__(self, state_type: type[_T], /) -> _T:
    return self._states[state_type]  # type: ignore[return-value]

  def __delitem__(self, state_type: type, /):
    self.remove(self[state_type])

  @overload
  def get(self, state_type: type[_T], /) -> _T | None: ...
  @overload
  def get(self, state_type: type[_T], default: _D, /) -> _T | _D: ...
  def get(self, state_type, default=None, /):
    return self._states.get(state_type, default)

  @overload
  def pop(self, state_type: type[_T], /) -> _T: ...
  @overload
  def pop(self, state_type: type[_T], default: _D, /) -> _T | _D: ...
  def pop(self, state_type, default=_SENTINEL, /):
    try:
      state = self[state_type]
    except KeyError:
      if default is _SENTINEL:
        raise
      return default
    self.remove(state)
    return state

  def types(self):
    return self._states.keys()

  def __iter__(self):
    return iter(self._states.values())

  def __reversed__(self):
    return reversed(self._states.values())

  def __len__(self):
    return len(self._states)

  def __contains__(self, obj: object, /):
    return obj in self._states

  def clear(self) -> None:
    self.remove(*self)
