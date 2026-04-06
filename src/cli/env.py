from pathlib import Path

ENV_KEYS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "GITHUB_TOKEN",
)


def get_env_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / ".env"


def load_env() -> None:
    from dotenv import load_dotenv

    env_path = get_env_path()
    if env_path.exists():
        load_dotenv(env_path, override=False)


def read_env_file(env_path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    if not env_path.exists():
        return entries
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            entries[key.strip()] = value.strip().strip("\"'")
    return entries


def write_env_file(env_path: Path, entries: dict[str, str]) -> None:
    existing = read_env_file(env_path)
    merged = {**existing, **entries}
    lines: list[str] = []
    for key, value in sorted(merged.items()):
        if value:
            lines.append(f'{key}="{value}"')
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
