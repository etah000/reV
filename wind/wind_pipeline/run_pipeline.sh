#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONDA_ENV_NAME="${REV_CONDA_ENV:-rev}"
CONDA_BIN="${CONDA_BIN:-/Users/frank/miniconda3/bin/conda}"

if [[ ! -x "${CONDA_BIN}" ]]; then
  if command -v conda >/dev/null 2>&1; then
    CONDA_BIN="$(command -v conda)"
  else
    echo "Could not find conda. Set CONDA_BIN or ensure conda is on PATH." >&2
    exit 127
  fi
fi

cd "${SCRIPT_DIR}"

# Remove stale pipeline status before each run, otherwise reV/gaps can skip
# steps based on old state even when output files were removed.
rm -rf .gaps logs

rm -f \
  local_wind_pipeline_ri_final_generation_2012.h5 \
  local_wind_pipeline_ri_final_supply-curve-aggregation.csv \
  local_wind_pipeline_ri_final_supply-curve.csv \
  ri_exclusions_local.h5

"${CONDA_BIN}" run -n "${CONDA_ENV_NAME}" python generate_project_points.py
cp "${REPO_ROOT}/tests/data/ri_exclusions/ri_exclusions.h5" ./ri_exclusions_local.h5
"${CONDA_BIN}" run -n "${CONDA_ENV_NAME}" python -m reV.cli pipeline -c config_pipeline.json --monitor

rm -rf .gaps logs

printf 'Pipeline completed successfully in %s\n' "${SCRIPT_DIR}"