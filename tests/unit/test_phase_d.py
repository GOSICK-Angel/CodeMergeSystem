"""Tests for Phase D (D1-D2): Smart model routing and tool backend abstraction."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

# ============================================================================
# D1: Smart model routing
# ============================================================================

from src.llm.model_router import TaskComplexity, classify_task_complexity, select_model
from src.models.config import AgentLLMConfig


class TestTaskComplexity:
    def test_enum_values(self):
        assert TaskComplexity.TRIVIAL == "trivial"
        assert TaskComplexity.STANDARD == "standard"
        assert TaskComplexity.COMPLEX == "complex"


class TestClassifyTaskComplexity:
    def test_empty_messages_is_standard(self):
        assert classify_task_complexity([]) == TaskComplexity.STANDARD

    def test_short_simple_message_is_trivial(self):
        msgs = [{"role": "user", "content": "Is this correct?"}]
        assert classify_task_complexity(msgs) == TaskComplexity.TRIVIAL

    def test_short_with_code_is_standard(self):
        msgs = [{"role": "user", "content": "def hello(): pass"}]
        assert classify_task_complexity(msgs) == TaskComplexity.STANDARD

    def test_long_message_is_standard(self):
        msgs = [{"role": "user", "content": "a " * 100}]
        assert classify_task_complexity(msgs) == TaskComplexity.STANDARD

    def test_many_code_patterns_is_complex(self):
        code = """
def foo():
    pass

def bar():
    pass

class Baz:
    def qux(self):
        import os
        from pathlib import Path
        """
        msgs = [{"role": "user", "content": code}]
        assert classify_task_complexity(msgs) == TaskComplexity.COMPLEX

    def test_very_long_content_is_complex(self):
        msgs = [{"role": "user", "content": "x " * 3000}]
        assert classify_task_complexity(msgs) == TaskComplexity.COMPLEX

    def test_only_assistant_messages_is_standard(self):
        msgs = [{"role": "assistant", "content": "ok"}]
        assert classify_task_complexity(msgs) == TaskComplexity.STANDARD

    def test_multiple_messages_uses_last_user(self):
        msgs = [
            {"role": "user", "content": "def foo(): pass\ndef bar(): pass"},
            {"role": "assistant", "content": "done"},
            {"role": "user", "content": "yes"},
        ]
        assert classify_task_complexity(msgs) == TaskComplexity.TRIVIAL

    def test_list_content_handled(self):
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "ok"},
                ],
            }
        ]
        assert classify_task_complexity(msgs) == TaskComplexity.TRIVIAL

    def test_custom_thresholds(self):
        msgs = [{"role": "user", "content": "hello world"}]
        assert (
            classify_task_complexity(msgs, max_trivial_chars=5)
            == TaskComplexity.STANDARD
        )
        assert (
            classify_task_complexity(msgs, max_trivial_chars=500)
            == TaskComplexity.TRIVIAL
        )


class TestSelectModel:
    def test_no_cheap_model_returns_primary(self):
        config = AgentLLMConfig(model="claude-opus-4-6", cheap_model=None)
        msgs = [{"role": "user", "content": "yes"}]
        assert select_model(msgs, config) == "claude-opus-4-6"

    def test_trivial_uses_cheap_model(self):
        config = AgentLLMConfig(
            model="claude-opus-4-6",
            cheap_model="claude-haiku-4-5-20251001",
        )
        msgs = [{"role": "user", "content": "yes"}]
        assert select_model(msgs, config) == "claude-haiku-4-5-20251001"

    def test_standard_uses_primary(self):
        config = AgentLLMConfig(
            model="claude-opus-4-6",
            cheap_model="claude-haiku-4-5-20251001",
        )
        msgs = [{"role": "user", "content": "a " * 100}]
        assert select_model(msgs, config) == "claude-opus-4-6"

    def test_complex_uses_primary(self):
        config = AgentLLMConfig(
            model="claude-opus-4-6",
            cheap_model="claude-haiku-4-5-20251001",
        )
        msgs = [{"role": "user", "content": "x " * 3000}]
        assert select_model(msgs, config) == "claude-opus-4-6"

    def test_force_complexity(self):
        config = AgentLLMConfig(
            model="claude-opus-4-6",
            cheap_model="claude-haiku-4-5-20251001",
        )
        msgs = [{"role": "user", "content": "x " * 3000}]
        result = select_model(msgs, config, force_complexity=TaskComplexity.TRIVIAL)
        assert result == "claude-haiku-4-5-20251001"


class TestAgentLLMConfigCheapModel:
    def test_default_none(self):
        config = AgentLLMConfig()
        assert config.cheap_model is None

    def test_set_cheap_model(self):
        config = AgentLLMConfig(cheap_model="claude-haiku-4-5-20251001")
        assert config.cheap_model == "claude-haiku-4-5-20251001"

    def test_backward_compat(self):
        data = {
            "provider": "anthropic",
            "model": "claude-opus-4-6",
            "api_key_env": "ANTHROPIC_API_KEY",
        }
        config = AgentLLMConfig.model_validate(data)
        assert config.cheap_model is None

    def test_yaml_round_trip(self):
        config = AgentLLMConfig(
            model="claude-opus-4-6",
            cheap_model="claude-haiku-4-5-20251001",
        )
        data = config.model_dump()
        restored = AgentLLMConfig.model_validate(data)
        assert restored.cheap_model == "claude-haiku-4-5-20251001"


# ============================================================================
# D1: LLMClient.with_model context manager
# ============================================================================

from src.llm.client import AnthropicClient, OpenAIClient, _ModelOverrideContext


class TestModelOverrideContext:
    def test_anthropic_override_and_restore(self):
        client = AnthropicClient(
            model="claude-opus-4-6",
            api_key="test",
            temperature=0.2,
            max_tokens=1024,
            max_retries=1,
        )
        assert client.model == "claude-opus-4-6"
        with client.with_model("claude-haiku-4-5-20251001") as c:
            assert c.model == "claude-haiku-4-5-20251001"
        assert client.model == "claude-opus-4-6"

    def test_openai_override_and_restore(self):
        client = OpenAIClient(
            model="gpt-4o",
            api_key="test",
            temperature=0.2,
            max_tokens=1024,
            max_retries=1,
        )
        assert client.model == "gpt-4o"
        with client.with_model("gpt-4o-mini") as c:
            assert c.model == "gpt-4o-mini"
        assert client.model == "gpt-4o"

    def test_restores_on_exception(self):
        client = AnthropicClient(
            model="claude-opus-4-6",
            api_key="test",
            temperature=0.2,
            max_tokens=1024,
            max_retries=1,
        )
        try:
            with client.with_model("claude-haiku-4-5-20251001"):
                raise ValueError("boom")
        except ValueError:
            pass
        assert client.model == "claude-opus-4-6"

    def test_same_model_noop(self):
        client = AnthropicClient(
            model="claude-opus-4-6",
            api_key="test",
            temperature=0.2,
            max_tokens=1024,
            max_retries=1,
        )
        with client.with_model("claude-opus-4-6") as c:
            assert c.model == "claude-opus-4-6"
        assert client.model == "claude-opus-4-6"


# ============================================================================
# D2: Tool backend abstraction
# ============================================================================

from src.tools.backend import (
    BackendRegistry,
    BuiltinDiffBackend,
    BuiltinSyntaxBackend,
    LocalGateBackend,
    ToolBackend,
    register_default_backends,
)


class DummyBackend(ToolBackend):
    @property
    def name(self) -> str:
        return "dummy"

    def check_available(self) -> bool:
        return True

    def run(self, **kwargs: Any) -> Any:
        return {"result": "dummy", **kwargs}


class UnavailableBackend(ToolBackend):
    @property
    def name(self) -> str:
        return "unavailable"

    def check_available(self) -> bool:
        return False

    def run(self, **kwargs: Any) -> Any:
        raise RuntimeError("not available")


class TestBackendRegistry:
    def setup_method(self):
        BackendRegistry.clear()

    def test_register_and_get(self):
        backend = DummyBackend()
        BackendRegistry.register("test_tool", "dummy", backend)
        assert BackendRegistry.get("test_tool") is backend

    def test_first_registration_becomes_active(self):
        b1 = DummyBackend()
        b2 = DummyBackend()
        BackendRegistry.register("tool", "first", b1)
        BackendRegistry.register("tool", "second", b2)
        assert BackendRegistry.active_name("tool") == "first"
        assert BackendRegistry.get("tool") is b1

    def test_set_active(self):
        b1 = DummyBackend()
        b2 = DummyBackend()
        BackendRegistry.register("tool", "first", b1)
        BackendRegistry.register("tool", "second", b2)
        BackendRegistry.set_active("tool", "second")
        assert BackendRegistry.get("tool") is b2

    def test_set_active_unknown_tool_raises(self):
        with pytest.raises(ValueError, match="Unknown tool"):
            BackendRegistry.set_active("nonexistent", "dummy")

    def test_set_active_unknown_backend_raises(self):
        BackendRegistry.register("tool", "a", DummyBackend())
        with pytest.raises(ValueError, match="not registered"):
            BackendRegistry.set_active("tool", "nonexistent")

    def test_get_unknown_tool_raises(self):
        with pytest.raises(ValueError, match="No backend"):
            BackendRegistry.get("nonexistent")

    def test_get_all(self):
        b1 = DummyBackend()
        b2 = DummyBackend()
        BackendRegistry.register("tool", "a", b1)
        BackendRegistry.register("tool", "b", b2)
        all_backends = BackendRegistry.get_all("tool")
        assert len(all_backends) == 2
        assert all_backends["a"] is b1
        assert all_backends["b"] is b2

    def test_get_all_unknown_returns_empty(self):
        assert BackendRegistry.get_all("nonexistent") == {}

    def test_registered_tools(self):
        BackendRegistry.register("tool_a", "x", DummyBackend())
        BackendRegistry.register("tool_b", "y", DummyBackend())
        tools = BackendRegistry.registered_tools()
        assert "tool_a" in tools
        assert "tool_b" in tools

    def test_clear(self):
        BackendRegistry.register("tool", "x", DummyBackend())
        BackendRegistry.clear()
        assert BackendRegistry.registered_tools() == []

    def test_set_active_on_register(self):
        b1 = DummyBackend()
        b2 = DummyBackend()
        BackendRegistry.register("tool", "first", b1)
        BackendRegistry.register("tool", "second", b2, set_active=True)
        assert BackendRegistry.active_name("tool") == "second"

    def test_run_dummy_backend(self):
        backend = DummyBackend()
        BackendRegistry.register("tool", "dummy", backend)
        result = BackendRegistry.get("tool").run(key="value")
        assert result == {"result": "dummy", "key": "value"}


class TestBuiltinSyntaxBackend:
    def test_name(self):
        assert BuiltinSyntaxBackend().name == "builtin"

    def test_available(self):
        assert BuiltinSyntaxBackend().check_available()

    def test_run_valid_python(self):
        result = BuiltinSyntaxBackend().run(file_path="test.py", content="x = 1")
        assert result.valid is True

    def test_run_invalid_python(self):
        result = BuiltinSyntaxBackend().run(file_path="test.py", content="def (")
        assert result.valid is False

    def test_run_valid_json(self):
        result = BuiltinSyntaxBackend().run(file_path="test.json", content='{"a": 1}')
        assert result.valid is True


class TestBuiltinDiffBackend:
    def test_name(self):
        assert BuiltinDiffBackend().name == "builtin"

    def test_available(self):
        assert BuiltinDiffBackend().check_available()

    def test_run_empty_diff(self):
        result = BuiltinDiffBackend().run(raw_diff="", file_path="test.py")
        assert result == []

    def test_run_with_hunk(self):
        diff = "@@ -1,3 +1,3 @@\n-old\n+new\n context\n"
        result = BuiltinDiffBackend().run(raw_diff=diff, file_path="test.py")
        assert len(result) == 1


class TestLocalGateBackend:
    def test_name(self):
        assert LocalGateBackend().name == "local"

    def test_available(self):
        assert LocalGateBackend().check_available()

    def test_run_raises(self):
        with pytest.raises(NotImplementedError):
            LocalGateBackend().run()


class TestRegisterDefaultBackends:
    def setup_method(self):
        BackendRegistry.clear()

    def test_registers_all_defaults(self):
        register_default_backends()
        assert "syntax_checker" in BackendRegistry.registered_tools()
        assert "diff_parser" in BackendRegistry.registered_tools()
        assert "gate_runner" in BackendRegistry.registered_tools()

    def test_idempotent(self):
        register_default_backends()
        register_default_backends()
        assert len(BackendRegistry.get_all("syntax_checker")) == 1

    def test_active_names(self):
        register_default_backends()
        assert BackendRegistry.active_name("syntax_checker") == "builtin"
        assert BackendRegistry.active_name("diff_parser") == "builtin"
        assert BackendRegistry.active_name("gate_runner") == "local"
