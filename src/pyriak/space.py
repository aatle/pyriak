"""This module implements the Space class."""

__all__ = ["Space"]

from collections import deque

from pyriak import EventQueue
from pyriak.entity_manager import EntityManager
from pyriak.state_manager import StateManager
from pyriak.system_manager import SystemManager


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

    __slots__ = "event_queue", "systems", "entities", "states", "__weakref__"

    def __init__(
        self,
        *,
        event_queue: EventQueue | None = None,
        systems: SystemManager | None = None,
        entities: EntityManager | None = None,
        states: StateManager | None = None,
    ) -> None:
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
            systems = SystemManager()
        self.systems = systems
        systems.space = self
        systems.event_queue = event_queue
        if entities is None:
            entities = EntityManager()
        self.entities = entities
        entities.event_queue = event_queue
        if states is None:
            states = StateManager()
        self.states = states
        states.event_queue = event_queue

    def process(self, event: object, /) -> bool:
        """Immediately invoke event handlers for an event.

        Syntactic sugar for self.systems.process().
        See SystemManager.process() documentation for more details.

        The difference between process() and post() is that process()
        is synchronous and blocks until the event has been processed,
        while post() is asynchronous, deferring the event to the event queue
        to eventually be processed.
        Since post() only puts events on a queue, it is non-blocking.

        Args:
            event: The event to process.

        Returns:
            True if event processing was stopped by a callback, False otherwise.

        Raises:
            RuntimeError: If the SystemManager's space is None or deleted.
        """
        return self.systems.process(event)

    def post(self, event: object, /) -> None:
        """Append an event to the end of self's event queue.

        Args:
            event: The event to be posted to the event queue.
        """
        self.event_queue.append(event)

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
        It is 0 if the event queue was already empty when pump()
        was called and there are no more events left to process.

        Args:
            events: The max number of events to process. Defaults to None (infinite).

        Returns:
            The number of events actually popped from the event queue and processed.
        """
        queue = self.event_queue
        pop = queue.popleft if isinstance(queue, deque) else lambda: queue.pop(0)
        i = 0
        while queue and (events is None or i < events):
            self.process(pop())
            i += 1
        return i
