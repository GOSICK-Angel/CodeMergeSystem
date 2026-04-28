import json

from src.memory.hit_tracker import MemoryHitTracker


def test_empty_tracker_summary():
    tracker = MemoryHitTracker()
    summary = tracker.summary()
    assert summary["total_calls"] == 0
    assert summary["hit_calls"] == 0
    assert summary["hit_rate"] == 0.0
    assert summary["by_phase"] == {}
    assert summary["by_layer"] == {}


def test_records_hit_when_any_layer_has_content():
    tracker = MemoryHitTracker()
    tracker.record_call(
        "planning",
        {"l0": 0, "l1_patterns": 3, "l1_decisions": 0, "l2": 0},
    )
    summary = tracker.summary()
    assert summary["total_calls"] == 1
    assert summary["hit_calls"] == 1
    assert summary["hit_rate"] == 1.0
    assert summary["by_layer"] == {"l1_patterns": 3}
    assert summary["by_phase"]["planning"]["calls"] == 1
    assert summary["by_phase"]["planning"]["hit_calls"] == 1


def test_records_miss_when_all_layers_empty():
    tracker = MemoryHitTracker()
    tracker.record_call(
        "auto_merge",
        {"l0": 0, "l1_patterns": 0, "l1_decisions": 0, "l2": 0},
    )
    summary = tracker.summary()
    assert summary["total_calls"] == 1
    assert summary["hit_calls"] == 0
    assert summary["hit_rate"] == 0.0
    assert summary["by_layer"] == {}
    assert summary["by_phase"]["auto_merge"]["hit_calls"] == 0


def test_aggregates_across_phases():
    tracker = MemoryHitTracker()
    tracker.record_call(
        "planning", {"l0": 2, "l1_patterns": 0, "l1_decisions": 0, "l2": 0}
    )
    tracker.record_call(
        "planning", {"l0": 0, "l1_patterns": 0, "l1_decisions": 0, "l2": 0}
    )
    tracker.record_call(
        "conflict_analysis", {"l0": 0, "l1_patterns": 1, "l1_decisions": 2, "l2": 5}
    )
    summary = tracker.summary()
    assert summary["total_calls"] == 3
    assert summary["hit_calls"] == 2
    assert summary["hit_rate"] == 2 / 3
    assert summary["by_layer"] == {
        "l0": 2,
        "l1_patterns": 1,
        "l1_decisions": 2,
        "l2": 5,
    }
    assert summary["by_phase"]["planning"]["calls"] == 2
    assert summary["by_phase"]["planning"]["hit_calls"] == 1
    assert summary["by_phase"]["conflict_analysis"]["hit_calls"] == 1


def test_layered_loader_records_hits():
    from src.memory.layered_loader import LayeredMemoryLoader
    from src.memory.store import MemoryStore
    from src.memory.models import MergeMemory, PhaseSummary

    memory = MergeMemory(
        codebase_profile={"language": "python", "framework": "fastapi"},
        phase_summaries={
            "planning": PhaseSummary(
                phase="planning",
                files_processed=8507,
                key_decisions=["Plan generated"],
                patterns_discovered=["35 C-class files in tools/linear/"],
            ),
        },
    )
    store = MemoryStore(memory)
    tracker = MemoryHitTracker()
    loader = LayeredMemoryLoader(store, tracker)

    text = loader.load_for_agent("planning", file_paths=None)
    assert "Project Profile" in text
    assert "Phase Context" in text

    summary = tracker.summary()
    assert summary["total_calls"] == 1
    assert summary["hit_calls"] == 1
    assert summary["by_layer"]["l0"] == 2
    assert summary["by_layer"]["l1_patterns"] == 1


def test_persist_writes_sidecar(tmp_path):
    sidecar = tmp_path / "memory_hit_stats.json"
    tracker = MemoryHitTracker(persist_path=sidecar)
    tracker.record_call(
        "planning", {"l0": 1, "l1_patterns": 2, "l1_decisions": 0, "l2": 3}
    )
    assert sidecar.exists()
    payload = json.loads(sidecar.read_text())
    assert payload["schema_version"] == 1
    assert payload["calls_by_phase"] == {"planning": 1}
    assert payload["hit_calls_by_phase"] == {"planning": 1}
    assert payload["entries_by_phase_layer"]["planning"] == {
        "l0": 1,
        "l1_patterns": 2,
        "l2": 3,
    }


def test_load_resumes_from_sidecar(tmp_path):
    sidecar = tmp_path / "memory_hit_stats.json"
    sidecar.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "calls_by_phase": {"planning": 5, "auto_merge": 3},
                "hit_calls_by_phase": {"planning": 4, "auto_merge": 2},
                "entries_by_phase_layer": {
                    "planning": {"l0": 10, "l1_patterns": 8},
                    "auto_merge": {"l2": 5},
                },
            }
        )
    )
    tracker = MemoryHitTracker(persist_path=sidecar)
    summary = tracker.summary()
    assert summary["total_calls"] == 8
    assert summary["hit_calls"] == 6
    assert summary["by_phase"]["planning"]["calls"] == 5
    assert summary["by_phase"]["planning"]["hit_calls"] == 4
    assert summary["by_layer"]["l0"] == 10
    assert summary["by_layer"]["l2"] == 5


def test_set_persist_path_after_init_loads_existing(tmp_path):
    sidecar = tmp_path / "memory_hit_stats.json"
    sidecar.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "calls_by_phase": {"planning": 2},
                "hit_calls_by_phase": {"planning": 1},
                "entries_by_phase_layer": {"planning": {"l0": 1}},
            }
        )
    )
    tracker = MemoryHitTracker()
    assert tracker.summary()["total_calls"] == 0
    tracker.set_persist_path(sidecar)
    assert tracker.summary()["total_calls"] == 2
    tracker.record_call(
        "auto_merge", {"l0": 0, "l1_patterns": 1, "l1_decisions": 0, "l2": 0}
    )
    payload = json.loads(sidecar.read_text())
    assert payload["calls_by_phase"]["planning"] == 2
    assert payload["calls_by_phase"]["auto_merge"] == 1


def test_invalid_sidecar_schema_is_ignored(tmp_path):
    sidecar = tmp_path / "memory_hit_stats.json"
    sidecar.write_text(
        json.dumps({"schema_version": 999, "calls_by_phase": {"planning": 5}})
    )
    tracker = MemoryHitTracker(persist_path=sidecar)
    assert tracker.summary()["total_calls"] == 0


def test_corrupt_sidecar_is_ignored(tmp_path):
    sidecar = tmp_path / "memory_hit_stats.json"
    sidecar.write_text("{not valid json")
    tracker = MemoryHitTracker(persist_path=sidecar)
    assert tracker.summary()["total_calls"] == 0


def _build_test_store():
    from src.memory.models import MergeMemory, PhaseSummary
    from src.memory.store import MemoryStore

    memory = MergeMemory(
        codebase_profile={"language": "python"},
        phase_summaries={
            "auto_merge": PhaseSummary(
                phase="auto_merge",
                files_processed=100,
                key_decisions=["Plan generated"],
                patterns_discovered=["models/tongyi double-changed"],
            ),
        },
    )
    return MemoryStore(memory)


def _build_test_llm_config():
    from src.models.config import AgentLLMConfig

    return AgentLLMConfig(
        provider="anthropic",
        model="claude-haiku-4-5",
        temperature=0.2,
        max_tokens=4096,
        max_retries=1,
        api_key_env="ANTHROPIC_API_KEY",
    )


def test_prompt_builder_propagates_tracker_to_loader(tmp_path):
    """AgentPromptBuilder must pass tracker through to LayeredMemoryLoader."""
    from src.llm.prompt_builders import AgentPromptBuilder

    sidecar = tmp_path / "memory_hit_stats.json"
    tracker = MemoryHitTracker(persist_path=sidecar)
    store = _build_test_store()
    config = _build_test_llm_config()

    builder = AgentPromptBuilder(config, store, tracker)
    text = builder.build_memory_context_text(
        ["models/tongyi/llm.py"], current_phase="auto_merge"
    )

    assert "Project Profile" in text
    assert "Phase Context" in text

    summary = tracker.summary()
    assert summary["total_calls"] == 1
    assert summary["hit_calls"] == 1
    assert summary["by_phase"]["auto_merge"]["calls"] == 1

    assert sidecar.exists()
    payload = json.loads(sidecar.read_text())
    assert payload["calls_by_phase"]["auto_merge"] == 1


def test_prompt_builder_without_phase_skips_loader_path(tmp_path):
    """Backward-compat: when current_phase is None the legacy path is used and tracker stays untouched."""
    from src.llm.prompt_builders import AgentPromptBuilder

    sidecar = tmp_path / "memory_hit_stats.json"
    tracker = MemoryHitTracker(persist_path=sidecar)
    store = _build_test_store()
    config = _build_test_llm_config()

    builder = AgentPromptBuilder(config, store, tracker)
    builder.build_memory_context_text(["models/tongyi/llm.py"])

    assert tracker.summary()["total_calls"] == 0
    assert not sidecar.exists()


def test_prompt_builder_without_tracker_works(tmp_path):
    """Backward-compat: AgentPromptBuilder constructed without tracker works."""
    from src.llm.prompt_builders import AgentPromptBuilder

    store = _build_test_store()
    config = _build_test_llm_config()

    builder = AgentPromptBuilder(config, store)
    text = builder.build_memory_context_text(
        ["models/tongyi/llm.py"], current_phase="auto_merge"
    )
    assert "Project Profile" in text
