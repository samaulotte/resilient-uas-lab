"""`reslab` - command line interface for Resilient UAS Lab.

Talks to the platform API when one is reachable (default http://localhost:8080, the
Compose gateway) and can execute mock scenarios entirely in-process with `--local`.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from reslab_cli import regression as regression_module
from reslab_cli.local import run_locally
from reslab_core.duration import format_duration, format_mission_time
from reslab_core.scenario import (
    ScenarioValidationError,
    load_scenario,
    scenario_content_hash,
)
from reslab_core.scenario.loader import scenario_warnings
from reslab_core.states import EventKind
from reslab_core.versions import SCENARIO_API_VERSION, SOFTWARE_VERSION

app = typer.Typer(
    name="reslab",
    help="Resilient UAS Lab: validate scenarios, run resilience tests, inspect reports.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
scenario_app = typer.Typer(help="Scenario library and validation.", no_args_is_help=True)
regression_app = typer.Typer(help="Resilience regression checks for CI.", no_args_is_help=True)
app.add_typer(scenario_app, name="scenario")
app.add_typer(regression_app, name="regression")

console = Console()
err_console = Console(stderr=True)

DEFAULT_API = os.environ.get("RESLAB_API_URL", "http://localhost:8080")
ApiOption = Annotated[
    str, typer.Option("--api", envvar="RESLAB_API_URL", help="Platform API base URL")
]


def _client(api: str) -> httpx.Client:
    return httpx.Client(base_url=api.rstrip("/"), timeout=30.0)


def _fail(message: str, code: int = 1) -> None:
    err_console.print(f"[red]error:[/red] {message}")
    raise typer.Exit(code)


def _api_error(exc: Exception, api: str) -> None:
    if isinstance(exc, httpx.ConnectError):
        _fail(
            f"cannot reach the API at {api}. Start the platform with `docker compose up` "
            "or pass --api, or use `reslab run --local` for the in-process mock."
        )
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            detail = exc.response.json().get("detail", exc.response.text)
        except ValueError:
            detail = exc.response.text
        _fail(f"API returned {exc.response.status_code}: {detail}")
    _fail(str(exc))


def _read_scenario(path: Path) -> tuple[str, Any]:
    if not path.exists():
        _fail(f"scenario file not found: {path}")
    document = path.read_text(encoding="utf-8")
    try:
        return document, load_scenario(document)
    except ScenarioValidationError as exc:
        err_console.print(f"[red]invalid scenario:[/red] {path}")
        for issue in exc.issues:
            err_console.print(f"  [yellow]{issue.path}[/yellow]: {issue.message}")
        raise typer.Exit(2) from exc


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: Annotated[bool, typer.Option("--version", help="Show version and exit")] = False,
) -> None:
    if version:
        console.print(f"reslab {SOFTWARE_VERSION} (scenario API {SCENARIO_API_VERSION})")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()


# ---------------------------------------------------------------- scenario


@scenario_app.command("validate")
def scenario_validate(
    paths: Annotated[list[Path], typer.Argument(help="Scenario YAML file(s)")],
    quiet: Annotated[bool, typer.Option("--quiet", "-q")] = False,
) -> None:
    """Validate scenario files against the schema and the fault catalog (offline)."""

    failures = 0
    for path in paths:
        text = path.read_text(encoding="utf-8") if path.exists() else None
        if text is None:
            err_console.print(f"[red]missing[/red] {path}")
            failures += 1
            continue
        try:
            scenario = load_scenario(text)
        except ScenarioValidationError as exc:
            failures += 1
            err_console.print(f"[red]INVALID[/red] {path}")
            for issue in exc.issues:
                err_console.print(f"  {issue.path}: {issue.message}")
            continue
        warnings = scenario_warnings(scenario)
        if not quiet:
            console.print(
                f"[green]VALID[/green]   {path}  "
                f"[dim]{scenario.metadata.name} v{scenario.metadata.version}, "
                f"{len(scenario.expanded_events())} events, {len(scenario.assertions)} assertions, "
                f"{scenario_content_hash(text)[:19]}[/dim]"
            )
            for warning in warnings:
                console.print(f"  [yellow]warning[/yellow] {warning.path}: {warning.message}")
    if failures:
        raise typer.Exit(2)


@scenario_app.command("list")
def scenario_list(
    api: ApiOption = DEFAULT_API,
    local: Annotated[
        Path | None,
        typer.Option("--local", help="List YAML files in a directory instead of the API"),
    ] = None,
) -> None:
    """List scenarios from the platform library (or a local directory with --local)."""

    table = Table(title="Scenarios", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("Adapter")
    table.add_column("Events", justify="right")
    table.add_column("Assertions", justify="right")
    table.add_column("Last run")
    if local is not None:
        for path in sorted(local.glob("*.yaml")):
            try:
                scenario = load_scenario(path.read_text(encoding="utf-8"))
            except ScenarioValidationError:
                table.add_row(path.stem, "[red]invalid[/red]", "", "", "")
                continue
            table.add_row(
                scenario.metadata.name,
                scenario.target.adapter,
                str(len(scenario.expanded_events())),
                str(len(scenario.assertions)),
                "-",
            )
        console.print(table)
        return
    try:
        with _client(api) as client:
            response = client.get("/api/v1/scenarios")
            response.raise_for_status()
            rows = response.json()
    except httpx.HTTPError as exc:
        _api_error(exc, api)
        return
    for row in rows:
        last = row.get("last_run")
        last_text = "-"
        if last:
            last_text = f"{last['state']}"
            if last.get("result"):
                last_text += f" / {last['result']} {last.get('resilience_score') or ''}"
        table.add_row(
            row["name"],
            row["adapter"],
            str(row["event_count"]),
            str(row["assertion_count"]),
            last_text,
        )
    console.print(table)


@scenario_app.command("show")
def scenario_show(name: str, api: ApiOption = DEFAULT_API) -> None:
    """Print the YAML document of a library scenario."""

    try:
        with _client(api) as client:
            response = client.get(f"/api/v1/scenarios/{name}/document")
            response.raise_for_status()
            console.print(response.text, highlight=False, markup=False)
    except httpx.HTTPError as exc:
        _api_error(exc, api)


# ---------------------------------------------------------------- run


def _print_summary(report: dict[str, Any]) -> None:
    summary = report["summary"]
    metrics = report["metrics"]
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column(style="bold")
    table.add_row(
        "Result", f"{report['result'].upper()}  (score {report['resilience_score']:.1f} / 100)"
    )
    table.add_row("Mission", "COMPLETE" if summary["mission_complete"] else "NOT COMPLETE")
    table.add_row(
        "Faults injected", f"{summary['faults_injected']} (applied {summary['faults_applied']})"
    )
    table.add_row("Critical failures", str(summary["critical_failures"]))
    table.add_row("Recovered subsystems", str(summary["recovered_subsystems"]))
    table.add_row("Degraded transitions", str(summary["degraded_transitions"]))
    table.add_row("Loss of control", "YES" if summary["loss_of_control"] else "NO")
    table.add_row("Safety preservation", summary["safety_preservation"])
    table.add_row("Fault containment", summary["fault_containment"])
    mttr = metrics["recovery"]["mean_time_to_recovery"]
    table.add_row("Mean time to recovery", format_duration(mttr) if mttr is not None else "n/a")
    table.add_row("Affected domains", f"{len(metrics['propagation']['affected_domains'])} / 7")
    console.print(table)
    failed = [a for a in report["assertions"] if a["outcome"] != "passed"]
    if failed:
        console.print("[yellow]Assertions not passed:[/yellow]")
        for a in failed:
            console.print(f"  [{a['severity']}] {a['expression']}: {a['explanation']}")


def _event_line(event: dict[str, Any]) -> str:
    t = format_mission_time(event["simulation_time"])
    kind = event["kind"]
    colour = {
        "INJECTION_APPLIED": "cyan",
        "INJECTION_REJECTED": "red",
        "OBSERVED_EFFECT": "yellow",
        "RECOVERY": "green",
        "SYSTEM_RESPONSE": "magenta",
        "EXPECTATION_RESULT": "blue",
    }.get(kind, "white")
    return f"{t}  [{colour}]{kind:18s}[/{colour}] {event['message']}"


@app.command("run")
def run(
    scenario: Annotated[str, typer.Argument(help="Scenario YAML path or library scenario name")],
    adapter: Annotated[
        str | None, typer.Option("--adapter", help="Adapter override (mock, px4-gazebo)")
    ] = None,
    seed: Annotated[int | None, typer.Option("--seed")] = None,
    speed: Annotated[float | None, typer.Option("--speed", help="Simulation speed factor")] = None,
    label: Annotated[str, typer.Option("--label")] = "",
    local: Annotated[
        bool, typer.Option("--local", help="Execute in-process with the mock adapter")
    ] = False,
    output: Annotated[
        Path, typer.Option("--output", "-o", help="Directory for local reports")
    ] = Path("artifacts/local-runs"),
    wait: Annotated[
        bool, typer.Option("--wait/--no-wait", help="Follow the run until it finishes")
    ] = True,
    api: ApiOption = DEFAULT_API,
) -> None:
    """Execute a scenario through the platform or locally."""

    path = Path(scenario)
    document: str | None = None
    parsed = None
    if path.exists():
        document, parsed = _read_scenario(path)
        if adapter and parsed.target.adapter != adapter:
            from reslab_core.scenario import scenario_to_yaml

            parsed = parsed.model_copy(
                update={"target": parsed.target.model_copy(update={"adapter": adapter})}  # type: ignore[arg-type]
            )
            document = scenario_to_yaml(parsed)

    if local:
        if document is None or parsed is None:
            _fail("--local needs a scenario file path")
        assert document is not None and parsed is not None
        console.print(
            f"[bold]{parsed.metadata.name}[/bold] on the mock adapter (in-process, speed "
            f"{speed or 50.0}x, seed {seed if seed is not None else parsed.simulation.seed})"
        )

        def _on_event(event) -> None:
            if event.kind in (
                EventKind.INJECTION_APPLIED,
                EventKind.INJECTION_REJECTED,
                EventKind.OBSERVED_EFFECT,
                EventKind.RECOVERY,
                EventKind.SYSTEM_RESPONSE,
                EventKind.MISSION,
            ):
                console.print(_event_line(event.model_dump(mode="json")))

        result = asyncio.run(
            run_locally(
                parsed,
                document,
                seed=seed,
                speed=speed or 50.0,
                output_dir=output,
                on_event=_on_event,
            )
        )
        console.print()
        _print_summary(json.loads(result.report.model_dump_json()))
        if result.output_dir is not None:
            console.print(f"\n[dim]report written to {result.output_dir}[/dim]")
        raise typer.Exit(0 if result.report.result == "passed" else 1)

    payload: dict[str, Any] = {"label": label}
    if document is not None:
        payload["document"] = document
    else:
        payload["scenario_name"] = scenario
    if adapter:
        payload["adapter"] = adapter
    if seed is not None:
        payload["seed"] = seed
    if speed is not None:
        payload["speed"] = speed
    try:
        with _client(api) as client:
            response = client.post("/api/v1/runs", json=payload)
            response.raise_for_status()
            run_data = response.json()
            run_id = run_data["id"]
            console.print(
                f"run [bold]{run_id}[/bold] queued: {run_data['scenario_name']} on "
                f"{run_data['adapter']} (seed {run_data['seed']}, speed {run_data['speed']}x)"
            )
            if not wait:
                return
            seen = -1
            last_state = None
            while True:
                run_data = client.get(f"/api/v1/runs/{run_id}").json()
                events = client.get(
                    f"/api/v1/runs/{run_id}/events", params={"after_sequence": seen, "limit": 500}
                ).json()["events"]
                for event in events:
                    seen = event["sequence"]
                    if event["kind"] in (
                        "INJECTION_APPLIED",
                        "INJECTION_REJECTED",
                        "OBSERVED_EFFECT",
                        "RECOVERY",
                        "SYSTEM_RESPONSE",
                        "MISSION",
                    ):
                        console.print(_event_line(event))
                if run_data["state"] != last_state:
                    last_state = run_data["state"]
                    console.print(f"[dim]state: {last_state}[/dim]")
                if run_data["state"] in ("COMPLETED", "FAILED", "CANCELLED"):
                    break
                time.sleep(1.0)
            if run_data["state"] != "COMPLETED":
                _fail(f"run {run_data['state'].lower()}: {run_data['reason']}", 1)
            report = client.get(f"/api/v1/runs/{run_id}/report").json()
            console.print()
            _print_summary(report)
            console.print(f"\n[dim]report: {api}/api/v1/runs/{run_id}/report.html[/dim]")
            raise typer.Exit(0 if report["result"] == "passed" else 1)
    except httpx.HTTPError as exc:
        _api_error(exc, api)


@app.command("report")
def report(
    run_id: str,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write report.json here")
    ] = None,
    html: Annotated[Path | None, typer.Option("--html", help="Write report.html here")] = None,
    raw: Annotated[bool, typer.Option("--json", help="Print the raw JSON report")] = False,
    api: ApiOption = DEFAULT_API,
) -> None:
    """Show or download the report of a run."""

    try:
        with _client(api) as client:
            response = client.get(f"/api/v1/runs/{run_id}/report")
            response.raise_for_status()
            data = response.json()
            if output is not None:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(data, indent=2), encoding="utf-8")
                console.print(f"[dim]wrote {output}[/dim]")
            if html is not None:
                page = client.get(f"/api/v1/runs/{run_id}/report.html")
                page.raise_for_status()
                html.parent.mkdir(parents=True, exist_ok=True)
                html.write_text(page.text, encoding="utf-8")
                console.print(f"[dim]wrote {html}[/dim]")
    except httpx.HTTPError as exc:
        _api_error(exc, api)
        return
    if raw:
        console.print_json(json.dumps(data))
        return
    console.print(
        f"[bold]{data['scenario']['name']}[/bold]  run {data['run_id']}  "
        f"adapter {data['target']['adapter']}"
    )
    _print_summary(data)


@app.command("compare")
def compare(baseline: str, candidate: str, api: ApiOption = DEFAULT_API) -> None:
    """Compare two completed runs (baseline vs candidate)."""

    try:
        with _client(api) as client:
            response = client.get(
                "/api/v1/compare", params={"baseline": baseline, "candidate": candidate}
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        _api_error(exc, api)
        return
    table = Table(title=f"Compare  {baseline[:8]} (baseline) vs {candidate[:8]} (candidate)")
    table.add_column("Metric")
    table.add_column("Baseline", justify="right")
    table.add_column("Candidate", justify="right")
    table.add_column("Delta", justify="right")
    table.add_column("Verdict")

    def fmt(value: Any, unit: str) -> str:
        if value is None:
            return "n/a"
        if unit == "percent":
            return f"{float(value) * 100:.1f} %"
        if unit == "seconds":
            return f"{float(value):.1f} s"
        if unit == "bool":
            return str(value).lower()
        if unit == "score":
            return f"{float(value):.1f}"
        return str(value)

    colours = {
        "regression": "red",
        "improvement": "green",
        "changed": "cyan",
        "unchanged": "dim",
        "not_comparable": "dim",
    }
    for m in data["metrics"]:
        delta = (
            ""
            if m["delta"] is None
            else fmt(m["delta"], m["unit"] if m["unit"] != "percent" else "percent")
        )
        table.add_row(
            m["label"],
            fmt(m["baseline"], m["unit"]),
            fmt(m["candidate"], m["unit"]),
            delta,
            f"[{colours.get(m['verdict'], 'white')}]{m['verdict']}"
            f"[/{colours.get(m['verdict'], 'white')}]",
        )
    console.print(table)
    console.print(
        f"Verdict: [bold]{data['verdict'].upper()}[/bold]  "
        f"({data['regressions']} regressions, {data['improvements']} improvements)"
    )
    if data["verdict"] in ("regression", "mixed"):
        raise typer.Exit(1)


@app.command("system")
def system(api: ApiOption = DEFAULT_API) -> None:
    """Show platform health, adapters and runners."""

    try:
        with _client(api) as client:
            response = client.get("/api/v1/system")
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        _api_error(exc, api)
        return
    health = data["health"]
    console.print(
        f"Resilient UAS Lab {data['software_version']}  "
        f"scenario API {data['scenario_api_version']}  "
        f"report schema {data['report_schema_version']}"
    )
    console.print(
        "health: "
        + "  ".join(
            f"{k} {'[green]ok[/green]' if v else '[red]down[/red]'}" for k, v in health.items()
        )
    )
    table = Table(title="Adapters")
    table.add_column("Adapter")
    table.add_column("Status")
    table.add_column("Online")
    table.add_column("Runners")
    for adapter in data["adapters"]:
        table.add_row(
            adapter["name"],
            adapter["status"],
            "[green]yes[/green]" if adapter["online"] else "[dim]no[/dim]",
            ", ".join(adapter["runners"]) or "-",
        )
    console.print(table)
    console.print(
        f"scenarios: {data['counts'].get('scenarios', 0)}  runs: {data['counts'].get('runs', 0)}"
    )


# ---------------------------------------------------------------- regression


@regression_app.command("check")
def regression_check(
    candidate: Annotated[
        Path, typer.Option("--candidate", "-c", help="report.json file or directory")
    ],
    baseline: Annotated[
        Path | None, typer.Option("--baseline", "-b", help="Baseline report.json or directory")
    ] = None,
    thresholds: Annotated[
        Path | None, typer.Option("--thresholds", "-t", help="Thresholds YAML")
    ] = None,
    output_json: Annotated[
        Path | None, typer.Option("--json-output", help="Write machine readable result")
    ] = None,
) -> None:
    """Compare candidate resilience reports against a baseline and configured thresholds."""

    try:
        outcome = regression_module.run_regression(baseline, candidate, thresholds)
    except ValueError as exc:
        _fail(str(exc), 2)
        return
    console.print(regression_module.render_text(outcome), markup=False, highlight=False)
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(regression_module.render_json(outcome), encoding="utf-8")
    raise typer.Exit(0 if outcome.passed else 1)


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
