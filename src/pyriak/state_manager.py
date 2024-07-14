"""This module implements the StateManager class."""

__all__ = ['StateManager']

from collections.abc import Iterable
from typing import TypeVar, overload

from pyriak import _SENTINEL, EventQueue
from pyriak.events import StateAdded, StateRemoved


_T = TypeVar('_T')
_D = TypeVar('_D')


class StateManager:
  """A manager and container of states.

  All objects are valid states.

  The StateManager can be thought of as the program's dedicated Entity
  instance, where global and unique data can be put, e.g. global time.
  A common use is a system storing data in a state that it 'owns',
  as systems are not allowed to have any mutable data themselves.

  The general purpose of the StateManager is to provide storage for data
  that does not make sense to have multiple of, nor put in an entity.

  The StateManager is owned directly by the Space.
  There is usually only one, accessible via the Space's 'states' attribute.

  In many aspects, StateManager is identical to Entity.
  Like Entity, the structure of StateManager is akin to a set of states mixed
  with a dict of state types to states. States don't need to be hashable.

  Attributes:
    event_queue: The optional event queue that the StateManager may post to.
      This is usually assigned the space's event queue.
  """

  __slots__ = '_states', 'event_queue', '__weakref__'

  def __init__(
    self, states: Iterable[object] = (), /, event_queue: EventQueue | None = None
  ):
    """Initialize the StateManager with the given states and event queue.

    By default, the StateManager is initialized with no states and
    event queue as None.

    Args:
      states: The iterable of initial states. Defaults to no states.
      event_queue: The event queue to post to. Defaults to None.
    """
    self.event_queue = event_queue
    self._states: dict[type, object] = {}
    self.add(*states)

  def add(self, *states: object) -> None:
    """Add an arbitrary number of states to self.

    Each state is stored by its class.

    If self already has an existing state of the exact same type, that
    existing state is removed right before adding the provided state.
    This is unless the two states are equivalent or the same object,
    in which case the provided state is skipped without posting events.

    If self's event queue is not None, each state added and removed
    generates a StateAdded and StateRemoved event, respectively.

    Args:
      *states: The states to be added.
    """
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
    """Remove an arbitrary number of states from self.

    For each provided state, an existing state in self of
    the exact same type is removed. The existing state must
    be equivalent or the same object as the provided state.

    If no such state is found in self, an exception is raised,
    preventing the rest of the states from being removed
    but not affecting the states already removed.

    If self's event queue is not None, a StateRemoved event is
    posted for each state removed.

    Args:
      *states: The states to be removed.

    Raises:
      ValueError: If one of the states is not found in self.
    """
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
