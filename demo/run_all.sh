#!/usr/bin/env bash
# 跑完所有 demo。需要先: uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python typesafe-sdk socksio
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
for f in demo/jev_lite.py demo/01_triage.py demo/02_guardrails.py \
         demo/03_semantic_rerank.py demo/04_function_calling.py demo/05_benchmark.py; do
  echo
  echo "################################################################"
  echo "# $f"
  echo "################################################################"
  "$PY" "$f"
done
