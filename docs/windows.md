# Windows (PowerShell) quickstart

> Verified on Windows 10 22H2 with Python 3.13.5
> Anaconda's Python (`python -m venv .venv`).

This page covers only what differs from the [Unix quickstart](../README.md#quickstart)
in the README — same package, same CLI, same test suite.

Requires Python 3.10+ from [python.org](https://www.python.org/downloads/windows/)
with the Python Launcher (`py`) on `PATH`.

## Create and activate a virtual environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Execution policy

If activation fails with *"cannot be loaded because running scripts is disabled on
this system"*, don't change the execution policy machine-wide. Scope it to your user:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Or bypass for a single session with no policy change:

```powershell
powershell -ExecutionPolicy Bypass -File .\.venv\Scripts\Activate.ps1
```

## Run the tests

```powershell
pytest -q
```

## CLI smoke run

```powershell
voice-eval run --scenario basic_booking --adapter cascade
```

Writes `reports\<run-id>.json` and `reports\<run-id>.md` relative to the current
directory (override with `$env:VOICE_EVAL_REPORT_DIR`). Add `--audio` to also write
WAV files under `reports\audio\<run-id>\`.

## Troubleshooting

- `voice-eval` not recognized: venv not activated, or install didn't finish.
- `python`/`py` not found: reinstall from python.org with "Add to PATH" checked.
- Long-path errors: `git config --system core.longpaths true`, or clone nearer the
  drive root (e.g. `C:\dev\voice-eval`).