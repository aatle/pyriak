# pyriak

[![PyPI version](https://img.shields.io/pypi/v/pyriak?color=blue)](https://pypi.org/project/pyriak)
[![License](https://img.shields.io/pypi/l/pyriak.svg)](https://pypi.org/project/pyriak)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://github.com/python/mypy)
[![Linting: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Pyriak is a lightweight Python implementation of Entity Component System (ECS) architecture.

ECS is an alternative paradigm to object-oriented programming,
emphasizing composition and data oriented design.
This can help with structuring complex programs, especially in game development.


## Installation
```
pip install pyriak
```


## ECS implementation
There are many different styles of ECS depending on its goals.

This implementation focuses on development speed, ease of use, and architecture,
rather than performance, aligning with the principles of python.

- Entities are concrete component containers that have an ID.
  - Components can be any object, and do not reference their entity.
- Systems are collections of event handlers, and are typically
  implemented as modules with functions.
- Event handlers are the main control flow, invoked by processing events.
  - Events can be any object, and are put in the event queue
    or processed immediately.
- All resources are added to managers, and these managers are joined
  together with a Space object.
- For convenience, there is an entity-like manager that contains states,
  which are essentially global or singleton components.


## Usage
In your main file, create a `Space` instance. It will encapsulate the majority of the program. With no arguments, the managers are created automatically.\
The three managers are `space.systems`, `space.entities`, and `space.states`. The `Space` also has an event queue object, `space.event_queue`.
```python
# main.py
from pyriak import Space

space = Space()
```

The raw data is stored as components, states, and events. For these objects, define small classes with miminal functionality/code, comparable to structs in other languages.\
`dataclasses` and similar packages or modules are especially convenient for writing these.
```python
@dataclass
class Health:
    max_value: float
    value: float = 0.0
```
Entities hold the components, and can be created with the entity manager's `create()` method, or manually with the constructor (must be added to the manager).\
It is not a good idea to hold direct entity references within components or states. Each entity has a unique `.id` attribute that should be used as a stored reference instead.
```python
enemy = Entity([Health(50.0)])
space.entities.add(enemy)

player = space.entities.create(Health(100.0))
enemy.add(Target(player.id))
```

Components and states can be accessed through their owner with square bracket (subscript) notation, with the class of the component or state, like a mapping.
For entities, their id is used.
```python
enemy[Health].value -= 20.5
total_seconds = space.states[Time].elapsed
del entity[Sprite]
del space.entities[enemy.id]
```

Systems, which hold the logic and behavior, are most often implemented as module objects with functions (the module itself is the system).\
When an event is processed, the relevant event handlers of the space are called automatically. In a system module, import the `bind()` decorator from pyriak. Define a module-level function as an event handler callback and decorate it with a call to `bind()`, with the arguments being the event type (class object) and handler priority.
The callback takes arguments `space` and `event`. (The name of the function is not used.)
```python
# game_loop.py
@bind(InitializeGame, 100)
def run(space: Space, event: InitializeGame):
    pass
```
Most event handlers should not return anything (return None).\
The handler priority is any object that can be compared, such as an `int` instance. The priority determines the order in which handlers for the same event type are invoked, with higher priority handlers being first.

The space processes events in two main ways:
- Call `space.process(event)`, with the event as argument. This calls the event handlers immediately, so the program will not resume until the handlers are done.
- Put the event in the space's event queue, usually with `space.post(event)`. Then, take and process events from the queue with `space.pump()`.
  - `space.pump()`, with no arguments, consumes events from the queue until it is empty. Note that more events may be posted during it.
Which method to use depends on if behavior needs to execute immediately (synchronous), or can be deferred (asynchronous).
```python
# game_loop.py
@bind(InitializeGame, 100)
def run(space: Space, event: InitializeGame):
    while not space.states[GameLoop].stop_game:
        space.post(UpdateGame(dt))
        space.pump()
        space.post(RenderGame())
        space.pump()
```

For the handlers of a system to work, the system **must** be added to the space's `SystemManager`.
Forgetting to add a new system after writing it is a common mistake.\
Import the system module and add it to `space.systems`.
```python
# main.py
from systems import game_loop
...
space.systems.add(game_loop)
```

Systems may optionally define callbacks `_added_()` and `_removed_()` that are invoked when the system is added to or removed from a `SystemManager`.\
The return value is ignored.
```python
# game_loop.py
def _added_(space: Space):
    space.states.add(states.GameLoop(FPS))
```

In ECS, systems need to access components in bulk. This can be done with the `space.query()` method, which takes any number of component types as arguments.
The return value is an object with methods to access the data, such as `.zip()`.
```python
@bind(events.UpdateGame)
def update_physics(space: Space, event: events.UpdateGame)
    for position, velocity, acceleration in space.query(
      components.Position, components.Velocity, components.Acceleration
    ).zip():
        velocity += acceleration
        position += velocity
```

Those are all of the basic features needed to write a program with pyriak.


## When to use pyriak?
This package is only intended for complex, interconnected programs, especially games, which could benefit from events and data/logic separation.
Since pyriak is written in python, it does not offer any performance benefits over other paradigms.
For small programs with not many moving parts, ECS is overkill and can be slower to write.


## Installing from source
Pyriak has no package dependencies, and its source is entirely python.
The source can be installed and used, without any building or set-up.
```
pip install -U git+https://github.com/aatle/pyriak.git
```


## Help
Currently, all available resources are in the [pyriak GitHub repo](https://github.com/aatle/pyriak).
Create an issue if there are any concerns or problems.\
There is no external documentation; see docstrings for information.
In the future, an example program may be available.
