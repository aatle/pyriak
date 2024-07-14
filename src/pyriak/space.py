"""This module implements the Space class."""

__all__ = ['Space']

from collections import deque
from collections.abc import Callable

from pyriak import EventQueue, managers
from pyriak.managers.entitymanager import QueryResult


class Space:
  """An encapsulation of a standalone program.

  A Space glues together the three managers into
  a single object that represents the entire program.
  It also has a central event queue that controls the flow of the program.

  As this object contains everything, it can be used to access any needed data,
  and is useful to pass as an argument into a function to allow it to
  read or change the program state.

  A Space does not implement anything on its own. Instead, it serves as a
  bundle for the behavior (systems), data (entities and states), and
  communication (events).

  Attributes:
    event_queue: A mutable sequence that holds events to be processed.
    systems: A SystemManager, holds the systems of the space.
    entities: An EntityManager, holds the entities of the space.
    states: A StateManager, holds the states of the space.
  """

  __slots__ = 'event_queue', 'systems', 'entities', 'states', '__weakref__'

  def __init__(
    self, *,
    event_queue: EventQueue | None = None,
    systems: managers.SystemManager | None = None,
    entities: managers.EntityManager | None = None,
    states: managers.StateManager | None = None,
  ):
    """Initialize the Space with the managers and event queue.

    By default (or when None is given as the argument), instantiates
    an empty deque for the event queue, and creates the managers.

    The managers' event_queue attributes are set to the space's
    event queue. The SystemManager's space attribute is set to self.

    Args:
      event_queue: The Space's event queue. Defaults to a creating a new deque.
      systems: The Space's SystemManager. Defaults to creating one.
      entities: The Space's EntityManager. Defaults to creating one.
      states: The Space's StateManager. Defaults to creating one.
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
    """Get bulk entity and component data from self's entities.

    Syntactic sugar for self.entities.query().
    For more details and specifics, see documentation of EntityManager.query().

    Args:
      *component_types: The types that are used to generate the set of entities.
      merge: The set merge function used to combine the sets of ids into one.

    Returns:
      A readonly QueryResult object that contains the data and info of the query.

    Raises:
      TypeError: If exactly zero component types were given.

    Example:
      Typical usage of query() method::

        for sprite, position in space.query(Sprite, Position).zip():
          render(sprite, position)
    """
    return self.entities.query(*component_types, merge=merge)

  def process(self, event: object, /) -> bool:
    """Syntactic sugar for self.systems.process().

    ...
    """
    return self.systems.process(event)

  def post(self, *events: object) -> None:
    """Append an event or events to the end of self's event queue.

    Args:
      *events: The events to be posted to the event queue.
    """
    self.event_queue.extend(events)

  def pump(self, events: int | None = None, /) -> int:
    """Pop and process events from self's event queue.

    For the given number of times, or until the event queue is empty,
    events are popped from the front of the event queue and then processed.
    (The event queue can still get new events while this method is running.)

    The number of times defaults to None (infinite), meaning it will
    only stop when the event queue is empty.

    pump() is safe to be called recursively/nested.

    The return value is the actual number of events processed, which is
    less than or equal to the number passed in.
    It is 0 if and only if the event queue was already empty when pump()
    was called and there are no more events left to process.

    Args:
      events: The max number of events to process. Defaults to None (infinite).

    Returns:
      The number of events actually popped from the event queue and processed.
    """
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
