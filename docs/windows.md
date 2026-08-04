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
this system"*, don't change the execution policy machine-wide. Scope it to your user
account instead:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Or, to allow it for just the current terminal session without changing any saved
policy, set the scope to `Process` *before* activating (this must be run in the same
shell you'll keep using, since a policy set on a child process won't affect your
current one):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Run the tests

```powershell
pytest -q
```

## CLI smoke run

```powershell
voice-eval run --scenario basic_booking --adapter cascade
```

This prints a scorecard to the terminal and writes:

- `reports\<run-id>.json` — machine-readable report
- `reports\<run-id>.md` — human-readable Markdown scorecard

both relative to your current working directory. Use `--output` to write elsewhere:

```powershell
voice-eval run --scenario basic_booking --adapter cascade --output path\to\reports
```

(`VOICE_EVAL_REPORT_DIR` only applies to the FastAPI service, not the CLI.)

Add `--audio` to also write per-turn WAV files under
`reports\audio\<run-id>\t01_user.wav`, `t01_bot.wav`, etc. The bundled audio is
deterministic synthetic tones, not spoken TTS — see the README for details.

## Troubleshooting

- `voice-eval` not recognized: venv not activated, or install didn't finish.
- `python`/`py` not found: reinstall from python.org with "Add to PATH" checked.
- Long-path errors on deeply nested clones: clone closer to the drive root
(e.g. `C:\dev\voice-eval` instead of a deeply nested folder), which avoids the
issue without needing a system-wide Git configuration change.
