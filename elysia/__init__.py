'\nUnified Elysia runtime package.\n\nProvides the command-line interface (`python -m elysia`) and runtime\norchestration used to power the "god switch" workflow described in the\nimplementation plan.\n'

__all__ = ['RuntimeConfig', 'ElysiaRuntime']

# Resolve public exports on demand; package import must not boot the runtime.
_EXPORTS = {'RuntimeConfig': ('.config', 'RuntimeConfig'), 'ElysiaRuntime': ('.runtime', 'ElysiaRuntime')}

def __getattr__(name):
    from importlib import import_module
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module, attribute = _EXPORTS[name]
    value = getattr(import_module(module, __name__), attribute)
    globals()[name] = value
    return value
