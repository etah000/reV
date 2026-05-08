"""
era5_adapter.py
===============
Phase-B – Load ERA5 reanalysis NetCDF4/GRIB file(s) and produce per-site
hourly meteorological arrays in exactly the same format returned by
``synthetic_met.synthesize_all()``.

Supported ERA5 layouts
-----------------------
1. **Single combined file** – one NetCDF4/GRIB containing all variables.
2. **Per-variable files** – separate files, e.g.::

       era5_u100_2012.nc
       era5_v100_2012.nc
       era5_t2m_2012.nc
       era5_sp_2012.nc

3. **Monthly files** – multiple files for the same year, auto-merged via
   ``xarray.open_mfdataset``.

Variable auto-detection
-----------------------
The adapter detects variables by looking for well-known ERA5 short names in
priority order:

Wind (100 m):
  u100, v100  (direct 100 m components – preferred)
  u10,  v10   (10 m components – extrapolated to hub height via power law)

Temperature:
  t2m   – 2 m temperature (K)         → °C + lapse-rate correction to hub ht.
  t100  – 100 m temperature if present (unusual in ERA5 single-level)

Pressure:
  sp    – surface pressure (Pa)        → barometric formula to hub height
  msl   – mean sea-level pressure (Pa) → barometric formula

Spatial interpolation
----------------------
``scipy.interpolate.RegularGridInterpolator`` (bilinear, method='linear') is
used to map the ERA5 lat/lon grid to the irregular site locations.  ERA5 grids
are assumed to be regular in WGS-84.

Dependencies: xarray, scipy, numpy, pandas
Install (NetCDF4): pip install xarray scipy netcdf4
Install (GRIB):    pip install xarray scipy cfgrib
"""

from __future__ import annotations

import warnings
from glob import glob
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd


# ─── Physical constants (shared with synthetic_met) ──────────────────────────
KELVIN_OFFSET = 273.15
P0 = 101325.0
LAPSE_RATE = 0.0065      # K m⁻¹
G = 9.80665
M_AIR = 0.0289644
R = 8.31446

# Wind-shear exponent (power law) for extrapolating 10 m → hub height
# Typical open-terrain value; 0.14 is the IEC onshore default.
DEFAULT_WIND_SHEAR_ALPHA = 0.14


# ─── ERA5 variable name catalogue ────────────────────────────────────────────

# Keys are canonical internal names; values are ordered lists of ERA5 short names
_VAR_CANDIDATES = {
    "u_wind":    ["u100", "u10"],
    "v_wind":    ["v100", "v10"],
    "temp":      ["t2m", "t100", "2m_temperature"],
    "pressure":  ["sp", "msl", "surface_pressure", "mean_sea_level_pressure"],
}

# Reference heights for ERA5 wind variables (metres)
_WIND_REF_HEIGHT = {"u100": 100, "v100": 100, "u10": 10, "v10": 10}


# ─── Dataset loader ───────────────────────────────────────────────────────────

def open_era5(
    paths: Union[str, Path, list],
) -> "xr.Dataset":
    """
    Open one or more ERA5 NetCDF4/GRIB files as a single xarray Dataset.

    Parameters
    ----------
    paths : str, Path, or list of str/Path
        Single file, glob pattern (str), or list of files.

    Returns
    -------
    xr.Dataset
    """
    import xarray as xr

    def _to_file_list(inp: Union[str, Path, list]) -> list[str]:
        if isinstance(inp, (str, Path)):
            p = str(inp)
            if any(ch in p for ch in "*?[]"):
                return sorted(glob(p))
            return [p]

        out = []
        for item in inp:
            p = str(item)
            if any(ch in p for ch in "*?[]"):
                out.extend(sorted(glob(p)))
            else:
                out.append(p)
        return out

    def _engine_for_path(path: str) -> str:
        suffix = Path(path).suffix.lower()
        if suffix in {".grib", ".grb", ".grib2"}:
            return "cfgrib"
        return "netcdf4"

    def _open_single(path: str) -> "xr.Dataset":
        return xr.open_dataset(path, engine=_engine_for_path(path))

    files = _to_file_list(paths)
    if not files:
        raise FileNotFoundError(f"No ERA5 files matched: {paths}")

    by_engine: dict[str, list[str]] = {}
    for fp in files:
        by_engine.setdefault(_engine_for_path(fp), []).append(fp)

    opened = []
    for engine, engine_files in by_engine.items():
        if len(engine_files) == 1:
            opened.append(_open_single(engine_files[0]))
        elif engine == "netcdf4":
            opened.append(xr.open_mfdataset(engine_files, combine="by_coords", engine="netcdf4"))
        else:
            # cfgrib multi-file open_mfdataset can be brittle across monthly files;
            # open one-by-one then combine by coordinates.
            opened.extend(_open_single(fp) for fp in engine_files)

    if len(opened) == 1:
        return opened[0]

    ds = xr.combine_by_coords(opened, combine_attrs="override")
    return ds


def detect_variable(ds: "xr.Dataset", role: str) -> tuple[str, int]:
    """
    Find the first available ERA5 variable in the dataset for the given role.

    Returns
    -------
    (var_name, reference_height_m)
    """
    candidates = _VAR_CANDIDATES[role]
    for name in candidates:
        if name in ds.data_vars:
            ref_h = _WIND_REF_HEIGHT.get(name, 2 if "t" in name else 0)
            return name, ref_h
    available = list(ds.data_vars)
    raise KeyError(
        f"None of the expected ERA5 variables for '{role}' "
        f"({candidates}) found in dataset.  Available: {available}"
    )


# ─── Coordinate normalisation ─────────────────────────────────────────────────

def _normalise_coords(ds: "xr.Dataset") -> "xr.Dataset":
    """
    Rename ERA5 coordinate variants to standard ``latitude`` / ``longitude``
    and ensure longitude is in [-180, 180].
    """
    rename_map = {}
    for dim in ds.dims:
        if dim in ("lat", "LAT"):
            rename_map[dim] = "latitude"
        elif dim in ("lon", "LON"):
            rename_map[dim] = "longitude"
        elif dim in ("valid_time",):
            rename_map[dim] = "time"
    if rename_map:
        ds = ds.rename(rename_map)

    if "longitude" in ds.coords:
        lon = ds["longitude"].values
        if lon.max() > 180:
            # ERA5 default: 0–360 → shift to -180–180
            ds = ds.assign_coords(longitude=((lon + 180) % 360) - 180)
            ds = ds.sortby("longitude")

    return ds


# ─── Time slicing ─────────────────────────────────────────────────────────────

def _slice_year(ds: "xr.Dataset", year: int) -> "xr.Dataset":
    """Select only the timesteps belonging to *year*."""
    return ds.sel(time=str(year))


def _build_hourly_time_index(year: int) -> pd.DatetimeIndex:
    """Full UTC hourly DatetimeIndex for *year* (8760 or 8784 for leap years)."""
    start = pd.Timestamp(f"{year}-01-01 00:00:00", tz="UTC")
    end = pd.Timestamp(f"{year + 1}-01-01 00:00:00", tz="UTC")
    return pd.date_range(start, end, freq="h", inclusive="left")


def _align_to_target_index(
    arr: np.ndarray,
    era5_time: pd.DatetimeIndex,
    target_time: pd.DatetimeIndex,
) -> np.ndarray:
    """
    Reindex arr (T_era5, N) to target_time by forward-fill of missing hours
    and zero-fill of genuinely missing data (no ERA5 coverage).

    ERA5 may have fewer timesteps than 8784 if the download is incomplete.
    """
    if len(era5_time) == len(target_time) and (era5_time == target_time).all():
        return arr

    # Build a DataFrame to reindex safely
    df = pd.DataFrame(arr, index=era5_time)
    df = df.reindex(target_time, method="nearest", tolerance="1h")
    n_missing = df.isna().any(axis=1).sum()
    if n_missing > 0:
        warnings.warn(
            f"{n_missing} target timesteps have no ERA5 coverage; "
            "values filled by nearest-neighbour.", stacklevel=3
        )
        df = df.ffill().bfill()
    return df.values


# ─── Spatial interpolation ────────────────────────────────────────────────────

def _build_interpolator(
    lat_grid: np.ndarray,
    lon_grid: np.ndarray,
    data_2d: np.ndarray,
) -> "RegularGridInterpolator":
    """
    Build a scipy RegularGridInterpolator for a single (lat, lon) 2-D field.

    ERA5 latitude axis may be descending (90 → -90); scipy requires ascending,
    so we flip if necessary.
    """
    from scipy.interpolate import RegularGridInterpolator

    lats = lat_grid.astype(float)
    lons = lon_grid.astype(float)

    if lats[0] > lats[-1]:
        lats = lats[::-1]
        data_2d = data_2d[::-1, :]

    return RegularGridInterpolator(
        (lats, lons), data_2d,
        method="linear", bounds_error=False, fill_value=None,
    )


def _interpolate_field(
    lat_grid: np.ndarray,
    lon_grid: np.ndarray,
    field: np.ndarray,
    site_lats: np.ndarray,
    site_lons: np.ndarray,
) -> np.ndarray:
    """
    Bilinear spatial interpolation of a 3-D ERA5 field (T, nlat, nlon)
    to site locations.

    Returns
    -------
    ndarray, shape (T, N_sites)
    """
    T, nlat, nlon = field.shape
    N = len(site_lats)
    out = np.empty((T, N), dtype=np.float32)
    pts = np.column_stack([site_lats, site_lons])

    for t in range(T):
        interp = _build_interpolator(lat_grid, lon_grid, field[t])
        out[t] = interp(pts)

    return out


# ─── Physical conversions ─────────────────────────────────────────────────────

def uv_to_speed_direction(
    u: np.ndarray,
    v: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Convert (u, v) wind components to speed (m/s) and meteorological direction
    (degrees, 0 = from North, clockwise).

    Meteorological wind direction convention:
        direction = atan2(-u, -v) × 180 / π  (mod 360)
    """
    speed = np.sqrt(u ** 2 + v ** 2).astype(np.float32)
    direction = (np.degrees(np.arctan2(-u, -v)) % 360).astype(np.float32)
    direction[direction >= 360.0] = 0.0
    return speed, direction


def extrapolate_wind_to_hub(
    speed: np.ndarray,
    ref_height_m: float,
    hub_height_m: float,
    alpha: float = DEFAULT_WIND_SHEAR_ALPHA,
) -> np.ndarray:
    """
    Power-law wind-shear extrapolation from *ref_height_m* to *hub_height_m*.

        V_hub = V_ref × (h_hub / h_ref) ^ alpha

    Only applied when ref_height_m ≠ hub_height_m.
    """
    if abs(ref_height_m - hub_height_m) < 1.0:
        return speed
    factor = (hub_height_m / ref_height_m) ** alpha
    return (speed * factor).astype(np.float32)


def kelvin_to_celsius(t_k: np.ndarray) -> np.ndarray:
    """K → °C."""
    return (t_k - KELVIN_OFFSET).astype(np.float32)


def lapse_rate_correction(
    t_surface: np.ndarray,
    surface_elevation: np.ndarray,
    hub_height_m: float,
) -> np.ndarray:
    """
    Apply dry-adiabatic lapse rate correction to estimate temperature
    at hub height above the surface.

        ΔT = -LAPSE_RATE × (hub_height_m)        [K per metre]

    Note: *surface_elevation* is not used here (ERA5 t2m is at 2 m AGL,
    not at sea level); the correction is purely for the AGL height difference.
    """
    delta = -LAPSE_RATE * (hub_height_m - 2.0)  # 2 m → hub_height
    return (t_surface + delta).astype(np.float32)


def pressure_to_hub_height(
    p_surface: np.ndarray,
    surface_elevation: np.ndarray,
    hub_height_m: float,
) -> np.ndarray:
    """
    Barometric pressure at hub height above terrain.

    P_hub = P_surface × exp(-g × M_air × Δh / (R × T_mean))

    Uses T_mean = 288 K (ISA standard).
    """
    T_mean = 288.0  # K
    delta_h = hub_height_m  # approximate: hub is hub_height_m above surface
    factor = np.exp(-(G * M_AIR * delta_h) / (R * T_mean))
    return (p_surface * factor).astype(np.float32)


# ─── Top-level adapter ────────────────────────────────────────────────────────

def era5_adapter(
    era5_path: Union[str, Path, list],
    site_meta: pd.DataFrame,
    year: int = 2012,
    hub_height_m: float = 100.0,
    wind_shear_alpha: float = DEFAULT_WIND_SHEAR_ALPHA,
    verbose: bool = True,
) -> dict[str, np.ndarray]:
    """
    Load ERA5 NetCDF4/GRIB data and return per-site hourly meteorological
    arrays.

    This function is a drop-in replacement for ``synthetic_met.synthesize_all()``;
    it returns a dict with exactly the same keys.

    Parameters
    ----------
    era5_path : str, Path, or list
        Path(s) to ERA5 NetCDF4 or GRIB file(s). Supports single file, list of
        files, or a glob pattern string (e.g. ``"era5_*.nc"`` or
        ``"era5_*.grib"``).
    site_meta : DataFrame
        Must contain ``latitude``, ``longitude``, ``elevation``.
    year : int
        Calendar year to extract from the ERA5 data.
    hub_height_m : float
        Hub height in metres for wind shear extrapolation and lapse correction.
    wind_shear_alpha : float
        Power-law shear exponent (default 0.14, IEC onshore).
    verbose : bool
        Print progress messages.

    Returns
    -------
    dict with keys:
        ``time_index``      : pd.DatetimeIndex (T,)
        ``windspeed``       : float32 ndarray (T, N)
        ``winddirection``   : float32 ndarray (T, N)
        ``temperature``     : float32 ndarray (T, N)
        ``pressure``        : float32 ndarray (T, N)
    """
    import xarray as xr

    site_lats = site_meta["latitude"].values.astype(float)
    site_lons = site_meta["longitude"].values.astype(float)
    site_elevs = site_meta["elevation"].values.astype(float)
    N = len(site_lats)

    target_index = _build_hourly_time_index(year)
    T = len(target_index)

    if verbose:
        print(f"[era5_adapter] Loading ERA5 data from {era5_path} …")

    ds = open_era5(era5_path)
    ds = _normalise_coords(ds)
    ds = _slice_year(ds, year)

    # ── Detect ERA5 time axis ──────────────────────────────────────────────────
    era5_time = pd.DatetimeIndex(
        pd.to_datetime(ds["time"].values).tz_localize("UTC")
    )

    lat_grid = ds["latitude"].values.astype(float)
    lon_grid = ds["longitude"].values.astype(float)

    if verbose:
        print(f"  ERA5 grid    : {len(lat_grid)} lat × {len(lon_grid)} lon")
        print(f"  ERA5 time    : {len(era5_time)} steps, "
              f"{era5_time[0]} → {era5_time[-1]}")

    # ── Wind ──────────────────────────────────────────────────────────────────
    u_name, u_ref_h = detect_variable(ds, "u_wind")
    v_name, v_ref_h = detect_variable(ds, "v_wind")
    if verbose:
        print(f"  Wind vars    : {u_name} (ref {u_ref_h} m), {v_name} (ref {v_ref_h} m)")

    u_raw = ds[u_name].values.astype(np.float32)   # (T_era5, nlat, nlon)
    v_raw = ds[v_name].values.astype(np.float32)

    u_sites = _interpolate_field(lat_grid, lon_grid, u_raw, site_lats, site_lons)  # (T_era5, N)
    v_sites = _interpolate_field(lat_grid, lon_grid, v_raw, site_lats, site_lons)

    # Align to target time index
    u_sites = _align_to_target_index(u_sites, era5_time, target_index).astype(np.float32)
    v_sites = _align_to_target_index(v_sites, era5_time, target_index).astype(np.float32)

    ws, wd = uv_to_speed_direction(u_sites, v_sites)

    # Extrapolate to hub height if needed
    ws = extrapolate_wind_to_hub(ws, u_ref_h, hub_height_m, wind_shear_alpha)

    # ── Temperature ───────────────────────────────────────────────────────────
    t_name, _ = detect_variable(ds, "temp")
    if verbose:
        print(f"  Temp var     : {t_name}")

    t_raw = ds[t_name].values.astype(np.float32)
    t_sites = _interpolate_field(lat_grid, lon_grid, t_raw, site_lats, site_lons)
    t_sites = _align_to_target_index(t_sites, era5_time, target_index).astype(np.float32)

    # Convert K → °C (ERA5 temperatures are in Kelvin)
    if t_sites.mean() > 100:   # sanity: clearly in Kelvin
        t_sites = kelvin_to_celsius(t_sites)

    temp = lapse_rate_correction(t_sites, site_elevs, hub_height_m)

    # ── Pressure ──────────────────────────────────────────────────────────────
    p_name, _ = detect_variable(ds, "pressure")
    if verbose:
        print(f"  Pressure var : {p_name}")

    p_raw = ds[p_name].values.astype(np.float32)
    p_sites = _interpolate_field(lat_grid, lon_grid, p_raw, site_lats, site_lons)
    p_sites = _align_to_target_index(p_sites, era5_time, target_index).astype(np.float32)

    pressure = pressure_to_hub_height(p_sites, site_elevs, hub_height_m)

    ds.close()

    # ── Physical bounds check ─────────────────────────────────────────────────
    ws = np.clip(ws, 0.0, None)
    wd[wd >= 360.0] = 0.0
    temp = np.clip(temp, -80.0, 80.0)
    pressure = np.clip(pressure, 50_000, 110_000)

    if verbose:
        print(f"  windspeed    : mean={ws.mean():.2f} m/s, min={ws.min():.2f}, max={ws.max():.2f}")
        print(f"  winddirection: mean={wd.mean():.1f}°")
        print(f"  temperature  : mean={temp.mean():.1f} °C, min={temp.min():.1f}, max={temp.max():.1f}")
        print(f"  pressure     : mean={pressure.mean():.0f} Pa, min={pressure.min():.0f}, max={pressure.max():.0f}")
        print(f"[era5_adapter] Done. Shape ({T}, {N})")

    return {
        "time_index":    target_index,
        "windspeed":     ws.astype(np.float32),
        "winddirection": wd.astype(np.float32),
        "temperature":   temp.astype(np.float32),
        "pressure":      pressure.astype(np.float32),
    }


# ─── Helper: create a minimal synthetic ERA5-format NetCDF for testing ────────

def create_test_era5_netcdf(
    output_path: str | Path,
    year: int = 2012,
    lat_range: tuple = (39.0, 42.0),
    lon_range: tuple = (115.0, 118.0),
    resolution_deg: float = 0.25,
    seed: int = 0,
) -> Path:
    """
    Create a minimal ERA5-format NetCDF file with synthetic data for unit tests.

    The file contains u100, v100, t2m, sp on a regular 0.25° grid.
    This allows testing the era5_adapter without a real ERA5 download.

    Parameters
    ----------
    output_path : path-like
    year : int
    lat_range, lon_range : (min, max) tuples in degrees
    resolution_deg : float – grid spacing
    seed : int

    Returns
    -------
    Path to the written file.
    """
    import xarray as xr

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lats = np.arange(lat_range[1], lat_range[0] - resolution_deg, -resolution_deg)
    lons = np.arange(lon_range[0], lon_range[1] + resolution_deg, resolution_deg)

    # Use monthly time step for a tiny test file (12 steps instead of 8784)
    time_idx = pd.date_range(f"{year}-01-01", periods=12, freq="MS", tz="UTC")
    T = len(time_idx)
    nlat, nlon = len(lats), len(lons)

    rng = np.random.default_rng(seed)

    u100 = (7.0 + rng.normal(0, 1.5, (T, nlat, nlon))).astype(np.float32)
    v100 = (1.0 + rng.normal(0, 1.0, (T, nlat, nlon))).astype(np.float32)
    t2m  = (285.0 + 15 * np.sin(np.linspace(0, 2*np.pi, T))[:, None, None]
            + rng.normal(0, 2, (T, nlat, nlon))).astype(np.float32)
    sp   = (98000.0 + rng.normal(0, 500, (T, nlat, nlon))).astype(np.float32)

    # Remove timezone for NetCDF compatibility
    time_no_tz = time_idx.tz_localize(None)

    ds = xr.Dataset(
        {
            "u100": (["time", "latitude", "longitude"], u100),
            "v100": (["time", "latitude", "longitude"], v100),
            "t2m":  (["time", "latitude", "longitude"], t2m),
            "sp":   (["time", "latitude", "longitude"], sp),
        },
        coords={
            "time":      time_no_tz,
            "latitude":  lats,
            "longitude": lons,
        },
        attrs={
            "Conventions": "CF-1.6",
            "source":      "synthetic ERA5-format for testing",
            "history":     f"Created by era5_adapter.create_test_era5_netcdf (year={year})",
        },
    )

    ds.to_netcdf(str(output_path))
    print(f"[era5_adapter] Test NetCDF written: {output_path} "
          f"({T} timesteps, {nlat}×{nlon} grid)")
    return output_path
