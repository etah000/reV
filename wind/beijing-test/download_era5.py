#!/usr/bin/env python
"""
download_era5.py
================
Helper script to download ERA5 hourly reanalysis data for a given year and
bounding box using the Copernicus Climate Data Store (CDS) API.

Prerequisites
-------------
1. Register at https://cds.climate.copernicus.eu/ and obtain API credentials.
2. Create ``~/.cdsapirc``::

    url: https://cds.climate.copernicus.eu/api/v2
    key: <UID>:<API-KEY>

3. Install the CDS client::

    pip install cdsapi

Variables downloaded (ERA5 single-levels, hourly)
--------------------------------------------------
  u100  – 100 m U-wind component (m/s)
  v100  – 100 m V-wind component (m/s)
  t2m   – 2 m temperature (K)
  sp    – Surface pressure (Pa)

Usage
-----
    python download_era5.py \\
        --year 2012 \\
        --bbox 39.0/115.0/42.0/118.0 \\   # south/west/north/east (degrees)
        --output ./era5_data \\
        [--monthly]    # download month by month (smaller individual files)

Output
------
    era5_data/beijing_era5_2012.nc          (all months in one file, default)
    era5_data/beijing_era5_2012_01.nc       (per-month, if --monthly)
    ...

After downloading, pass the file path to the build pipeline::

    python build_beijing_dataset.py \\
        --geojson /path/to/beijing.geojson \\
        --output ./output_era5 \\
        --era5 ./era5_data/beijing_era5_2012.nc
"""

from __future__ import annotations

import argparse
from pathlib import Path


# ERA5 CDS variable names for the 4 required fields
ERA5_VARIABLES = [
    "100m_u_component_of_wind",
    "100m_v_component_of_wind",
    "2m_temperature",
    "surface_pressure",
]


def _parse_bbox(bbox_str: str) -> dict:
    """Parse 'south/west/north/east' string into CDS area dict."""
    parts = [float(x) for x in bbox_str.split("/")]
    if len(parts) != 4:
        raise ValueError(
            "bbox must be 'south/west/north/east', e.g. '39.0/115.0/42.0/118.0'"
        )
    south, west, north, east = parts
    return [north, west, south, east]   # CDS API order: N/W/S/E


def download_era5_year(
    year: int,
    bbox: str,
    output_dir: str | Path,
    monthly: bool = False,
) -> list[Path]:
    """
    Download ERA5 hourly single-level data for the given year.

    Parameters
    ----------
    year : int
    bbox : str  – 'south/west/north/east' in degrees
    output_dir : path-like
    monthly : bool – if True, one file per month (reduces peak memory)

    Returns
    -------
    list of downloaded file paths
    """
    import cdsapi

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    area = _parse_bbox(bbox)
    client = cdsapi.Client()

    months = [f"{m:02d}" for m in range(1, 13)]
    days   = [f"{d:02d}" for d in range(1, 32)]
    hours  = [f"{h:02d}:00" for h in range(24)]

    downloaded = []

    if monthly:
        for month in months:
            output_path = output_dir / f"beijing_era5_{year}_{month}.nc"
            if output_path.exists():
                print(f"[download_era5] Already exists: {output_path}")
                downloaded.append(output_path)
                continue

            print(f"[download_era5] Downloading {year}-{month} …")
            client.retrieve(
                "reanalysis-era5-single-levels",
                {
                    "product_type": "reanalysis",
                    "variable": ERA5_VARIABLES,
                    "year":  str(year),
                    "month": month,
                    "day":   days,
                    "time":  hours,
                    "area":  area,
                    "format": "netcdf",
                },
                str(output_path),
            )
            downloaded.append(output_path)
    else:
        output_path = output_dir / f"beijing_era5_{year}.nc"
        if output_path.exists():
            print(f"[download_era5] Already exists: {output_path}")
            return [output_path]

        print(f"[download_era5] Downloading full year {year} …")
        client.retrieve(
            "reanalysis-era5-single-levels",
            {
                "product_type": "reanalysis",
                "variable": ERA5_VARIABLES,
                "year":  str(year),
                "month": months,
                "day":   days,
                "time":  hours,
                "area":  area,
                "format": "netcdf",
            },
            str(output_path),
        )
        downloaded.append(output_path)

    print(f"[download_era5] Done. Files: {[str(p) for p in downloaded]}")
    return downloaded


def main():
    parser = argparse.ArgumentParser(
        description="Download ERA5 hourly data for Beijing wind resource pipeline."
    )
    parser.add_argument("--year",    type=int, default=2012,
                        help="Year to download (default: 2012).")
    parser.add_argument(
        "--bbox",
        default="38.5/114.5/42.5/118.5",
        help="Bounding box as 'south/west/north/east' (default: Beijing region).",
    )
    parser.add_argument("--output",  default="./era5_data",
                        help="Output directory for downloaded files.")
    parser.add_argument("--monthly", action="store_true",
                        help="Download one file per month instead of full year.")
    args = parser.parse_args()

    downloaded = download_era5_year(args.year, args.bbox, args.output, args.monthly)

    print("\nNext step:")
    paths = " ".join(f'"{p}"' for p in downloaded)
    print(f"  python build_beijing_dataset.py \\")
    print(f"    --geojson /path/to/beijing.geojson \\")
    print(f"    --output ./output_era5 \\")
    print(f"    --era5 {paths}")


if __name__ == "__main__":
    main()
