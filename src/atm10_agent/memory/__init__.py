"""Embedded ATM10 memory with separate online capture and offline consolidation."""

from atm10_agent.memory.consolidation import consolidate_memory
from atm10_agent.memory.model import (
    MEMORY_AUTHORITY_CEILING,
    MEMORY_OBJECT_SCHEMA_VERSION,
    MemoryLifecycle,
    MemoryObject,
    MemoryTrust,
)
from atm10_agent.memory.store import EmbeddedMemoryStore, capture_turn_memory

__all__ = [
    "MEMORY_AUTHORITY_CEILING",
    "MEMORY_OBJECT_SCHEMA_VERSION",
    "EmbeddedMemoryStore",
    "MemoryLifecycle",
    "MemoryObject",
    "MemoryTrust",
    "capture_turn_memory",
    "consolidate_memory",
]
