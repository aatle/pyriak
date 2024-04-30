__all__ = ['install']

import sys
from functools import wraps as _wraps
from importlib.util import find_spec as _find_spec

from pyriak.system import System as _System


_LOADER = '_loader'  # the name of the wrapped loader in the wrapper class.


def _set_loader(self, module, loader):
  """Sets the module's __loader__ to the actual loader instead of the wrapper."""
  module_loader = getattr(module, '__loader__', object())
  if module_loader is None or module_loader is self:
    try:
      module.__loader__ = loader
    except AttributeError:
      pass
  spec = getattr(module, '__spec__', None)
  if spec is not None and getattr(spec, 'loader', None) is self:
    spec.loader = loader


class _SystemLoaderWrapper:
  """Wraps the actual loader.

  Initializes modules into Systems if possible, using wrapper methods.
  """

  def __init__(self, loader, /):
    object.__setattr__(self, _LOADER, loader)

  def __getattribute__(self, name, /):
    loader = object.__getattribute__(self, _LOADER)
    if name == _LOADER:
      return loader
    if name == 'exec_module':
      loader_exec_module = loader.exec_module
      @_wraps(loader_exec_module)
      def exec_module(module):
        _set_loader(self, module, loader)
        result = loader_exec_module(module)
        if hasattr(module, '_system_'):
          _System.init(module)
        return result
      return exec_module
    if name == 'load_module':
      # legacy method
      loader_load_module = loader.load_module
      @_wraps(loader_load_module)
      def load_module(fullname):
        module = loader_load_module(fullname)
        _set_loader(self, module, loader)
        if hasattr(module, '_system_'):
          _System.init(module)
        return module
      return load_module
    return getattr(loader, name)

  def __setattr__(self, name, value, /):
    loader = object.__getattribute__(self, _LOADER)
    return setattr(loader, name, value)

  def __delattr__(self, name, /):
    loader = object.__getattribute__(self, _LOADER)
    return delattr(loader, name)


class _SystemFinder:
  """Finder in sys.meta_path.

  When a module is imported, return a spec from another finder
  but with a wrapped loader.
  System modules will be initialized.
  """

  wrapper = _SystemLoaderWrapper
  #= hooks

  def __init__(self):
    self._lock_names = set()

  def find_spec(self, fullname, _path=None, target=None):
    lock_names = self._lock_names
    if target is not None or fullname in lock_names:
      return None
    lock_names.add(fullname)
    try:
      spec = _find_spec(fullname)
      if spec is None:
        return None
      loader = getattr(spec, 'loader', None)
      if loader is not None:
        spec.loader = self.wrapper(loader)  # type: ignore
      return spec
    finally:
      lock_names.remove(fullname)


def _install(cls, /):
  """Install a finder at the front of sys.meta_path.

  Will not install if cls is already the exact type of another finder in sys.meta_path.
  """
  for finder in sys.meta_path:
    if type(finder) is cls:
      return
  sys.meta_path.insert(0, cls())


def install():
  """
  Install the meta path finder in sys.meta_paths,
  allowing for automatic system initialization via import.
  """
  return _install(_SystemFinder)
