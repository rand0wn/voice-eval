import argparse
import math
import sys
from pathlib import Path

from .adapters import available_adapters
from .models import RunReport

from .runner import (
    comparison_markdown,
    compare_evaluation,
    markdown,
    run_evaluation,
    run_suite,
    suite_markdown,
    write_compare_reports,
    write_reports,
    write_suite_reports,
)


def _ratio(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or not 0 <= parsed <= 1:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return parsed


def _non_negative(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def _add_gates(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--min-score",
        type=_ratio,
        help="fail when overall score is below this value (0 to 1)",
    )
    parser.add_argument(
        "--min-tool-recall",
        type=_ratio,
        help="fail when tool recall is below this value (0 to 1)",
    )
    parser.add_argument(
        "--max-p95-ms",
        type=_non_negative,
        help="fail when P95 latency exceeds this many milliseconds",
    )


def _gate_failures(report: RunReport, args: argparse.Namespace) -> list[str]:
    metric = report.evaluation
    failures: list[str] = []
    if args.min_score is not None and metric.overall_score < args.min_score:
        failures.append(f"overall score {metric.overall_score:.2%} < {args.min_score:.2%}")
    if args.min_tool_recall is not None and metric.tool_recall < args.min_tool_recall:
        failures.append(f"tool recall {metric.tool_recall:.2%} < {args.min_tool_recall:.2%}")
    p95_ms = float(metric.details["p95_ms"])
    if args.max_p95_ms is not None and p95_ms > args.max_p95_ms:
        failures.append(f"P95 latency {p95_ms:g} ms > {args.max_p95_ms:g} ms")
    return failures


def _enforce_gates(reports: list[RunReport], args: argparse.Namespace) -> None:
    failures = [
        f"{report.adapter}: {failure}"
        for report in reports
        for failure in _gate_failures(report, args)
    ]
    if not failures:
        return
    print("Evaluation gate failed:", file=sys.stderr)
    for failure in failures:
        print(f"- {failure}", file=sys.stderr)
    raise SystemExit(1)


def _run(args: argparse.Namespace) -> None:
    audio_root = args.output / "audio" if args.audio else None
    report = run_evaluation(args.scenario, args.adapter, audio_root=audio_root)
    json_path, md_path = write_reports(report, args.output)
    print(markdown(report))
    print(f"Wrote {json_path} and {md_path}")
    if audio_root:
        print(f"Wrote turn audio under {report.audio_dir}")
    _enforce_gates([report], args)


def _compare(args: argparse.Namespace) -> None:
    audio_root = args.output / "audio" if args.audio else None
    report = compare_evaluation(args.scenario, args.adapters, audio_root=audio_root)
    json_path, md_path = write_compare_reports(report, args.output)
    print(comparison_markdown(report))
    print(f"Wrote {json_path} and {md_path}")
    _enforce_gates(report.runs, args)


def _suite(args: argparse.Namespace) -> None:
    audio_root = args.output / "audio" if args.audio else None
    report = run_suite(args.adapter, args.scenarios, audio_root=audio_root)
    json_path, md_path = write_suite_reports(report, args.output)
    print(suite_markdown(report))
    print(f"Wrote {json_path} and {md_path}")
    if audio_root:
        print(f"Wrote turn audio under {audio_root}")
    _enforce_gates(report.runs, args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate and grade voice pipelines")
    sub = parser.add_subparsers(dest="command", required=True)
    adapter_choices = available_adapters()

    run_parser = sub.add_parser("run", help="Run one scenario through one pipeline adapter")
    run_parser.add_argument("--scenario", default="basic_booking")
    run_parser.add_argument("--adapter", choices=adapter_choices, default="cascade")
    run_parser.add_argument("--output", type=Path, default=Path("reports"))
    run_parser.add_argument(
        "--audio", action="store_true", help="Synthesize a WAV file per turn under reports/audio/"
    )
    _add_gates(run_parser)
    run_parser.set_defaults(func=_run)

    compare_parser = sub.add_parser(
        "compare", help="Run one scenario through every listed adapter and compare"
    )
    compare_parser.add_argument("--scenario", default="basic_booking")
    compare_parser.add_argument(
        "--adapters",
        nargs="+",
        choices=adapter_choices,
        default=["cascade", "realtime"],
    )
    compare_parser.add_argument("--output", type=Path, default=Path("reports"))
    compare_parser.add_argument("--audio", action="store_true")
    _add_gates(compare_parser)
    compare_parser.set_defaults(func=_compare)

    suite_parser = sub.add_parser(
        "suite", help="Run every scenario in a directory through one adapter"
    )
    suite_parser.add_argument(
        "--scenarios",
        type=Path,
        help="directory containing YAML scenarios (defaults to bundled scenarios)",
    )
    suite_parser.add_argument("--adapter", choices=adapter_choices, default="cascade")
    suite_parser.add_argument("--output", type=Path, default=Path("reports"))
    suite_parser.add_argument("--audio", action="store_true")
    _add_gates(suite_parser)
    suite_parser.set_defaults(func=_suite)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
