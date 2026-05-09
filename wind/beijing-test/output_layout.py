"""Output layout helpers for beijing-test project.

Canonical layout under an output root (e.g. output_era5):
- data/
- configs/
- images/
- logs/

Helpers in this module create the directory structure and resolve files with
backward compatibility to legacy flat output paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OutputLayout:
    root: Path

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def configs(self) -> Path:
        return self.root / "configs"

    @property
    def images(self) -> Path:
        return self.root / "images"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.data.mkdir(parents=True, exist_ok=True)
        self.configs.mkdir(parents=True, exist_ok=True)
        self.images.mkdir(parents=True, exist_ok=True)
        self.logs.mkdir(parents=True, exist_ok=True)


def make_layout(output_dir: str | Path) -> OutputLayout:
    layout = OutputLayout(Path(output_dir))
    layout.ensure()
    return layout


def resolve_existing(output_dir: str | Path, *candidates: str | Path) -> Path:
    """Resolve the first existing candidate under output_dir.

    Candidate order should be from preferred to legacy fallback.
    Returns a path even if none exists (the first candidate under output_dir).
    """
    root = Path(output_dir)
    for cand in candidates:
        p = root / Path(cand)
        if p.exists():
            return p
    return root / Path(candidates[0])
