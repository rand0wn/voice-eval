# Contributing to Voice Eval

Thanks for helping make voice-agent testing more repeatable. Contributions of
all sizes are useful: a typo fix, a clearer example, a new synthetic scenario,
an adapter, or a grading improvement.

## Before you start

- Search [existing issues](https://github.com/rand0wn/voice-eval/issues) before
  opening a new one.
- For a small fix, feel free to open a pull request directly.
- For a larger feature or behavior change, open an issue first so the approach
  can be discussed before you invest significant time.
- Never include real customer recordings, transcripts, phone numbers, API
  keys, private prompts, or other sensitive data. Use synthetic examples only.

## Local setup

Voice Eval requires Python 3.10 or newer.

```bash
git clone https://github.com/rand0wn/voice-eval.git
cd voice-eval
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run the tests:

```bash
pytest -q
```

Run a complete local smoke test:

```bash
voice-eval run --scenario basic_booking --adapter cascade
voice-eval compare --scenario arjun_cancel --adapters cascade degraded --audio
```

The comparison should produce JSON and Markdown reports under `reports/`, plus
valid WAV files under `reports/audio/`. The bundled audio is made from
deterministic tones, not spoken TTS, so the test remains offline and
credential-free.

## Choose a contribution

### Add a scenario

Add the same synthetic YAML scenario to both:

- `scenarios/`, for source checkouts; and
- `src/voice_agent_eval_lab/scenario_data/`, so it is included in installed
  wheels.

Follow the schema and examples described in the README. Prefer multi-turn
scenarios that test state, tool calls, required content, response shape, or
latency. Add a test proving that the packaged scenario loads successfully.

### Add an adapter

Implement `VoicePipelineAdapter.execute` in
`src/voice_agent_eval_lab/adapters.py`, then register the adapter in
`get_adapter()`. Return the shared `TurnResult` model so the existing runner
and graders remain provider-neutral.

If the adapter calls a paid or networked service:

- keep credentials in environment variables;
- never make network access part of the default test suite;
- mock provider calls in unit tests;
- document required variables and expected costs;
- record provider and model versions in result metadata when possible.

### Improve a grading rule

Put grading behavior in `src/voice_agent_eval_lab/grading.py`. Include tests
for a passing turn, a failing turn, and relevant edge cases. Error messages
should identify the failed rule and turn clearly enough for a CI log.

### Improve documentation

Documentation pull requests are welcome. Commands in the README and examples
should be runnable as written. Clearly distinguish:

- deterministic demo results from real-provider benchmarks;
- tone-based WAV fixtures from intelligible speech;
- current functionality from proposed functionality.

## Development checks

Before opening a pull request, run:

```bash
pytest -q
python -m compileall -q src tests
voice-eval run --scenario basic_booking --adapter cascade
```

If you change packaging, also verify a clean wheel install:

```bash
python -m pip install build
python -m build
python -m pip install --force-reinstall dist/*.whl
voice-eval run --scenario basic_booking --adapter cascade
```

GitHub Actions repeats the supported-version, packaging, CLI, comparison, and
audio checks on every pull request.

## Pull request checklist

- Keep the pull request focused on one change.
- Explain the problem and why the change solves it.
- Add or update tests for behavior changes.
- Update the README or examples when users need new instructions.
- Do not commit generated `reports/`, audio, virtual environments, secrets, or
  customer data.
- Confirm that the development checks pass.

A helpful pull request description includes:

```text
What changed:
Why:
How I tested it:
Example output or scorecard:
```

## Reporting bugs

Open a [GitHub issue](https://github.com/rand0wn/voice-eval/issues) with:

- your operating system and Python version;
- the command you ran;
- the expected and actual behavior;
- the smallest synthetic scenario that reproduces the problem;
- the traceback or report excerpt, with secrets and personal data removed.

## Questions and ideas

If you are unsure whether an idea fits, open an issue and describe the voice
testing problem you are trying to solve. A concrete failure mode is more useful
than a broad feature request.

Thank you for making voice-agent evaluation easier to reproduce and automate.
