"""
synthetic_met.py
================
Step 2 – Generate synthetic hourly meteorological time-series for all sites.

Model (Phase A – statistics-only):
  - Wind speed   : Weibull-shaped annual mean + seasonal cycle + diurnal cycle
                   + spatially correlated Gaussian noise.
  - Wind direction: Annual mean (prevailing NW in Beijing winter, SE summer)
                   + seasonal swing + small random walk per timestep.
  - Temperature  : Seasonal sinusoid + diurnal sinusoid + small white noise.
  - Pressure     : Barometric formula from elevation + slow seasonal drift
                   + site-scale noise.

Phase B hook: replace `synthesize_all()` with `era5_adapter.synthesize_all()`
that reads a pre-downloaded ERA5 NetCDF and returns the same dict of arrays.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


# ─── Physical constants ───────────────────────────────────────────────────────
KELVIN_OFFSET = 273.15   # °C → K
P0 = 101325.0            # Pa – standard sea-level pressure
LAPSE_RATE = 0.0065      # K m⁻¹ – standard atmosphere lapse rate
G = 9.80665              # m s⁻² – gravity
M_AIR = 0.0289644        # kg mol⁻¹ – molar mass of air
R = 8.31446              # J mol⁻¹ K⁻¹ – universal gas constant

# ─── Beijing climate parameters ───────────────────────────────────────────────
# Wind speed at 100 m: typical annual mean ~7–9 m/s over open terrain
WS_MEAN = 7.5            # m/s  – annual-mean wind speed at 100 m
WS_SEASONAL_AMP = 1.5   # m/s  – peak-to-peak seasonal amplitude (stronger in spring)
WS_DIURNAL_AMP = 0.8    # m/s  – peak-to-peak diurnal amplitude (higher afternoon)
WS_SPATIAL_CORR_LEN = 50_000  # m – spatial correlation length-scale (~50 km)
WS_NOISE_STD = 1.2       # m/s  – local residual noise

WD_PREVAILING = 315.0    # degrees – prevailing NW direction
WD_SEASONAL_AMP = 90.0  # degrees – summer swing toward SE (~135°)
WD_NOISE_STD = 30.0      # degrees

T_MEAN = 12.0            # °C – annual-mean 2 m temperature (100 m ≈ slightly cooler)
T_SEASONAL_AMP = 20.0   # °C – summer/winter swing
T_DIURNAL_AMP = 5.0     # °C – day/night swing
T_LAPSE_CORRECTION = -0.65  # °C per 100 m – adjust for hub height vs surface

YEAR = 2012              # leap year → 8 784 hours


def _build_time_index(year: int = YEAR) -> pd.DatetimeIndex:
    """UTC hourly DatetimeIndex for the full calendar year."""
    start = pd.Timestamp(f"{year}-01-01 00:00:00", tz="UTC")
    end = pd.Timestamp(f"{year + 1}-01-01 00:00:00", tz="UTC")
    return pd.date_range(start, end, freq="h", inclusive="left")


def _phase_of_year(time_index: pd.DatetimeIndex) -> np.ndarray:
    """Normalised annual phase in [0, 2π] for each timestep."""
    doy = time_index.day_of_year.values.astype(float)
    n_days = 366 if _is_leap(time_index[0].year) else 365
    return 2 * np.pi * doy / n_days


def _phase_of_day(time_index: pd.DatetimeIndex, tz_offset_h: float = 8.0) -> np.ndarray:
    """Normalised daily phase in [0, 2π] adjusted for local time."""
    local_hour = (time_index.hour.values + tz_offset_h) % 24
    return 2 * np.pi * local_hour / 24


def _is_leap(year: int) -> bool:
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)


# ─── Spatial correlation helpers ─────────────────────────────────────────────

def _spatial_corr_cholesky(
    lats: np.ndarray,
    lons: np.ndarray,
    corr_len_m: float,
    max_sites: int = 500,
) -> np.ndarray:
    """
    Lower-triangular Cholesky factor of an isotropic exponential spatial
    correlation matrix.

    For very large site counts the matrix is approximated by clamping to
    *max_sites* representative nodes and falling back to a diagonal (no spatial
    correlation), to avoid O(N²) memory issues.

    Returns
    -------
    L : ndarray, shape (N, N)
        Cholesky factor such that ``L @ z`` gives spatially correlated noise.
    """
    n = len(lats)
    # Convert lat/lon to rough cartesian metres (equirectangular, good enough
    # for correlation distances relative to the study area).
    lat0 = np.deg2rad(np.mean(lats))
    dx = np.deg2rad(lons - np.mean(lons)) * np.cos(lat0) * 6_371_000
    dy = np.deg2rad(lats - np.mean(lats)) * 6_371_000

    if n > max_sites:
        # Fallback: diagonal (independent noise)
        return np.eye(n)

    dist = np.sqrt((dx[:, None] - dx[None, :]) ** 2 +
                   (dy[:, None] - dy[None, :]) ** 2)
    C = np.exp(-dist / corr_len_m)
    # Add small nugget for numerical stability
    C += 1e-6 * np.eye(n)
    return np.linalg.cholesky(C)


# ─── Individual variable synthesizers ────────────────────────────────────────

def synthesize_wind_speed(
    time_index: pd.DatetimeIndex,
    lats: np.ndarray,
    lons: np.ndarray,
    elevations: np.ndarray,
    rng: np.random.Generator,
    hub_height_m: float = 100.0,
) -> np.ndarray:
    """
    Synthetic 100 m wind speed (m/s), shape (T, N).

    Parameters
    ----------
    time_index : DatetimeIndex
    lats, lons, elevations : 1-D arrays of length N
    rng : numpy Generator (seeded externally for reproducibility)
    hub_height_m : float – hub height for shear adjustment

    Returns
    -------
    ws : float32 array (T, N), values ≥ 0
    """
    T = len(time_index)
    N = len(lats)

    phi_year = _phase_of_year(time_index)   # (T,)
    phi_day = _phase_of_day(time_index)     # (T,)

    # Seasonal: stronger in spring (March–April ≈ φ ≈ π/3)
    seasonal = WS_SEASONAL_AMP * np.cos(phi_year - np.pi / 3)  # (T,)
    # Diurnal: peak in early afternoon (14:00 local ≈ φ ≈ π·14/12)
    diurnal = WS_DIURNAL_AMP * np.sin(phi_day - np.pi * 14 / 12)  # (T,)

    # Deterministic signal broadcast to (T, N)
    base = np.broadcast_to(
        (WS_MEAN + seasonal[:, None] + diurnal[:, None]),  # (T, 1)
        (T, N),
    ).copy()

    # Small site-scale elevation bias: higher terrain → slightly higher speed
    elev_bias = 0.001 * (elevations - 50.0)  # (N,)
    signal = base + elev_bias[None, :]

    # Spatially correlated noise
    L = _spatial_corr_cholesky(lats, lons, WS_SPATIAL_CORR_LEN)
    white = rng.standard_normal((T, N))
    corr_noise = WS_NOISE_STD * (white @ L.T)  # (T, N)

    ws = signal + corr_noise
    ws = np.clip(ws, 0.0, None)  # physically non-negative
    return ws.astype(np.float32)


def synthesize_wind_direction(
    time_index: pd.DatetimeIndex,
    n_sites: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Synthetic 100 m wind direction (degrees, [0, 360)), shape (T, N).

    Beijing prevailing wind: NW (≈315°) in winter, shifting to SE (≈135°) in
    summer, modelled with a seasonal cosine swing.
    """
    T = len(time_index)
    phi_year = _phase_of_year(time_index)  # (T,)

    # Summer peak at φ = π (≈ July 2)
    seasonal_shift = WD_SEASONAL_AMP * np.cos(phi_year - np.pi)  # (T,)
    mean_dir = WD_PREVAILING + seasonal_shift  # (T,)

    # White noise per site (spatial correlation in direction is minor)
    noise = rng.normal(0, WD_NOISE_STD, size=(T, n_sites))
    wd = mean_dir[:, None] + noise
    wd = wd % 360.0
    # Guard against floating-point 360.0 exactly (can survive float32 cast too)
    wd[wd >= 360.0] = 0.0
    wd = wd.astype(np.float32)
    wd[wd >= 360.0] = 0.0   # re-check after float32 cast
    return wd


def synthesize_temperature(
    time_index: pd.DatetimeIndex,
    elevations: np.ndarray,
    rng: np.random.Generator,
    hub_height_m: float = 100.0,
) -> np.ndarray:
    """
    Synthetic air temperature at hub height (°C), shape (T, N).

    Seasonal + diurnal sinusoid plus a lapse-rate correction from surface
    elevation to hub height.
    """
    T = len(time_index)
    N = len(elevations)

    phi_year = _phase_of_year(time_index)
    phi_day = _phase_of_day(time_index)

    # Seasonal: peak in July (φ ≈ π)
    seasonal = T_SEASONAL_AMP * np.cos(phi_year - np.pi)   # warm in summer
    # Diurnal: peak around 14:00 local
    diurnal = T_DIURNAL_AMP * np.sin(phi_day - np.pi * 14 / 12)

    base = np.broadcast_to(
        T_MEAN + seasonal[:, None] + diurnal[:, None],  # (T, 1)
        (T, N),
    ).copy()

    # Lapse-rate correction: hub is hub_height_m above ground level
    lapse_correction = T_LAPSE_CORRECTION * hub_height_m / 100.0  # scalar (°C)
    base += lapse_correction

    # Elevation correction from mean to actual site elevation
    elev_correction = T_LAPSE_CORRECTION * (elevations - 50.0) / 100.0  # (N,)
    signal = base + elev_correction[None, :]

    noise = rng.normal(0, 0.5, size=(T, N))
    temp = signal + noise
    return temp.astype(np.float32)


def synthesize_pressure(
    time_index: pd.DatetimeIndex,
    elevations: np.ndarray,
    rng: np.random.Generator,
    hub_height_m: float = 100.0,
) -> np.ndarray:
    """
    Synthetic air pressure at hub height (Pa), shape (T, N).

    Uses the barometric formula to derive base pressure from site elevation
    then adds seasonal drift and small random noise.
    """
    T = len(time_index)
    N = len(elevations)

    # Barometric formula: P = P0 * (1 - L*h / T0) ^ (g*M / (R*L))
    T0 = KELVIN_OFFSET + 15.0  # K – ISA sea-level temperature
    exp = G * M_AIR / (R * LAPSE_RATE)
    h_total = elevations + hub_height_m  # total height above sea level
    p_base = P0 * np.power(np.maximum(1 - LAPSE_RATE * h_total / T0, 1e-4), exp)

    phi_year = _phase_of_year(time_index)
    # Slight seasonal: higher pressure in winter in Beijing (anticyclone)
    seasonal_pa = 500.0 * np.cos(phi_year)   # ±500 Pa seasonal swing

    signal = (p_base[None, :] + seasonal_pa[:, None]) * np.ones((T, N))

    noise = rng.normal(0, 100.0, size=(T, N))  # ±100 Pa RMS noise
    pressure = signal + noise
    pressure = np.clip(pressure, 50_000, 110_000)  # physical plausibility
    return pressure.astype(np.float32)


# ─── Top-level synthesizer ────────────────────────────────────────────────────

def synthesize_all(
    site_meta: "pd.DataFrame",
    year: int = YEAR,
    hub_height_m: float = 100.0,
    seed: Optional[int] = 42,
) -> dict[str, np.ndarray]:
    """
    Generate all four meteorological variables for every site.

    Parameters
    ----------
    site_meta : DataFrame
        Must contain columns: ``latitude``, ``longitude``, ``elevation``.
    year : int
        Calendar year (use 2012 to match reV test fixtures).
    hub_height_m : float
        Hub height (metres) – used for lapse rate and shear corrections.
    seed : int or None
        Random seed for reproducibility. ``None`` → non-deterministic.

    Returns
    -------
    dict with keys:
        ``time_index``      : pd.DatetimeIndex (T,)
        ``windspeed``       : float32 ndarray (T, N)
        ``winddirection``   : float32 ndarray (T, N)
        ``temperature``     : float32 ndarray (T, N)
        ``pressure``        : float32 ndarray (T, N)
    """
    rng = np.random.default_rng(seed)
    time_index = _build_time_index(year)

    lats = site_meta["latitude"].values.astype(float)
    lons = site_meta["longitude"].values.astype(float)
    elevations = site_meta["elevation"].values.astype(float)
    n_sites = len(lats)
    T = len(time_index)

    print(f"[synthetic_met] Synthesizing {T} timesteps × {n_sites} sites …")

    ws = synthesize_wind_speed(time_index, lats, lons, elevations, rng, hub_height_m)
    wd = synthesize_wind_direction(time_index, n_sites, rng)
    temp = synthesize_temperature(time_index, elevations, rng, hub_height_m)
    pres = synthesize_pressure(time_index, elevations, rng, hub_height_m)

    # Quick sanity checks
    _validate_arrays(ws=ws, wd=wd, temp=temp, pres=pres, T=T, N=n_sites)

    return {
        "time_index":    time_index,
        "windspeed":     ws,
        "winddirection": wd,
        "temperature":   temp,
        "pressure":      pres,
    }


def _validate_arrays(
    ws: np.ndarray,
    wd: np.ndarray,
    temp: np.ndarray,
    pres: np.ndarray,
    T: int,
    N: int,
) -> None:
    """Raise ValueError if any physical constraint is violated."""
    assert ws.shape == (T, N),   f"windspeed shape mismatch: {ws.shape}"
    assert wd.shape == (T, N),   f"winddirection shape mismatch: {wd.shape}"
    assert temp.shape == (T, N), f"temperature shape mismatch: {temp.shape}"
    assert pres.shape == (T, N), f"pressure shape mismatch: {pres.shape}"

    if np.any(ws < 0):
        raise ValueError("Wind speed contains negative values.")
    if np.any(wd < 0) or np.any(wd >= 360.0):
        bad = wd[(wd < 0) | (wd >= 360.0)]
        raise ValueError(f"Wind direction outside [0, 360): {bad[:5]}")
    if np.any((temp < -80) | (temp > 60)):
        raise ValueError("Temperature outside plausible range [-80, 60] °C.")
    if np.any((pres < 50_000) | (pres > 110_000)):
        raise ValueError("Pressure outside plausible range [50 000, 110 000] Pa.")

    print(f"  windspeed    : mean={ws.mean():.2f} m/s, min={ws.min():.2f}, max={ws.max():.2f}")
    print(f"  winddirection: mean={wd.mean():.1f}°")
    print(f"  temperature  : mean={temp.mean():.1f} °C, min={temp.min():.1f}, max={temp.max():.1f}")
    print(f"  pressure     : mean={pres.mean():.0f} Pa, min={pres.min():.0f}, max={pres.max():.0f}")


# ─── ERA5 Phase-B adapter (delegates to era5_adapter module) ────────────────────

def era5_adapter(
    era5_nc_path: str,
    site_meta: "pd.DataFrame",
    year: int = YEAR,
    hub_height_m: float = 100.0,
    wind_shear_alpha: float = 0.14,
) -> dict[str, np.ndarray]:
    """
    Phase-B: load ERA5 NetCDF file(s) and interpolate to site locations.

    Delegates to :mod:`era5_adapter`; see that module for full documentation.
    The return dict has exactly the same keys as ``synthesize_all()``.

    Parameters
    ----------
    era5_nc_path : str, Path, or list
        Path(s) to ERA5 NetCDF file(s) or a glob pattern.
    site_meta : DataFrame
        Must contain ``latitude``, ``longitude``, ``elevation``.
    year : int
        Calendar year to extract.
    hub_height_m : float
        Hub height for wind shear extrapolation and lapse-rate correction.
    wind_shear_alpha : float
        Power-law shear exponent (default 0.14).
    """
    from era5_adapter import era5_adapter as _era5_adapter
    return _era5_adapter(
        era5_nc_path, site_meta,
        year=year, hub_height_m=hub_height_m,
        wind_shear_alpha=wind_shear_alpha,
    )


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Synthesize hourly meteorological data for reV resource file."
    )
    parser.add_argument("site_meta_csv", help="CSV produced by grid_generation.py")
    parser.add_argument("--year", type=int, default=YEAR)
    parser.add_argument("--hub-height", type=float, default=100.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output-npy", default=None,
        help="Optional: save arrays to a .npz file for inspection."
    )
    args = parser.parse_args()

    meta = pd.read_csv(args.site_meta_csv)
    data = synthesize_all(meta, year=args.year, hub_height_m=args.hub_height, seed=args.seed)

    if args.output_npy:
        np.savez_compressed(
            args.output_npy,
            windspeed=data["windspeed"],
            winddirection=data["winddirection"],
            temperature=data["temperature"],
            pressure=data["pressure"],
        )
        print(f"[synthetic_met] Arrays saved to {args.output_npy}")
