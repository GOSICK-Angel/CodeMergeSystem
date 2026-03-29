from copy import deepcopy
from typing import Any
from pydantic import BaseModel
from src.models.state import MergeState


class ReadOnlyStateView:
    def __init__(self, state: MergeState) -> None:
        object.__setattr__(self, "_state", state)

    def __getattr__(self, name: str) -> Any:
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
