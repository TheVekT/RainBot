#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ -x "./venv/bin/python" ]]; then
	./venv/bin/python main.py
else
	python3 main.py
fi
