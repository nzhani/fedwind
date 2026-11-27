#!/usr/bin/env bash
# Everything a pull request must pass (requirement NFR-12); the same steps run in CI
# (.github/workflows/checks.yml).
#
#   scripts/check.sh            lint + all test suites
#   scripts/check.sh lint       lint only (fast)
#   BASE=origin/main scripts/check.sh lint    black-check the files changed since BASE (default: main)
#
# Needs: ruff and black (pip install ruff==0.8.4 black==24.10.0), the test virtualenvs
# (federated-website/FastApi/.venv, Long-term_Forecasting/.venv), Docker or TEST_DATABASE_URL for the
# API tests, and node_modules in federated-website for the type check.
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0
step() { printf "\n== %s\n" "$1"; }
run() { "$@" || fail=1; }

PY_DIRS=(federated-website/FastApi/app federated-website/FastApi/tests federated-website/FastApi/main.py
         site_agent inference Long-term_Forecasting/flower_app/my_flower_app Long-term_Forecasting/tests
         Long-term_Forecasting/scripts deploy/central/pki_init.py)

step "ruff (errors: syntax, undefined names, unused imports)"
run ruff check "${PY_DIRS[@]}"

step "black (Python files changed since ${BASE:-main})"
mapfile -t changed < <( { git diff --name-only --diff-filter=ACMR "${BASE:-main}" -- '*.py';
                          git ls-files --others --exclude-standard -- '*.py'; } | sort -u |
                        grep -vE '(^|/)(\.venv|node_modules|datasets)/|gateway-spike' || true)
if ((${#changed[@]})); then
  if black --check --quiet "${changed[@]}"; then
    echo "${#changed[@]} files formatted"
  else
    black --check "${changed[@]}" 2>&1 | grep "would reformat" || true
    echo "black: format them with  black <file>  (whole files: commit the formatting on its own)"
    fail=1
  fi
else
  echo "no changed Python files"
fi

[[ "${1:-all}" == "lint" ]] && exit $fail

step "API tests"
(cd federated-website/FastApi && .venv/bin/python -m pytest -q) || fail=1
step "ML core tests"
(cd Long-term_Forecasting && .venv/bin/python -m pytest -q tests) || fail=1
step "inference tests"
run Long-term_Forecasting/.venv/bin/python -m pytest -q inference/tests
step "site agent tests"
run federated-website/FastApi/.venv/bin/python -m pytest -q site_agent/tests
step "frontend type check"
(cd federated-website && npx tsc --noEmit -p .) || fail=1

echo; ((fail)) && echo "FAILED" || echo "all checks passed"
exit $fail
