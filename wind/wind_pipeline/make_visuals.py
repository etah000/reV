#!/usr/bin/env python

from __future__ import annotations

import json
from pathlib import Path

import h5py
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from reV.generation.generation import Gen


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "visuals"
LAYER_DIR = OUTPUT_DIR / "qgis_layers"
RESOURCE_FPATH = (BASE_DIR / "../../tests/data/wtk/ri_100_wtk_2012.h5").resolve()
SAM_FPATH = (
    BASE_DIR / "../../tests/data/SAM/wind_gen_standard_losses_0.json"
).resolve()
GEN_FPATH = BASE_DIR / "local_wind_pipeline_ri_final_generation_2012.h5"
SC_AGG_FPATH = BASE_DIR / "local_wind_pipeline_ri_final_supply-curve-aggregation.csv"
SC_FPATH = BASE_DIR / "local_wind_pipeline_ri_final_supply-curve.csv"
EXCL_FPATH = BASE_DIR / "ri_exclusions_local.h5"
PROJECT_POINTS_FPATH = BASE_DIR / "project_points.csv"
HOURS_PER_YEAR = 8760
PIXEL_AREA_SQ_KM = 0.0081


def ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LAYER_DIR.mkdir(parents=True, exist_ok=True)


def structured_to_frame(array: np.ndarray) -> pd.DataFrame:
    frame = pd.DataFrame(array)
    for column in frame.columns:
        if frame[column].dtype == object:
            frame[column] = frame[column].map(
                lambda value: value.decode("utf-8") if isinstance(value, bytes) else value
            )
    return frame


def load_resource_meta() -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    with h5py.File(RESOURCE_FPATH, "r") as handle:
        meta = structured_to_frame(handle["meta"][:])
        time_index = pd.to_datetime(handle["time_index"][:].astype(str))

    meta = meta.rename_axis("gid").reset_index()
    meta["gid"] = meta["gid"].astype(int)
    return meta, time_index


def load_generation_outputs() -> pd.DataFrame:
    with h5py.File(GEN_FPATH, "r") as handle:
        meta = structured_to_frame(handle["meta"][:])
        meta["gid"] = meta["gid"].astype(int)
        meta["cf_mean"] = handle["cf_mean"][:]
        meta["system_capacity_kw"] = handle["system_capacity"][:]

    meta["annual_energy_mwh"] = (
        meta["cf_mean"] * meta["system_capacity_kw"] * HOURS_PER_YEAR / 1000.0
    )
    return meta


def build_grid_edges(values: pd.Series) -> dict[float, tuple[float, float]]:
    rounded = np.sort(np.unique(np.round(values.to_numpy(dtype=float), 6)))
    if len(rounded) == 1:
        delta = 0.01
        return {rounded[0]: (rounded[0] - delta / 2, rounded[0] + delta / 2)}

    mids = (rounded[:-1] + rounded[1:]) / 2
    first_edge = rounded[0] - (rounded[1] - rounded[0]) / 2
    last_edge = rounded[-1] + (rounded[-1] - rounded[-2]) / 2
    edges = np.concatenate(([first_edge], mids, [last_edge]))
    return {
        value: (edges[index], edges[index + 1])
        for index, value in enumerate(rounded)
    }


def polygon_from_center(lat: float, lon: float, lat_edges: dict, lon_edges: dict) -> list[list[float]]:
    lat_key = round(float(lat), 6)
    lon_key = round(float(lon), 6)
    south, north = lat_edges[lat_key]
    west, east = lon_edges[lon_key]
    return [
        [west, south],
        [east, south],
        [east, north],
        [west, north],
        [west, south],
    ]


def dataframe_to_geojson(df: pd.DataFrame, geom_builder, out_fpath: Path) -> None:
    features = []
    for row in df.to_dict(orient="records"):
        properties = {}
        for key, value in row.items():
            if isinstance(value, (np.integer, np.int32, np.int64)):
                properties[key] = int(value)
            elif isinstance(value, (np.floating, np.float32, np.float64)):
                properties[key] = float(value)
            elif pd.isna(value):
                properties[key] = None
            else:
                properties[key] = value

        features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": geom_builder(row),
            }
        )

    out_fpath.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, indent=2),
        encoding="utf-8",
    )


def export_qgis_layers(resource_meta: pd.DataFrame, project_points: pd.DataFrame, sc_df: pd.DataFrame) -> None:
    resource_layer = resource_meta.merge(project_points[["gid"]].assign(in_project_points=1), on="gid", how="left")
    resource_layer["in_project_points"] = resource_layer["in_project_points"].fillna(0).astype(int)

    lat_edges = build_grid_edges(resource_layer["latitude"])
    lon_edges = build_grid_edges(resource_layer["longitude"])

    dataframe_to_geojson(
        resource_layer,
        lambda row: {
            "type": "Polygon",
            "coordinates": [[
                *polygon_from_center(row["latitude"], row["longitude"], lat_edges, lon_edges)
            ]],
        },
        LAYER_DIR / "resource_grid.geojson",
    )

    dataframe_to_geojson(
        project_points,
        lambda row: {
            "type": "Point",
            "coordinates": [float(row["longitude"]), float(row["latitude"])],
        },
        LAYER_DIR / "project_points.geojson",
    )

    sc_row_lookup = sc_df.groupby("sc_row_ind")["latitude"].mean().sort_index()
    sc_col_lookup = sc_df.groupby("sc_col_ind")["longitude"].mean().sort_index()
    sc_lat_edges = build_grid_edges(sc_row_lookup)
    sc_lon_edges = build_grid_edges(sc_col_lookup)

    sc_cells = sc_df.copy()
    sc_cells["developable_ratio"] = (
        sc_cells["area_developable_sq_km"] / (64 * 64 * PIXEL_AREA_SQ_KM)
    )

    dataframe_to_geojson(
        sc_cells,
        lambda row: {
            "type": "Polygon",
            "coordinates": [[
                *polygon_from_center(
                    sc_row_lookup.loc[row["sc_row_ind"]],
                    sc_col_lookup.loc[row["sc_col_ind"]],
                    sc_lat_edges,
                    sc_lon_edges,
                )
            ]],
        },
        LAYER_DIR / "supply_curve_cells.geojson",
    )

    sc_cells.to_csv(LAYER_DIR / "supply_curve_cells.csv", index=False)


def rerun_top5_profiles(generation_df: pd.DataFrame, time_index: pd.DatetimeIndex) -> tuple[pd.DataFrame, list[int]]:
    top5 = generation_df.nlargest(5, "annual_energy_mwh").copy()
    top5_gids = sorted(top5["gid"].astype(int).tolist())

    gen = Gen(
        "windpower",
        top5_gids,
        str(SAM_FPATH),
        str(RESOURCE_FPATH),
        output_request=("gen_profile", "cf_mean", "system_capacity"),
        sites_per_worker=5,
    )
    gen.run(max_workers=1)

    meta = gen.meta.reset_index(drop=True)
    gids = meta["gid"].astype(int).tolist()
    profiles = pd.DataFrame(gen.out["gen_profile"], index=time_index[: gen.out["gen_profile"].shape[0]], columns=gids)
    return profiles, gids


def plot_resource_map(resource_meta: pd.DataFrame, project_points: pd.DataFrame, top5_gids: list[int]) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 9.2))
    ax.scatter(
        resource_meta["longitude"],
        resource_meta["latitude"],
        marker="s",
        s=60,
        color="#d9d9d9",
        edgecolors="#ffffff",
        linewidths=0.3,
        label="WTK RI resource grid",
    )

    scatter = ax.scatter(
        project_points["longitude"],
        project_points["latitude"],
        c=project_points["cf_mean"],
        cmap="YlGnBu",
        s=78,
        edgecolors="#0f172a",
        linewidths=0.35,
        label="Project points",
    )

    top5 = project_points[project_points["gid"].isin(top5_gids)]
    ax.scatter(
        top5["longitude"],
        top5["latitude"],
        facecolors="none",
        edgecolors="#c2410c",
        s=180,
        linewidths=1.3,
        label="Top 5 annual energy gids",
    )

    for row in top5.itertuples(index=False):
        ax.text(row.longitude + 0.01, row.latitude + 0.003, f"gid {row.gid}", fontsize=8)

    cbar = fig.colorbar(scatter, ax=ax, shrink=0.85)
    cbar.set_label("Capacity factor")
    lon_pad = (resource_meta["longitude"].max() - resource_meta["longitude"].min()) * 0.06
    lat_pad = (resource_meta["latitude"].max() - resource_meta["latitude"].min()) * 0.03
    ax.set_xlim(resource_meta["longitude"].min() - lon_pad, resource_meta["longitude"].max() + lon_pad)
    ax.set_ylim(resource_meta["latitude"].min() - lat_pad, resource_meta["latitude"].max() + lat_pad)
    ax.set_title("Rhode Island Wind Resource Grid and Selected Project Points")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend(loc="lower left")
    ax.set_aspect("equal", adjustable="box")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "resource_project_points_map.png", dpi=220)
    plt.close(fig)


def plot_top5_profiles(profiles: pd.DataFrame) -> None:
    hourly_mw = profiles / 1000.0
    annual_energy = hourly_mw.sum(axis=0)

    fig, axes = plt.subplots(2, 1, figsize=(11, 10), height_ratios=[2.2, 1])

    for gid in hourly_mw.columns:
        axes[0].plot(hourly_mw.index, hourly_mw[gid], linewidth=1.2, label=f"gid {gid}")

    axes[0].set_title("Top 5 Gids Hourly Generation Profile (UTC, 8760 points)")
    axes[0].set_ylabel("Hourly generation (MW)")
    axes[0].set_xlabel("Time (UTC)")
    axes[0].grid(alpha=0.25)
    axes[0].legend(ncol=3, fontsize=9)

    colors = ["#0f766e", "#0ea5e9", "#eab308", "#ea580c", "#7c3aed"]
    axes[1].bar([str(gid) for gid in annual_energy.index], annual_energy.values, color=colors[: len(annual_energy)])
    axes[1].set_title("Top 5 Gids Annual Generation")
    axes[1].set_xlabel("gid")
    axes[1].set_ylabel("Annual generation (MWh)")
    axes[1].grid(axis="y", alpha=0.25)

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "top5_generation_profiles.png", dpi=220)
    plt.close(fig)


def plot_exclusion_overlay(sc_df: pd.DataFrame) -> None:
    with h5py.File(EXCL_FPATH, "r") as handle:
        techmap = handle["techmap_wtk_ri_100_local"][:]
        lat = handle["latitude"][:]
        lon = handle["longitude"][:]

    inclusion = (techmap != -1).astype(float)
    step = 8
    inclusion_ds = inclusion[::step, ::step]
    lat_ds = lat[::step, ::step]
    lon_ds = lon[::step, ::step]

    sc_plot = sc_df.copy()
    sc_plot["developable_ratio"] = (
        sc_plot["area_developable_sq_km"] / (64 * 64 * PIXEL_AREA_SQ_KM)
    )

    fig, ax = plt.subplots(figsize=(7.2, 9.2))
    mesh = ax.pcolormesh(
        lon_ds,
        lat_ds,
        inclusion_ds,
        cmap="Greys",
        shading="auto",
        alpha=0.55,
    )

    scatter = ax.scatter(
        sc_plot["longitude"],
        sc_plot["latitude"],
        c=sc_plot["developable_ratio"],
        cmap="YlOrRd",
        s=100,
        edgecolors="#111827",
        linewidths=0.35,
    )

    fig.colorbar(mesh, ax=ax, shrink=0.75, label="Techmap availability (0 excluded, 1 included)")
    fig.colorbar(scatter, ax=ax, shrink=0.75, label="Developable ratio per SC cell")
    lon_pad = (float(np.nanmax(lon_ds)) - float(np.nanmin(lon_ds))) * 0.04
    lat_pad = (float(np.nanmax(lat_ds)) - float(np.nanmin(lat_ds))) * 0.03
    ax.set_xlim(float(np.nanmin(lon_ds)) - lon_pad, float(np.nanmax(lon_ds)) + lon_pad)
    ax.set_ylim(float(np.nanmin(lat_ds)) - lat_pad, float(np.nanmax(lat_ds)) + lat_pad)
    ax.set_title("Techmap Footprint with Supply Curve Developable Area Overlay")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal", adjustable="box")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "exclusion_overlay_map.png", dpi=220)
    plt.close(fig)


def plot_supply_curve(sc_df: pd.DataFrame) -> None:
    curve = sc_df.dropna(subset=["lcoe_all_in_usd_per_mwh"]).copy()
    curve = curve.sort_values("lcoe_all_in_usd_per_mwh").reset_index(drop=True)
    curve["cumulative_capacity_mw"] = curve["capacity_ac_mw"].cumsum()

    fig, ax = plt.subplots(figsize=(10.5, 6.8))
    ax.step(
        curve["cumulative_capacity_mw"],
        curve["lcoe_all_in_usd_per_mwh"],
        where="post",
        linewidth=2.2,
        color="#0f766e",
    )
    ax.scatter(
        curve["cumulative_capacity_mw"],
        curve["lcoe_all_in_usd_per_mwh"],
        s=18,
        color="#115e59",
    )
    ax.set_title("Local Rhode Island Wind Supply Curve")
    ax.set_xlabel("Cumulative capacity (MW)")
    ax.set_ylabel("All-in LCOE (USD/MWh)")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "supply_curve.png", dpi=220)
    plt.close(fig)


def write_manifest(top5_gids: list[int]) -> None:
    manifest = {
        "figures": [
            "resource_project_points_map.png",
            "top5_generation_profiles.png",
            "exclusion_overlay_map.png",
            "supply_curve.png",
        ],
        "qgis_layers": [
            "qgis_layers/resource_grid.geojson",
            "qgis_layers/project_points.geojson",
            "qgis_layers/supply_curve_cells.geojson",
            "qgis_layers/supply_curve_cells.csv",
        ],
        "top5_gids": top5_gids,
        "notes": [
            "The current pipeline config sets excl_dict to null, so the exclusion overlay is a techmap availability footprint plus aggregated developable ratio.",
            "Top-5 generation profiles are produced by a minimal rerun for those five gids using reV Gen with gen_profile output.",
        ],
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> None:
    ensure_dirs()
    resource_meta, time_index = load_resource_meta()
    generation_df = load_generation_outputs()
    project_points = pd.read_csv(PROJECT_POINTS_FPATH).merge(generation_df, on="gid", how="left")
    sc_df = pd.read_csv(SC_FPATH)

    profiles, top5_gids = rerun_top5_profiles(generation_df, time_index)
    export_qgis_layers(resource_meta, project_points, sc_df)
    plot_resource_map(resource_meta, project_points, top5_gids)
    plot_top5_profiles(profiles)
    plot_exclusion_overlay(pd.read_csv(SC_AGG_FPATH))
    plot_supply_curve(sc_df)
    write_manifest(top5_gids)


if __name__ == "__main__":
    main()