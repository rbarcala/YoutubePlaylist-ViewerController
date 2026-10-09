"""Shim de compatibilidad hacia services.config_manager."""
import sys
import services.config_manager as _cm

# Re-export everything from services.config_manager
for _k, _v in list(_cm.__dict__.items()):
    if not _k.startswith('__'):
        globals()[_k] = _v

# Module proxy to sync attribute updates with services.config_manager
class _ConfigModuleProxy(sys.modules[__name__].__class__):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if hasattr(_cm, name):
            setattr(_cm, name, value)

    def __getattr__(self, name):
        return getattr(_cm, name)

sys.modules[__name__].__class__ = _ConfigModuleProxy
