"""P1-1: ReverseImpactScanner.

For each upstream ``InterfaceChange.symbol``, grep the fork-only scope
(D_EXTRA files + customization files + user-supplied extra globs) to find
call sites that may still assume the old interface.

Conservative: uses a word-boundary regex so ``foo`` does not match ``foobar``.
Only text search — does not resolve imports/namespaces.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Iterable

from src.tools.interface_change_extractor import InterfaceChange


class ReverseImpactScanner:
    def __init__(self, repo_path: Path | str, max_files_per_symbol: int = 100):
        self.repo_path = Path(repo_path)
        self.max_files_per_symbol = max_files_per_symbol

    def scan(
        self,
        changes: Iterable[InterfaceChange],
        fork_only_files: Iterable[str],
        extra_globs: Iterable[str] = (),
    ) -> dict[str, list[str]]:
        """Return ``{symbol: [file_path, ...]}`` for symbols referenced in
        the fork-only scope."""
        scope = self._resolve_scope(fork_only_files, extra_globs)
        impacts: dict[str, list[str]] = {}
        cache: dict[str, str] = {}

        for change in changes:
            symbol = change.symbol
            if not symbol:
                continue
            if symbol in impacts:
                continue
            pattern = re.compile(rf"\b{re.escape(symbol)}\b")

            hits: list[str] = []
            for fp in scope:
                if len(hits) >= self.max_files_per_symbol:
                    break
                content = cache.get(fp)
                if content is None:
                    abs_path = self.repo_path / fp
                    if not abs_path.is_file():
                        cache[fp] = ""
                        continue
                    try:
                        content = abs_path.read_text(encoding="utf-8")
                    except (UnicodeDecodeError, OSError):
                        content = ""
                    cache[fp] = content
                if content and pattern.search(content):
                    hits.append(fp)

            if hits:
                impacts[symbol] = hits

        return impacts

    def _resolve_scope(
        self,
        fork_only_files: Iterable[str],
        extra_globs: Iterable[str],
    ) -> list[str]:
        files: set[str] = set(fork_only_files)

        extra_list = list(extra_globs)
        if extra_list:
            all_files = [
                str(p.relative_to(self.repo_path))
                for p in self.repo_path.rglob("*")
                if p.is_file()
            ]
            for glob_pat in extra_list:
                for fp in all_files:
                    if fnmatch.fnmatch(fp, glob_pat):
                        files.add(fp)
        return sorted(files)
