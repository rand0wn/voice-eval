#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

if [[ -x .venv/bin/voice-eval ]]; then
  voice_eval=(.venv/bin/voice-eval)
else
  voice_eval=(voice-eval)
fi

demo_output="${VOICE_EVAL_DEMO_OUTPUT:-/tmp/voice-eval-demo-reports}"
demo_delay="${VOICE_EVAL_DEMO_DELAY:-0}"

pause() {
  if [[ "$demo_delay" != "0" ]]; then
    sleep "$demo_delay"
  fi
}

printf '$ voice-eval compare --scenario arjun_cancel --adapters cascade degraded\n\n'
"${voice_eval[@]}" compare \
  --scenario arjun_cancel \
  --adapters cascade degraded \
  --output "$demo_output"
pause

printf '\n$ voice-eval run --scenario arjun_cancel --adapter degraded --min-score 0.90\n\n'
if "${voice_eval[@]}" run \
  --scenario arjun_cancel \
  --adapter degraded \
  --output "$demo_output" \
  --min-score 0.90; then
  printf 'Unexpected gate result\n' >&2
  exit 1
else
  printf '\n✓ CI gate blocked the degraded pipeline\n'
fi
pause

printf '\n$ voice-eval suite --adapter cascade --min-score 0.90\n\n'
"${voice_eval[@]}" suite \
  --adapter cascade \
  --output "$demo_output" \
  --min-score 0.90 \
  --min-tool-recall 1.0 \
  --max-p95-ms 900

printf '\n✓ Reports: %s\n' "$demo_output"
