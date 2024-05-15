__all__ = ['Space']

from collections import deque
from collections.abc import Callable
from typing import NoReturn, overload

from pyriak import EventQueue, managers
from pyriak.query import ComponentQueryResult, EntityQueryResult, IdQueryResult, Query


class Space:
  __slots__ = 'systems', 'entities', 'states', 'event_queue', '__weakref__'

  _event_queue: EventQueue

  def __init__(
    self, *,
    systems: managers.SystemManager | None = None,
    entities: managers.EntityManager | None = None,
    states: managers.StateManager | None = None,
    event_queue: EventQueue | None = None
  ):
    """A new Space instance, which glues together the managers and the event queue.

    By default, creates the EntityManager, StateManager, and SystemManager.
    """
    if systems is None:
      systems = managers.SystemManager()
      systems.space = self
    if entities is None:
      entities = managers.EntityManager()
    if states is None:
      states = managers.StateManager()
    if event_queue is None:
      event_queue = deque()
    self.systems = systems
    self.entities = entities
    self.states = states
    self.event_queue = event_queue
    systems.event_queue = entities.event_queue = states.event_queue = event_queue

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
  def query(self, /, *types, merge=None):
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
  def entity_query(self, /, *types, merge=None):
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
  def id_query(self, /, *types, merge=None):
    return self.entities.id_query(*types, merge=merge)

  def process(self, event: object):
    return self.systems.process(event, space=self)

  def post(self, *events: object) -> None:
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
