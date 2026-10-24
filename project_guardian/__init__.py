__version__ = '1.0.0'

__author__ = 'Project Guardian Team'

__all__ = ['GuardianCore', 'MemoryCore', 'MutationEngine', 'DevilsAdvocate', 'TrustMatrix', 'RollbackEngine', 'TaskEngine', 'PluginLoader', 'ConsensusEngine', 'SelfReflector', 'IntrospectionLens', 'SystemMonitor', 'Heartbeat', 'ErrorTrap', 'GuardianAPI', 'ContextBuilder', 'DreamEngine', 'MemorySearch', 'WebReader', 'VoiceThread', 'AIInteraction', 'MissionDirector']

# Resolve public exports on demand; package import must not boot the runtime.
_EXPORTS = {'GuardianCore': ('.core', 'GuardianCore'),
 'MemoryCore': ('.memory', 'MemoryCore'),
 'MutationEngine': ('.mutation', 'MutationEngine'),
 'DevilsAdvocate': ('.safety', 'DevilsAdvocate'),
 'TrustMatrix': ('.trust', 'TrustMatrix'),
 'RollbackEngine': ('.rollback', 'RollbackEngine'),
 'TaskEngine': ('.tasks', 'TaskEngine'),
 'PluginLoader': ('.plugins', 'PluginLoader'),
 'ConsensusEngine': ('.consensus', 'ConsensusEngine'),
 'SelfReflector': ('.introspection', 'SelfReflector'),
 'IntrospectionLens': ('.introspection', 'IntrospectionLens'),
 'SystemMonitor': ('.monitoring', 'SystemMonitor'),
 'Heartbeat': ('.monitoring', 'Heartbeat'),
 'ErrorTrap': ('.monitoring', 'ErrorTrap'),
 'GuardianAPI': ('.api', 'GuardianAPI'),
 'ContextBuilder': ('.creativity', 'ContextBuilder'),
 'DreamEngine': ('.creativity', 'DreamEngine'),
 'MemorySearch': ('.creativity', 'MemorySearch'),
 'WebReader': ('.external', 'WebReader'),
 'VoiceThread': ('.external', 'VoiceThread'),
 'AIInteraction': ('.external', 'AIInteraction'),
 'MissionDirector': ('.missions', 'MissionDirector')}

def __getattr__(name):
    from importlib import import_module
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module, attribute = _EXPORTS[name]
    value = getattr(import_module(module, __name__), attribute)
    globals()[name] = value
    return value
