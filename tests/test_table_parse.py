"""Parse load / combination dataframes → DesignInputs fields and Combination lists."""

from __future__ import annotations

import pandas as pd
import pytest

from app.components.load_tables import (
    default_combo_dataframe,
    default_load_dataframe,
    parse_combo_table,
    parse_load_table,
)
from composite_beam.combinations.asce7 import ASCEEdition, Combination
from composite_beam.design_engine import DesignEngine, DesignInputs
from composite_beam.loads.load_cases import PointLoadSpec
from composite_beam.materials.concrete import ConcreteMaterial
from composite_beam.materials.steel import SteelMaterial
from composite_beam.composite.effective_width import BeamLocation
from composite_beam.composite.slab import DeckOrientation, SlabConfig
from composite_beam.units import in_to_mm, ksi_to_mpa


def _set(df: pd.DataFrame, case: str, **kwargs) -> pd.DataFrame:
    out = df.copy()
    mask = out["Case"] == case
    assert mask.any(), case
    for k, v in kwargs.items():
        out.loc[mask, k] = v
    return out


def test_default_load_table_maps_sdl_ll_c_and_auto_sw():
    df = default_load_dataframe()
    parsed = parse_load_table(df, L_mm=9000.0)
    assert parsed.w_SDL_kNpm == 2
    assert parsed.w_LL_kNpm == 7
    assert parsed.w_construction_kNpm == 1
    assert parsed.include_beam_self_weight is True
    assert parsed.include_slab_self_weight is True
    assert parsed.points_LL == []
    assert parsed.points_DL == []
    assert parsed.Pu_kN == 0
    kw = parsed.as_design_kwargs()
    assert kw["w_SDL_kNpm"] == 2
    assert "points_C" in kw


def test_misc_dead_and_live_fold_into_totals():
    df = default_load_dataframe()
    df = _set(df, "Misc D1", Include=True, w_kNpm=3)
    df = _set(df, "Additional SW", Include=True, w_kNpm=1)
    df = _set(df, "Live (non-red.)", Include=True, w_kNpm=2)
    df = _set(df, "Misc L1", Include=True, w_kNpm=1)
    parsed = parse_load_table(df)
    assert parsed.w_SDL_kNpm == 2 + 3 + 1
    assert parsed.w_LL_kNpm == 7 + 2 + 1


def test_self_weight_include_false():
    df = _set(default_load_dataframe(), "Self-weight", Include=False)
    parsed = parse_load_table(df)
    assert parsed.include_beam_self_weight is False
    assert parsed.include_slab_self_weight is False


def test_point_rows_split_dead_and_live():
    df = default_load_dataframe()
    df = _set(df, "SDL", Type="Point", P_kN=20, LocationMode="Ratio", Location=0.25, w_kNpm=0)
    df = _set(
        df,
        "Live (reducible)",
        Type="Point",
        P_kN=45,
        LocationMode="Absolute_mm",
        Location=4500,
        w_kNpm=0,
    )
    parsed = parse_load_table(df, L_mm=9000.0)
    assert parsed.w_SDL_kNpm == 0
    assert parsed.w_LL_kNpm == 0
    assert len(parsed.points_DL) == 1
    assert parsed.points_DL[0].P_kN == 20
    assert parsed.points_DL[0].spec == PointLoadSpec.RATIO
    assert parsed.points_DL[0].location == pytest.approx(0.25)
    assert len(parsed.points_LL) == 1
    assert parsed.points_LL[0].P_kN == 45
    assert parsed.points_LL[0].spec == PointLoadSpec.ABSOLUTE
    assert parsed.points_LL[0].location == pytest.approx(4500)


def test_extra_points_table_and_axial_sum():
    df = _set(default_load_dataframe(), "Axial (dedicated)", Include=True, Axial_kN=80)
    df = _set(df, "SDL", Axial_kN=20)  # SDL already included
    extra = pd.DataFrame(
        [
            {
                "Include": True,
                "Role": "LL",
                "P_kN": 10,
                "LocationMode": "Ratio",
                "Location": 0.4,
                "Axial_kN": 5,
                "Notes": "extra live",
            }
        ]
    )
    parsed = parse_load_table(df, L_mm=8000.0, extra_points=extra)
    # dedicated 80 + SDL 20 + extra 5
    assert parsed.Pu_kN == 105
    assert len(parsed.points_LL) == 1
    assert parsed.points_LL[0].P_kN == 10


def test_ew_udl_and_thermal_note():
    df = default_load_dataframe()
    df = _set(df, "Wind W1", Include=True, w_kNpm=4)
    df = _set(df, "Seismic E2", Include=True, Type="Point", P_kN=30, Location=0.5)
    df = _set(df, "Thermal T", Include=True, w_kNpm=1)
    parsed = parse_load_table(df, L_mm=9000.0)
    assert parsed.w_W_kNpm == 4
    assert len(parsed.points_E) == 1
    assert parsed.points_E[0].P_kN == 30
    assert any("Thermal" in n for n in parsed.notes)


def test_combo_table_builtin_and_include_flags():
    df = default_combo_dataframe(ASCEEdition.ASCE7_22, "LRFD")
    assert "1.2D+1.6L" in set(df["Name"])
    assert "1.2Dwet+1.6C" in set(df["Name"])
    parsed = parse_combo_table(df, method="LRFD", edition=ASCEEdition.ASCE7_22)
    names = {c.name for c in parsed.occupancy}
    assert "1.2D+1.6L" in names
    assert "1.4D" in names
    assert any(c.factor("C") == 1.6 for c in parsed.construction)
    # Uncheck occupancy 1.4D
    df.loc[df["Name"] == "1.4D", "Include"] = False
    parsed2 = parse_combo_table(df, method="LRFD", edition="ASCE7-22")
    assert "1.4D" not in {c.name for c in parsed2.occupancy}


def test_combo_custom_blank_name_and_cap():
    df = default_combo_dataframe(ASCEEdition.ASCE7_16, "ASD")
    extras = []
    for i in range(6):
        extras.append(
            {
                "Name": "" if i < 2 else f"EXTRA{i}",
                "Method": "ASD",
                "D": 1.0,
                "L": 0.5,
                "Lr": 0.0,
                "S": 0.0,
                "R": 0.0,
                "W": 0.0,
                "E": 0.0,
                "C": 0.0,
                "Include": True,
            }
        )
    df = pd.concat([df, pd.DataFrame(extras)], ignore_index=True)
    parsed = parse_combo_table(df, method="ASD", edition=ASCEEdition.ASCE7_16, max_custom=5)
    custom_names = [c.name for c in parsed.occupancy if c.name.startswith("CUSTOM") or c.name.startswith("EXTRA")]
    assert "CUSTOM1" in custom_names
    assert "CUSTOM2" in custom_names
    assert parsed.custom_count == 6  # 6 attempted; 6th skipped
    assert len(custom_names) == 5
    assert parsed.construction_or_none()  # wet+C still included by default


def test_parsed_loads_drive_designinputs(wdb):
    """End-to-end: dataframe → DesignInputs → engine (no search)."""
    df = default_load_dataframe()
    parsed = parse_load_table(df, L_mm=in_to_mm(30 * 12))
    combos = parse_combo_table(
        default_combo_dataframe(ASCEEdition.ASCE7_22, "LRFD"),
        method="LRFD",
        edition=ASCEEdition.ASCE7_22,
    )
    shape = wdb.get("W18X35")
    steel = SteelMaterial.from_grade("A992", tf_mm=shape.tf_mm)
    slab = SlabConfig(
        t_solid_mm=in_to_mm(4.0),
        hr_mm=0.0,
        orientation=DeckOrientation.NONE,
        fc_MPa=ksi_to_mpa(4.0),
    )
    inp = DesignInputs(
        L_mm=in_to_mm(30 * 12),
        shape=shape,
        steel=steel,
        concrete=ConcreteMaterial(fc_MPa=slab.fc_MPa),
        slab=slab,
        location=BeamLocation.INTERIOR,
        spacing_left_mm=in_to_mm(10 * 12),
        spacing_right_mm=in_to_mm(10 * 12),
        target_composite_ratio=1.0,
        **parsed.as_design_kwargs(),
        occupancy_combinations=combos.occupancy_or_none(),
        construction_combinations_override=combos.construction_or_none(),
        deck_braces_construction=True,
    )
    res = DesignEngine(wdb).design(inp, search_passing=False)
    assert res.positive_moment.phiMn_kNm > 0
    assert res.DCR_flexure > 0
    from composite_beam.reporting.html_report import result_to_html

    html = result_to_html(res, project_label="Unit test beam", include_charts=False)
    assert "Unit test beam" in html
    assert "PASS" in html or "FAIL" in html
    assert "Capacity vs demand" in html
