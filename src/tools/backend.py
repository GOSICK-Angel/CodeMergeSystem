"""Tool backend abstraction layer (D2).

Provides a registry pattern so that tools (syntax checker, gate runner,
diff parser) can swap implementations without changing calling code.

Inspired by Hermes' multi-backend web tool architecture where Exa,
Firecrawl, and Tavily are interchangeable.

Usage::

    # Register backends
    BackendRegistry.register("syntax_checker", "builtin", BuiltinSyntaxBackend())
    BackendRegistry.register("syntax_checker", "ruff", RuffSyntaxBackend())

    # Select active backend
    BackendRegistry.set_active("syntax_checker", "ruff")

    # Get the active backend
    backend = BackendRegistry.get("syntax_checker")
    result = backend.run(file_path="main.py", content=src)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class ToolBackend(ABC):
    """Abstract base class for tool backends."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this backend."""
        ...

    @abstractmethod
    def check_available(self) -> bool:
        """Return True if this backend's dependencies are satisfied."""
        ...

    @abstractmethod
    def run(self, **kwargs: Any) -> Any:
        """Execute the backend's primary operation."""
        ...


@dataclass
class _ToolEntry:
    """Internal tracking of registered backends for a single tool."""

    backends: dict[str, ToolBackend] = field(default_factory=dict)
    active: str = ""


class BackendRegistry:
    """Global registry mapping tool names to their available backends.

    Each tool can have multiple backends registered.  One is marked
    *active* — that's the one returned by :meth:`get`.
    """

    _tools: dict[str, _ToolEntry] = {}

    @classmethod
    def register(
        cls,
        tool: str,
        backend_name: str,
        backend: ToolBackend,
        *,
        set_active: bool = False,
    ) -> None:
        """Register *backend* under *tool* / *backend_name*.

        If the tool has no active backend yet, this one becomes active
        automatically.  Pass ``set_active=True`` to force activation.
        """
        entry = cls._tools.setdefault(tool, _ToolEntry())
        entry.backends[backend_name] = backend
        if not entry.active or set_active:
            entry.active = backend_name
        logger.debug(
            "Registered backend %s/%s (active=%s)",
            tool,
            backend_name,
            entry.active,
        )

    @classmethod
    def set_active(cls, tool: str, backend_name: str) -> None:
        """Switch the active backend for *tool*."""
        entry = cls._tools.get(tool)
        if entry is None:
            raise ValueError(f"Unknown tool: {tool}")
        if backend_name not in entry.backends:
            raise ValueError(
                f"Backend '{backend_name}' not registered for tool '{tool}'. "
                f"Available: {list(entry.backends.keys())}"
            )
        entry.active = backend_name

    @classmethod
    def get(cls, tool: str) -> ToolBackend:
        """Return the active backend for *tool*."""
        entry = cls._tools.get(tool)
        if entry is None or not entry.active:
            raise ValueError(f"No backend registered for tool: {tool}")
        return entry.backends[entry.active]

    @classmethod
    def get_all(cls, tool: str) -> dict[str, ToolBackend]:
        """Return all registered backends for *tool*."""
        entry = cls._tools.get(tool)
        if entry is None:
            return {}
        return dict(entry.backends)

    @classmethod
    def active_name(cls, tool: str) -> str:
        """Return the name of the active backend for *tool*."""
        entry = cls._tools.get(tool)
        if entry is None:
            raise ValueError(f"No backend registered for tool: {tool}")
        return entry.active

    @classmethod
    def registered_tools(cls) -> list[str]:
        """Return all tool names with at least one registered backend."""
        return list(cls._tools.keys())

    @classmethod
    def clear(cls) -> None:
        """Remove all registrations (for testing)."""
        cls._tools.clear()


# ---------------------------------------------------------------------------
# Concrete backends for existing tools
# ---------------------------------------------------------------------------


class BuiltinSyntaxBackend(ToolBackend):
    """Default syntax checker using ast/json/yaml (existing implementation)."""

    @property
    def name(self) -> str:
        return "builtin"

    def check_available(self) -> bool:
        return True

    def run(self, **kwargs: Any) -> Any:
        from src.tools.syntax_checker import check_syntax

        file_path: str = kwargs["file_path"]
        content: str = kwargs["content"]
        return check_syntax(file_path, content)


class BuiltinDiffBackend(ToolBackend):
    """Default diff parser using Python difflib (existing implementation)."""

    @property
    def name(self) -> str:
        return "builtin"

    def check_available(self) -> bool:
        return True

    def run(self, **kwargs: Any) -> Any:
        from src.tools.diff_parser import parse_unified_diff

        raw_diff: str = kwargs["raw_diff"]
        file_path: str = kwargs["file_path"]
        return parse_unified_diff(raw_diff, file_path)


class LocalGateBackend(ToolBackend):
    """Default gate runner using local subprocess (existing implementation)."""

    @property
    def name(self) -> str:
        return "local"

    def check_available(self) -> bool:
        return True

    def run(self, **kwargs: Any) -> Any:
        raise NotImplementedError(
            "GateRunner is async — use GateRunner.run_gate() directly. "
            "This backend exists for registry tracking only."
        )


def register_default_backends() -> None:
    """Register the built-in backends for all tools.

    Call once at startup.  Idempotent — safe to call multiple times.
    """
    if "syntax_checker" not in BackendRegistry.registered_tools():
        BackendRegistry.register("syntax_checker", "builtin", BuiltinSyntaxBackend())
    if "diff_parser" not in BackendRegistry.registered_tools():
        BackendRegistry.register("diff_parser", "builtin", BuiltinDiffBackend())
    if "gate_runner" not in BackendRegistry.registered_tools():
        BackendRegistry.register("gate_runner", "local", LocalGateBackend())
