#!/usr/bin/env bash
set -euo pipefail

uv run --env-file .env \
  opencode run \
    --dir ./workspace \
    --model openrouter-audit/moonshotai/kimi-k2.5 \
    "Create a simple game called game.py where the player has to guess a number between 1 and 10. The game should provide feedback on whether the guess is too high, too low, or correct."

uv run --env-file .env \
  opencode run \
    --dir ./workspace \
    --model openrouter-audit/moonshotai/kimi-k2.5 \
    "Create a script called parse_csv.py that reads a CSV file passed as a command-line argument, prints the number of rows and columns, and outputs the first 5 rows as a formatted table. Handle missing files and malformed CSV gracefully."

uv run --env-file .env \
  opencode run \
    --dir ./workspace \
    --model openrouter-audit/moonshotai/kimi-k2.5 \
    "Create a script called organize_files.py that takes a source directory as an argument and organizes files into subdirectories by extension (e.g., .py -> python/, .txt -> text/, .jpg -> images/). It should do a dry-run by default and only move files when --execute is passed."

uv run --env-file .env \
  opencode run \
    --dir ./workspace \
    --model openrouter-audit/moonshotai/kimi-k2.5 \
    "Create a CLI tool called fib.py that accepts an integer N as an argument and prints the first N Fibonacci numbers. Support a --json flag to output as a JSON array. Validate that N is a positive integer and print a helpful error otherwise."
