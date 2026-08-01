from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import yaml

from .adapters import get_adapter
from .grading import evaluate
from .models import CompareReport, RunReport, Scenario, SuiteReport
from .scenarios import default_scenario_dir, load_scenario


def _run_scenario(
    scenario: Scenario,
    adapter_name: str,
    audio_root: Path | None = None,
) -> RunReport:
    run_id = uuid4().hex
    audio_dir = (audio_root / run_id) if audio_root is not None else None
    results = get_adapter(adapter_name).execute(scenario, audio_dir)
    return RunReport(
        id=run_id,
        scenario_id=scenario.id,
        adapter=adapter_name,
        turns=results,
        evaluation=evaluate(scenario, results),
        audio_dir=str(audio_dir) if audio_dir else None,
    )


def run_evaluation(
    scenario_name: str,
    adapter_name: str,
    audio_root: Path | None = None,
) -> RunReport:
    """Simulate one scenario through one pipeline adapter.

    If `audio_root` is given, one WAV file per turn (user + assistant) is
    written under `audio_root/<run_id>/` — a real, playable artifact, not
    just a text transcript, so a reviewer can spot-check what a turn
    "sounded like" without wiring up a live call.
    """
    return _run_scenario(load_scenario(scenario_name), adapter_name, audio_root)


def run_suite(
    adapter_name: str,
    scenario_directory: Path | None = None,
    audio_root: Path | None = None,
) -> SuiteReport:
    """Run all YAML scenarios in deterministic filename order.

    When ``scenario_directory`` is omitted, the built-in scenario directory is
    used. Scenario IDs must be unique even when their filenames differ.
    """
    directory = scenario_directory or default_scenario_dir()
    if not directory.is_dir():
        raise ValueError(f"Scenario directory does not exist: {directory}")
    paths = sorted(
        (*directory.glob("*.yaml"), *directory.glob("*.yml")), key=lambda path: path.name
    )
    if not paths:
        raise ValueError(f"Scenario directory contains no YAML files: {directory}")

    scenarios: list[Scenario] = []
    ids: set[str] = set()
    for path in paths:
        try:
            scenario = Scenario.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        except Exception as exc:
            raise ValueError(f"Invalid scenario file {path}: {exc}") from exc
        if scenario.id in ids:
            raise ValueError(f"Duplicate scenario id '{scenario.id}' in {path}")
        ids.add(scenario.id)
        scenarios.append(scenario)

    runs = [_run_scenario(scenario, adapter_name, audio_root) for scenario in scenarios]
    count = len(runs)
    return SuiteReport(
        id=uuid4().hex,
        adapter=adapter_name,
        runs=runs,
        scenario_count=count,
        overall_score=sum(run.evaluation.overall_score for run in runs) / count,
        tool_recall=sum(run.evaluation.tool_recall for run in runs) / count,
        average_latency_ms=sum(run.evaluation.details["average_latency_ms"] for run in runs) / count,
        p95_latency_ms=max(run.evaluation.details["p95_ms"] for run in runs),
    )


def compare_evaluation(
    scenario_name: str,
    adapter_names: list[str],
    audio_root: Path | None = None,
) -> CompareReport:
    """Run the same scenario through every adapter and return all reports.

    This is the core question a simulation module answers before an
    architecture decision: not "does pipeline A work" but "how does A
    compare to B on identical scripted turns" — same personas, same tool
    expectations, same rubric, graded the same way.
    """
    scenario = load_scenario(scenario_name)
    runs = [run_evaluation(scenario_name, name, audio_root) for name in adapter_names]
    return CompareReport(id=uuid4().hex, scenario_id=scenario.id, runs=runs)


def markdown(report: RunReport) -> str:
    metric = report.evaluation
    lines = [
        f"# Voice evaluation: {report.scenario_id}",
        "",
        f"- Run: `{report.id}`",
        f"- Adapter: `{report.adapter}`",
        f"- Overall: **{metric.overall_score:.2%}**",
        f"- Average latency: **{metric.details['average_latency_ms']} ms** "
        f"(P50 {metric.details['p50_ms']} ms, P95 {metric.details['p95_ms']} ms)",
        f"- Tool recall: **{metric.tool_recall:.2%}**",
        f"- Transcript completeness: **{metric.transcript_score:.2%}**",
        f"- Rubric: **{metric.rubric_score:.2%}**",
        f"- Per-turn grade: **{metric.turn_grade_score:.2%}**",
        "",
        "## Per-turn results",
        "",
    ]
    for grade in metric.turn_grades:
        turn = report.turns[grade.index]
        status = "PASS" if not grade.failed_rules else f"FAIL: {', '.join(grade.failed_rules)}"
        lines.append(f"- Turn {grade.index}: {grade.score:.0%} — {status}")
        lines.append(f"  - user: {turn.user}")
        lines.append(f"  - assistant: {turn.assistant}")
    return "\n".join(lines) + "\n"


def comparison_markdown(report: CompareReport) -> str:
    lines = [f"# Pipeline comparison: {report.scenario_id}", "", f"- Run: `{report.id}`", ""]
    lines.append("| Adapter | Overall | Avg latency (ms) | P95 latency (ms) | Tool recall |")
    lines.append("|---|---|---|---|---|")
    for run in report.runs:
        metric = run.evaluation
        lines.append(
            f"| {run.adapter} | {metric.overall_score:.2%} | "
            f"{metric.details['average_latency_ms']} | {metric.details['p95_ms']} | "
            f"{metric.tool_recall:.2%} |"
        )
    return "\n".join(lines) + "\n"


def suite_markdown(report: SuiteReport) -> str:
    lines = [
        "# Voice evaluation suite",
        "",
        f"- Suite: `{report.id}`",
        f"- Adapter: `{report.adapter}`",
        f"- Scenarios: **{report.scenario_count}**",
        f"- Overall: **{report.overall_score:.2%}**",
        f"- Tool recall: **{report.tool_recall:.2%}**",
        f"- Average latency: **{report.average_latency_ms:.0f} ms**",
        f"- Worst scenario P95: **{report.p95_latency_ms:.0f} ms**",
        "",
        "| Scenario | Overall | Tool recall | P95 latency (ms) |",
        "|---|---|---|---|",
    ]
    for run in report.runs:
        lines.append(
            f"| {run.scenario_id} | {run.evaluation.overall_score:.2%} | "
            f"{run.evaluation.tool_recall:.2%} | {run.evaluation.details['p95_ms']} |"
        )
    return "\n".join(lines) + "\n"


def write_reports(report: RunReport, directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{report.id}.json"
    md_path = directory / f"{report.id}.md"
    json_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")
    md_path.write_text(markdown(report), encoding="utf-8")
    return json_path, md_path


def write_compare_reports(report: CompareReport, directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{report.id}_compare.json"
    md_path = directory / f"{report.id}_compare.md"
    json_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")
    md_path.write_text(comparison_markdown(report), encoding="utf-8")
    return json_path, md_path


def write_suite_reports(report: SuiteReport, directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{report.id}_suite.json"
    md_path = directory / f"{report.id}_suite.md"
    json_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")
    md_path.write_text(suite_markdown(report), encoding="utf-8")
    return json_path, md_path
