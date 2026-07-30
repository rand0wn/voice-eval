import argparse
from pathlib import Path

from .runner import (
    comparison_markdown,
    compare_evaluation,
    markdown,
    run_evaluation,
    write_compare_reports,
    write_reports,
)

ADAPTER_CHOICES = ["cascade", "realtime", "degraded"]


def _run(args: argparse.Namespace) -> None:
    audio_root = args.output / "audio" if args.audio else None
    report = run_evaluation(args.scenario, args.adapter, audio_root=audio_root)
    json_path, md_path = write_reports(report, args.output)
    print(markdown(report))
    print(f"Wrote {json_path} and {md_path}")
    if audio_root:
        print(f"Wrote turn audio under {report.audio_dir}")


def _compare(args: argparse.Namespace) -> None:
    audio_root = args.output / "audio" if args.audio else None
    report = compare_evaluation(args.scenario, args.adapters, audio_root=audio_root)
    json_path, md_path = write_compare_reports(report, args.output)
    print(comparison_markdown(report))
    print(f"Wrote {json_path} and {md_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate and grade voice pipelines")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run one scenario through one pipeline adapter")
    run_parser.add_argument("--scenario", default="basic_booking")
    run_parser.add_argument("--adapter", choices=ADAPTER_CHOICES, default="cascade")
    run_parser.add_argument("--output", type=Path, default=Path("reports"))
    run_parser.add_argument(
        "--audio", action="store_true", help="Synthesize a WAV file per turn under reports/audio/"
    )
    run_parser.set_defaults(func=_run)

    compare_parser = sub.add_parser(
        "compare", help="Run one scenario through every listed adapter and compare"
    )
    compare_parser.add_argument("--scenario", default="basic_booking")
    compare_parser.add_argument(
        "--adapters",
        nargs="+",
        choices=ADAPTER_CHOICES,
        default=["cascade", "realtime"],
    )
    compare_parser.add_argument("--output", type=Path, default=Path("reports"))
    compare_parser.add_argument("--audio", action="store_true")
    compare_parser.set_defaults(func=_compare)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
