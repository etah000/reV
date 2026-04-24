# reV Copilot Instructions

## Build, test, and lint commands

```bash
# Install local editable package with common contributor extras
pip install -e ".[dev,test,doc]"

# Full test suite (matches the main PR workflow)
python -m pytest -v

# Single test function
python -m pytest -v tests/test_config.py::test_config_entries

# Single test selected by pattern within one file
python -m pytest -v tests/test_gen_pv.py -k test_pv_gen_slice

# Repo-configured linting
pre-commit run --all-files
flake8
pylint reV

# Documentation build
cd docs && make html

# Package build used for release publishing
pip install .[build]
python reV/utilities/_clean_readme.py README.rst
python -m build --sdist --wheel --outdir dist/ .
```

## High-level architecture

- `reV/cli.py` is the top-level CLI entrypoint. It composes module CLIs with `gaps.cli.make_cli`, so the user-facing `reV` command exposes both reV modules and GAPs pipeline/batch/status commands from one place.
- The codebase is heavily config-driven. `reV/config/` defines config objects for analyses and execution, and module CLIs preprocess configs before dispatch. `execution_control` is a required config block for analysis runs.
- `reV/generation/` and `reV/econ/` share `reV.generation.base.BaseGen`, which owns output-request parsing, per-site memory management, site-data merging, and worker splitting. Site selection and SAM config mapping flow through `ProjectPoints` and `PointsControl` in `reV/config/project_points.py`.
- `reV/generation/` runs PySAM generation models against resource HDF5 inputs readable by `rex`. `reV/econ/` consumes generation capacity-factor outputs and runs SAM LCOE / SingleOwner / WindBos calculations on the same project-point abstraction.
- `reV/handlers/outputs.py` defines the shared reV HDF5 contract and version metadata. Other handlers, especially `reV/handlers/multi_year.py`, collect or transform module outputs rather than introducing a separate storage format.
- `reV/supply_curve/` is the downstream spatial aggregation layer: it combines exclusions, techmaps, generation outputs, optional econ outputs, and optional friction or data layers to build supply-curve points and final supply-curve tables.
- `reV/rep_profiles/` extracts representative profiles from generation and supply-curve outputs. `reV/qa_qc/`, `reV/hybrids/`, `reV/nrwal/`, and `reV/bespoke/` are downstream analysis layers that build on the same outputs and metadata conventions.

## Key conventions

- Normalize technology identifiers the way the CLIs do: lower-case them and remove spaces / underscores before dispatch (`pvwattsv8`, `windpower`).
- Treat project points as the core unit of execution. CSV/DataFrame inputs usually key on `gid` with optional `config` and `curtailment` columns, and additional columns can be site-specific SAM inputs. Reuse `ProjectPoints` / `PointsControl` instead of inventing parallel site-selection logic.
- Preserve pipeline-aware config behavior. Several modules accept `"PIPELINE"` sentinels to resolve inputs from previous GAPs steps, and generation / aggregation configs also support resource paths with `{}` placeholders that are filled from `analysis_years`.
- Reuse canonical field names from `reV.utilities` enums (`SiteDataField`, `ResourceMetaField`, `SupplyCurveField`) when touching shared metadata, supply-curve outputs, or site-data tables.
- Keep HDF5 outputs in the reV/rex shape contract: initialize `meta` and `time_index`; 1D datasets are spatial and must align with `meta`; 2D datasets are spatiotemporal and must align with `(len(time_index), len(meta))`. `Outputs` may scale floats on write and unscale on read.
- Supply-curve aggregation expects an exclusions file with a valid techmap dataset, or enough information (`res_fpath`) to create one. Generation and econ outputs are often read together through `rex.MultiFileResource` rather than copied into a new intermediate format.
- Tests lean on real fixture data under `tests/data` and on `reV.TESTDATADIR` examples. Prefer existing fixture files and module-specific test files over synthetic ad hoc fixtures when extending coverage.
