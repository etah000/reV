"""
build_beijing_dataset.py
========================
Top-level CLI entry point – orchestrates all steps of the Beijing
wind-resource data-preparation pipeline.

Steps executed in order:
  1. grid_generation    – 4 km² grid over beijing.geojson
  2. synthetic_met      – hourly wind/temperature/pressure synthesis (Phase A)
  3. resource_writer    – write + validate reV-compatible HDF5
  4. project_points     – generate project_points.csv
  5. exclusions_techmap – build placeholder exclusions + techmap HDF5
  6. config_generator   – write all reV JSON config files
  (optional)
  7. qgis_verify        – PyQGIS layer-load verification (if --qgis flag set)

Usage
-----
    cd wind/beijing-test
    python build_beijing_dataset.py \\
        --geojson  /path/to/beijing/beijing.geojson \\
        --output   ./output \\
        [--year 2012] \\
        [--hub-height 100] \\
        [--cell-size 2000] \\
        [--seed 42] \\
        [--qgis] \\
        [--smoke-test] \\
        [--overwrite]

After running, the output directory will contain:
    beijing_wind_resource_2012.h5   – reV wind resource file
    project_points.csv
    beijing_exclusions.h5
    site_meta.csv
    grid_cells.geojson
    sam_wind_default.json
    beijing_transmission_table.csv
    config_generation.json
    config_sc_aggregation.json
    config_supply_curve.json
    config_pipeline.json
    logs/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


# ─── Pipeline steps ───────────────────────────────────────────────────────────

def step_grid(geojson: Path, output_dir: Path, cell_size: float):
    from grid_generation import generate_grid
    grid_utm, site_meta = generate_grid(geojson, output_dir, cell_size_m=cell_size)
    return grid_utm, site_meta


def step_synthesize(site_meta, year: int, hub_height: float, seed: int,
                    smoke_test: bool):
    from synthetic_met import synthesize_all
    if smoke_test:
        # Trim to first 10 sites to keep smoke-test fast
        site_meta = site_meta.head(10).copy()
        site_meta["gid"] = range(10)
        print("[build] smoke-test mode: using first 10 sites only")
    met = synthesize_all(site_meta, year=year, hub_height_m=hub_height, seed=seed)
    return site_meta, met


def step_era5(site_meta, era5_path: str, year: int, hub_height: float,
              smoke_test: bool):
    from era5_adapter import era5_adapter
    if smoke_test:
        site_meta = site_meta.head(10).copy()
        site_meta["gid"] = range(10)
        print("[build] smoke-test mode: using first 10 sites only")
    met = era5_adapter(era5_path, site_meta, year=year, hub_height_m=hub_height)
    return site_meta, met


def step_write_resource(output_dir: Path, site_meta, met, year: int,
                        hub_height: int, overwrite: bool) -> Path:
    from resource_writer import write_resource_file, validate_resource_file
    h5_path = output_dir / f"beijing_wind_resource_{year}.h5"
    write_resource_file(
        h5_path, site_meta, met,
        hub_height_m=hub_height,
        overwrite=overwrite,
    )
    validate_resource_file(h5_path)
    return h5_path


def step_project_points(site_meta, output_dir: Path):
    from project_points import generate_project_points
    return generate_project_points(site_meta, output_dir)


def step_exclusions(site_meta, resource_h5: Path, output_dir: Path,
                    overwrite: bool) -> Path:
    from exclusions_techmap import build_exclusions_and_techmap
    return build_exclusions_and_techmap(
        site_meta, resource_h5, output_dir, overwrite=overwrite,
    )


def step_configs(output_dir: Path, resource_h5: Path, pp_csv: Path,
                 excl_h5: Path, site_meta, year: int):
    from config_generator import generate_all_configs
    return generate_all_configs(
        output_dir, resource_h5, pp_csv, excl_h5,
        site_meta=site_meta,
        analysis_years=[year],
    )


def step_qgis_verify(geojson: Path, output_dir: Path):
    try:
        from qgis_verify import verify_layers
        verify_layers(
            geojson,
            output_dir / "grid_cells.geojson",
            output_dir / "qgis_verify_log.txt",
        )
    except ImportError:
        print(
            "[build] PyQGIS not available in this Python environment. "
            "Run qgis_verify.py manually inside the QGIS Python console."
        )


# ─── Main ─────────────────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build Beijing reV wind dataset from scratch."
    )
    parser.add_argument(
        "--geojson", required=True,
        help="Path to beijing.geojson boundary file."
    )
    parser.add_argument(
        "--output", default="./output",
        help="Output directory (will be created if needed)."
    )
    parser.add_argument("--year",       type=int,   default=2012)
    parser.add_argument("--hub-height", type=float, default=100.0,
                        help="Hub height in metres (default: 100).")
    parser.add_argument("--cell-size",  type=float, default=2000.0,
                        help="Grid cell side in metres (default: 2000 → 4 km²).")
    parser.add_argument("--seed",       type=int,   default=42,
                        help="Random seed for synthetic data (default: 42).")
    parser.add_argument(
        "--era5", default=None, metavar="PATH",
        help=(
            "(Phase-B) Path to ERA5 NetCDF file(s). "
            "Accepts a single file, a glob pattern, or multiple paths "
            "separated by spaces (quote the pattern). "
            "When omitted, Phase-A statistical synthesis is used."
        ),
    )
    parser.add_argument("--qgis",       action="store_true",
                        help="Run PyQGIS layer verification after build.")
    parser.add_argument("--smoke-test", action="store_true",
                        help="Use only the first 10 sites for a quick test run.")
    parser.add_argument("--overwrite",  action="store_true",
                        help="Overwrite existing output files.")
    args = parser.parse_args(argv)

    geojson    = Path(args.geojson)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not geojson.exists():
        print(f"[build] ERROR: GeoJSON not found: {geojson}", file=sys.stderr)
        sys.exit(1)

    phase = "B (ERA5)" if args.era5 else "A (synthetic)"

    print(f"\n{'=' * 60}")
    print(f"  Beijing reV Wind Dataset Builder")
    print(f"  GeoJSON    : {geojson}")
    print(f"  Output dir : {output_dir}")
    print(f"  Year       : {args.year}")
    print(f"  Hub height : {args.hub_height} m")
    print(f"  Cell size  : {args.cell_size / 1000:.1f} km × {args.cell_size / 1000:.1f} km")
    print(f"  Data phase : {phase}")
    if args.era5:
        print(f"  ERA5 path  : {args.era5}")
    else:
        print(f"  Seed       : {args.seed}")
    print(f"  Smoke test : {args.smoke_test}")
    print(f"{'=' * 60}\n")

    # ── Step 1: grid ──────────────────────────────────────────────────────────
    print("\n─── Step 1/6: Grid generation ───")
    _, site_meta_full = step_grid(geojson, output_dir, args.cell_size)

    # ── Step 2: meteorological data (Phase-A or Phase-B) ───────────────────────
    if args.era5:
        print("\n─── Step 2/6: ERA5 meteorology (Phase-B) ───")
        site_meta, met = step_era5(
            site_meta_full, args.era5, args.year, args.hub_height, args.smoke_test
        )
    else:
        print("\n─── Step 2/6: Synthetic meteorology (Phase-A) ───")
        site_meta, met = step_synthesize(
            site_meta_full, args.year, args.hub_height, args.seed, args.smoke_test
        )

    # ── Step 3: resource HDF5 ─────────────────────────────────────────────────
    print("\n─── Step 3/6: Write & validate resource HDF5 ───")
    resource_h5 = step_write_resource(
        output_dir, site_meta, met, args.year,
        int(args.hub_height), args.overwrite,
    )

    # ── Step 4: project points ────────────────────────────────────────────────
    print("\n─── Step 4/6: Project points ───")
    pp_csv = output_dir / "project_points.csv"
    step_project_points(site_meta, output_dir)

    # ── Step 5: exclusions + techmap ──────────────────────────────────────────
    print("\n─── Step 5/6: Exclusions + techmap ───")
    excl_h5 = step_exclusions(site_meta, resource_h5, output_dir, args.overwrite)

    # ── Step 6: reV configs ───────────────────────────────────────────────────
    print("\n─── Step 6/6: reV configuration files ───")
    step_configs(output_dir, resource_h5, pp_csv, excl_h5, site_meta, args.year)

    # ── Optional: QGIS verification ───────────────────────────────────────────
    if args.qgis:
        print("\n─── (Optional) PyQGIS verification ───")
        step_qgis_verify(geojson, output_dir)

    print(f"\n{'=' * 60}")
    print("  Build complete.")
    print(f"  All outputs in: {output_dir.resolve()}")
    print(f"{'=' * 60}\n")

    print("Next steps:")
    print(f"  cd {output_dir.resolve()}")
    print("  reV pipeline -c config_pipeline.json --monitor")


if __name__ == "__main__":
    main()
