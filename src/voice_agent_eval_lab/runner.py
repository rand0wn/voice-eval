from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from .adapters import get_adapter
from .grading import evaluate
from .models import CompareReport, RunReport
from .scenarios import load_scenario


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
    scenario = load_scenario(scenario_name)
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
        f"- Adapter: `{report.adapter.value}`",
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
            f"| {run.adapter.value} | {metric.overall_score:.2%} | "
            f"{metric.details['average_latency_ms']} | {metric.details['p95_ms']} | "
            f"{metric.tool_recall:.2%} |"
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
