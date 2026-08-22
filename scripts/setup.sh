#!/usr/bin/env sh
set -eu

repository=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repository"

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi

.venv/bin/python -c 'import sys; assert sys.version_info >= (3, 11), sys.version'
.venv/bin/python -m pip install 'uv==0.12.5'
.venv/bin/uv sync --all-extras --frozen
.venv/bin/opportunityos init --format json
