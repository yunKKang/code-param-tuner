#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON:-python3}"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
elif [ -x "backend/venv/bin/python" ]; then
  PYTHON_BIN="backend/venv/bin/python"
fi

"$PYTHON_BIN" -m py_compile backend/main.py backend/ai_analyzer.py backend/parser.py
"$PYTHON_BIN" -m unittest discover -s tests
