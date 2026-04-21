"""Tests for the O-A Agent Contract infrastructure.

Covers:
* contract yaml loads and validates;
* restricted ReadOnlyStateView enforces the field whitelist;
* static forbidden-rule scans catch violations in an agent module.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.agents.contract import (
    AgentContract,
    FieldNotInContract,
    contract_path,
    contracts_dir,
    list_contract_names,
    load_contract,
)
from src.core.read_only_state_view import ReadOnlyStateView
from src.llm.prompts.gate_registry import get_gate, registered_gate_ids


# ---------- contract loading & schema ----------


def test_contract_dir_exists() -> None:
    assert contracts_dir().is_dir()


def test_planner_judge_contract_loads() -> None:
    contract = load_contract("planner_judge")
    assert isinstance(contract, AgentContract)
    assert contract.name == "planner_judge"
    assert "merge_plan" in contract.inputs
    assert contract.output_schema == "PlanJudgeVerdict"
    assert contract.collaboration == "review_only"
    assert "writes_state" in contract.forbidden


def test_missing_contract_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_contract("does_not_exist_xyz")


def test_contract_name_must_match_filename(tmp_path: Path, monkeypatch) -> None:
    bad = tmp_path / "foo.yaml"
    bad.write_text("name: bar\ninputs: [x]\noutput_schema: X\n", encoding="utf-8")
    monkeypatch.setattr("src.agents.contract.contract_path", lambda name: bad)
    with pytest.raises(ValueError, match="name mismatch"):
        load_contract("foo")


def test_all_declared_gates_are_registered() -> None:
    """Every gate ID in every contract yaml must be registered in gate_registry."""
    registered = set(registered_gate_ids())
    for name in list_contract_names():
        contract = load_contract(name)
        for gate_id in contract.gates:
            assert gate_id in registered, (
                f"Contract '{name}' references unregistered gate '{gate_id}'. "
                f"Register it in src/llm/prompts/gate_registry.py."
            )


def test_gate_registry_returns_callable() -> None:
    gate = get_gate("PJ-SYSTEM")
    assert callable(gate.builder)
    assert gate.description


# ---------- restricted ReadOnlyStateView ----------


class _DummyState:
    """Plain object that mimics MergeState enough for view tests."""

    def __init__(self) -> None:
        self.merge_plan = {"phases": []}
        self.file_diffs = ["a", "b"]
        self.config = {"lang": "en"}
        self.errors = ["secret"]


def test_unrestricted_view_allows_all_reads() -> None:
    state = _DummyState()
    view = ReadOnlyStateView(state)  # type: ignore[arg-type]
    assert view.merge_plan == {"phases": []}
    assert view.errors == ["secret"]


def test_restricted_view_blocks_outside_whitelist() -> None:
    state = _DummyState()
    view = ReadOnlyStateView.restricted(
        state,  # type: ignore[arg-type]
        allowed_fields={"merge_plan", "file_diffs", "config"},
        contract_name="planner_judge",
    )
    assert view.merge_plan == {"phases": []}
    with pytest.raises(FieldNotInContract) as excinfo:
        _ = view.errors
    assert "planner_judge" in str(excinfo.value)
    assert "errors" in str(excinfo.value)


def test_view_blocks_writes_regardless_of_mode() -> None:
    state = _DummyState()
    view = ReadOnlyStateView(state)  # type: ignore[arg-type]
    with pytest.raises(PermissionError):
        view.merge_plan = {}  # type: ignore[misc]


def test_restricted_view_deep_copies_mutables() -> None:
    state = _DummyState()
    view = ReadOnlyStateView.restricted(
        state,  # type: ignore[arg-type]
        allowed_fields={"file_diffs"},
    )
    copy = view.file_diffs
    copy.append("mutated")
    assert state.file_diffs == ["a", "b"]


# ---------- forbidden static scans ----------

AGENT_SOURCES = {
    "planner": Path("src/agents/planner_agent.py"),
    "planner_judge": Path("src/agents/planner_judge_agent.py"),
    "conflict_analyst": Path("src/agents/conflict_analyst_agent.py"),
    "executor": Path("src/agents/executor_agent.py"),
    "judge": Path("src/agents/judge_agent.py"),
    "human_interface": Path("src/agents/human_interface_agent.py"),
}

# `state.xxx = value` anywhere in an agent module is forbidden.
# Allows `state.xxx == value` (comparison) and attribute access.
_STATE_WRITE_RE = re.compile(r"\bstate\.\w+\s*=(?!=)")

# direct LLM client calls must go through BaseAgent._call_llm_with_retry.
_DIRECT_LLM_RE = re.compile(r"\bself\.llm\.(complete|chat|generate)\s*\(")


def _violations(source: str, pattern: re.Pattern[str]) -> list[str]:
    return [m.group(0) for m in pattern.finditer(source)]


@pytest.mark.parametrize("name,path", list(AGENT_SOURCES.items()))
def test_forbidden_rules_respected(name: str, path: Path) -> None:
    contract = load_contract(name)
    source = path.read_text(encoding="utf-8")
    if "writes_state" in contract.forbidden:
        hits = _violations(source, _STATE_WRITE_RE)
        assert not hits, f"{name}: writes_state forbidden but found {hits}"
    if "direct_llm_call" in contract.forbidden:
        hits = _violations(source, _DIRECT_LLM_RE)
        assert not hits, f"{name}: direct_llm_call forbidden but found {hits}"


# ---------- BaseAgent.contract lazy loading ----------


def test_all_contracts_load_and_declared_gates_resolve() -> None:
    """Every contract on disk loads and every gate it declares is callable."""
    names = list_contract_names()
    assert {
        "planner",
        "planner_judge",
        "conflict_analyst",
        "executor",
        "judge",
        "human_interface",
    }.issubset(set(names)), names
    for name in names:
        contract = load_contract(name)
        for gate_id in contract.gates:
            gate = get_gate(gate_id)
            assert callable(gate.builder)


def test_planner_judge_run_uses_restricted_view() -> None:
    """End-to-end: PlannerJudge wraps state; access to non-whitelisted attrs raises."""
    from src.agents.base_agent import BaseAgent
    from src.agents.planner_judge_agent import PlannerJudgeAgent

    agent = PlannerJudgeAgent.__new__(PlannerJudgeAgent)
    agent._contract = None
    BaseAgent.contract_name.__set__ if False else None  # noqa: no-op

    class _S:
        merge_plan = {"phases": []}
        file_diffs: list = []
        config = None
        errors = ["should be blocked"]

    # Use the helper directly; it should produce a restricted view.
    view = agent.restricted_view(_S())
    assert view.merge_plan == {"phases": []}
    with pytest.raises(FieldNotInContract):
        _ = view.errors


AGENT_CLASSES = {
    "planner": ("src.agents.planner_agent", "PlannerAgent"),
    "planner_judge": ("src.agents.planner_judge_agent", "PlannerJudgeAgent"),
    "conflict_analyst": ("src.agents.conflict_analyst_agent", "ConflictAnalystAgent"),
    "executor": ("src.agents.executor_agent", "ExecutorAgent"),
    "judge": ("src.agents.judge_agent", "JudgeAgent"),
    "human_interface": ("src.agents.human_interface_agent", "HumanInterfaceAgent"),
}


@pytest.mark.parametrize("name", list(AGENT_CLASSES))
def test_every_agent_declares_matching_contract_name(name: str) -> None:
    """Each BaseAgent subclass has contract_name matching its yaml file name."""
    import importlib

    module_name, class_name = AGENT_CLASSES[name]
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    assert cls.contract_name == name, (
        f"{class_name}.contract_name={cls.contract_name!r} does not match "
        f"yaml file name {name!r}"
    )


@pytest.mark.parametrize("name", list(AGENT_CLASSES))
def test_restricted_view_enforces_each_contract(name: str) -> None:
    """Bypass __init__ and verify restricted_view builds a contract-bound view."""
    import importlib

    module_name, class_name = AGENT_CLASSES[name]
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)

    agent = cls.__new__(cls)
    agent._contract = None

    contract = load_contract(name)

    class _State:
        pass

    dummy = _State()
    for field in contract.inputs:
        setattr(dummy, field, object())
    setattr(dummy, "__not_in_contract__xyz", "blocked")

    view = agent.restricted_view(dummy)
    for field in contract.inputs:
        _ = getattr(view, field)  # allowed — must not raise
    with pytest.raises(FieldNotInContract):
        _ = view.__not_in_contract__xyz


def test_agent_without_contract_name_returns_none() -> None:
    from src.agents.base_agent import BaseAgent

    class _Dummy(BaseAgent):
        agent_type = None  # type: ignore[assignment]

        async def run(self, state):  # type: ignore[override]
            return None

        def can_handle(self, state):  # type: ignore[override]
            return False

    d = _Dummy.__new__(_Dummy)
    d._contract = None
    # Bypass __init__ since it builds an LLM client; contract_name is class-level.
    assert _Dummy.contract_name is None
    assert BaseAgent.contract.fget(d) is None  # type: ignore[union-attr]
