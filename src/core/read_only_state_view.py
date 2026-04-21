from copy import deepcopy
from typing import Any

from pydantic import BaseModel

from src.models.state import MergeState


class ReadOnlyStateView:
    """Read-only view over MergeState.

    Two modes:

    * **Unrestricted** (default, ``allowed_fields=None``): every attribute is
      readable; deep-copies mutable values to prevent incidental mutation.
      Writes always raise ``PermissionError`` (invariant P5).
    * **Restricted** (``allowed_fields={...}``): only names in the whitelist
      are readable; access to any other attribute raises
      :class:`FieldNotInContract`.  Used by agents that declare a contract
      so the whitelist comes from ``contract.inputs``.
    """

    def __init__(
        self,
        state: MergeState,
        *,
        allowed_fields: frozenset[str] | None = None,
        contract_name: str | None = None,
    ) -> None:
        object.__setattr__(self, "_state", state)
        object.__setattr__(self, "_allowed_fields", allowed_fields)
        object.__setattr__(self, "_contract_name", contract_name)

    @classmethod
    def restricted(
        cls,
        state: MergeState,
        allowed_fields: set[str] | frozenset[str],
        *,
        contract_name: str | None = None,
    ) -> "ReadOnlyStateView":
        """Build a view that only exposes the given whitelist of attributes."""
        return cls(
            state,
            allowed_fields=frozenset(allowed_fields),
            contract_name=contract_name,
        )

    def __getattr__(self, name: str) -> Any:
        allowed = object.__getattribute__(self, "_allowed_fields")
        if allowed is not None and name not in allowed:
            from src.agents.contract import FieldNotInContract

            cname = object.__getattribute__(self, "_contract_name")
            scope = f"contract '{cname}'" if cname else "contract"
            raise FieldNotInContract(
                f"{scope} does not grant read access to MergeState.{name!r}. "
                f"Allowed: {sorted(allowed)}"
            )
        state = object.__getattribute__(self, "_state")
        value = getattr(state, name)
        if isinstance(value, (dict, list, BaseModel)):
            return deepcopy(value)
        return value

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            raise PermissionError(
                f"Read-only view: attempted write to '{name}'. "
                f"Use Orchestrator to write state on behalf of review agents."
            )

    def __delattr__(self, name: str) -> None:
        raise PermissionError(
            f"Read-only view: attempted delete of '{name}'. "
            f"Use Orchestrator to modify state."
        )
