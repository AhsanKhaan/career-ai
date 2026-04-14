#!/usr/bin/env bash
# batch-runner.sh — Parallel claude -p worker orchestrator for career-ai
#
# Adapted from career-ops batch/batch-runner.sh by santifer.io
# Each worker is an isolated `claude -p` process — no API key required.
# Requires: claude CLI installed + logged in (claude login)
#
# Usage:
#   ./batch/batch-runner.sh                    Process all pending jobs
#   ./batch/batch-runner.sh --parallel 3       3 concurrent workers (default: 1)
#   ./batch/batch-runner.sh --dry-run          Preview without executing
#   ./batch/batch-runner.sh --retry-failed     Retry jobs marked 'failed'
#   ./batch/batch-runner.sh --job-id abc123    Process a single job by ID

set -euo pipefail

# ─── Paths ───────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BATCH_DIR="$SCRIPT_DIR"
INPUT_FILE="$BATCH_DIR/batch-input.tsv"
STATE_FILE="$BATCH_DIR/batch-state.tsv"
PROMPT_FILE="$BATCH_DIR/batch-prompt.md"
PROFILE_CTX="$BATCH_DIR/.profile-context.md"
LOGS_DIR="$BATCH_DIR/logs"
TRACKER_DIR="$BATCH_DIR/tracker-additions"
PID_FILE="$BATCH_DIR/batch-runner.pid"

# ─── Defaults ────────────────────────────────────────────────────────────────
PARALLEL=1
DRY_RUN=false
RETRY_FAILED=false
SINGLE_JOB_ID=""
TIMEOUT=180  # seconds per claude -p call

# ─── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

log()  { echo -e "${BLUE}[batch]${RESET} $*"; }
ok()   { echo -e "${GREEN}[ok]${RESET}    $*"; }
warn() { echo -e "${YELLOW}[warn]${RESET}  $*"; }
err()  { echo -e "${RED}[error]${RESET} $*" >&2; }
hr()   { echo -e "${CYAN}────────────────────────────────────────${RESET}"; }

# ─── Parse arguments ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --parallel|-p)   PARALLEL="${2:-1}"; shift 2 ;;
    --dry-run)       DRY_RUN=true; shift ;;
    --retry-failed)  RETRY_FAILED=true; shift ;;
    --job-id)        SINGLE_JOB_ID="${2:-}"; shift 2 ;;
    --help|-h)
      echo "Usage: $0 [--parallel N] [--dry-run] [--retry-failed] [--job-id ID]"
      exit 0
      ;;
    *) err "Unknown argument: $1"; exit 1 ;;
  esac
done

# ─── Guards ───────────────────────────────────────────────────────────────────
if [[ -f "$PID_FILE" ]]; then
  existing_pid=$(cat "$PID_FILE")
  if kill -0 "$existing_pid" 2>/dev/null; then
    err "batch-runner already running (PID $existing_pid). Use --retry-failed or wait."
    exit 1
  fi
  rm -f "$PID_FILE"
fi

if ! command -v claude &>/dev/null; then
  err "claude CLI not found. Install: https://claude.ai/download"
  err "Then run: claude login"
  exit 1
fi

if [[ ! -f "$INPUT_FILE" ]]; then
  err "Input file not found: $INPUT_FILE"
  err "Create it with columns: id<TAB>url<TAB>source<TAB>notes"
  exit 1
fi

if [[ ! -f "$PROMPT_FILE" ]]; then
  err "Prompt template not found: $PROMPT_FILE"
  exit 1
fi

# Ensure profile context file exists (written by CareerAIClient.__init__)
if [[ ! -f "$PROFILE_CTX" ]]; then
  warn "Profile context file not found: $PROFILE_CTX"
  warn "Run 'career score' or 'career apply' once to generate it, or run:"
  warn "  python -c \"from career_ai.ai.client import get_claude_client; get_claude_client()\""
  # Generate it now via Python
  cd "$PROJECT_ROOT"
  python -c "from career_ai.ai.client import get_claude_client; get_claude_client()" 2>/dev/null || {
    err "Failed to generate profile context. Is profile.yml configured?"
    exit 1
  }
fi

mkdir -p "$LOGS_DIR" "$TRACKER_DIR"

# ─── State file helpers ───────────────────────────────────────────────────────
# Columns: id<TAB>url<TAB>source<TAB>notes<TAB>status<TAB>score<TAB>started_at<TAB>finished_at
init_state() {
  if [[ ! -f "$STATE_FILE" ]]; then
    echo -e "id\turl\tsource\tnotes\tstatus\tscore\tstarted_at\tfinished_at" > "$STATE_FILE"
    # Copy input rows with status=pending
    tail -n +2 "$INPUT_FILE" | while IFS=$'\t' read -r id url source notes; do
      echo -e "${id}\t${url}\t${source}\t${notes}\tpending\t\t\t"
    done >> "$STATE_FILE"
    log "Initialized state file with $(tail -n +2 "$STATE_FILE" | wc -l) jobs"
  fi
}

get_pending_ids() {
  if [[ "$RETRY_FAILED" == "true" ]]; then
    awk -F'\t' 'NR>1 && ($5=="pending" || $5=="failed") {print $1}' "$STATE_FILE"
  else
    awk -F'\t' 'NR>1 && $5=="pending" {print $1}' "$STATE_FILE"
  fi
}

get_job_url() {
  local id="$1"
  awk -F'\t' -v id="$id" 'NR>1 && $1==id {print $2}' "$STATE_FILE"
}

get_job_source() {
  local id="$1"
  awk -F'\t' -v id="$id" 'NR>1 && $1==id {print $3}' "$STATE_FILE"
}

update_state() {
  local id="$1" status="$2" score="${3:-}" ts="$4"
  local tmpfile
  tmpfile=$(mktemp)
  awk -F'\t' -v OFS='\t' -v id="$id" -v status="$status" -v score="$score" -v ts="$ts" '
    NR==1 { print; next }
    $1==id {
      $5 = status
      if (score != "") $6 = score
      if ($7 == "") $7 = ts
      if (status == "completed" || status == "failed") $8 = ts
    }
    { print }
  ' "$STATE_FILE" > "$tmpfile" && mv "$tmpfile" "$STATE_FILE"
}

# ─── Worker ───────────────────────────────────────────────────────────────────
run_worker() {
  local id="$1"
  local url
  url=$(get_job_url "$id")
  local source
  source=$(get_job_source "$id")
  local ts
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  local log_file="$LOGS_DIR/${id}.log"
  local output_file="$TRACKER_DIR/${id}.json"

  log "Starting worker for job ${BOLD}${id}${RESET} (${source}: ${url})"
  update_state "$id" "running" "" "$ts"

  # Build the user prompt — substituting placeholders in batch-prompt.md
  local prompt
  prompt=$(sed \
    -e "s|{{URL}}|${url}|g" \
    -e "s|{{ID}}|${id}|g" \
    -e "s|{{SOURCE}}|${source}|g" \
    -e "s|{{DATE}}|$(date +%Y-%m-%d)|g" \
    -e "s|{{OUTPUT_FILE}}|${output_file}|g" \
    "$PROMPT_FILE")

  if [[ "$DRY_RUN" == "true" ]]; then
    warn "[DRY-RUN] Would call: claude -p --dangerously-skip-permissions --append-system-prompt-file $PROFILE_CTX \"<prompt>\""
    update_state "$id" "dry-run" "" "$ts"
    return 0
  fi

  # Run claude -p worker (same pattern as career-ops)
  local exit_code=0
  timeout "$TIMEOUT" claude \
    -p \
    --dangerously-skip-permissions \
    --append-system-prompt-file "$PROFILE_CTX" \
    "$prompt" \
    > "$log_file" 2>&1 || exit_code=$?

  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  if [[ $exit_code -ne 0 ]]; then
    err "Worker failed for ${id} (exit $exit_code). See: $log_file"
    update_state "$id" "failed" "" "$ts"
    return 1
  fi

  # Extract score from output JSON (last JSON object in stdout)
  local score=""
  score=$(grep -o '"score"[[:space:]]*:[[:space:]]*[0-9]*' "$log_file" | tail -1 | grep -o '[0-9]*' || true)

  # Extract JSON summary output and write to tracker-additions/
  local json_output
  json_output=$(python3 -c "
import sys, json, re
content = open('$log_file').read()
matches = re.findall(r'\{[^{}]*\"job_id\"[^{}]*\}', content, re.DOTALL)
if matches:
    try:
        obj = json.loads(matches[-1])
        print(json.dumps(obj, indent=2))
    except:
        pass
" 2>/dev/null || true)

  if [[ -n "$json_output" ]]; then
    echo "$json_output" > "$output_file"
  fi

  ok "Completed ${id} — score: ${score:-unknown}"
  update_state "$id" "completed" "$score" "$ts"
  return 0
}

# ─── Main ─────────────────────────────────────────────────────────────────────
echo $$ > "$PID_FILE"
trap 'rm -f "$PID_FILE"' EXIT

hr
log "${BOLD}career-ai batch runner${RESET}"
log "Parallel workers: $PARALLEL | Dry-run: $DRY_RUN | Retry failed: $RETRY_FAILED"
hr

cd "$PROJECT_ROOT"
init_state

# Collect jobs to process
if [[ -n "$SINGLE_JOB_ID" ]]; then
  pending_ids=("$SINGLE_JOB_ID")
else
  mapfile -t pending_ids < <(get_pending_ids)
fi

total=${#pending_ids[@]}
if [[ $total -eq 0 ]]; then
  log "Nothing to process — all jobs already completed."
  exit 0
fi

log "Jobs to process: ${BOLD}${total}${RESET}"

# Run workers with controlled parallelism
completed=0
failed=0
active=0
declare -A worker_pids=()

for id in "${pending_ids[@]}"; do
  # Wait if at capacity
  while [[ $active -ge $PARALLEL ]]; do
    for wid in "${!worker_pids[@]}"; do
      if ! kill -0 "${worker_pids[$wid]}" 2>/dev/null; then
        wait "${worker_pids[$wid]}" && ((completed++)) || ((failed++))
        unset worker_pids["$wid"]
        ((active--))
      fi
    done
    sleep 1
  done

  # Spawn worker in background
  run_worker "$id" &
  worker_pids["$id"]=$!
  ((active++))
done

# Wait for remaining workers
for wid in "${!worker_pids[@]}"; do
  wait "${worker_pids[$wid]}" && ((completed++)) || ((failed++))
done

hr
log "${BOLD}Batch complete${RESET}"
ok "Completed: $completed / $total"
[[ $failed -gt 0 ]] && warn "Failed: $failed (run with --retry-failed to retry)"
hr

# Merge tracker additions back into SQLite
if [[ $completed -gt 0 ]] && [[ "$DRY_RUN" == "false" ]]; then
  log "Merging results into data/career-ai.db..."
  python3 -c "
from career_ai.pipeline.batch import merge_tracker_additions
merge_tracker_additions('$TRACKER_DIR')
" && ok "Merge complete." || warn "Merge failed — results are in $TRACKER_DIR/"
fi
