#!/usr/bin/env bash
set -euo pipefail

# Base workspace directory
BASE_WORKSPACE="./workspace"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
EVAL_ROOT="${BASE_WORKSPACE}/evals_${TIMESTAMP}"

mkdir -p "$EVAL_ROOT"

echo "Running evals in: $EVAL_ROOT"
echo "========================================"

# --- Eval definitions ---
# Format: EVAL_NAME | PROMPT
declare -a EVAL_NAMES=(
  "number_guess_game"
  "csv_parser"
  "file_organizer"
  "fibonacci_cli"
)

declare -a EVAL_PROMPTS=(
  "Create a simple game called game.py where the player has to guess a number between 1 and 10. The game should provide feedback on whether the guess is too high, too low, or correct."
  "Create a script called parse_csv.py that reads a CSV file passed as a command-line argument, prints the number of rows and columns, and outputs the first 5 rows as a formatted table. Handle missing files and malformed CSV gracefully."
  "Create a script called organize_files.py that takes a source directory as an argument and organizes files into subdirectories by extension (e.g., .py -> python/, .txt -> text/, .jpg -> images/). It should do a dry-run by default and only move files when --execute is passed."
  "Create a CLI tool called fib.py that accepts an integer N as an argument and prints the first N Fibonacci numbers. Support a --json flag to output as a JSON array. Validate that N is a positive integer and print a helpful error otherwise."
)

MODEL="openrouter-audit/moonshotai/kimi-k2.5"
PASS=0
FAIL=0

for i in "${!EVAL_NAMES[@]}"; do
  NAME="${EVAL_NAMES[$i]}"
  PROMPT="${EVAL_PROMPTS[$i]}"
  EVAL_DIR="${EVAL_ROOT}/${NAME}"

  mkdir -p "$EVAL_DIR"

  echo ""
  echo "[$((i+1))/${#EVAL_NAMES[@]}] Running eval: $NAME"
  echo "  Dir: $EVAL_DIR"
  echo "  Prompt: ${PROMPT:0:80}..."

  if uv run opencode \
    run \
    --dir "$EVAL_DIR" \
    --model "$MODEL" \
    "$PROMPT"; then
    echo "  ✅ PASSED: $NAME"
    ((PASS++))
  else
    echo "  ❌ FAILED: $NAME (exit code $?)"
    ((FAIL++))
  fi
done

echo ""
echo "========================================"
echo "Results: $PASS passed, $FAIL failed out of ${#EVAL_NAMES[@]} evals"
echo "Output dir: $EVAL_ROOT"