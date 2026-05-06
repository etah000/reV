"""
config_generator.py
===================
Step 6 – Programmatically generate reV JSON configuration files for the
Beijing wind pipeline:

  config_generation.json     – reV windpower generation
  config_sc_aggregation.json – supply-curve spatial aggregation
  config_supply_curve.json   – supply-curve LCOE calculation
  config_pipeline.json       – pipeline orchestration

All paths are written **relative to the output directory** so the whole
directory is relocatable.
"""

from __future__ import annotations

import json
from pathlib import Path


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _rel(target: Path, base: Path) -> str:
    """Return *target* as a path relative to *base*, using POSIX separators."""
    try:
        return target.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        # Fall back to absolute if not under base
        return str(target.resolve())


def _dump(cfg: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    print(f"[config_generator] Wrote {path}")


# ─── Individual config builders ───────────────────────────────────────────────

def build_generation_config(
    output_dir: Path,
    resource_h5: Path,
    project_points_csv: Path,
    sam_json: Path,
    analysis_years: list[int] | None = None,
    max_workers: int = 2,
    sites_per_worker: int = 50,
) -> dict:
    """
    Build the reV generation config dict.

    The resource_file uses a ``{}`` placeholder for the year; reV fills it
    from analysis_years at runtime.  Since we only have one year's file we
    encode the full path with the year literal instead.
    """
    if analysis_years is None:
        analysis_years = [2012]

    return {
        "analysis_years": analysis_years,
        "log_directory": "./logs/",
        "execution_control": {
            "option": "local",
            "max_workers": max_workers,
            "sites_per_worker": sites_per_worker,
        },
        "log_level": "INFO",
        "output_request": [
            "cf_mean",
            "capital_cost",
            "fixed_operating_cost",
            "variable_operating_cost",
            "system_capacity",
            "fixed_charge_rate",
        ],
        "project_points": _rel(project_points_csv, output_dir),
        "resource_file": _rel(resource_h5, output_dir),
        "sam_files": {
            "default": _rel(sam_json, output_dir),
        },
        "technology": "windpower",
    }


def build_sc_aggregation_config(
    output_dir: Path,
    resource_h5: Path,
    exclusions_h5: Path,
    tm_key: str = "techmap_beijing",
    excl_dict: dict | None = None,
    resolution: int = 4,
    power_density: float = 3.0,
) -> dict:
    """
    Build the supply-curve aggregation config dict.

    resolution=4 means each supply-curve cell aggregates 4×4 exclusion pixels.
    With 500 m pixels that yields 2 km × 2 km = 4 km² supply-curve cells,
    matching our resource grid exactly.
    """
    return {
        "log_directory": "./logs/",
        "execution_control": {
            "option": "local",
            "max_workers": 1,
        },
        "excl_fpath": _rel(exclusions_h5, output_dir),
        "tm_dset": tm_key,
        "res_fpath": _rel(resource_h5, output_dir),
        "excl_dict": excl_dict,
        "gen_fpath": "PIPELINE",
        "cf_dset": "cf_mean",
        "lcoe_dset": None,
        "recalc_lcoe": False,
        "res_class_dset": "cf_mean",
        "res_class_bins": [0.0, 0.3, 1.0],
        "resolution": resolution,
        "power_density": power_density,
    }


def build_supply_curve_config(
    output_dir: Path,
    trans_table_csv: Path,
    fixed_charge_rate: float = 0.096,
) -> dict:
    """Build the supply-curve LCOE / transmission config dict."""
    return {
        "log_directory": "./logs/",
        "execution_control": {
            "option": "local",
            "max_workers": 1,
        },
        "fixed_charge_rate": fixed_charge_rate,
        "sc_features": None,
        "sc_points": "PIPELINE",
        "simple": True,
        "trans_table": _rel(trans_table_csv, output_dir),
        "transmission_costs": {
            "center_tie_in_cost": 10,
            "line_cost": 1000,
            "line_tie_in_cost": 200,
            "sink_tie_in_cost": 100,
            "station_tie_in_cost": 50,
        },
    }


def build_pipeline_config(output_dir: Path) -> dict:
    """Build the pipeline orchestration config dict."""
    return {
        "logging": {"log_level": "INFO"},
        "pipeline": [
            {"reV-gen":          "./config_generation.json"},
            {"reV-supply-curve-aggregation": "./config_sc_aggregation.json"},
            {"reV-supply-curve": "./config_supply_curve.json"},
        ],
    }


# ─── SAM wind turbine config builder ─────────────────────────────────────────

def build_sam_wind_config(output_path: Path) -> Path:
    """
    Write a minimal SAM WindPower JSON config for a generic 2 MW turbine
    at 100 m hub height.  This mirrors the parameters used in the reV tests.
    """
    sam_cfg = {
        "wind_turbine_hub_ht": 100,
        "wind_turbine_rotor_diameter": 90,
        "wind_turbine_powercurve_windspeeds": [
            0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
            16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30
        ],
        "wind_turbine_powercurve_powerout": [
            0, 0, 0, 50, 150, 350, 600, 900, 1200, 1500, 1750,
            1950, 2000, 2000, 2000, 2000, 2000, 2000, 2000, 2000, 2000,
            2000, 2000, 2000, 2000, 2000, 0, 0, 0, 0, 0
        ],
        "wind_farm_losses_percent": 8.0,
        "wind_farm_wake_model": 0,
        "system_capacity": 2000,
        "fixed_charge_rate": 0.096,
        "capital_cost": 1300,
        "fixed_operating_cost": 40,
        "variable_operating_cost": 0,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(sam_cfg, indent=2))
    print(f"[config_generator] Wrote SAM config → {output_path}")
    return output_path


# ─── Transmission table builder ───────────────────────────────────────────────

def build_transmission_table(
    site_meta: "pd.DataFrame",
    output_path: Path,
) -> Path:
    """
    Build a minimal transmission table CSV for the supply-curve step.

    Creates one synthetic substation per site as the tie-in point.
    In production replace with real substation/transmission data.
    """
    import numpy as np
    import pandas as pd

    n = len(site_meta)
    lats = site_meta["latitude"].values
    lons = site_meta["longitude"].values

    trans = pd.DataFrame({
        "sc_point_gid": np.arange(n),
        "trans_gid":    np.arange(n),
        "trans_type":   "Substation",
        "dist_mi":      np.random.default_rng(0).uniform(1, 50, n),
        "latitude":     lats,
        "longitude":    lons,
        "ac_cap":       np.full(n, 500.0),
        "reinforcement_cost_per_mw": np.full(n, 0.0),
    })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    trans.to_csv(str(output_path), index=False)
    print(f"[config_generator] Transmission table ({n} rows) → {output_path}")
    return output_path


# ─── Top-level config suite generator ────────────────────────────────────────

def generate_all_configs(
    output_dir: str | Path,
    resource_h5: str | Path,
    project_points_csv: str | Path,
    exclusions_h5: str | Path,
    site_meta: "pd.DataFrame | None" = None,
    tm_key: str = "techmap_beijing",
    analysis_years: list[int] | None = None,
) -> dict[str, Path]:
    """
    Write all reV config files to *output_dir*.

    Parameters
    ----------
    output_dir : path-like
    resource_h5 : path-like
    project_points_csv : path-like
    exclusions_h5 : path-like
    site_meta : DataFrame, optional
        If provided, also writes SAM config and transmission table.
    tm_key : str
    analysis_years : list[int], optional (default [2012])

    Returns
    -------
    dict mapping config name → Path of written file.
    """
    import pandas as pd

    output_dir = Path(output_dir)
    resource_h5 = Path(resource_h5)
    project_points_csv = Path(project_points_csv)
    exclusions_h5 = Path(exclusions_h5)

    sam_json = output_dir / "sam_wind_default.json"
    trans_csv = output_dir / "beijing_transmission_table.csv"

    build_sam_wind_config(sam_json)

    if site_meta is not None:
        build_transmission_table(site_meta, trans_csv)

    gen_cfg = build_generation_config(
        output_dir, resource_h5, project_points_csv, sam_json,
        analysis_years=analysis_years or [2012],
    )
    agg_cfg = build_sc_aggregation_config(
        output_dir, resource_h5, exclusions_h5, tm_key=tm_key,
    )
    sc_cfg = build_supply_curve_config(output_dir, trans_csv)
    pipe_cfg = build_pipeline_config(output_dir)

    paths = {}
    _dump(gen_cfg,  output_dir / "config_generation.json");      paths["generation"]    = output_dir / "config_generation.json"
    _dump(agg_cfg,  output_dir / "config_sc_aggregation.json");  paths["sc_aggregation"] = output_dir / "config_sc_aggregation.json"
    _dump(sc_cfg,   output_dir / "config_supply_curve.json");    paths["supply_curve"]  = output_dir / "config_supply_curve.json"
    _dump(pipe_cfg, output_dir / "config_pipeline.json");        paths["pipeline"]      = output_dir / "config_pipeline.json"

    return paths


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import pandas as pd

    parser = argparse.ArgumentParser(
        description="Generate reV JSON configs for Beijing wind pipeline."
    )
    parser.add_argument("output_dir")
    parser.add_argument("resource_h5")
    parser.add_argument("project_points_csv")
    parser.add_argument("exclusions_h5")
    parser.add_argument("--site-meta-csv", default=None)
    parser.add_argument("--tm-key", default="techmap_beijing")
    args = parser.parse_args()

    meta = pd.read_csv(args.site_meta_csv) if args.site_meta_csv else None
    generate_all_configs(
        args.output_dir,
        args.resource_h5,
        args.project_points_csv,
        args.exclusions_h5,
        site_meta=meta,
        tm_key=args.tm_key,
    )
