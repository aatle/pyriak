__all__ = ['Space']

from collections import deque
from collections.abc import Callable
from typing import Any, NoReturn, overload

from pyriak import EventQueue, managers
from pyriak.query import ComponentQueryResult, EntityQueryResult, IdQueryResult, Query


class Space:
  __slots__ = 'systems', 'entities', 'states', '_event_queue', '__weakref__'

  def __init__(
    self, *,
    systems: managers.SystemManager = ...,
    entities: managers.EntityManager = ...,
    states: managers.StateManager = ...,
    event_queue: EventQueue = ...
  ):
    """A new Space instance, which glues together the managers and the event queue.

    By default, creates the EntityManager, StateManager, and SystemManager.
    """
    if systems is Ellipsis:
      systems = managers.SystemManager()
      systems.space = self
    self.systems = systems
    if entities is Ellipsis:
      entities = managers.EntityManager()
    self.entities = entities
    if states is Ellipsis:
      states = managers.StateManager()
    self.states = states
    if event_queue is Ellipsis:
      event_queue = deque()
    self.event_queue = event_queue

  @property
  def event_queue(self) -> EventQueue:
    return self._event_queue

  @event_queue.setter
  def event_queue(self, value: EventQueue):
    self._event_queue = value
    if self.entities is not None:
      self.entities.event_queue = value
    if self.states is not None:
      self.states.event_queue = value

  @event_queue.deleter
  def event_queue(self):
    del self._event_queue

  @overload
  def query(self, query: Query, /) -> ComponentQueryResult: ...
  @overload
  def query(
    self, /, *, merge: Callable[..., set] = set.intersection,
  ) -> NoReturn: ...
  @overload
  def query(
    self, /,
    *component_types: type,
    merge: Callable[..., set] = set.intersection,
  ) -> ComponentQueryResult: ...
  def query(self, /, *types, merge=...):
    return self.entities.query(*types, merge=merge)

  @overload
  def entity_query(self, query: Query, /) -> EntityQueryResult: ...
  @overload
  def entity_query(
    self, /, *, merge: Callable[..., set] = set.intersection,
  ) -> NoReturn: ...
  @overload
  def entity_query(
    self, /,
    *component_types: type,
    merge: Callable[..., set] = set.intersection,
  ) -> EntityQueryResult: ...
  def entity_query(self, /, *types, merge=...):
    return self.entities.entity_query(*types, merge=merge)

  @overload
  def id_query(self, query: Query, /) -> IdQueryResult: ...
  @overload
  def id_query(
    self, /, *, merge: Callable[..., set] = set.intersection,
  ) -> NoReturn: ...
  @overload
  def id_query(
    self, /,
    *component_types: type,
    merge: Callable[..., set] = set.intersection,
  ) -> IdQueryResult: ...
  def id_query(self, /, *types, merge=...):
    return self.entities.id_query(*types, merge=merge)

  def process(self, event: Any):
    return self.systems.process(event, space=self)

  def post(self, *events: Any) -> None:
    self.event_queue.extend(events)

  def pump(self, events: int | None = None) -> int:
    process_event = self.process
    queue = self.event_queue
    if isinstance(queue, deque):
      pop = queue.popleft
    else:
      def pop():
        return queue.pop(0)
    i = -1
    if events is None:
      while queue:
        i += 1
        process_event(pop())
    else:
      for i in range(events):
        if not queue:
          return i
        process_event(pop())
    return i + 1
