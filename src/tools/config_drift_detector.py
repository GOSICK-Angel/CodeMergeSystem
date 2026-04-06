from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field


class ConfigDrift(BaseModel):
    key: str
    code_default: str | None = None
    env_default: str | None = None
    docker_default: str | None = None
    impact: str = ""
    suggestion: str = ""


class ConfigDriftReport(BaseModel):
    drifts: list[ConfigDrift] = Field(default_factory=list)
    total_keys_checked: int = 0
    drift_count: int = 0

    @property
    def has_drifts(self) -> bool:
        return self.drift_count > 0


_ENV_LINE_RE = re.compile(
    r"^\s*(?!#)([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", re.MULTILINE
)

_PYTHON_GETENV_RE = re.compile(
    r"""os\.(?:environ\.get|getenv)\(\s*["']([A-Za-z_][A-Za-z0-9_]*)["']\s*(?:,\s*["']?([\w.]*?)["']?)?\s*\)""",
)


class ConfigDriftDetector:
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    def detect_drift(
        self,
        code_defaults: dict[str, str],
        env_defaults: dict[str, str],
        docker_env_defaults: dict[str, str],
    ) -> list[ConfigDrift]:
        all_keys = sorted(
            set(code_defaults) | set(env_defaults) | set(docker_env_defaults)
        )
        drifts: list[ConfigDrift] = []

        for key in all_keys:
            code_val = code_defaults.get(key)
            env_val = env_defaults.get(key)
            docker_val = docker_env_defaults.get(key)

            present = [v for v in (code_val, env_val, docker_val) if v is not None]
            if len(present) < 2:
                continue

            unique_values = set(present)
            if len(unique_values) <= 1:
                continue

            sources: list[str] = []
            if code_val is not None:
                sources.append(f"code={code_val}")
            if env_val is not None:
                sources.append(f"env={env_val}")
            if docker_val is not None:
                sources.append(f"docker={docker_val}")

            drifts.append(
                ConfigDrift(
                    key=key,
                    code_default=code_val,
                    env_default=env_val,
                    docker_default=docker_val,
                    impact=f"Config key '{key}' has divergent defaults: {', '.join(sources)}",
                    suggestion=f"Align defaults for '{key}' across all sources",
                )
            )

        return drifts

    def detect_drift_from_files(
        self,
        env_files: list[str] | None = None,
        docker_env_files: list[str] | None = None,
        code_files: list[str] | None = None,
    ) -> ConfigDriftReport:
        env_defaults = self._parse_env_files(env_files or [".env.example", ".env"])
        docker_defaults = self._parse_env_files(
            docker_env_files or ["docker/.env", "docker/.env.example"]
        )
        code_defaults = self._parse_code_defaults(code_files or [])

        drifts = self.detect_drift(code_defaults, env_defaults, docker_defaults)
        all_keys = set(code_defaults) | set(env_defaults) | set(docker_defaults)

        return ConfigDriftReport(
            drifts=drifts,
            total_keys_checked=len(all_keys),
            drift_count=len(drifts),
        )

    def _parse_env_files(self, file_patterns: list[str]) -> dict[str, str]:
        defaults: dict[str, str] = {}
        for pattern in file_patterns:
            path = self.repo_path / pattern
            if not path.exists():
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue
            for match in _ENV_LINE_RE.finditer(content):
                key = match.group(1)
                value = match.group(2).strip().strip("'\"")
                defaults[key] = value
        return defaults

    def _parse_code_defaults(self, file_paths: list[str]) -> dict[str, str]:
        defaults: dict[str, str] = {}
        for fp in file_paths:
            path = self.repo_path / fp
            if not path.exists():
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue
            for match in _PYTHON_GETENV_RE.finditer(content):
                key = match.group(1)
                val = match.group(2)
                if val is not None and val != "":
                    defaults[key] = val
        return defaults

    def find_env_files(self) -> tuple[list[str], list[str]]:
        env_files: list[str] = []
        docker_env_files: list[str] = []

        env_names = [".env", ".env.example", ".env.sample", ".env.template"]
        for name in env_names:
            if (self.repo_path / name).exists():
                env_files.append(name)

        docker_dirs = ["docker", "dev"]
        for d in docker_dirs:
            for name in env_names:
                path = f"{d}/{name}"
                if (self.repo_path / path).exists():
                    docker_env_files.append(path)

        return env_files, docker_env_files
