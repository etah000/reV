"""
project_points.py
=================
Step 4 – Generate project_points.csv from site metadata.

reV requires a CSV with at minimum:
  gid     – integer, must match the row index of resource file meta
  config  – key into sam_files dict (string)

Optional columns:
  curtailment – path to curtailment config (string, default null)
  capacity    – site-level installed capacity override (float, MW)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def build_project_points(
    site_meta: pd.DataFrame,
    sam_config_key: str = "default",
    gid_subset: list[int] | None = None,
) -> pd.DataFrame:
    """
    Build a project_points DataFrame from site metadata.

    Parameters
    ----------
    site_meta : DataFrame
        Must contain a ``gid`` column (or will use row index).
    sam_config_key : str
        Value for the ``config`` column; must match a key in the reV
        generation config's ``sam_files`` dict.
    gid_subset : list of int, optional
        If provided, only include these gids (useful for smoke tests).

    Returns
    -------
    DataFrame with columns: gid, config
    """
    if "gid" in site_meta.columns:
        gids = site_meta["gid"].values
    else:
        gids = site_meta.index.values

    if gid_subset is not None:
        gids = [g for g in gids if g in set(gid_subset)]

    pp = pd.DataFrame({
        "gid":    gids,
        "config": sam_config_key,
    })
    return pp


def save_project_points(
    pp: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    """Save project_points to CSV."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pp.to_csv(str(output_path), index=False)
    print(f"[project_points] {len(pp)} points → {output_path}")
    return output_path


def generate_project_points(
    site_meta: pd.DataFrame,
    output_dir: str | Path,
    sam_config_key: str = "default",
    gid_subset: list[int] | None = None,
) -> pd.DataFrame:
    """
    Full project points pipeline: build + save.

    Returns the DataFrame.
    """
    pp = build_project_points(site_meta, sam_config_key, gid_subset)
    save_project_points(pp, Path(output_dir) / "project_points.csv")
    return pp


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate project_points.csv from site_meta.csv."
    )
    parser.add_argument("site_meta_csv", help="CSV from grid_generation.py")
    parser.add_argument("--output-dir", default="./output")
    parser.add_argument("--config-key", default="default",
                        help="SAM config key (default: 'default')")
    parser.add_argument(
        "--gids", nargs="*", type=int, default=None,
        help="Subset of gids to include (default: all)"
    )
    args = parser.parse_args()

    meta = pd.read_csv(args.site_meta_csv)
    generate_project_points(meta, args.output_dir, args.config_key, args.gids)
