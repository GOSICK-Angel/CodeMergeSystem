---
name: run-integration
description: Guide for running integration tests in CodeMergeSystem. Integration tests require real API keys and are not part of CI — use this skill to set up and run them locally.
---

Help the user run integration tests for CodeMergeSystem.

## Prerequisites

Integration tests require real API keys set in the environment:
```bash
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
```

Keys can also be placed in `.env` at the project root (loaded automatically by the test fixtures).

## Running Integration Tests

```bash
# All integration tests
pytest tests/integration/ -v

# Single test by name
pytest tests/integration/ -k "test_name" -v

# With coverage
pytest tests/integration/ --cov=src -v
```

## Key Fixtures (tests/integration/conftest.py)

- `patch_llm_factory` — replace real LLM clients with mocks for hybrid runs
- `FakeGitTool` — in-memory git operations, no real repo needed
- `tmp_repo` — creates a temporary git repo for end-to-end scenarios

## Common Issues

- **AuthenticationError**: check that ANTHROPIC_API_KEY / OPENAI_API_KEY are valid and not expired
- **Slow tests**: integration tests make real LLM calls — expect 30–120s per test
- **State pollution**: each test should create its own MergeState; never share state between tests

After running, report which tests passed/failed and summarize any errors.
