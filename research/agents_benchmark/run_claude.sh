#!/usr/bin/env bash
# One command for the Claude part of the agents benchmark (PREREG sections 4, 6, 8):
#   bash research/agents_benchmark/run_claude.sh
# Needs the research key in C:/Users/Nicolas/.anthropic/research_key.txt (separate workspace, 15 USD limit).
# Pilots first (50 calls per model), projection, pre-stated reductions if needed, full runs, judges, analysis.
# The program refuses any submission that could take the Anthropic spend above 10 USD (ledger.check_budget).
set -euo pipefail
cd "$(dirname "$0")/../.."
KEY="C:/Users/Nicolas/.anthropic/research_key.txt"
VENV="C:/Users/Nicolas/medical-imaging-viewer/data/cohorts/agents-benchmark/venv"
PY="$VENV/Scripts/python.exe"
if [ ! -f "$KEY" ]; then echo "No está la clave de investigación de Anthropic en $KEY"; exit 2; fi
if [ ! -x "$PY" ]; then
  python -m venv --system-site-packages "$VENV"
  "$PY" -m pip install -q -r research/agents_benchmark/requirements.txt
fi
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN || true
"$PY" -m research.agents_benchmark.runner pilot --model haiku
"$PY" -m research.agents_benchmark.runner pilot --model sonnet
"$PY" -m research.agents_benchmark.runner full --model haiku
"$PY" -m research.agents_benchmark.runner full --model sonnet
"$PY" -m research.agents_benchmark.judges sample
"$PY" -m research.agents_benchmark.judges run --judge claude
"$PY" -m research.agents_benchmark.judges run --judge gemini
"$PY" -m research.agents_benchmark.judges kappa
"$PY" -m research.agents_benchmark.analysis
echo "Listo: resultados en docs/research/agents-benchmark/results/"
