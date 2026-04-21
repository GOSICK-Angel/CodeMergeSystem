"""Unit tests for ParallelFileRunner (O-C)."""

import asyncio
from unittest.mock import patch

import pytest

from src.core.parallel_file_runner import ParallelFileRunner


async def _ok(key: str) -> str:
    return f"result:{key}"


async def _fail(key: str) -> str:
    raise ValueError(f"boom:{key}")


async def _slow_ok(key: str) -> str:
    await asyncio.sleep(0)
    return f"slow:{key}"


class TestRunFiles:
    async def test_empty_keys_returns_empty_dict(self) -> None:
        runner = ParallelFileRunner(concurrency=4)
        result = await runner.run_files([], _ok)
        assert result == {}

    async def test_all_success(self) -> None:
        runner = ParallelFileRunner(concurrency=4)
        result = await runner.run_files(["a", "b", "c"], _ok)
        assert result == {"a": "result:a", "b": "result:b", "c": "result:c"}

    async def test_single_failure_isolated(self) -> None:
        """A failing handler must not cancel sibling tasks."""

        async def mixed(key: str) -> str:
            if key == "b":
                raise RuntimeError("only b fails")
            return f"ok:{key}"

        runner = ParallelFileRunner(concurrency=4)
        result = await runner.run_files(["a", "b", "c"], mixed)

        assert result["a"] == "ok:a"
        assert isinstance(result["b"], RuntimeError)
        assert result["c"] == "ok:c"

    async def test_all_failures_captured(self) -> None:
        runner = ParallelFileRunner(concurrency=4)
        result = await runner.run_files(["x", "y"], _fail)
        assert all(isinstance(v, ValueError) for v in result.values())

    async def test_concurrency_limit_respected(self) -> None:
        """At most `concurrency` handlers run at the same time."""
        max_concurrent = 0
        in_flight = 0

        async def counting(key: str) -> str:
            nonlocal max_concurrent, in_flight
            in_flight += 1
            max_concurrent = max(max_concurrent, in_flight)
            await asyncio.sleep(0)
            in_flight -= 1
            return key

        runner = ParallelFileRunner(concurrency=2)
        await runner.run_files(["a", "b", "c", "d", "e"], counting)
        assert max_concurrent <= 2

    async def test_concurrency_one_is_serial(self) -> None:
        order: list[str] = []

        async def track(key: str) -> str:
            order.append(f"start:{key}")
            await asyncio.sleep(0)
            order.append(f"end:{key}")
            return key

        runner = ParallelFileRunner(concurrency=1)
        await runner.run_files(["a", "b"], track)
        assert order == ["start:a", "end:a", "start:b", "end:b"]

    async def test_integer_keys(self) -> None:
        runner = ParallelFileRunner(concurrency=3)

        async def double(k: int) -> int:
            return k * 2

        result = await runner.run_files([1, 2, 3], double)
        assert result == {1: 2, 2: 4, 3: 6}


class TestFromApiKeyEnvList:
    def test_override_takes_precedence(self) -> None:
        runner = ParallelFileRunner.from_api_key_env_list(
            ["MISSING_KEY_A", "MISSING_KEY_B"], override=7
        )
        assert runner._concurrency == 7

    def test_counts_active_env_vars(self) -> None:
        with patch.dict(
            "os.environ",
            {"TEST_KEY_1": "sk-abc", "TEST_KEY_2": "sk-def"},
            clear=False,
        ):
            runner = ParallelFileRunner.from_api_key_env_list(
                ["TEST_KEY_1", "TEST_KEY_2", "TEST_KEY_3_MISSING"]
            )
        assert runner._concurrency == 2

    def test_no_active_keys_defaults_to_one(self) -> None:
        runner = ParallelFileRunner.from_api_key_env_list(
            ["DEFINITELY_MISSING_KEY_XYZ"]
        )
        assert runner._concurrency == 1

    def test_empty_env_list_defaults_to_one(self) -> None:
        runner = ParallelFileRunner.from_api_key_env_list([])
        assert runner._concurrency == 1

    def test_whitespace_only_env_var_not_counted(self) -> None:
        with patch.dict("os.environ", {"WS_KEY": "   "}, clear=False):
            runner = ParallelFileRunner.from_api_key_env_list(["WS_KEY"])
        assert runner._concurrency == 1

    def test_override_zero_clamped_to_one(self) -> None:
        runner = ParallelFileRunner(concurrency=0)
        assert runner._concurrency == 1
