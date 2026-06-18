#!/usr/bin/env bash
# Live progress for the v2v batch. Run in any shell:
#   bash "/home/doug_/susan-exhibition/code/v2v_progress.sh"
# Updates every 30s. Ctrl-C to quit.

ROOT="/home/doug_/susan-exhibition"
SRC="$ROOT/CPR story lines"
T1="$ROOT/CPR story lines (v2v take 1)"
T2="$ROOT/CPR story lines (v2v take 2)"
STATE="$SRC/_v2v_state.json"
INTERVAL=30

start_done=-1
start_t=0

while true; do
  now=$(date +%s)
  total=$(( $(find "$SRC" -name '*.mp4' 2>/dev/null | wc -l) * 2 ))
  done=$(find "$T1" "$T2" -name '*.mp4' -size +1k 2>/dev/null | wc -l)
  [ "$total" -eq 0 ] && total=1
  pct=$(awk "BEGIN{printf \"%.1f\", ($done/$total)*100}")
  errs=$(grep -c '"status": "error"' "$STATE" 2>/dev/null || echo 0)
  pgrep -f v2v_batch >/dev/null && state="RUNNING" || state="idle (not running)"

  # average rate + ETA since this monitor started
  [ "$start_done" -lt 0 ] && { start_done=$done; start_t=$now; }
  eta="—"; rate="—"
  elapsed=$((now - start_t))
  delta=$((done - start_done))
  if [ "$elapsed" -gt 30 ] && [ "$delta" -gt 0 ]; then
    rate=$(awk "BEGIN{printf \"%.1f\", $delta/($elapsed/60.0)}")          # jobs/min
    rem=$((total - done))
    eta=$(awk "BEGIN{m=$rem/($delta/($elapsed/60.0)); printf \"%dh%02dm\", m/60, m%60}")
  fi

  filled=$(awk "BEGIN{printf \"%d\", ($done/$total)*40}")
  bar=$(printf '%*s' "$filled" '' | tr ' ' '#')

  clear
  echo "  v2v batch progress      $(date '+%Y-%m-%d %H:%M:%S')      [$state]"
  echo "  ------------------------------------------------------------"
  printf "  done:     %d / %d   (%s%%)\n" "$done" "$total" "$pct"
  printf "  [%-40s]\n" "$bar"
  printf "  errors:   %s logged\n" "$errs"
  printf "  rate:     %s jobs/min      ETA: ~%s\n" "$rate" "$eta"
  echo "  ------------------------------------------------------------"
  echo "  (refreshing every ${INTERVAL}s — Ctrl-C to quit)"
  sleep "$INTERVAL"
done
