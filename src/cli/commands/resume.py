import asyncio
import sys
from pathlib import Path
from rich.console import Console
from src.models.state import MergeState, SystemStatus
from src.core.checkpoint import Checkpoint
from src.core.orchestrator import Orchestrator


console = Console()


def resume_command_impl(
    run_id: str | None,
    checkpoint_path: str | None,
    decisions: str | None = None,
) -> None:
    if checkpoint_path:
        cp_path = Path(checkpoint_path)
        if not cp_path.exists():
            console.print(f"[red]Checkpoint not found: {checkpoint_path}[/red]")
            sys.exit(1)
        checkpoint = Checkpoint("./outputs")
        state = checkpoint.load(cp_path)
    elif run_id:
        checkpoint = Checkpoint("./outputs")
        latest = checkpoint.get_latest(run_id)
        if latest is None:
            console.print(f"[red]No checkpoint found for run_id: {run_id}[/red]")
            sys.exit(1)
        state = checkpoint.load(latest)
    else:
        console.print("[red]Either --run-id or --checkpoint is required[/red]")
        sys.exit(1)

    console.print(f"[blue]Resuming run {state.run_id}[/blue]")
    status_val = (
        state.status.value if hasattr(state.status, "value") else str(state.status)
    )
    console.print(f"  Current status: {status_val}")

    if state.status in (SystemStatus.COMPLETED, SystemStatus.FAILED):
        console.print(
            f"[yellow]Run is already in terminal state: {status_val}[/yellow]"
        )
        return

    if decisions and state.status == SystemStatus.AWAITING_HUMAN:
        from src.agents.human_interface_agent import HumanInterfaceAgent

        pending = [
            req
            for req in state.human_decision_requests.values()
            if req.human_decision is None
        ]
        if pending:
            hi = HumanInterfaceAgent(state.config.agents.human_interface)
            updated = asyncio.run(hi.collect_decisions_file(decisions, pending))
            decided_count = 0
            for req in updated:
                if req.human_decision is not None:
                    state.human_decision_requests[req.file_path] = req
                    state.human_decisions[req.file_path] = req.human_decision
                    decided_count += 1
            console.print(
                f"[green]Loaded {decided_count} decisions from {decisions}[/green]"
            )

            still_pending = [
                fp
                for fp, req in state.human_decision_requests.items()
                if req.human_decision is None
            ]
            if not still_pending:
                from src.core.state_machine import StateMachine

                sm = StateMachine()
                sm.transition(
                    state,
                    SystemStatus.JUDGE_REVIEWING,
                    "all human decisions collected from file",
                )

    orchestrator = Orchestrator(state.config)

    async def execute() -> MergeState:
        return await orchestrator.run(state)

    final_state = asyncio.run(execute())

    final_status = (
        final_state.status.value
        if hasattr(final_state.status, "value")
        else str(final_state.status)
    )
    if final_state.status == SystemStatus.COMPLETED:
        console.print("[green]Merge completed successfully![/green]")
    elif final_state.status == SystemStatus.AWAITING_HUMAN:
        console.print("[yellow]Still awaiting human decisions[/yellow]")
        remaining = [
            fp
            for fp, req in final_state.human_decision_requests.items()
            if req.human_decision is None
        ]
        console.print(f"  Pending: {len(remaining)} files")
    elif final_state.status == SystemStatus.FAILED:
        console.print("[red]Run failed[/red]")
        for err in final_state.errors[-3:]:
            console.print(f"  Error: {err.get('message', '')}")
        sys.exit(1)
    else:
        console.print(f"Final status: {final_status}")
