from __future__ import annotations

from stackchanctl.backends.bridge import BridgeBackend
from stackchanctl.backends.mock import MockBackend


def create_backend(name: str):
    if name == "mock":
        return MockBackend()
    if name == "bridge":
        return BridgeBackend()
    raise ValueError(f"unknown backend: {name}")
