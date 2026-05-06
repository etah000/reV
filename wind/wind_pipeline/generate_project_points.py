#!/usr/bin/env python

import argparse
from pathlib import Path

import pandas as pd
from rex import Resource


DEFAULT_RESOURCE = Path("../../tests/data/wtk/ri_100_wtk_2012.h5")
DEFAULT_OUTPUT = Path("project_points.csv")


def build_project_points(resource_path, output_path, count):
    with Resource(resource_path) as resource:
        gids = resource.meta.index.to_list()[:count]

    project_points = pd.DataFrame({"gid": gids, "config": "default"})
    project_points.to_csv(output_path, index=False)


def main():
    parser = argparse.ArgumentParser(
        description="Generate a local project_points CSV from a resource file."
    )
    parser.add_argument(
        "--resource",
        default=str(DEFAULT_RESOURCE),
        help="Resource H5 file used to source gids.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output CSV path.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=100,
        help="Number of gids to include from the resource meta table.",
    )
    args = parser.parse_args()

    build_project_points(args.resource, args.output, args.count)


if __name__ == "__main__":
    main()