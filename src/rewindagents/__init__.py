"""rewindagents: a tamper-evident flight recorder for AI agent tool calls."""
from .log import GENESIS, Recorder, head, read, verify

__all__ = ["GENESIS", "Recorder", "head", "read", "verify"]
__version__ = "0.0.7"
