#!/usr/bin/env bash
# 跑完所有 demo。
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python

if [ ! -x "$PY" ]; then
  echo "找不到 $PY —— 先建虚拟环境：" >&2
  echo "  uv venv --python 3.12 .venv" >&2
  echo "  uv pip install --python .venv/bin/python -r requirements.txt" >&2
  exit 1
fi
if [ ! -s .env ] && [ -z "${TYPESAFE_API_KEY:-}" ]; then
  echo "找不到 API key —— 到 https://console.typesafe.ai/keys 创建后写入 .env：" >&2
  echo "  echo 'TYPESAFE_API_KEY=apikey_xxx' > .env" >&2
  exit 1
fi

for f in demo/jev_lite.py demo/01_triage.py demo/02_guardrails.py \
         demo/03_semantic_rerank.py demo/04_function_calling.py demo/05_benchmark.py; do
  echo
  echo "################################################################"
  echo "# $f"
  echo "################################################################"
  "$PY" "$f"
done
