# pyriak
A lightweight implementation of Entity Component System architecture for Python.

(Originally created August 2, 2022.)


## Concepts







## Usage





System naming convention:
Systems are modules. Use snake_case because they are often accessed through attribute notation.
The name should describe the system's purpose or feature, either managing or controlling something, e.g.:
display.py controls Display state,
camera.py controls Camera state
but if it does not control any data, then it should be describing the action it does or thing it does
initialize.py
exit.py
camera_shake.py


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


### Entity creation
Any entity must first be created and populated with components.

A system can directly create and populate an entity.
This system may decide itself to create an entity, or handle an event that
directly tells it to create one.
```py
player = space.entities.create(
  components.Player(),
  components.CameraFocus(),
  components.Sprite(),
)
```
A listening system can extend a created entity.
```py
@bind(ComponentAdded, 200, RocketBooster):
def add_rocket_exhaust(space, event):
  event.entity.add(ParticleEmitter(rocket_particles))
```

Often, multiple systems will need to create a certain set of components that are not
related enough to put under a single component, but common enough to necessitate code reuse.
A dedicated module can provide functions that
produce a "batch", a set of components, sometimes with parameters for customization.
```py
# batches.py
def spaceship(radius=20):
  body = components.Body(radius)
  body.collision_type = 'spaceship'
  return body, components.Engine(), components.Sprite(spaceship_sprite)
...
```
```py
# systems/player.py
import batches
...
player = space.entities.create(
  *batches.spaceship(),
  components.CameraFocus(),
  components.PlayerController()
)
enemy = space.entities.create(
  *batches.spaceship(),
  components.AIController()
)
```
It is also easy to customize or initialize the components after the entity and batch have been created
as opposed to passing in customization parameters to the batch function.

Small, individual components may be created directly by systems.
Batch functions should only be made when necessary, for when it is likely to be reused:
repeated at least twice, lots of boilerplate.
Batch functions should not be made for a large, unique set of components for a specific entity.
It is preferable to have smaller batches to allow for more control in choosing which components to use.

A batch function that calls another batch function mimics inheritance, which can lead to
avoidable problems.
Batches should be considered large components, not a standalone pseudo-class.
(However, a batch function that *only* calls other batch functions is fine because it
does not create any components itself, so its use is not directly required by anything.)

Also note that the components should represent one, indivisible thing.
Components can be created large and then later broken down into a batch of multiple components.
 

## TO DO:
- dynamic handlers?
- 3.11 typing features
- fix multibinding typing
- check set_key typing
- convert _bindings_ to EventHandler dict keys
- system "new" method instantiation
- `__future__.annotations`
- type aliases
- possibly entity, stmgr getitem iterable
- 'direct', 'indirect', 'strict', 'immediate' vocab docs
- validate subclasses: hash, mro
- sys mgr expose handlers + bind predicate/filter + _Binding public
- `__contains__` TypeError raise?
- picklable `__setstate__ __getstate__ __copy__` classes
- 'processor' game pump generator yield event method, 'event loop'
- discard method
- possibly entity and statemanager base class (better for user subclassing)
- keys method (for dict protocol)
- improve error messages
- raise from None bad
- views, items methods: mappingproxy
- `__eq__`, remove `__hash__`: mgrs
- types(*types) method functionality all mgrs+entity ?
- entities from ids: itertools helpers in entitymgr
- 'add', 'remove' methods return value
- entity mgr garbage collection behavior (currently undefined?)
- game `__call__` use ?
- more container (set) dunder methods, operations
- copy methods
- more positional only arguments
- more system config
- str and repr methods all
- place documentation in code, along with all rules (style guide first)
- optimization through profiling, scalene (in a game)
- make imported module variables private (consistency)
- python version lower in poetry dependencies ? find min python version
- review and rewrite readme.txt
