#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'

echo "MathLab Python environment installed."
echo "Optional system packages for a serious maths VM: SageMath, PARI/GP, Lean4/mathlib, LaTeX, ripgrep."
echo "Run: mathlab doctor"
