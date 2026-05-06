# Local Rhode Island wind pipeline

This directory contains a small, local-only wind pipeline that was validated
against the repository's existing test data. The working pipeline is:

1. generation
2. supply-curve-aggregation
3. supply-curve

It intentionally omits collect and multi-year because the final goal here is a
stable, reproducible local example that stays small and only depends on data
already checked into this repository.

For a per-file and per-step business explanation, see:

- ./BUSINESS_OVERVIEW.md
- ./BUSINESS_OVERVIEW_CN.md

## Inputs

All required inputs are local repository files:

- ../../tests/data/wtk/ri_100_wtk_2012.h5
- ../../tests/data/ri_exclusions/ri_exclusions.h5
- ../../tests/data/trans_tables/ri_transmission_table.csv
- ../../tests/data/SAM/wind_gen_standard_losses_0.json
- ./project_points.csv

The file ri_exclusions.h5 does not need to be downloaded.

## Why ri_exclusions_local.h5 exists

ri_exclusions_local.h5 is a local copy of the repository test exclusions file.
It is used so this example can write a resource-specific techmap dataset without
modifying the shared test fixture.

Compared with the original exclusions file, this local copy adds only:

- techmap_wtk_ri_100_local

That dataset is generated for ../../tests/data/wtk/ri_100_wtk_2012.h5 and is
what makes the supply-curve aggregation step align with the selected wind
resource file.

## Project points

The generation step uses a single project points file:

- ./project_points.csv

This CSV was generated from the resource metadata and currently contains the
first 100 gids from the Rhode Island resource file so aggregation has enough
sites to form non-empty supply-curve points.

If you need to regenerate the file from the resource metadata, run:

```bash
python generate_project_points.py
```

## Running the pipeline

From this directory:

```bash
python -m reV.cli pipeline -c config_pipeline.json --monitor
```

Or, if the reV entrypoint is available:

```bash
reV pipeline -c config_pipeline.json --monitor
```

For a one-command rebuild and rerun, use:

```bash
./run_pipeline.sh
```

If your conda environment name is not `rev`, override it like this:

```bash
REV_CONDA_ENV=my_env ./run_pipeline.sh
```

## Outputs

A successful run writes:

- local_wind_pipeline_ri_final_generation_2012.h5
- local_wind_pipeline_ri_final_supply-curve-aggregation.csv
- local_wind_pipeline_ri_final_supply-curve.csv

The full pipeline was rerun successfully from zero on 2026-05-02 using this
directory's current files.

## Execution notes

- collect is not executed in this pipeline.
- multi-year is not executed in this pipeline.
- config_pipeline.json contains only the three steps listed above.
- config_collect.json and config_multi_year.json were experimental leftovers and
   have been removed from the final local example.
