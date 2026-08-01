#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
mkdir -p docs

output="${1:-docs/voice-eval-demo.cast}"

if command -v asciinema >/dev/null 2>&1; then
  demo_config_dir="${TMPDIR:-/tmp}/voice-eval-asciinema"
  mkdir -p "$demo_config_dir"
  ASCIINEMA_CONFIG_HOME="$demo_config_dir" VOICE_EVAL_DEMO_DELAY=2 asciinema rec \
    --overwrite \
    --idle-time-limit 2 \
    --command scripts/demo.sh \
    "$output"
  printf 'Recorded %s\n' "$output"
  exit 0
fi

printf '%s\n' \
  'asciinema is required to create the portable demo recording.' \
  'Install it from https://asciinema.org/docs/cli/installation/ and rerun:' \
  '  scripts/record-demo.sh'
exit 1
