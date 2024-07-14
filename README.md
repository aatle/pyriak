# pyriak
A lightweight implementation of Entity Component System architecture for Python.

(Originally created August 2, 2022.)


## Concepts
Object oriented programming is used for many projects.
In larger, more complex projects, it can have some shortcomings.
The inheritance hierarchies can become messy and inflexible,
forcing the base classes to grow in size when code reuse is needed.


## Usage



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
@bind(ComponentAdded, 200, RocketBooster)
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
- `__future__.annotations`
- dynamic handlers?
- 3.11 typing features
- type aliases
- 'direct', 'indirect', 'strict', 'immediate' vocab docs
- sys mgr expose handlers + bind predicate/filter?
- `__contains__` TypeError raise?
- picklable `__setstate__ __getstate__ __copy__` classes
- 'processor' game pump generator yield event method, 'event loop'?
- discard method
- keys method (for dict protocol)?
- views, items methods: mappingproxy
- improve error messages
- raise from None bad
- `__eq__`, remove `__hash__`: mgrs
- entities from ids: itertools helpers in entitymgr
- more container (set) dunder methods, operations
- copy methods
- .has() method (for component, state, entity)?
- more positional only arguments
- str and repr methods all
- place documentation in code, along with all rules
- optimization through profiling, scalene (in a game)
- make imported module variables private (consistency)
- review and rewrite readme.txt
