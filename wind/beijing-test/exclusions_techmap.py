"""
exclusions_techmap.py
=====================
Step 5 – Build a minimal reV-compatible exclusions HDF5 and techmap dataset.

For the Beijing smoke-test / Phase-A pipeline we create a *placeholder*
exclusion layer (all cells included, i.e. no area excluded) and a techmap
that maps every exclusion-raster pixel to its nearest resource-file gid.

The raster is aligned to the same WGS-84 bounding box as the site grid,
at a configurable pixel resolution (default 500 m, matching WTK techmap
conventions – each resource cell covers ~4 pixels per side for a 2 km grid).

Replacing this module with real exclusion data (slope rasters, protected
areas, etc.) only requires swapping out ``build_exclusion_layer()``.

HDF5 output schema
------------------
  /latitude   – float64 (rows, cols)  – pixel centre latitudes
  /longitude  – float64 (rows, cols)  – pixel centre longitudes
  /<excl_key> – uint8   (1, rows, cols) – 0 = excluded, 100 = fully included
  /<tm_key>   – int32   (rows, cols)  – resource gid (-1 = no data)
    attrs:
      distance_threshold  – float
      src_res_fpath       – str
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import h5py
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree


# ─── Defaults ─────────────────────────────────────────────────────────────────
DEFAULT_PIXEL_M = 500        # exclusion raster pixel size in metres
DEFAULT_EXCL_KEY = "beijing_placeholder"
DEFAULT_TM_KEY = "techmap_beijing"
UTM50N_EPSG = "EPSG:32650"


# ─── Grid helpers ─────────────────────────────────────────────────────────────

def _build_pixel_grid(
    site_meta: pd.DataFrame,
    pixel_m: float,
    padding_m: float = 4_000,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Build a regular pixel grid in WGS-84 that covers all sites with padding.

    Uses an equirectangular approximation (fine for ~300 km study areas).

    Returns
    -------
    lat_grid, lon_grid : 2D float64 arrays of shape (rows, cols)
    """
    import geopandas as gpd
    from shapely.geometry import Point

    # Convert to UTM for equal-area raster construction
    gdf = gpd.GeoDataFrame(
        site_meta,
        geometry=gpd.points_from_xy(site_meta["longitude"], site_meta["latitude"]),
        crs="EPSG:4326",
    ).to_crs(UTM50N_EPSG)

    minx, miny, maxx, maxy = gdf.total_bounds
    minx -= padding_m
    miny -= padding_m
    maxx += padding_m
    maxy += padding_m

    xs = np.arange(minx + pixel_m / 2, maxx, pixel_m)
    ys = np.arange(miny + pixel_m / 2, maxy, pixel_m)
    xx, yy = np.meshgrid(xs, ys)  # (rows, cols)

    # Back-project to WGS-84
    rows, cols = xx.shape
    flat_pts = gpd.GeoDataFrame(
        geometry=[Point(x, y) for x, y in zip(xx.ravel(), yy.ravel())],
        crs=UTM50N_EPSG,
    ).to_crs("EPSG:4326")

    lons = np.array([pt.x for pt in flat_pts.geometry]).reshape(rows, cols)
    lats = np.array([pt.y for pt in flat_pts.geometry]).reshape(rows, cols)
    return lats.astype(np.float64), lons.astype(np.float64)


# ─── Exclusion layer builder ──────────────────────────────────────────────────

def build_exclusion_layer(
    lat_grid: np.ndarray,
    lon_grid: np.ndarray,
) -> np.ndarray:
    """
    Build a uint8 exclusion raster of shape (1, rows, cols).

    Convention (matches reV):
      0   – fully excluded
      100 – fully included

    This placeholder marks ALL pixels as fully included (100).
    Replace with real logic (slope mask, land-use mask, etc.) as needed.
    """
    rows, cols = lat_grid.shape
    excl = np.full((1, rows, cols), 100, dtype=np.uint8)
    return excl


def build_techmap(
    lat_grid: np.ndarray,
    lon_grid: np.ndarray,
    site_meta: pd.DataFrame,
    distance_threshold_deg: float = 0.05,
) -> tuple[np.ndarray, float]:
    """
    Build a techmap (int32) of shape (rows, cols) mapping each raster pixel
    to its nearest resource gid.

    Pixels farther than *distance_threshold_deg* from all sites are set to -1.

    Parameters
    ----------
    lat_grid, lon_grid : 2D arrays
    site_meta : DataFrame with latitude, longitude, gid columns
    distance_threshold_deg : float
        Pixels beyond this great-circle distance (degrees ≈ km / 111) from
        the nearest site get gid = -1.  Default 0.05° ≈ 5.5 km.

    Returns
    -------
    techmap : int32 (rows, cols)
    actual_threshold : float  (stored as HDF5 attribute)
    """
    rows, cols = lat_grid.shape

    site_lats = site_meta["latitude"].values
    site_lons = site_meta["longitude"].values
    gids = site_meta["gid"].values if "gid" in site_meta.columns else np.arange(len(site_meta))

    # Build KD-tree in (lat, lon) space
    tree = cKDTree(np.column_stack([site_lats, site_lons]))

    pixel_coords = np.column_stack([lat_grid.ravel(), lon_grid.ravel()])
    dists, idxs = tree.query(pixel_coords, workers=-1)

    techmap = gids[idxs].astype(np.int32)
    techmap[dists > distance_threshold_deg] = -1

    techmap = techmap.reshape(rows, cols)

    # Compute a representative threshold for the attrs (mean nearest-site dist)
    actual_threshold = float(np.median(dists[dists < distance_threshold_deg]))
    return techmap, actual_threshold


# ─── Writer ───────────────────────────────────────────────────────────────────

def write_exclusions_h5(
    output_path: str | Path,
    lat_grid: np.ndarray,
    lon_grid: np.ndarray,
    excl_layer: np.ndarray,
    techmap: np.ndarray,
    distance_threshold: float,
    resource_fpath: str,
    excl_key: str = DEFAULT_EXCL_KEY,
    tm_key: str = DEFAULT_TM_KEY,
    overwrite: bool = False,
) -> Path:
    """Write the exclusions + techmap HDF5 file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"{output_path} exists. Pass overwrite=True to replace."
        )

    rows, cols = lat_grid.shape
    print(f"[exclusions_techmap] Writing {output_path} …")
    print(f"  Raster size     : {rows} × {cols} pixels")
    print(f"  Excl key        : {excl_key}")
    print(f"  Techmap key     : {tm_key}")

    with h5py.File(str(output_path), "w") as f:
        f.create_dataset("latitude", data=lat_grid,
                         compression="gzip", compression_opts=4)
        f.create_dataset("longitude", data=lon_grid,
                         compression="gzip", compression_opts=4)
        f.create_dataset(excl_key, data=excl_layer,
                         compression="gzip", compression_opts=4)
        tm_ds = f.create_dataset(tm_key, data=techmap,
                                  compression="gzip", compression_opts=4)
        tm_ds.attrs["distance_threshold"] = distance_threshold
        tm_ds.attrs["src_res_fpath"] = str(resource_fpath)

    file_mb = output_path.stat().st_size / 1_048_576
    print(f"  Done. File size : {file_mb:.1f} MB → {output_path}")
    return output_path


# ─── Top-level pipeline entry point ──────────────────────────────────────────

def build_exclusions_and_techmap(
    site_meta: pd.DataFrame,
    resource_fpath: str | Path,
    output_dir: str | Path,
    pixel_m: float = DEFAULT_PIXEL_M,
    excl_key: str = DEFAULT_EXCL_KEY,
    tm_key: str = DEFAULT_TM_KEY,
    overwrite: bool = False,
) -> Path:
    """
    Full pipeline: build raster grid, exclusion layer, techmap, and write HDF5.

    Parameters
    ----------
    site_meta : DataFrame
    resource_fpath : path-like
        Path to the wind resource HDF5 (stored in techmap attrs).
    output_dir : path-like
        Directory for the output ``beijing_exclusions.h5`` file.
    pixel_m : float
        Exclusion raster pixel size in metres.
    excl_key : str
        Dataset name for the exclusion layer inside the HDF5.
    tm_key : str
        Dataset name for the techmap inside the HDF5.
    overwrite : bool

    Returns
    -------
    Path to the written HDF5 file.
    """
    output_path = Path(output_dir) / "beijing_exclusions.h5"

    lat_grid, lon_grid = _build_pixel_grid(site_meta, pixel_m)
    excl_layer = build_exclusion_layer(lat_grid, lon_grid)
    techmap, dist_thresh = build_techmap(lat_grid, lon_grid, site_meta)

    write_exclusions_h5(
        output_path,
        lat_grid, lon_grid,
        excl_layer, techmap,
        distance_threshold=dist_thresh,
        resource_fpath=str(resource_fpath),
        excl_key=excl_key,
        tm_key=tm_key,
        overwrite=overwrite,
    )
    return output_path


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Build Beijing exclusions + techmap HDF5."
    )
    parser.add_argument("site_meta_csv",   help="CSV from grid_generation.py")
    parser.add_argument("resource_h5",     help="Wind resource HDF5 path")
    parser.add_argument("--output-dir",    default="./output")
    parser.add_argument("--pixel-m",       type=float, default=500)
    parser.add_argument("--excl-key",      default=DEFAULT_EXCL_KEY)
    parser.add_argument("--tm-key",        default=DEFAULT_TM_KEY)
    parser.add_argument("--overwrite",     action="store_true")
    args = parser.parse_args()

    meta = pd.read_csv(args.site_meta_csv)
    build_exclusions_and_techmap(
        meta, args.resource_h5, args.output_dir,
        args.pixel_m, args.excl_key, args.tm_key, args.overwrite,
    )
