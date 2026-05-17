import importlib
import pkgutil
from pathlib import Path

_current_dir = str(Path(__file__).parent)

# Dynamically discover all submodules in the current directory, excluding private ones (those starting with '_').
__all__ = [
    name
    for _, name, _ in pkgutil.iter_modules([_current_dir])
    if not name.startswith("_")
]


def __getattr__(name):
    """
    Lazy loading of modules. This is triggered dynamically whenever
    someone types `runtimes.SOMETHING`. If SOMETHING isn't already loaded,
    it attempts to import it here.
    """
    if name in __all__:
        return importlib.import_module(f".{name}", package=__name__)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """
    Exposes the dynamically discovered modules to IDE REPLs
    and Jupyter Notebooks for autocompletion.
    """
    return sorted(list(globals().keys()) + __all__)
