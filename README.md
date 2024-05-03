# pyriak
A lightweight implementation of Entity Component System architecture for Python.

Originally created August 2, 2022


ECS Implementation:

types -
- Space
- Managers
- Systems
- Entities
- Components (any)
- Events (any)
- States (any)

Rules:

- All data is contained within Entities and their Components, and States

- Entities hold:
  - Any number of Components (Component types must be unique)
  - A single entity ID, guaranteed unique in the entity's lifetime

- Components hold:
  - Data
  - Some simple methods (can only affect self's data)
    - Getter, Setter, Deleter methods
    - Data interpretation methods
    - Data manipulation methods
- A Component can only have one existing owner Entity at any given time
- A Component can only be directly stored long term in an Entity

- The Game holds:
  - One SystemManager
  - One EntityManager
  - Ideally, NOTHING else

- Systems hold:
  - Behavior, scripts
- Systems query the EntityManager for Entities,
  which hold the components the systems work on




Possible extensions:
- system concurrency by declaring the component types the systems read/write with
- entity pool


TO DO:
- change SpaceCallback call signature
- 'take_first' merge function `lambda *sets: sets[0]`
- fix ellipsis kwarg typing
- use mypy typecheck

- dynamic handlers?
- 3.11 typing features
- fix multibinding typing
- check set_key typing
- convert _bindings_ to EventHandler dict keys
- system "new" method instantiation
- __future__.annotations
- type aliases
- possibly entity, stmgr getitem iterable
- 'direct', 'indirect', 'strict', 'immediate' vocab docs
- validate subclasses: hash, mro
- sys mgr expose handlers + bind predicate/filter + _Binding public
- __contains__ TypeError raise?
- picklable __setstate__ __getstate__ __copy__ classes
- 'processor' game pump generator yield event method, 'event loop'
- discard method
- possibly entity and statemanager base class (better for user subclassing)
- keys method (for dict protocol)
- improve error messages
- raise from None bad
- views, items methods: mappingproxy
- __eq__, remove __hash__: mgrs
- types(*types) method functionality all mgrs+entity ?
- entities from ids: itertools helpers in entitymgr
- 'add', 'remove' methods return value
- entity mgr garbage collection behavior (currently undefined?)
- game __call__ use ?
- more container (set) dunder methods, operations
- copy methods
- more positional only arguments
- more system config
- str and repr methods all
- place documentation in code, along with all rules (style guide first)
- optimization through profiling, scalene (in a game)
- for optimization: consider cython
- make imported module variables private (consistency)
- python version lower in poetry dependencies ? find min python version
- pyright generator issue (overloads)
- review and rewrite readme.txt



System naming convention:
Systems are modules. Use snake_case because they are often accessed through attribute notation.
The name should describe the system's purpose or feature, either managing or controlling something, e.g.:
display.py controls Display state,
camera.py controls Camera state
but if it does not control any data, then it should be describing the action it does or thing it does
initialize.py
exit.py
camera_shake.py



NOTES:

More of an 'ECSSE' engine: Entity, Component, System, State, Event

Event processing:
+- All subclasses of Event are automatically registered in SystemManager binds
+- System added to SystemManager
|  +- System type's static binds registered in SystemManager binds, as bound method callbacks
+- System removed from SystemManager
|  +- System's binds removed from SystemManager binds
+- Event triggered by a system: 'source' (source is irrelevant)
   +- Event directed to a specific 'target'/'receiver'/'recipient'
   |  +- Bound callback is found for the event type for the system type, and executed
   |  +- Bound callback is not found: raise TypeError
   +- Event received by all systems in SystemManager (in order of highest priority to lowest)
      +- All bound callbacks for that event type are executed
      +- No callbacks for event type: nothing happens
      +- Event type not registered in SystemManager binds: raise TypeError, incorrect argument type



RECOMMENDED DESIGN:
One of the main goals of this ECS is to reduce coupling of game functionality
Decoupling game functionality has many benefits.

Let's say we would like our player to kill an enemy, and get loot and an acheivement

The directly relevant systems would be:
InputSystem
AudioSystem
AnimationSystem
PlayerAttackSystem
AttackCollisionSystem
EnemyCollisionSystem
EnemyKillSystem
CollisionSystem
AcheivementSystem(s)

Glue it together with events that the systems respond to:
KeyInput
StartAttack
Collision
EnemyHit
EnemyKilled


Code should not be centralized in one spot,
e.g. code for player attack does the attack, plays the audio, etc.
Instead, the code should be centralized around an event that everything responds to,
or around data (both approaches are basically the same)
Centralizing code around an event is more of a write data relationship
Centralizing code around data is more of a read relationship

Compared to extremely centralized code,
this is a bit slower since less data is shared between game functionality,
but sharing data by pre-computing it can help.
It also may seem cumbersome, since everything has to be split up.
The benefits are plentiful, though


State may name clash. Some alternatives for common name clashes:
GameState -> GameScene, GameScreen, GameStatus, GameStage
StateMachine, WalkingState -> PhaseMachine, WalkingPhase



How to create entities?
A system can directly create and populate an entity.
A module like those for events or components can provide functions that
produce "batches" of more than one component, sometimes with some parameters for customization.
It is also easy to customize and change the components after the entity/batch has been created.
(Do not nest batch making, let the user combine all of the batches necessary.)
These batches are almost like their own huge components.
Small, individual components may be created directly by systems.
Batch functions should only be made when necessary:
- repeated at least twice, and especially when a lot of code
- likely to reuse
Batch functions should not be made for:
- a large, unique set of components for a specific entity, that cannot be reused by other code
- combining multiple batches into one (defeats the purpose of composition)
- a batch meant to represent a unique entity, similarly to a class, that only appears once
It is preferred to have smaller batches, so break down large batches.

Components should represent one, indivisible thing.
Components can be created large and then later broken down into useful parts.


Removed feature storage:
```
def load_package(package: str, /) -> dict[str, _ModuleType]:
  """Loads all modules and packages (recursively) in a package.

  This is so that the modules can be accessed without importing them.
  All errors are propagated.
  """
  module = _import_module(package)
  try:
    path = module.__path__
  except AttributeError:
    raise ImportError(f'{module!r} is not a package') from None
  return {
    (name:=info.name): _import_module(name) for info in _walk_packages(path, package+'.')
  }
```
