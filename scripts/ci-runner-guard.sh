#!/usr/bin/env bash
# A hosted runner that exhausts memory loses its connection, and its job ends
# without logs. Exempt the runner's own processes from the OOM killer, so it
# ends the offending check instead, and record memory use for the diagnostics.
set -euo pipefail
for pid in $(pgrep -f 'Runner\.(Listener|Worker)|provisioner|hosted-compute-agent' || true); do
  echo -1000 | sudo tee "/proc/$pid/oom_score_adj" > /dev/null || true
done
monitor="${GITHUB_WORKSPACE:-$PWD}/build/ci-monitor"
mkdir -p "$monitor"
nohup bash -c '
  while :; do
    date -u +%FT%TZ
    free -m | sed -n 2,3p
    ps -eo rss=,pcpu=,args= --sort=-rss | head -n 5 | cut -c1-200
    sleep 30
  done' > "$monitor/memory.log" 2>&1 < /dev/null &
