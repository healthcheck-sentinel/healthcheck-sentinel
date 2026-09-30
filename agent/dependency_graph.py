"""Dependency graph modeling services and shared infrastructure components."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


DEFAULT_DEPENDENCIES: dict[str, list[str]] = {
    "payment-service": ["postgresql", "redis"],
    "order-service": ["postgresql", "redis"],
    "user-service": [],
}

# Alias mapping for dependency name normalization
DEPENDENCY_ALIASES: dict[str, str] = {
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "redis": "redis",
}


def normalize_dependency_name(name: str) -> str:
    """Normalize dependency names (e.g. 'postgres' -> 'postgresql')."""
    return DEPENDENCY_ALIASES.get(name.lower(), name.lower())


@dataclass
class DependencyGraph:
    """Directed dependency graph from services to dependencies."""

    _dependencies: dict[str, list[str]] = field(default_factory=dict)

    def __init__(self, mapping: Mapping[str, list[str]] | None = None) -> None:
        raw = mapping if mapping is not None else DEFAULT_DEPENDENCIES
        self._dependencies = {
            service: [normalize_dependency_name(dep) for dep in deps]
            for service, deps in raw.items()
        }

    def dependencies_for(self, service: str) -> list[str]:
        """Return normalized list of dependencies for a given service."""
        return list(self._dependencies.get(service, []))

    def services_depending_on(self, dependency: str) -> list[str]:
        """Return list of services that depend on the given dependency."""
        norm = normalize_dependency_name(dependency)
        return [
            service for service, deps in self._dependencies.items()
            if norm in deps
        ]

    def is_shared(self, dependency: str) -> bool:
        """Return True if more than one service depends on the given dependency."""
        return len(self.services_depending_on(dependency)) > 1

    def get_shared_dependencies(self) -> set[str]:
        """Return the set of all dependencies shared across multiple services."""
        seen: set[str] = set()
        shared: set[str] = set()
        for deps in self._dependencies.values():
            for dep in deps:
                if dep in seen:
                    shared.add(dep)
                seen.add(dep)
        return shared

    def to_dict(self) -> dict[str, list[str]]:
        return {k: list(v) for k, v in self._dependencies.items()}
