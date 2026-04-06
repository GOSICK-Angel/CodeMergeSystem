import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class TraceLogger:
    def __init__(self, debug_dir: str, run_id: str):
        self._path = Path(debug_dir) / f"llm_traces_{run_id}.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def record(
        self,
        agent: str,
        model: str,
        provider: str,
        prompt_chars: int,
        response_chars: int,
        elapsed_seconds: float,
        attempt: int,
        max_attempts: int,
        success: bool,
        error: str | None = None,
        prompt_preview: str = "",
        response_preview: str = "",
    ) -> None:
        entry: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent,
            "model": model,
            "provider": provider,
            "prompt_chars": prompt_chars,
            "response_chars": response_chars,
            "elapsed_s": round(elapsed_seconds, 2),
            "attempt": attempt,
            "max_attempts": max_attempts,
            "success": success,
        }
        if error:
            entry["error"] = error
        if prompt_preview:
            entry["prompt_preview"] = prompt_preview[:300]
        if response_preview:
            entry["response_preview"] = response_preview[:300]

        line = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    @property
    def path(self) -> Path:
        return self._path
