import yaml
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from src.cli.env import get_env_path, read_env_file, write_env_file

console = Console()

DEFAULT_CONFIG_NAME = "merge-config.yaml"


def init_command_impl() -> None:
    console.print(
        Panel(
            "[bold cyan]Code Merge System - Interactive Setup[/bold cyan]\n"
            "This wizard will guide you through configuration.",
            title="merge init",
            border_style="cyan",
        )
    )

    # --- Step 1: Repository settings ---
    console.print("\n[bold yellow]Step 1/4:[/bold yellow] Repository Settings\n")

    repo_path = Prompt.ask(
        "  Repository path",
        default=".",
    )
    upstream_ref = Prompt.ask(
        "  Upstream branch ref",
        default="upstream/main",
    )
    fork_ref = Prompt.ask(
        "  Fork / downstream branch ref",
        default="origin/main",
    )
    project_context = Prompt.ask(
        "  Project description (helps LLM understand your code)",
        default="",
    )

    # --- Step 2: API Keys ---
    console.print("\n[bold yellow]Step 2/4:[/bold yellow] LLM API Keys\n")

    env_path = get_env_path()
    existing_env = read_env_file(env_path)

    anthropic_key = _prompt_api_key(
        "ANTHROPIC_API_KEY",
        existing_env.get("ANTHROPIC_API_KEY", ""),
        required=True,
    )
    anthropic_base_url = _prompt_base_url(
        "Anthropic",
        existing_env.get("ANTHROPIC_BASE_URL", ""),
    )
    openai_key = _prompt_api_key(
        "OPENAI_API_KEY",
        existing_env.get("OPENAI_API_KEY", ""),
        required=True,
    )
    openai_base_url = _prompt_base_url(
        "OpenAI",
        existing_env.get("OPENAI_BASE_URL", ""),
    )
    github_token = _prompt_api_key(
        "GITHUB_TOKEN",
        existing_env.get("GITHUB_TOKEN", ""),
        required=False,
    )

    # --- Step 3: Thresholds ---
    console.print("\n[bold yellow]Step 3/4:[/bold yellow] Merge Thresholds\n")

    use_defaults = Confirm.ask(
        "  Use default thresholds? (auto_merge=0.85, risk_low=0.3, risk_high=0.6)",
        default=True,
    )

    if use_defaults:
        auto_merge_confidence = 0.85
        risk_score_low = 0.30
        risk_score_high = 0.60
    else:
        auto_merge_confidence = _prompt_float(
            "  Auto-merge confidence threshold", 0.85, 0.0, 1.0
        )
        risk_score_low = _prompt_float("  Risk score LOW threshold", 0.30, 0.0, 1.0)
        risk_score_high = _prompt_float("  Risk score HIGH threshold", 0.60, 0.0, 1.0)

    # --- Step 4: Output settings ---
    console.print("\n[bold yellow]Step 4/4:[/bold yellow] Output Settings\n")

    output_dir = Prompt.ask("  Output directory", default="./outputs")

    config_path = Prompt.ask(
        "  Config file save path",
        default=str(Path(repo_path).resolve() / DEFAULT_CONFIG_NAME),
    )

    # --- Write .env ---
    env_entries: dict[str, str] = {}
    if anthropic_key:
        env_entries["ANTHROPIC_API_KEY"] = anthropic_key
    if anthropic_base_url:
        env_entries["ANTHROPIC_BASE_URL"] = anthropic_base_url
    if openai_key:
        env_entries["OPENAI_API_KEY"] = openai_key
    if openai_base_url:
        env_entries["OPENAI_BASE_URL"] = openai_base_url
    if github_token:
        env_entries["GITHUB_TOKEN"] = github_token

    if env_entries:
        write_env_file(env_path, env_entries)
        console.print(f"\n  [green]API Keys saved to:[/green] {env_path}")

    # --- Write config YAML ---
    config_data = _build_config(
        repo_path=repo_path,
        upstream_ref=upstream_ref,
        fork_ref=fork_ref,
        project_context=project_context,
        auto_merge_confidence=auto_merge_confidence,
        risk_score_low=risk_score_low,
        risk_score_high=risk_score_high,
        output_dir=output_dir,
        has_github_token=bool(github_token),
        anthropic_base_url=anthropic_base_url,
        openai_base_url=openai_base_url,
    )

    config_file = Path(config_path)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        yaml.dump(config_data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    console.print(f"  [green]Config saved to:[/green]  {config_file}")

    # --- Summary ---
    console.print(
        Panel(
            f"[green]Setup complete![/green]\n\n"
            f"  Run merge:  [cyan]merge run --config {config_file}[/cyan]\n"
            f"  Validate:   [cyan]merge validate --config {config_file}[/cyan]\n"
            f"  Env file:   {env_path}",
            title="Next Steps",
            border_style="green",
        )
    )


def _prompt_api_key(name: str, existing: str, required: bool) -> str:
    masked = _mask_key(existing) if existing else ""
    hint = f" (current: {masked})" if masked else ""
    label = f"  {name}{hint}"
    if not required:
        label += " [optional]"

    value = Prompt.ask(label, default="", show_default=False)

    if not value and existing:
        return existing
    if not value and required:
        console.print(
            f"    [yellow]Warning: {name} not set. Some agents will fail.[/yellow]"
        )
    return value


def _prompt_base_url(provider_name: str, existing: str) -> str:
    hint = f" (current: {existing})" if existing else ""
    label = f"  {provider_name} Base URL{hint} [optional, press Enter to skip]"
    value = Prompt.ask(label, default="", show_default=False)
    if not value and existing:
        return existing
    return value


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


def _prompt_float(label: str, default: float, min_val: float, max_val: float) -> float:
    while True:
        raw = Prompt.ask(label, default=str(default))
        try:
            val = float(raw)
            if min_val <= val <= max_val:
                return val
            console.print(f"    [red]Must be between {min_val} and {max_val}[/red]")
        except ValueError:
            console.print("    [red]Please enter a valid number[/red]")


def _build_config(
    repo_path: str,
    upstream_ref: str,
    fork_ref: str,
    project_context: str,
    auto_merge_confidence: float,
    risk_score_low: float,
    risk_score_high: float,
    output_dir: str,
    has_github_token: bool,
    anthropic_base_url: str,
    openai_base_url: str,
) -> dict[str, object]:
    anthropic_agent: dict[str, object] = {
        "provider": "anthropic",
        "api_key_env": "ANTHROPIC_API_KEY",
    }
    if anthropic_base_url:
        anthropic_agent["api_base_url_env"] = "ANTHROPIC_BASE_URL"

    openai_agent: dict[str, object] = {
        "provider": "openai",
        "api_key_env": "OPENAI_API_KEY",
    }
    if openai_base_url:
        openai_agent["api_base_url_env"] = "OPENAI_BASE_URL"

    config: dict[str, object] = {
        "upstream_ref": upstream_ref,
        "fork_ref": fork_ref,
        "working_branch": "merge/auto-{timestamp}",
        "repo_path": repo_path,
        "project_context": project_context,
        "max_files_per_run": 500,
        "max_plan_revision_rounds": 2,
        "agents": {
            "planner": {
                **anthropic_agent,
                "model": "claude-opus-4-6",
            },
            "planner_judge": {
                **openai_agent,
                "model": "gpt-4o",
            },
            "conflict_analyst": {
                **anthropic_agent,
                "model": "claude-sonnet-4-6",
            },
            "executor": {
                **openai_agent,
                "model": "gpt-4o",
                "temperature": 0.1,
            },
            "judge": {
                **anthropic_agent,
                "model": "claude-opus-4-6",
                "temperature": 0.1,
            },
            "human_interface": {
                **anthropic_agent,
                "model": "claude-haiku-4-5-20251001",
            },
        },
        "thresholds": {
            "auto_merge_confidence": auto_merge_confidence,
            "human_escalation": 0.60,
            "risk_score_low": risk_score_low,
            "risk_score_high": risk_score_high,
        },
        "output": {
            "directory": output_dir,
            "formats": ["json", "markdown"],
        },
    }

    if has_github_token:
        config["github"] = {
            "enabled": True,
            "token_env": "GITHUB_TOKEN",
        }

    return config
