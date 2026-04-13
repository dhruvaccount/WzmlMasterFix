"""
Client Registry

Manages all bot clients (Telegram, Discord, etc.)
"""

from typing import Dict, Optional, Type

from bots import ClientAdapter

registry: Dict[str, Type[ClientAdapter]] = {}


def register(name: str, client_class: Type[ClientAdapter]) -> None:
    """Register a client class"""
    registry[name] = client_class


def get(name: str) -> Optional[Type[ClientAdapter]]:
    """Get a client class"""
    return registry.get(name)


def list_clients() -> list[str]:
    """List registered clients"""
    return list(registry.keys())


__all__ = ["registry", "register", "get", "list_clients"]
