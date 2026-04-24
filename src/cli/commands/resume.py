import asyncio
import sys
from pathlib import Path
from rich.console import Console
from src.cli.paths import get_run_dir, is_dev_mode
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
        checkpoint = Checkpoint(cp_path.parent)
        state = checkpoint.load(cp_path)
    elif run_id:
        # Production: .merge/runs/<run_id>/checkpoint.json
        # Dev mode: ./outputs/debug/checkpoints/checkpoint.json
        run_dir = get_run_dir(run_id=run_id)
        checkpoint = Checkpoint(run_dir)
        latest = checkpoint.get_latest()
        if latest is None:
            console.print(f"[red]No checkpoint found for run_id: {run_id}[/red]")
            sys.exit(1)
        state = checkpoint.load(latest)
        if state.run_id != run_id and is_dev_mode():
            console.print(
                f"[yellow]Warning: checkpoint run_id {state.run_id} != requested {run_id}[/yellow]"
            )
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
        import yaml as _yaml
        from pathlib import Path as _Path
        from src.agents.human_interface_agent import HumanInterfaceAgent
        from src.models.plan_review import PlanHumanDecision, PlanHumanReview

        try:
            _raw = _yaml.safe_load(_Path(decisions).read_text(encoding="utf-8"))
        except Exception as _e:
            console.print(f"[red]Failed to read decisions file: {_e}[/red]")
            sys.exit(1)

        plan_approval = _raw.get("plan_approval") if isinstance(_raw, dict) else None

        # O-L4 fix: item_decisions must be injectable regardless of whether
        # plan_human_review is already set. After plan approval, AUTO_MERGE
        # may append new undecided items (e.g. O-M1 conflict_markers_*, O-B3
        # binary_asset_*) that the user needs to decide on a subsequent
        # resume. Previously this block was gated on
        # `plan_human_review is None`, causing undecided items to persist and
        # triggering an AUTO_MERGE ↔ AWAITING_HUMAN ping-pong.
        raw_items = (
            _raw.get("item_decisions") if isinstance(_raw, dict) else None
        ) or []
        by_path = {
            it["file_path"]: it
            for it in raw_items
            if isinstance(it, dict) and it.get("file_path")
        }
        applied = 0
        for idx, item in enumerate(state.pending_user_decisions):
            payload = by_path.get(item.file_path)
            if not payload:
                continue
            choice = payload.get("user_choice")
            if not choice:
                continue
            # Never overwrite an already-decided item; user must clear it
            # via a fresh run if they changed their mind.
            if item.user_choice is not None:
                continue
            valid_keys = {o.key for o in item.options}
            if choice not in valid_keys:
                console.print(
                    f"[red]Invalid user_choice {choice!r} for "
                    f"{item.file_path} (valid: {sorted(valid_keys)})[/red]"
                )
                sys.exit(1)
            state.pending_user_decisions[idx] = item.model_copy(
                update={
                    "user_choice": choice,
                    "user_input": payload.get("notes"),
                }
            )
            applied += 1
        if applied:
            console.print(f"[green]Applied {applied} per-file choices[/green]")

        if plan_approval and state.plan_human_review is None:
            try:
                pd = PlanHumanDecision(str(plan_approval).lower())
            except ValueError:
                console.print(
                    f"[red]Invalid plan_approval: {plan_approval!r} "
                    f"(expected approve|reject|modify)[/red]"
                )
                sys.exit(1)

            state.plan_human_review = PlanHumanReview(
                decision=pd,
                reviewer_name=(_raw.get("reviewer") if isinstance(_raw, dict) else None)
                or "cli",
                reviewer_notes=(_raw.get("notes") if isinstance(_raw, dict) else None),
                item_decisions=list(state.pending_user_decisions),
            )
            console.print(
                f"[green]Plan approval set to {pd.value!r} via decisions file[/green]"
            )
        elif applied and state.plan_human_review is not None:
            # Keep plan_human_review.item_decisions snapshot in sync with
            # the updated pending_user_decisions so downstream consumers
            # see the latest user_choice values.
            state.plan_human_review = state.plan_human_review.model_copy(
                update={"item_decisions": list(state.pending_user_decisions)}
            )

        judge_resolution = (
            _raw.get("judge_resolution") if isinstance(_raw, dict) else None
        )
        if judge_resolution is not None:
            val = str(judge_resolution).lower().strip()
            if val not in {"accept", "abort", "rerun"}:
                console.print(
                    f"[red]Invalid judge_resolution: {judge_resolution!r} "
                    f"(expected accept|abort|rerun)[/red]"
                )
                sys.exit(1)
            state.judge_resolution = val  # type: ignore[assignment]
            console.print(
                f"[green]Judge resolution set to {val!r} via decisions file[/green]"
            )

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

            # When all decisions are in, the next orchestrator.run() will
            # re-enter HumanReviewPhase which now sees 0 pending requests
            # and routes through executor → JUDGE_REVIEWING on its own.
            # (A prior version tried `sm.transition(state, AWAITING_HUMAN, …)`
            # here which is a no-op same-state transition; the state machine
            # rejects same-state transitions, so we just fall through.)

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
