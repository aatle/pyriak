# pyriak

[![PyPI version](https://img.shields.io/pypi/v/pyriak?color=blue)](https://pypi.org/project/pyriak)
[![License](https://img.shields.io/pypi/l/pyriak.svg)](https://pypi.org/project/pyriak)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://github.com/python/mypy)
[![Linting: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Pyriak is a Python implementation of Entity Component System (ECS) architecture.


## Installation
```
pip install pyriak
```


## Introduction to ECS
ECS (entity component system) architecture is an alternative paradigm to OOP (object-oriented programming),
emphasizing composition and usually data-oriented design over traditional OOP concepts.
This can help with structuring complex programs, especially in game development.

For a more detailed introduction, there is good information at https://github.com/SanderMertens/ecs-faq.

### Objects
These are the three standard parts of most ECS designs:\
**Entity** - A general-purpose object of the program, represented as a collection of components\
**Component** - A data object representing one characteristic of an entity, e.g. position\
**System** - Manipulates specific components of entities to do the functionality of one behavior, e.g. rendering\
\
pyriak includes two more things as part of its design:\
**State** - A data object for an aspect of the whole program; a global component\
**Event** - A signal object for communicating among systems and controlling the program's flow\
\
Additionally, there are helper container classes to manage these objects.\
**Manager** - A collection of either entities, systems, or states that exposes operations to manipulate its elements\
**Event queue** - A global queue of events shared among all systems\
**Space** - Represents a standalone program, encapsulating its data and behavior. Holds the managers and event queue

#### pyriak implementations
The following are how the above terms are implemented in pyriak.
- entity: `Entity` class, containing a unique entity ID and a set of components referenced by class
- system: a module object with event handlers and functions defined on it, static and holds no data
- component, event, state: user-defined classes containing mostly data and little behavior
  - akin to a struct in other languages. The `dataclasses` module and other similar utilities are useful for defining these
- managers:
  - `EntityManager`: a set of entities referenced by their ID, with querying operations available
  - `SystemManager`: a set of system objects, can process events by invoking the relevant event handlers
  - `StateManager`: a set of states referenced by their class, akin to an entity
- space: `Space` class, with attributes `.entities`, `.systems`, and `.states` for the managers, and `.event_queue`
- event queue: a `collections.deque` by default, attached to the space

## Usage
In your main module, create a `Space` instance.\
With no arguments to `Space()`, the managers and the event queue are created automatically.
```py
# main.py
from pyriak import Space

space = Space()
```

Now, create new modules for some systems. Then import and add them to the space.\
It's important to not forget to add systems, as otherwise their event handlers will never be invoked.
```py
# main.py
from pyriak import Space

from . import game_loop, physics, render

space = Space()
space.systems.add(game_loop, physics, render)
```

In another module, declare some events.
```py
# events.py
class UpdateGame:
    def __init__(self, dt: float) -> None:
        self.dt = dt

class RenderGame:
    pass

class StartGame:
    pass

...
```

In each system, add event handlers using the `@bind(event_type, priority)` decorator.\
The handler callback takes arguments `space` and `event`.
```py
# game_loop.py
from pyriak import Space, bind

from . import events

@bind(events.StartGame, 0)
def run_game_loop(space: Space, event: events.StartGame) -> None:
    while True:
        pass
```
Events can be either *processed* or *posted*, using the space.\
Processing an event invokes all event handlers in the space with a matching event type, sorted by priority.

Posting an event puts it in the space's event queue to later be processed.\
From anywhere in the program, `space.pump()` takes out events from the queue and processes them, in a loop.\
`space.pump()` runs until the event queue is empty. Alternatively, `space.pump(n)` runs for `n` iterations.\
Note that more events may be added to the event queue while `space.pump()` is running.
```py
# game_loop.py
...

@bind(events.StartGame, 0)
def run_game_loop(space: Space, event: events.StartGame) -> None:
    while True:
        space.post(events.UpdateGame())  # Add event to event queue
        space.pump()  # Process from event queue until all queued events have been processed
        space.post(events.RenderGame())
        space.pump()
```

States are useful for holding data for systems since systems shouldn't store any data.\
For example, a `Time` state could store the time.\
Then, a `game_time` system can update the `Time` state. But first, the state must be *added* to the space, using `space.states.add(*states)`.\
The best place to do this is in the optional, special `_added_(space)` callback on the system, invoked when the system is added to the manager.
```py
# game_time.py
from pyriak import Space, bind

from . import events, states

def _added_(space: Space) -> None:
    time = states.Time()
    # Add the Time state to the space
    space.states.add(time)
```
To access a state from the `StateManager` (or a component from an entity), use its type like a mapping key on the manager.
```py
# game_time.py
...

@bind(events.UpdateGame, 100)
def update_time(space: Space, event: events.UpdateGame) -> None:
    # Get the Time state
    time = space.states[states.Time]
    # Update the Time state
    time.elapsed += event.dt
    time.frame_count += 1

def _removed_(space: Space) -> None:
    # Remove the Time state when the system is removed from the space
    del space.states[states.Time]
```
Now it's time for entities.\
Define component classes for aspects of the objects that will be in your program.\
Some classes don't even need to hold data: it's presence on the entity serves as a marker, or 'tag'.
```python
# components.py
from dataclasses import dataclass

@dataclass
class Position:
    x: float
    y: float

class Player:
    pass

...
```
Entities can be created with the `Entity(components)` constructor. They must be added to the space with `space.entities.add(*entities)`.\
However, it is preferable to use `space.entities.create(*components)`, which adds it to the space automatically.
```python
# world.py
from pyriak import Entity, Space

from .components import *

def _added_(space: Space) -> None:
    enemy = Entity([Position(50.0, 0.0), Health(40)])
    space.entities.add(enemy)
    player = space.entities.create(Position(0.0, 0.0), Health(100), Player())
```
Systems operate on their specific components in bulk.\
To access batches of components, use the `space.entities.query(*component_types)` method, which takes any number of component types as arguments.\
This will select all entities in the space that contain every component type passed in, and return an query result object.\
This object has methods such as `.zip()`, which gives an iterator of the tuple of components for each entity.
E.g.,
```py
list(space.entities.query(Spam, Eggs, Foo).zip()) --> [  # for every entity with all three components
    (Spam(5), Eggs("a"), Foo()),  # components from first entity
    (Spam(1), Eggs("b"), Foo()),  # components from second entity
    ...
]
```
Used in an event handler, it would look something like this:
```py
# physics.py
...

@bind(events.UpdateGame, 500)
def update_physics(space: Space, event: events.UpdateGame) -> None:
    for position, velocity in space.entities.query(
        components.Position, components.Velocity
    ).zip():
        position.x += velocity.x * event.dt
        position.y += velocity.y * event.dt
```
Those are all of the core features of pyriak.


## When to use pyriak?
It may seem like a tedious and convoluted way of doing things, with all of the declarations and split code.\
However, for a larger, more complicated project, it is much more flexible and scalable.

In an OOP game, a common problem is that a base class (e.g. `GameObject`) may become bloated with optional features, as subclasses share some behavior but not all. Inheritance is often fragile or inflexible.
High coupling and low cohesion can become difficult to avoid.

In a game made with pyriak, coupling is very low because systems only interact with exactly what data they require, and cohesion is high because systems, components, states, and events are small and focused.\
The separation of data from logic also comes with its own benefits.

pyriak focuses on development speed, ease of use, and structure
rather than performance, aligning with the principles of python.
Unlike many ECS implementations, it does not offer performance gains because data locality is nonexistent in pure python.

In short, this package is mainly intended for complex, interconnected programs, especially games.
For small programs with simple mechanics or not many moving parts, ECS is probably overkill and can be slower to write.


## Installing from source
Pyriak has no package dependencies, and its source is entirely python.
The source can be installed and used without any building or set-up.
```
pip install -U git+https://github.com/aatle/pyriak.git
```


## Help
Currently, all available resources are in the [pyriak GitHub repo](https://github.com/aatle/pyriak).
Create an issue if there are any concerns or problems.\
There is no external documentation; see docstrings for information.
In the future, an example program may be available.
