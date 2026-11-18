"""rewindagents: a tamper-evident flight recorder for AI agent tool calls."""
# Lazy: `python -m rewindagents hook` runs twice per tool call and must not pay for log.py's imports (and, through
# the old eager import, rewind.py's) before the hook has said what it needs. Module __getattr__ (PEP 562) keeps
# `from rewindagents import Recorder` and `rewindagents.verify` working.
__all__ = ["GENESIS", "Recorder", "head", "read", "verify"]
__version__ = "1.1.0"


def __getattr__(name: str):
    if name in __all__:
        from . import log
        value = getattr(log, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
