import os
import yaml
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.models.decision import MergeDecision
from src.models.conflict import ConflictPoint, ConflictType, ChangeIntent
from src.models.human import HumanDecisionRequest, DecisionOption
from src.tools.decision_template import (
    generate_decision_template,
    export_decision_template,
)


def _make_conflict_point(file_path: str = "src/main.py") -> ConflictPoint:
    return ConflictPoint(
        file_path=file_path,
        hunk_id="hunk-1",
        conflict_type=ConflictType.CONCURRENT_MODIFICATION,
        upstream_intent=ChangeIntent(
            description="refactor logging",
            intent_type="refactor",
            confidence=0.9,
        ),
        fork_intent=ChangeIntent(
            description="add feature flag",
            intent_type="feature",
            confidence=0.85,
        ),
        can_coexist=False,
        suggested_decision=MergeDecision.SEMANTIC_MERGE,
        confidence=0.7,
        rationale="Both changes touch the same function",
    )


def _make_decision_request(
    file_path: str = "src/main.py",
    priority: int = 5,
) -> HumanDecisionRequest:
    return HumanDecisionRequest(
        file_path=file_path,
        priority=priority,
        conflict_points=[_make_conflict_point(file_path)],
        context_summary="Concurrent edits to logging module",
        upstream_change_summary="Refactored logger initialization",
        fork_change_summary="Added feature flag support",
        analyst_recommendation=MergeDecision.SEMANTIC_MERGE,
        analyst_confidence=0.75,
        analyst_rationale="Semantic merge can preserve both intents",
        options=[
            DecisionOption(
                option_key="A",
                decision=MergeDecision.TAKE_CURRENT,
                description="Keep current (upstream) version",
            ),
            DecisionOption(
                option_key="B",
                decision=MergeDecision.TAKE_TARGET,
                description="Keep target (fork) version",
            ),
            DecisionOption(
                option_key="C",
                decision=MergeDecision.SEMANTIC_MERGE,
                description="Merge both changes semantically",
            ),
            DecisionOption(
                option_key="D",
                decision=MergeDecision.MANUAL_PATCH,
                description="Provide a manual patch",
            ),
        ],
        created_at=datetime(2026, 1, 1, 12, 0, 0),
    )


class TestGenerateDecisionTemplate:
    def test_format_has_instructions_and_decisions(self) -> None:
        requests = [_make_decision_request()]
        output = generate_decision_template(requests)
        parsed = yaml.safe_load(output)

        assert "instructions" in parsed
        assert "decisions" in parsed
        assert isinstance(parsed["decisions"], list)
        assert "take_current" in parsed["instructions"]

    def test_includes_all_files(self) -> None:
        requests = [
            _make_decision_request("src/a.py", priority=3),
            _make_decision_request("src/b.py", priority=7),
            _make_decision_request("src/c.py", priority=1),
        ]
        output = generate_decision_template(requests)
        parsed = yaml.safe_load(output)

        file_paths = [d["file_path"] for d in parsed["decisions"]]
        assert file_paths == ["src/a.py", "src/b.py", "src/c.py"]

    def test_empty_requests_produces_valid_yaml(self) -> None:
        output = generate_decision_template([])
        parsed = yaml.safe_load(output)

        assert "instructions" in parsed
        assert parsed["decisions"] == []

    def test_decision_entry_fields(self) -> None:
        requests = [_make_decision_request()]
        output = generate_decision_template(requests)
        parsed = yaml.safe_load(output)

        entry = parsed["decisions"][0]
        assert entry["file_path"] == "src/main.py"
        assert entry["priority"] == 5
        assert entry["risk_summary"] == "Concurrent edits to logging module"
        assert entry["upstream_changes"] == "Refactored logger initialization"
        assert entry["fork_changes"] == "Added feature flag support"
        assert entry["analyst_recommendation"] == "semantic_merge"
        assert entry["analyst_confidence"] == 0.75
        assert entry["analyst_rationale"] == "Semantic merge can preserve both intents"
        assert entry["decision"] == ""
        assert entry["custom_content"] is None
        assert entry["reviewer_name"] == ""
        assert entry["reviewer_notes"] == ""

    def test_options_serialized_correctly(self) -> None:
        requests = [_make_decision_request()]
        output = generate_decision_template(requests)
        parsed = yaml.safe_load(output)

        options = parsed["decisions"][0]["options"]
        assert len(options) == 4
        assert options[0]["key"] == "A"
        assert options[0]["decision"] == "take_current"
        assert options[0]["description"] == "Keep current (upstream) version"

    def test_confidence_rounded(self) -> None:
        req = _make_decision_request()
        req_updated = req.model_copy(update={"analyst_confidence": 0.123456789})
        output = generate_decision_template([req_updated])
        parsed = yaml.safe_load(output)

        assert parsed["decisions"][0]["analyst_confidence"] == 0.12


class TestExportDecisionTemplate:
    def test_creates_file(self, tmp_path: Path) -> None:
        requests = [_make_decision_request()]
        output_path = str(tmp_path / "decisions.yaml")

        result = export_decision_template(requests, output_path)

        assert Path(result).exists()
        content = Path(result).read_text(encoding="utf-8")
        parsed = yaml.safe_load(content)
        assert "instructions" in parsed
        assert len(parsed["decisions"]) == 1

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        output_path = str(tmp_path / "nested" / "dir" / "decisions.yaml")
        result = export_decision_template([], output_path)

        assert Path(result).exists()

    def test_file_is_valid_yaml(self, tmp_path: Path) -> None:
        requests = [
            _make_decision_request("src/a.py"),
            _make_decision_request("src/b.py"),
        ]
        output_path = str(tmp_path / "decisions.yaml")
        export_decision_template(requests, output_path)

        content = Path(output_path).read_text(encoding="utf-8")
        parsed = yaml.safe_load(content)
        assert len(parsed["decisions"]) == 2


@pytest.fixture(autouse=True, scope="module")
def _preload_agents() -> None:
    """Pre-import to avoid circular import on first access."""
    import importlib

    try:
        importlib.import_module("src.core.orchestrator")
    except Exception:
        pass


class TestRoundtrip:
    @pytest.mark.asyncio
    @patch.dict(os.environ, {"TEST_KEY": "fake-api-key"})
    @patch("src.llm.client.LLMClientFactory.create", return_value=MagicMock())
    async def test_roundtrip_template_to_decisions(
        self, _mock_llm: MagicMock, tmp_path: Path
    ) -> None:
        from src.agents.human_interface_agent import HumanInterfaceAgent
        from src.models.config import AgentLLMConfig

        requests = [
            _make_decision_request("src/a.py"),
            _make_decision_request("src/b.py"),
        ]

        template_path = str(tmp_path / "template.yaml")
        export_decision_template(requests, template_path)

        raw = yaml.safe_load(Path(template_path).read_text(encoding="utf-8"))
        raw["decisions"][0]["decision"] = "take_current"
        raw["decisions"][0]["reviewer_name"] = "Alice"
        raw["decisions"][1]["decision"] = "take_target"
        raw["decisions"][1]["reviewer_name"] = "Bob"
        raw["decisions"][1]["reviewer_notes"] = "Looks good"
        Path(template_path).write_text(
            yaml.dump(raw, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        llm_config = AgentLLMConfig(
            provider="anthropic",
            model="test-model",
            api_key_env="TEST_KEY",
        )
        hi = HumanInterfaceAgent(llm_config)
        updated = await hi.collect_decisions_file(template_path, requests)

        assert updated[0].human_decision == MergeDecision.TAKE_CURRENT
        assert updated[0].reviewer_name == "Alice"
        assert updated[1].human_decision == MergeDecision.TAKE_TARGET
        assert updated[1].reviewer_name == "Bob"
        assert updated[1].reviewer_notes == "Looks good"

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"TEST_KEY": "fake-api-key"})
    @patch("src.llm.client.LLMClientFactory.create", return_value=MagicMock())
    async def test_roundtrip_manual_patch(
        self, _mock_llm: MagicMock, tmp_path: Path
    ) -> None:
        from src.agents.human_interface_agent import HumanInterfaceAgent
        from src.models.config import AgentLLMConfig

        requests = [_make_decision_request("src/patch.py")]

        template_path = str(tmp_path / "template.yaml")
        export_decision_template(requests, template_path)

        raw = yaml.safe_load(Path(template_path).read_text(encoding="utf-8"))
        raw["decisions"][0]["decision"] = "manual_patch"
        raw["decisions"][0]["custom_content"] = "print('patched')"
        Path(template_path).write_text(
            yaml.dump(raw, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        llm_config = AgentLLMConfig(
            provider="anthropic",
            model="test-model",
            api_key_env="TEST_KEY",
        )
        hi = HumanInterfaceAgent(llm_config)
        updated = await hi.collect_decisions_file(template_path, requests)

        assert updated[0].human_decision == MergeDecision.MANUAL_PATCH
        assert updated[0].custom_content == "print('patched')"

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"TEST_KEY": "fake-api-key"})
    @patch("src.llm.client.LLMClientFactory.create", return_value=MagicMock())
    async def test_roundtrip_skipped_decisions(
        self, _mock_llm: MagicMock, tmp_path: Path
    ) -> None:
        from src.agents.human_interface_agent import HumanInterfaceAgent
        from src.models.config import AgentLLMConfig

        requests = [
            _make_decision_request("src/a.py"),
            _make_decision_request("src/b.py"),
        ]

        template_path = str(tmp_path / "template.yaml")
        export_decision_template(requests, template_path)

        raw = yaml.safe_load(Path(template_path).read_text(encoding="utf-8"))
        raw["decisions"][0]["decision"] = "take_current"
        Path(template_path).write_text(
            yaml.dump(raw, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )

        llm_config = AgentLLMConfig(
            provider="anthropic",
            model="test-model",
            api_key_env="TEST_KEY",
        )
        hi = HumanInterfaceAgent(llm_config)
        updated = await hi.collect_decisions_file(template_path, requests)

        assert updated[0].human_decision == MergeDecision.TAKE_CURRENT
        assert updated[1].human_decision is None
