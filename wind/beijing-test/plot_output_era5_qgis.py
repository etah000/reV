#!/usr/bin/env python3
"""Generate QGIS-ready layers and figures for output_era5 pipeline results.

Outputs (under <output_dir>/viz):
- qgis_layers.gpkg with multiple layers:
  - grid_resource
  - top5_points
  - exclusions_points
  - supply_curve_points
- fig_12_grid_resource_map.png
- fig_11_top5_monthly_energy_line.png
- fig_11_top5_annual_energy_bar.png
- fig_13_exclusions_overlay_map.png
- fig_supply_curve.png
- top5_points_summary.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import h5py
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from shapely.geometry import Point


HOURS_PER_YEAR = 8760


def _structured_to_df(arr: np.ndarray) -> pd.DataFrame:
    """Convert an HDF5 structured array to DataFrame and decode byte columns."""
    df = pd.DataFrame(arr)
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(
                lambda x: x.decode("utf-8") if isinstance(x, (bytes, bytearray)) else x
            )
    return df


def _load_generation_site_table(output_dir: Path) -> pd.DataFrame:
    """Build site-level table with gid, cf_mean, system_capacity, annual_energy_mwh."""
    gen_h5 = output_dir / "output_era5_generation_2022.h5"
    project_points = pd.read_csv(output_dir / "project_points.csv")

    with h5py.File(gen_h5, "r") as f:
        cf_mean = np.asarray(f["cf_mean"])
        system_capacity = np.asarray(f["system_capacity"])

        if "meta" in f:
            meta = _structured_to_df(f["meta"][:])
            if "gid" in meta.columns and len(meta) == len(cf_mean):
                gids = pd.to_numeric(meta["gid"], errors="coerce")
                site = pd.DataFrame({"gid": gids, "cf_mean": cf_mean, "system_capacity_kw": system_capacity})
                site = site.dropna(subset=["gid"]).copy()
                site["gid"] = site["gid"].astype(int)
            else:
                site = pd.DataFrame({
                    "gid": pd.to_numeric(project_points["gid"], errors="coerce").astype(int),
                    "cf_mean": cf_mean,
                    "system_capacity_kw": system_capacity,
                })
        else:
            site = pd.DataFrame({
                "gid": pd.to_numeric(project_points["gid"], errors="coerce").astype(int),
                "cf_mean": cf_mean,
                "system_capacity_kw": system_capacity,
            })

    site["annual_energy_mwh"] = site["cf_mean"] * site["system_capacity_kw"] * HOURS_PER_YEAR / 1000.0
    return site


def _load_resource_index_map(resource_h5: Path) -> tuple[pd.DatetimeIndex, dict[int, int], np.ndarray]:
    """Return time index, gid->column index mapping, and windspeed array."""
    with h5py.File(resource_h5, "r") as f:
        time_raw = f["time_index"][:]
        time_index = pd.to_datetime(
            [t.decode("utf-8") if isinstance(t, (bytes, bytearray)) else str(t) for t in time_raw],
            utc=True,
        )

        meta = _structured_to_df(f["meta"][:])
        if "gid" not in meta.columns:
            raise KeyError("Dataset meta does not include gid; cannot map top-5 sites reliably.")

        gids = pd.to_numeric(meta["gid"], errors="coerce").astype("Int64")
        gid_to_idx = {int(g): i for i, g in enumerate(gids) if pd.notna(g)}

        windspeed = np.asarray(f["windspeed_100m"])

    return pd.DatetimeIndex(time_index), gid_to_idx, windspeed


def _build_top5_monthly_energy(
    top5: pd.DataFrame,
    time_index: pd.DatetimeIndex,
    gid_to_idx: dict[int, int],
    windspeed: np.ndarray,
) -> pd.DataFrame:
    """Distribute each top site's annual energy by hourly windspeed^3 and aggregate monthly."""
    rows = []
    for _, r in top5.iterrows():
        gid = int(r["gid"])
        annual_mwh = float(r["annual_energy_mwh"])
        if gid not in gid_to_idx:
            continue

        ws = windspeed[:, gid_to_idx[gid]].astype(float)
        ws = np.clip(ws, 0.0, None)
        weights = ws ** 3
        denom = float(weights.sum())
        if denom <= 0:
            hourly_mwh = np.full_like(weights, annual_mwh / len(weights), dtype=float)
        else:
            hourly_mwh = annual_mwh * (weights / denom)

        df = pd.DataFrame({
            "time": time_index,
            "gid": gid,
            "energy_mwh": hourly_mwh,
        })
        df["month"] = df["time"].dt.month
        monthly = df.groupby(["gid", "month"], as_index=False)["energy_mwh"].sum()
        rows.append(monthly)

    if not rows:
        return pd.DataFrame(columns=["gid", "month", "energy_mwh"])

    return pd.concat(rows, ignore_index=True)


def _build_exclusions_points(excl_h5: Path) -> gpd.GeoDataFrame:
    """Convert excluded pixels (value==0) to point layer for QGIS overlay."""
    with h5py.File(excl_h5, "r") as f:
        excl = np.asarray(f["beijing_osm_exclusions"])
        techmap = np.asarray(f["techmap_beijing"])
        lat = np.asarray(f["latitude"])
        lon = np.asarray(f["longitude"])

    if excl.ndim == 3:
        excl2 = excl[0]
    else:
        excl2 = excl

    rr, cc = np.where(excl2 == 0)
    out = pd.DataFrame({
        "row": rr,
        "col": cc,
        "excluded": 1,
        "value": excl2[rr, cc],
        "tech_gid": techmap[rr, cc],
        "latitude": lat[rr, cc],
        "longitude": lon[rr, cc],
    })

    geom = [Point(xy) for xy in zip(out["longitude"], out["latitude"])]
    return gpd.GeoDataFrame(out, geometry=geom, crs="EPSG:4326")


def make_visuals(output_dir: Path) -> Path:
    output_dir = output_dir.resolve()
    viz_dir = output_dir / "viz"
    viz_dir.mkdir(parents=True, exist_ok=True)

    site_meta = pd.read_csv(output_dir / "site_meta.csv")
    grid = gpd.read_file(output_dir / "grid_cells.geojson")
    supply_curve = pd.read_csv(output_dir / "output_era5_supply-curve.csv")

    site_table = _load_generation_site_table(output_dir)

    site_enriched = site_meta.merge(site_table, on="gid", how="left")
    grid_enriched = grid.merge(site_table, on="gid", how="left")

    # Write QGIS layers to a single GeoPackage for easy loading.
    gpkg = viz_dir / "qgis_layers.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    grid_enriched.to_file(gpkg, layer="grid_resource", driver="GPKG")

    top5 = site_enriched.sort_values("annual_energy_mwh", ascending=False).head(5).copy()
    top5_gdf = gpd.GeoDataFrame(
        top5,
        geometry=gpd.points_from_xy(top5["longitude"], top5["latitude"]),
        crs="EPSG:4326",
    )
    top5_gdf.to_file(gpkg, layer="top5_points", driver="GPKG")

    excl_gdf = _build_exclusions_points(output_dir / "beijing_exclusions.h5")
    excl_gdf.to_file(gpkg, layer="exclusions_points", driver="GPKG")

    sc_points = gpd.GeoDataFrame(
        supply_curve,
        geometry=gpd.points_from_xy(supply_curve["longitude"], supply_curve["latitude"]),
        crs="EPSG:4326",
    )
    sc_points.to_file(gpkg, layer="supply_curve_points", driver="GPKG")

    # Figure 12-like: gridded map with annual energy from generation+project points.
    fig, ax = plt.subplots(figsize=(10, 8), dpi=150)
    grid_enriched.plot(
        column="annual_energy_mwh",
        ax=ax,
        cmap="YlGnBu",
        linewidth=0.1,
        edgecolor="grey",
        legend=True,
        legend_kwds={"label": "Annual energy (MWh/site)"},
        missing_kwds={"color": "lightgrey", "label": "No data"},
    )
    top5_gdf.plot(ax=ax, color="red", markersize=18)
    ax.set_title("Beijing wind grid (project points joined with computed annual energy)")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(viz_dir / "fig_12_grid_resource_map.png")
    plt.close(fig)

    # Figure 11-like: top5 monthly energy line + bar charts.
    time_index, gid_to_idx, windspeed = _load_resource_index_map(output_dir / "beijing_wind_resource_2022.h5")
    monthly = _build_top5_monthly_energy(top5, time_index, gid_to_idx, windspeed)

    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    for gid, grp in monthly.groupby("gid"):
        grp = grp.sort_values("month")
        ax.plot(grp["month"], grp["energy_mwh"], marker="o", label=f"gid={gid}")
    ax.set_xticks(range(1, 13))
    ax.set_xlabel("Month")
    ax.set_ylabel("Energy (MWh)")
    ax.set_title("Top-5 sites monthly energy profile")
    ax.grid(alpha=0.3)
    ax.legend(ncol=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(viz_dir / "fig_11_top5_monthly_energy_line.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
    top5_plot = top5.sort_values("annual_energy_mwh", ascending=True)
    ax.barh(top5_plot["gid"].astype(str), top5_plot["annual_energy_mwh"], color="#2a9d8f")
    ax.set_xlabel("Annual energy (MWh)")
    ax.set_ylabel("gid")
    ax.set_title("Top-5 sites annual energy")
    fig.tight_layout()
    fig.savefig(viz_dir / "fig_11_top5_annual_energy_bar.png")
    plt.close(fig)

    # Figure 13-like: exclusions overlay on grid map.
    fig, ax = plt.subplots(figsize=(10, 8), dpi=150)
    grid_enriched.plot(
        column="annual_energy_mwh",
        ax=ax,
        cmap="YlGnBu",
        linewidth=0.05,
        edgecolor="none",
        legend=True,
        alpha=0.8,
        legend_kwds={"label": "Annual energy (MWh/site)"},
    )

    # Sampling keeps map readable and file size manageable.
    excl_plot = excl_gdf if len(excl_gdf) <= 120000 else excl_gdf.sample(120000, random_state=42)
    excl_plot.plot(ax=ax, color="crimson", markersize=1.5, alpha=0.45, label="Excluded pixels")
    top5_gdf.plot(ax=ax, color="black", markersize=16, marker="x", label="Top-5 sites")

    ax.set_title("Wind grid with exclusions overlay")
    ax.set_axis_off()
    ax.legend(loc="lower left")
    fig.tight_layout()
    fig.savefig(viz_dir / "fig_13_exclusions_overlay_map.png")
    plt.close(fig)

    # Final supply curve plot.
    sc = supply_curve.dropna(subset=["lcoe_all_in_usd_per_mwh", "capacity_ac_mw"]).copy()
    sc = sc.sort_values("lcoe_all_in_usd_per_mwh", ascending=True)
    sc["cum_capacity_mw"] = sc["capacity_ac_mw"].cumsum()

    fig, ax = plt.subplots(figsize=(9, 5), dpi=150)
    ax.step(sc["cum_capacity_mw"], sc["lcoe_all_in_usd_per_mwh"], where="post", color="#264653", linewidth=1.8)
    ax.set_xlabel("Cumulative capacity (MW)")
    ax.set_ylabel("LCOE all-in (USD/MWh)")
    ax.set_title("Supply curve")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(viz_dir / "fig_supply_curve.png")
    plt.close(fig)

    top5[["gid", "latitude", "longitude", "cf_mean", "system_capacity_kw", "annual_energy_mwh"]].to_csv(
        viz_dir / "top5_points_summary.csv", index=False
    )

    print(f"Created visualization package under: {viz_dir}")
    print(f"GeoPackage: {gpkg}")
    return viz_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build QGIS-ready maps/charts from output_era5 results.")
    parser.add_argument(
        "--output-dir",
        default="./output_era5",
        help="Path to pipeline output directory containing output_era5 files.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    make_visuals(Path(args.output_dir))
