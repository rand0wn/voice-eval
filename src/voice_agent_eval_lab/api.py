import os
from pathlib import Path

from fastapi import FastAPI, HTTPException

from . import __version__
from .models import CompareReport, CompareRequest, RunReport, RunRequest
from .runner import compare_evaluation, run_evaluation, write_compare_reports, write_reports
from .scenarios import list_scenarios

app = FastAPI(title="Voice Agent Evaluation Lab", version=__version__)
_runs: dict[str, RunReport] = {}
_compares: dict[str, CompareReport] = {}


def _report_dir() -> Path:
    return Path(os.getenv("VOICE_EVAL_REPORT_DIR", "reports"))


def _audio_root() -> Path | None:
    enabled = os.getenv("VOICE_EVAL_AUDIO", "0") == "1"
    return (_report_dir() / "audio") if enabled else None


@app.post("/runs", response_model=RunReport, status_code=201)
def create_run(request: RunRequest) -> RunReport:
    try:
        report = run_evaluation(request.scenario, request.adapter, audio_root=_audio_root())
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _runs[report.id] = report
    write_reports(report, _report_dir())
    return report


@app.get("/runs/{run_id}", response_model=RunReport)
def get_run(run_id: str) -> RunReport:
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail="Run not found")
    return _runs[run_id]


@app.post("/compare", response_model=CompareReport, status_code=201)
def create_compare(request: CompareRequest) -> CompareReport:
    try:
        report = compare_evaluation(
            request.scenario,
            request.adapters,
            audio_root=_audio_root(),
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _compares[report.id] = report
    write_compare_reports(report, _report_dir())
    return report


@app.get("/compare/{compare_id}", response_model=CompareReport)
def get_compare(compare_id: str) -> CompareReport:
    if compare_id not in _compares:
        raise HTTPException(status_code=404, detail="Comparison not found")
    return _compares[compare_id]


@app.get("/scenarios")
def get_scenarios() -> list[str]:
    return list_scenarios()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
