#!/usr/bin/env python3
"""Scheme-A verification utility for Beijing wind pipeline outputs.

Purpose:
1) Run SC aggregation and supply-curve with recalc_lcoe enabled.
2) Verify lcoe_site and lcoe_all_in are populated (non-null).

This script intentionally bypasses GAPs status caching by calling reV Python APIs
for aggregation and supply-curve directly.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from reV.supply_curve.sc_aggregation import SupplyCurveAggregation
from reV.supply_curve.supply_curve import SupplyCurve

from output_layout import make_layout, resolve_existing


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_pipeline_value(value: str, fallback: str) -> str:
    return fallback if str(value).upper() == "PIPELINE" else str(value)


def _resolve_cfg_path(cfg_dir: Path, output_dir: Path, rel_or_abs: str) -> Path:
    """Resolve a path referenced from config files with backward-compatible fallbacks."""
    p = Path(rel_or_abs)
    if p.is_absolute() and p.exists():
        return p

    candidates = [
        (cfg_dir / p),
        (output_dir / p),
        (output_dir / "data" / p.name),
        (output_dir / "configs" / p.name),
    ]
    for c in candidates:
        if c.exists():
            return c

    return candidates[0]


def run_scheme_a(output_dir: Path) -> dict:
    cfg_agg_path = resolve_existing(output_dir, "configs/config_sc_aggregation.json", "config_sc_aggregation.json")
    cfg_sc_path = resolve_existing(output_dir, "configs/config_supply_curve.json", "config_supply_curve.json")
    cfg_agg = _load_json(cfg_agg_path)
    cfg_sc = _load_json(cfg_sc_path)
    layout = make_layout(output_dir)
    cfg_agg_dir = cfg_agg_path.parent
    cfg_sc_dir = cfg_sc_path.parent

    if not cfg_agg.get("recalc_lcoe", False):
        raise ValueError("config_sc_aggregation.json has recalc_lcoe=false; scheme A requires true")

    gen_fpath = _resolve_pipeline_value(cfg_agg.get("gen_fpath", "PIPELINE"), "../data/output_era5_generation_2022.h5")
    sc_points = _resolve_pipeline_value(cfg_sc.get("sc_points", "PIPELINE"), "../data/output_era5_supply-curve-aggregation.csv")

    agg = SupplyCurveAggregation(
        excl_fpath=str(_resolve_cfg_path(cfg_agg_dir, layout.root, cfg_agg["excl_fpath"])),
        tm_dset=cfg_agg["tm_dset"],
        excl_dict=cfg_agg.get("excl_dict"),
        resolution=int(cfg_agg.get("resolution", 4)),
        excl_area=float(cfg_agg.get("excl_area", 0.25)),
        res_fpath=str(_resolve_cfg_path(cfg_agg_dir, layout.root, cfg_agg["res_fpath"])),
        cf_dset=cfg_agg.get("cf_dset", "cf_mean"),
        lcoe_dset=cfg_agg.get("lcoe_dset"),
        res_class_dset=cfg_agg.get("res_class_dset", "cf_mean"),
        res_class_bins=cfg_agg.get("res_class_bins", [0.0, 0.3, 1.0]),
        power_density=float(cfg_agg.get("power_density", 3.0)),
        recalc_lcoe=bool(cfg_agg.get("recalc_lcoe", True)),
    )
    agg.run(
        out_fpath=str(layout.data / "output_era5_supply-curve-aggregation.csv"),
        gen_fpath=str(_resolve_cfg_path(cfg_agg_dir, layout.root, gen_fpath)),
        max_workers=int(cfg_agg.get("execution_control", {}).get("max_workers", 1)),
        sites_per_worker=100,
    )

    sc = SupplyCurve(
        sc_points=str(_resolve_cfg_path(cfg_sc_dir, layout.root, sc_points)),
        trans_table=str(_resolve_cfg_path(cfg_sc_dir, layout.root, cfg_sc["trans_table"])),
        sc_features=cfg_sc.get("sc_features"),
    )
    sc.run(
        out_fpath=str(layout.data / "output_era5_supply-curve.csv"),
        fixed_charge_rate=float(cfg_sc.get("fixed_charge_rate", 0.096)),
        simple=bool(cfg_sc.get("simple", True)),
        transmission_costs=cfg_sc.get("transmission_costs"),
        max_workers=int(cfg_sc.get("execution_control", {}).get("max_workers", 1)),
    )

    agg_df = pd.read_csv(layout.data / "output_era5_supply-curve-aggregation.csv")
    sc_df = pd.read_csv(layout.data / "output_era5_supply-curve.csv")

    agg_lcoe = pd.to_numeric(agg_df["lcoe_site_usd_per_mwh"], errors="coerce")
    sc_lcoe_site = pd.to_numeric(sc_df["lcoe_site_usd_per_mwh"], errors="coerce")
    sc_lcoe_allin = pd.to_numeric(sc_df["lcoe_all_in_usd_per_mwh"], errors="coerce")

    summary = {
        "agg_rows": int(len(agg_df)),
        "sc_rows": int(len(sc_df)),
        "agg_lcoe_site_nonnull": int(agg_lcoe.notna().sum()),
        "sc_lcoe_site_nonnull": int(sc_lcoe_site.notna().sum()),
        "sc_lcoe_all_in_nonnull": int(sc_lcoe_allin.notna().sum()),
        "sc_lcoe_all_in_min": float(sc_lcoe_allin.min()) if sc_lcoe_allin.notna().any() else None,
        "sc_lcoe_all_in_max": float(sc_lcoe_allin.max()) if sc_lcoe_allin.notna().any() else None,
    }

    (layout.data / "scheme_a_verification.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify scheme A (recalc_lcoe) outputs.")
    parser.add_argument("--output-dir", default="./output_era5", help="Pipeline output directory.")
    args = parser.parse_args()

    out = Path(args.output_dir).resolve()
    summary = run_scheme_a(out)

    print("Scheme A verification summary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    if summary["sc_lcoe_all_in_nonnull"] == 0:
        raise SystemExit("Verification failed: lcoe_all_in_usd_per_mwh is entirely null")


if __name__ == "__main__":
    main()
