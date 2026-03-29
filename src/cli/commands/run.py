import asyncio
import sys
import yaml
from pathlib import Path
from rich.console import Console
from src.models.config import MergeConfig
from src.models.state import MergeState, SystemStatus
from src.core.orchestrator import Orchestrator
from src.cli.exit_codes import (
    EXIT_SUCCESS,
    EXIT_NEEDS_HUMAN,
    EXIT_JUDGE_REJECTED,
    EXIT_PARTIAL_FAILURE,
    EXIT_CONFIG_ERROR,
    EXIT_UNKNOWN_ERROR,
)
from src.tools.ci_reporter import build_ci_summary, format_ci_summary


console = Console()


def _handle_ci_exit(final_state: MergeState, export_decisions: str | None) -> None:
    summary = build_ci_summary(final_state)
    print(format_ci_summary(summary))

    if final_state.status == SystemStatus.COMPLETED:
        if final_state.judge_verdict:
            from src.models.judge import VerdictType

            if final_state.judge_verdict.verdict == VerdictType.FAIL:
                sys.exit(EXIT_JUDGE_REJECTED)
        if final_state.errors:
            sys.exit(EXIT_PARTIAL_FAILURE)
        sys.exit(EXIT_SUCCESS)
    elif final_state.status == SystemStatus.AWAITING_HUMAN:
        if export_decisions:
            try:
                from src.tools.decision_template import export_decision_template

                pending = [
                    req
                    for req in final_state.human_decision_requests.values()
                    if req.human_decision is None
                ]
                if pending:
                    export_decision_template(pending, export_decisions)
            except ImportError:
                pass
        sys.exit(EXIT_NEEDS_HUMAN)
    elif final_state.status == SystemStatus.FAILED:
        sys.exit(EXIT_UNKNOWN_ERROR)
    else:
        sys.exit(EXIT_UNKNOWN_ERROR)


def run_command_impl(
    config_path: str,
    dry_run: bool,
    export_decisions: str | None = None,
    ci: bool = False,
    github_pr: int | None = None,
) -> None:
    config_file = Path(config_path)
    if not config_file.exists():
        if ci:
            print('{"status": "error", "message": "Config file not found"}')
            sys.exit(EXIT_CONFIG_ERROR)
        console.print(f"[red]Config file not found: {config_path}[/red]")
        sys.exit(EXIT_CONFIG_ERROR)

    try:
        raw_config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        config = MergeConfig.model_validate(raw_config)
    except Exception as e:
        if ci:
            print(f'{{"status": "error", "message": "Invalid config: {e}"}}')
            sys.exit(EXIT_CONFIG_ERROR)
        console.print(f"[red]Invalid config: {e}[/red]")
        sys.exit(EXIT_CONFIG_ERROR)

    if dry_run and not ci:
        console.print("[yellow]Dry run mode: will analyze but not merge[/yellow]")

    state = MergeState(config=config)
    if not ci:
        console.print(f"[blue]Starting merge run {state.run_id}[/blue]")
        console.print(f"  Upstream: {config.upstream_ref}")
        console.print(f"  Fork: {config.fork_ref}")

    orchestrator = Orchestrator(config)

    async def execute() -> MergeState:
        return await orchestrator.run(state)

    final_state = asyncio.run(execute())

    if ci:
        _handle_ci_exit(final_state, export_decisions)
        return

    status_val = (
        final_state.status.value
        if hasattr(final_state.status, "value")
        else str(final_state.status)
    )
    if final_state.status == SystemStatus.COMPLETED:
        console.print("[green]Merge completed successfully![/green]")
    elif final_state.status == SystemStatus.AWAITING_HUMAN:
        console.print("[yellow]Paused: awaiting human decisions[/yellow]")
        console.print(f"  Run ID: {final_state.run_id}")
        console.print(f"  Resume with: merge resume --run-id {final_state.run_id}")

        if export_decisions:
            from src.tools.decision_template import export_decision_template

            pending = [
                req
                for req in final_state.human_decision_requests.values()
                if req.human_decision is None
            ]
            if pending:
                path = export_decision_template(pending, export_decisions)
                console.print(f"[green]Decision template exported to: {path}[/green]")
                console.print(
                    f"  Edit the file and resume with: merge resume"
                    f" --decisions {path} --run-id {final_state.run_id}"
                )

        if github_pr is not None:
            _publish_github_review(config, final_state, github_pr)

    elif final_state.status == SystemStatus.FAILED:
        console.print("[red]Merge failed[/red]")
        for err in final_state.errors:
            console.print(f"  Error: {err.get('message', '')}")
        sys.exit(EXIT_UNKNOWN_ERROR)
    else:
        console.print(f"Final status: {status_val}")


def _publish_github_review(
    config: MergeConfig, final_state: MergeState, github_pr: int
) -> None:
    import os

    token = os.environ.get(config.github.token_env or "GITHUB_TOKEN", "")
    repo = config.github.repo
    if not token or not repo:
        console.print(
            "[yellow]GitHub integration requires GITHUB_TOKEN env var"
            " and github.repo in config[/yellow]"
        )
        return

    from src.integrations.github_client import GitHubClient
    from src.integrations.github_formatter import (
        format_decision_request_as_comment,
        format_summary_comment,
    )

    gh = GitHubClient(token, repo)
    pending = [
        r
        for r in final_state.human_decision_requests.values()
        if r.human_decision is None
    ]
    if not pending:
        return

    comments = [format_decision_request_as_comment(r) for r in pending]
    summary = format_summary_comment(pending)
    try:
        asyncio.run(gh.create_review(github_pr, comments, summary))
        console.print(
            f"[green]Published {len(comments)} review comments"
            f" to PR #{github_pr}[/green]"
        )
    except Exception as e:
        console.print(f"[yellow]GitHub PR comment failed: {e}[/yellow]")
