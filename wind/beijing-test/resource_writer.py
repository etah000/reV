"""
resource_writer.py
==================
Step 3 – Write synthetic meteorological data to a reV/rex-compatible HDF5
wind resource file and verify the result.

HDF5 schema (mirrors NREL WTK / ri_100_wtk_2012.h5 structure):
  /meta           – structured numpy array, columns matching rex expectations
  /time_index     – byte-string array (ISO-8601 UTC timestamps)
  /windspeed_100m     – float32 (T, N)
  /winddirection_100m – float32 (T, N)
  /temperature_100m   – float32 (T, N)
  /pressure_100m      – float32 (T, N)

All datasets are written via reV ``Outputs`` where possible; otherwise via
h5py directly to guarantee no unintended format drift.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import h5py
import numpy as np
import pandas as pd


# ─── Required meta columns (matches rex WindResource expectations) ─────────────
REQUIRED_META_COLS = ["latitude", "longitude", "country", "state", "county",
                      "timezone", "elevation", "offshore"]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _encode_time_index(time_index: pd.DatetimeIndex) -> np.ndarray:
    """
    Encode a DatetimeIndex as a byte-string array readable by rex/WindResource.

    rex reads time_index as ``pandas.to_datetime(bytes_array)``, so the format
    must be ``b"YYYY-MM-DD HH:MM:SS+00:00"``.
    """
    strs = time_index.strftime("%Y-%m-%d %H:%M:%S+00:00")
    return np.array([s.encode("utf-8") for s in strs], dtype=object)


def _meta_to_structured_array(meta: pd.DataFrame) -> np.ndarray:
    """
    Convert a pandas DataFrame to a numpy void (structured) array as expected
    by rex Resource / WindResource.

    Columns are cast to dtypes matching the WTK reference file.
    """
    # Ensure all required columns are present, fill missing ones with defaults.
    meta = meta.copy()
    defaults = {
        "country":  "China",
        "state":    "Beijing",
        "county":   "Beijing",
        "timezone": 8,
        "offshore": 0,
    }
    for col, default in defaults.items():
        if col not in meta.columns:
            meta[col] = default

    # Define structured dtype (mirrors ri_100_wtk_2012.h5 meta dtype)
    dt = np.dtype([
        ("gid",       np.int32),
        ("latitude",  np.float32),
        ("longitude", np.float32),
        ("country",   "S32"),
        ("state",     "S32"),
        ("county",    "S32"),
        ("timezone",  np.int16),
        ("elevation", np.float32),
        ("offshore",  np.uint8),
    ])

    arr = np.empty(len(meta), dtype=dt)
    arr["gid"]       = meta.get("gid", np.arange(len(meta))).astype(np.int32)
    arr["latitude"]  = meta["latitude"].astype(np.float32)
    arr["longitude"] = meta["longitude"].astype(np.float32)
    arr["country"]   = meta["country"].astype(str).str.encode("utf-8")
    arr["state"]     = meta["state"].astype(str).str.encode("utf-8")
    arr["county"]    = meta["county"].astype(str).str.encode("utf-8")
    arr["timezone"]  = meta["timezone"].astype(np.int16)
    arr["elevation"] = meta["elevation"].astype(np.float32)
    arr["offshore"]  = meta["offshore"].astype(np.uint8)
    return arr


# ─── Writer ───────────────────────────────────────────────────────────────────

def write_resource_file(
    output_path: str | Path,
    site_meta: pd.DataFrame,
    met_data: dict[str, np.ndarray],
    hub_height_m: int = 100,
    chunk_time: int = 100,
    chunk_space: int = 25,
    overwrite: bool = False,
) -> Path:
    """
    Write a reV/rex-compatible wind resource HDF5 file.

    Parameters
    ----------
    output_path : path-like
        Destination ``.h5`` file path.
    site_meta : DataFrame
        Site metadata (at minimum: latitude, longitude, timezone, elevation).
    met_data : dict
        Must contain keys: ``time_index``, ``windspeed``, ``winddirection``,
        ``temperature``, ``pressure``.  Each array must be float32 (T, N).
    hub_height_m : int
        Hub height appended to dataset names (e.g. ``windspeed_100m``).
    chunk_time : int
        HDF5 chunk size along the time axis.
    chunk_space : int
        HDF5 chunk size along the spatial axis.
    overwrite : bool
        If False and the file already exists, raise FileExistsError.

    Returns
    -------
    Path to the written file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"{output_path} already exists. Pass overwrite=True to replace it."
        )

    time_index: pd.DatetimeIndex = met_data["time_index"]
    T = len(time_index)
    N = len(site_meta)

    _assert_shape(met_data["windspeed"],     (T, N), "windspeed")
    _assert_shape(met_data["winddirection"], (T, N), "winddirection")
    _assert_shape(met_data["temperature"],   (T, N), "temperature")
    _assert_shape(met_data["pressure"],      (T, N), "pressure")

    meta_arr = _meta_to_structured_array(site_meta)
    ti_bytes = _encode_time_index(time_index)

    # Clamp chunk sizes so they never exceed the actual dimension sizes.
    actual_chunk_time = min(chunk_time, T)
    actual_chunk_space = min(chunk_space, N)
    chunks = (actual_chunk_time, actual_chunk_space)

    h = hub_height_m
    datasets = {
        f"windspeed_{h}m":     met_data["windspeed"],
        f"winddirection_{h}m": met_data["winddirection"],
        f"temperature_{h}m":   met_data["temperature"],
        f"pressure_{h}m":      met_data["pressure"],
    }

    print(f"[resource_writer] Writing {output_path} …")
    print(f"  Sites      : {N}")
    print(f"  Timesteps  : {T}  ({time_index[0]} → {time_index[-1]})")
    print(f"  Hub height : {hub_height_m} m")

    with h5py.File(str(output_path), "w") as f:
        # meta
        f.create_dataset("meta", data=meta_arr, compression="gzip",
                         compression_opts=4)
        # time_index
        dt_vlen = h5py.special_dtype(vlen=bytes)
        f.create_dataset("time_index", data=ti_bytes, dtype=dt_vlen)
        # meteorological arrays
        for name, arr in datasets.items():
            f.create_dataset(
                name, data=arr.astype(np.float32),
                chunks=chunks, compression="gzip", compression_opts=4,
                shuffle=True,
            )
        f.attrs["source"] = "synthetic – beijing-test pipeline"
        f.attrs["hub_height_m"] = hub_height_m
        f.attrs["year"] = int(time_index[0].year)

    file_size_mb = output_path.stat().st_size / 1_048_576
    print(f"  Done. File size: {file_size_mb:.1f} MB → {output_path}")
    return output_path


def _assert_shape(arr: np.ndarray, expected: tuple, name: str) -> None:
    if arr.shape != expected:
        raise ValueError(
            f"{name}: expected shape {expected}, got {arr.shape}"
        )


# ─── Validator ────────────────────────────────────────────────────────────────

def validate_resource_file(resource_path: str | Path) -> bool:
    """
    Validate a wind resource HDF5 file against reV/rex requirements.

    Checks:
      1. Required datasets present (meta, time_index, windspeed/direction/
         temperature/pressure at any height).
      2. time_index starts on Jan 1 00:00 UTC.
      3. time_index length is a multiple of 8760 (or 8784 for leap years).
      4. All 2D datasets have shape (T, N) matching time_index and meta.
      5. Physical plausibility of each variable.
      6. meta has required columns (latitude, longitude, timezone, elevation).

    Returns True if all checks pass; raises AssertionError otherwise.
    """
    from rex import WindResource

    resource_path = Path(resource_path)
    print(f"\n[validate] Checking {resource_path} …")

    with WindResource(str(resource_path)) as res:
        # ── 1. Datasets ────────────────────────────────────────────────────
        keys = list(res.h5.keys())
        print(f"  Datasets   : {keys}")
        for required in ("meta", "time_index"):
            assert required in keys, f"Missing dataset: {required}"

        # Detect hub height from dataset names
        ws_keys = [k for k in keys if k.startswith("windspeed_")]
        assert ws_keys, "No windspeed_*m dataset found."
        hub_h = ws_keys[0].replace("windspeed_", "").replace("m", "")
        print(f"  Hub height : {hub_h} m  (detected)")

        # ── 2. time_index ──────────────────────────────────────────────────
        ti = res.time_index
        T = len(ti)
        assert ti[0].month == 1 and ti[0].day == 1 and ti[0].hour == 0, \
            f"time_index must start at Jan 1 00:00 UTC; got {ti[0]}"
        year = ti[0].year
        expected_hours = 8784 if _is_leap(year) else 8760
        assert T == expected_hours, \
            f"time_index length {T} ≠ {expected_hours} for year {year}"
        print(f"  time_index : {T} hours, starts {ti[0]}, ends {ti[-1]}")

        # ── 3. meta ────────────────────────────────────────────────────────
        meta = res.meta
        N = len(meta)
        required_meta = {"latitude", "longitude", "timezone", "elevation"}
        missing_meta = required_meta - set(meta.columns)
        assert not missing_meta, f"meta missing columns: {missing_meta}"
        print(f"  meta       : {N} sites, columns: {list(meta.columns)}")

        # ── 4. Array shapes ───────────────────────────────────────────────
        for prefix in (f"windspeed_{hub_h}m", f"winddirection_{hub_h}m",
                       f"temperature_{hub_h}m", f"pressure_{hub_h}m"):
            if prefix not in keys:
                continue
            arr = res[prefix]
            assert arr.shape == (T, N), \
                f"{prefix} shape {arr.shape} ≠ ({T}, {N})"
            print(f"  {prefix:30s}: shape {arr.shape} ✓")

        # ── 5. Physical plausibility ───────────────────────────────────────
        ws = res[f"windspeed_{hub_h}m"]
        wd = res[f"winddirection_{hub_h}m"]
        t_ = res[f"temperature_{hub_h}m"]
        p_ = res[f"pressure_{hub_h}m"]

        assert ws.min() >= 0,        f"Negative wind speed: {ws.min():.2f}"
        assert wd.min() >= 0,        f"Wind direction < 0: {wd.min():.2f}"
        assert wd.max() < 360,       f"Wind direction ≥ 360: {wd.max():.2f}"
        assert t_.min() > -80,       f"Temperature too low: {t_.min():.1f} °C"
        assert t_.max() < 80,        f"Temperature too high: {t_.max():.1f} °C"
        assert p_.min() > 40_000,    f"Pressure too low: {p_.min():.0f} Pa"
        assert p_.max() < 120_000,   f"Pressure too high: {p_.max():.0f} Pa"
        print(f"  Physical checks passed ✓")

    print("[validate] All checks passed ✓\n")
    return True


def _is_leap(year: int) -> bool:
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate an existing wind resource HDF5 file."
    )
    parser.add_argument("resource_h5", help="Path to wind resource HDF5 file.")
    args = parser.parse_args()

    validate_resource_file(args.resource_h5)
