"""P0-2: Shadow-path conflict detector.

Detects cross-extension / module-vs-package name collisions that survive
text-level merges but break at runtime module resolution.

No repository-specific knowledge — rules are language-agnostic defaults
plus user-supplied extras via ``MergeConfig.shadow_rules_extra``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Iterable

from pydantic import BaseModel

from src.models.config import ShadowRuleConfig


@dataclass(frozen=True)
class ShadowRule:
    exts_a: frozenset[str] = frozenset()
    exts_b: frozenset[str] = frozenset()
    module_vs_package: bool = False
    description: str = ""

    @classmethod
    def from_config(cls, cfg: ShadowRuleConfig) -> "ShadowRule":
        return cls(
            exts_a=frozenset(cfg.exts_a),
            exts_b=frozenset(cfg.exts_b),
            module_vs_package=cfg.module_vs_package,
            description=cfg.description,
        )


DEFAULT_SHADOW_RULES: tuple[ShadowRule, ...] = (
    ShadowRule(
        exts_a=frozenset({".ts"}),
        exts_b=frozenset({".tsx"}),
        description="TypeScript .ts vs .tsx resolution ambiguity",
    ),
    ShadowRule(
        exts_a=frozenset({".js"}),
        exts_b=frozenset({".jsx", ".mjs", ".cjs"}),
        description="JS extension variants",
    ),
    ShadowRule(
        module_vs_package=True,
        description="Python m.py vs m/__init__.py",
    ),
    ShadowRule(
        exts_a=frozenset({".java"}),
        exts_b=frozenset({".kt"}),
        description="Java vs Kotlin same class name",
    ),
    ShadowRule(
        exts_a=frozenset({".h"}),
        exts_b=frozenset({".hpp"}),
        description="C/C++ header variants",
    ),
    ShadowRule(
        exts_a=frozenset({".yaml"}),
        exts_b=frozenset({".yml"}),
        description="YAML file extension variants",
    ),
    ShadowRule(
        exts_a=frozenset({".json"}),
        exts_b=frozenset({".json5"}),
        description="JSON vs JSON5",
    ),
)


class ShadowConflict(BaseModel):
    """A pair of files that shadow each other under the same logical name."""

    logical_name: str
    path_a: str
    path_b: str
    rule_description: str = ""

    model_config = {"frozen": True}


@dataclass
class ShadowConflictDetector:
    rules: tuple[ShadowRule, ...] = field(default_factory=lambda: DEFAULT_SHADOW_RULES)

    @classmethod
    def from_config(
        cls, extra: list[ShadowRuleConfig] | None = None
    ) -> "ShadowConflictDetector":
        extra_rules = tuple(ShadowRule.from_config(c) for c in (extra or []))
        return cls(rules=DEFAULT_SHADOW_RULES + extra_rules)

    def detect(self, file_paths: Iterable[str]) -> list[ShadowConflict]:
        paths = sorted({p for p in file_paths if p})
        conflicts: list[ShadowConflict] = []
        seen: set[tuple[str, str]] = set()

        for rule in self.rules:
            if rule.module_vs_package:
                conflicts.extend(self._detect_module_vs_package(paths, rule, seen))
            elif rule.exts_a and rule.exts_b:
                conflicts.extend(self._detect_ext_pair(paths, rule, seen))

        return conflicts

    @staticmethod
    def _detect_ext_pair(
        paths: list[str],
        rule: ShadowRule,
        seen: set[tuple[str, str]],
    ) -> list[ShadowConflict]:
        by_stem_a: dict[str, list[str]] = {}
        by_stem_b: dict[str, list[str]] = {}
        for p in paths:
            pp = PurePosixPath(p)
            ext = pp.suffix
            if not ext:
                continue
            stem = str(pp.with_suffix(""))
            if ext in rule.exts_a:
                by_stem_a.setdefault(stem, []).append(p)
            elif ext in rule.exts_b:
                by_stem_b.setdefault(stem, []).append(p)

        results: list[ShadowConflict] = []
        for stem, a_paths in by_stem_a.items():
            if stem not in by_stem_b:
                continue
            for a in a_paths:
                for b in by_stem_b[stem]:
                    pair = sorted((a, b))
                    key: tuple[str, str] = (pair[0], pair[1])
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(
                        ShadowConflict(
                            logical_name=stem,
                            path_a=a,
                            path_b=b,
                            rule_description=rule.description,
                        )
                    )
        return results

    @staticmethod
    def _detect_module_vs_package(
        paths: list[str],
        rule: ShadowRule,
        seen: set[tuple[str, str]],
    ) -> list[ShadowConflict]:
        py_modules: dict[str, str] = {}
        pkg_inits: dict[str, str] = {}
        for p in paths:
            pp = PurePosixPath(p)
            if pp.suffix != ".py":
                continue
            if pp.name == "__init__.py":
                pkg_name = str(pp.parent)
                if pkg_name and pkg_name != ".":
                    pkg_inits[pkg_name] = p
            else:
                module_key = str(pp.with_suffix(""))
                py_modules[module_key] = p

        results: list[ShadowConflict] = []
        for module_key, module_path in py_modules.items():
            if module_key in pkg_inits:
                a = module_path
                b = pkg_inits[module_key]
                pair = sorted((a, b))
                key: tuple[str, str] = (pair[0], pair[1])
                if key in seen:
                    continue
                seen.add(key)
                results.append(
                    ShadowConflict(
                        logical_name=module_key,
                        path_a=a,
                        path_b=b,
                        rule_description=rule.description,
                    )
                )
        return results
