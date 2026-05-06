"""
qgis_verify.py
==============
Step 7 – PyQGIS automation script: load the Beijing boundary GeoJSON and
generated grid cells into a QGIS project, validate layer integrity, and
write a plain-text verification log.

Usage (run inside the QGIS Python console OR via qgis --no-splash --code):

    python qgis_verify.py \\
        --boundary  /path/to/beijing/beijing.geojson \\
        --grid      /path/to/output/grid_cells.geojson \\
        --output    /path/to/output/qgis_verify_log.txt

The script does NOT render or export any map images.  Its sole purpose is to
confirm that both layers load successfully and report basic statistics that
match what grid_generation.py printed.

Environment requirement
-----------------------
Run inside a QGIS-aware Python interpreter.  Typical invocations:

    # Option 1 – QGIS Python console (interactive):
    exec(open('/path/to/qgis_verify.py').read())

    # Option 2 – standalone via QGIS bundled Python:
    /Applications/QGIS.app/Contents/MacOS/bin/python3 qgis_verify.py ...
    # (requires QgsApplication.setPrefixPath + initQgis() below)

    # Option 3 – qgis --code flag:
    qgis --no-splash --code /path/to/qgis_verify.py
"""

from __future__ import annotations

import sys
import argparse
import datetime
from pathlib import Path


# ─── QGIS bootstrap (needed when running as standalone script) ────────────────

def _init_qgis_if_needed() -> "QgsApplication | None":
    """
    Initialise a headless QgsApplication when not already running inside QGIS.
    Returns the app instance (caller must keep a reference), or None if QGIS
    is already initialised.
    """
    try:
        from qgis.core import QgsApplication
        if QgsApplication.instance() is None:
            app = QgsApplication([], False)
            # Adjust prefix path to your QGIS installation if needed.
            possible_prefixes = [
                "/Applications/QGIS.app/Contents/MacOS",
                "/usr",
                "/usr/local",
            ]
            for prefix in possible_prefixes:
                if Path(prefix).exists():
                    QgsApplication.setPrefixPath(prefix, True)
                    break
            app.initQgis()
            return app
        return None
    except ImportError:
        return None


# ─── Layer loading helpers ────────────────────────────────────────────────────

def load_geojson_layer(path: str | Path, layer_name: str) -> "QgsVectorLayer":
    """Load a GeoJSON file as a QGIS vector layer; raise on failure."""
    from qgis.core import QgsVectorLayer

    layer = QgsVectorLayer(str(path), layer_name, "ogr")
    if not layer.isValid():
        raise RuntimeError(
            f"Failed to load layer '{layer_name}' from {path}"
        )
    return layer


def layer_summary(layer: "QgsVectorLayer") -> dict:
    """Return basic statistics about a vector layer."""
    extent = layer.extent()
    return {
        "name":        layer.name(),
        "feature_count": layer.featureCount(),
        "crs":         layer.crs().authid(),
        "bbox_xmin":   round(extent.xMinimum(), 6),
        "bbox_ymin":   round(extent.yMinimum(), 6),
        "bbox_xmax":   round(extent.xMaximum(), 6),
        "bbox_ymax":   round(extent.yMaximum(), 6),
        "fields":      [f.name() for f in layer.fields()],
    }


# ─── Validation checks ────────────────────────────────────────────────────────

def validate_grid_layer(grid_layer: "QgsVectorLayer") -> list[str]:
    """
    Run basic consistency checks on the grid layer.

    Returns a list of warning strings (empty = all OK).
    """
    warnings = []

    # Check required fields
    field_names = {f.name() for f in grid_layer.fields()}
    for required in ("gid", "latitude", "longitude"):
        if required not in field_names:
            warnings.append(f"Grid layer missing field: '{required}'")

    # Check for duplicate gids
    if "gid" in field_names:
        gids = [f["gid"] for f in grid_layer.getFeatures()]
        if len(gids) != len(set(gids)):
            n_dup = len(gids) - len(set(gids))
            warnings.append(f"Grid layer has {n_dup} duplicate gid values.")

    # Check geometry validity (sample first 100 features)
    invalid = 0
    for i, feat in enumerate(grid_layer.getFeatures()):
        if i >= 100:
            break
        if not feat.geometry().isGeosValid():
            invalid += 1
    if invalid:
        warnings.append(f"Grid layer: {invalid} / 100 sampled features have invalid geometry.")

    return warnings


def validate_boundary_layer(boundary_layer: "QgsVectorLayer") -> list[str]:
    """Basic checks on the boundary layer."""
    warnings = []
    if boundary_layer.featureCount() == 0:
        warnings.append("Boundary layer has no features.")
    for feat in boundary_layer.getFeatures():
        if not feat.geometry().isGeosValid():
            warnings.append("Boundary layer has at least one invalid geometry.")
        break
    return warnings


# ─── Log writer ───────────────────────────────────────────────────────────────

def write_log(
    log_path: str | Path,
    boundary_summary: dict,
    grid_summary: dict,
    boundary_warnings: list[str],
    grid_warnings: list[str],
) -> Path:
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "=" * 60,
        "QGIS Layer Verification Log",
        f"Generated: {datetime.datetime.now().isoformat(timespec='seconds')}",
        "=" * 60,
        "",
        "── Boundary Layer ──────────────────────────────────────",
    ]
    for k, v in boundary_summary.items():
        lines.append(f"  {k:<20}: {v}")
    if boundary_warnings:
        lines.append("  WARNINGS:")
        for w in boundary_warnings:
            lines.append(f"    ⚠  {w}")
    else:
        lines.append("  Status: OK ✓")

    lines += [
        "",
        "── Grid Layer ──────────────────────────────────────────",
    ]
    for k, v in grid_summary.items():
        lines.append(f"  {k:<20}: {v}")
    if grid_warnings:
        lines.append("  WARNINGS:")
        for w in grid_warnings:
            lines.append(f"    ⚠  {w}")
    else:
        lines.append("  Status: OK ✓")

    lines += ["", "=" * 60]

    text = "\n".join(lines) + "\n"
    log_path.write_text(text, encoding="utf-8")
    print(text)
    return log_path


# ─── Main verification pipeline ──────────────────────────────────────────────

def verify_layers(
    boundary_geojson: str | Path,
    grid_geojson: str | Path,
    log_output: str | Path,
) -> bool:
    """
    Load both layers, validate, and write a log file.

    Returns True if no warnings were raised, False otherwise.
    """
    app = _init_qgis_if_needed()  # noqa: F841 – keep reference alive

    try:
        boundary_layer = load_geojson_layer(boundary_geojson, "beijing_boundary")
        grid_layer     = load_geojson_layer(grid_geojson,     "beijing_grid_4km2")
    except RuntimeError as e:
        print(f"[qgis_verify] ERROR: {e}", file=sys.stderr)
        return False

    boundary_summary  = layer_summary(boundary_layer)
    grid_summary      = layer_summary(grid_layer)
    boundary_warnings = validate_boundary_layer(boundary_layer)
    grid_warnings     = validate_grid_layer(grid_layer)

    write_log(log_output, boundary_summary, grid_summary,
              boundary_warnings, grid_warnings)

    all_ok = not boundary_warnings and not grid_warnings
    status = "PASSED" if all_ok else "WARNINGS FOUND"
    print(f"\n[qgis_verify] Verification {status}")
    return all_ok


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Verify Beijing boundary + grid GeoJSON layers via PyQGIS."
    )
    parser.add_argument(
        "--boundary", required=True,
        help="Path to beijing.geojson boundary file."
    )
    parser.add_argument(
        "--grid", required=True,
        help="Path to grid_cells.geojson generated by grid_generation.py."
    )
    parser.add_argument(
        "--output", default="./output/qgis_verify_log.txt",
        help="Path for the output log file."
    )
    args = parser.parse_args()

    ok = verify_layers(args.boundary, args.grid, args.output)
    sys.exit(0 if ok else 1)
