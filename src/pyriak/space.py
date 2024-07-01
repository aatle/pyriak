__all__ = ['Space']

from collections import deque
from collections.abc import Callable

from pyriak import EventQueue, QueryResult, managers


class Space:
  __slots__ = 'event_queue', 'systems', 'entities', 'states', '__weakref__'

  def __init__(
    self, *,
    event_queue: EventQueue | None = None,
    systems: managers.SystemManager | None = None,
    entities: managers.EntityManager | None = None,
    states: managers.StateManager | None = None,
  ):
    """A new Space instance, which glues together the managers and the event queue.

    By default, creates the EntityManager, StateManager, and SystemManager.
    """
    if event_queue is None:
      event_queue = deque()
    self.event_queue = event_queue
    if systems is None:
      systems = managers.SystemManager()
    self.systems = systems
    systems.space = self
    systems.event_queue = event_queue
    if entities is None:
      entities = managers.EntityManager()
    self.entities = entities
    entities.event_queue = event_queue
    if states is None:
      states = managers.StateManager()
    self.states = states
    states.event_queue = event_queue

  def query(
    self, /, *component_types: type, merge: Callable[..., set] = set.intersection
  ) -> QueryResult:
    return self.entities.query(*component_types, merge=merge)

  def process(self, event: object) -> bool:
    return self.systems.process(event)

  def post(self, *events: object) -> None:
    self.event_queue.extend(events)

  def pump(self, events: int | None = None) -> int:
    process_event = self.process
    queue = self.event_queue
    pop = queue.popleft if isinstance(queue, deque) else lambda: queue.pop(0)
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
