"""Shared fixtures for composite beam tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from composite_beam.sections.w_shapes import WShapeDatabase


@pytest.fixture(scope="session")
def wdb() -> WShapeDatabase:
    return WShapeDatabase()
