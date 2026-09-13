"""Excel-like load and combination tables (pure parsers + Streamlit editors).

Parsers take pandas DataFrames and return structures that map onto
``DesignInputs`` / ``Combination`` lists. Streamlit is imported only in
the render helpers so unit tests can exercise the parsers without a
browser session.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from composite_beam.combinations.asce7 import (
    ASCEEdition,
    Combination,
    builtin_combinations_for_table,
)
from composite_beam.loads.load_cases import PointLoad, PointLoadSpec

# ---------------------------------------------------------------------------
# Load-table schema
# ---------------------------------------------------------------------------

LOAD_COLUMNS = [
    "Case",
    "Include",
    "Type",
    "w_kNpm",
    "P_kN",
    "LocationMode",
    "Location",
    "Axial_kN",
    "Notes",
]

# Case name → (role, default_include, default_w, default_notes)
# role: SW | D | L | C | E | W | T | P
_LOAD_SPECS: list[tuple[str, str, bool, int, str]] = [
    (
        "Self-weight",
        "SW",
        True,
        0,
        "Auto — engine computes beam + slab SW; Include toggles both. w/P ignored.",
    ),
    ("Additional SW", "D", False, 0, "Added into w_SDL (dead super)."),
    ("SDL", "D", True, 2, "Superimposed dead → w_SDL_kNpm."),
    ("Misc D1", "D", False, 0, "Added into w_SDL."),
    ("Misc D2", "D", False, 0, "Added into w_SDL."),
    ("Misc D3", "D", False, 0, "Added into w_SDL."),
    ("Live (reducible)", "L", True, 7, "Primary live → w_LL_kNpm."),
    ("Live (non-red.)", "L", False, 0, "Added into w_LL."),
    ("Misc L1", "L", False, 0, "Added into w_LL."),
    ("Misc L2", "L", False, 0, "Added into w_LL."),
    ("Misc L3", "L", False, 0, "Added into w_LL."),
    ("Construction", "C", True, 1, "Construction live → w_construction_kNpm."),
    ("Seismic E1", "E", False, 0, "Applied when a combo has an E factor."),
    ("Seismic E2", "E", False, 0, "Applied when a combo has an E factor."),
    ("Seismic E3", "E", False, 0, "Applied when a combo has an E factor."),
    ("Seismic E4", "E", False, 0, "Applied when a combo has an E factor."),
    ("Wind W1", "W", False, 0, "Applied when a combo has a W factor."),
    ("Wind W2", "W", False, 0, "Applied when a combo has a W factor."),
    ("Wind W3", "W", False, 0, "Applied when a combo has a W factor."),
    ("Wind W4", "W", False, 0, "Applied when a combo has a W factor."),
    ("Thermal T", "T", False, 0, "Stored only — not enveloped (no T combo role)."),
    (
        "Axial (dedicated)",
        "P",
        False,
        0,
        "Convenience row. Pu = sum of Axial_kN on all included rows.",
    ),
]

_CASE_ROLE = {name: role for name, role, *_ in _LOAD_SPECS}

STANDARD_CASE_NAMES = [name for name, *_ in _LOAD_SPECS]

EXTRA_POINT_COLUMNS = [
    "Include",
    "Role",
    "P_kN",
    "LocationMode",
    "Location",
    "Axial_kN",
    "Notes",
]

COMBO_FACTOR_COLS = ["D", "L", "Lr", "S", "R", "W", "E", "C"]
COMBO_COLUMNS = ["Name", "Method", *COMBO_FACTOR_COLS, "Include"]

WIRING_CAPTION = (
    "**Wiring:** Included SDL + Additional SW + misc D UDLs → `w_SDL_kNpm`. "
    "Live (reducible / non-red. / misc L) UDLs → `w_LL_kNpm`. "
    "Construction UDL → `w_construction_kNpm`. "
    "Included **Point** rows → `points_DL` (dead) or `points_LL` (live); "
    "C / W / E points go to `points_C` / `points_W` / `points_E`. "
    "**Pu_kN = sum of Axial_kN on every included row** "
    "(use the dedicated Axial row for a single Pr). "
    "Self-weight Include toggles engine auto SW (beam + slab). "
    "E/W UDLs and points are applied only when a combination has E/W factors. "
    "Thermal is stored in the table only (not enveloped). "
    "Lr / S / R have no matching load-case rows — those combo legs stay 0 "
    "unless you put magnitude on L or a custom mapping."
)


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------

def _as_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    if isinstance(v, float) and math.isnan(v):
        return default
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return default
        try:
            return float(s)
        except ValueError:
            return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _as_int(v: Any, default: int = 0) -> int:
    return int(round(_as_float(v, float(default))))


def _as_bool(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, float) and math.isnan(v):
        return default
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "y", "t", "on"}
    return bool(v)


def _as_str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    if isinstance(v, float) and math.isnan(v):
        return default
    return str(v).strip()


def _is_point(type_val: Any) -> bool:
    return _as_str(type_val, "UDL").lower().startswith("point")


def _point_from_row(row: Any, L_mm: float) -> PointLoad:
    mode = _as_str(row.get("LocationMode", "Ratio"), "Ratio")
    loc = _as_float(row.get("Location"), 0.5)
    if mode.lower().startswith("abs"):
        spec = PointLoadSpec.ABSOLUTE
        location = max(0.0, loc)
        if L_mm > 0:
            location = min(location, L_mm)
    else:
        spec = PointLoadSpec.RATIO
        location = min(max(loc, 0.0), 1.0)
    return PointLoad(
        P_kN=float(_as_int(row.get("P_kN"), 0)),
        location=location,
        spec=spec,
        axial_kN=float(_as_int(row.get("Axial_kN"), 0)),
        label=_as_str(row.get("Case") or row.get("Notes"), ""),
    )


# ---------------------------------------------------------------------------
# Default dataframes
# ---------------------------------------------------------------------------

def default_load_dataframe() -> pd.DataFrame:
    """Pre-populated brief load-case set (whole-number SI cells)."""
    rows = []
    for name, _role, inc, w, notes in _LOAD_SPECS:
        rows.append(
            {
                "Case": name,
                "Include": bool(inc),
                "Type": "UDL",
                "w_kNpm": int(w),
                "P_kN": 0,
                "LocationMode": "Ratio",
                "Location": 0.5,
                "Axial_kN": 0,
                "Notes": notes,
            }
        )
    return pd.DataFrame(rows, columns=LOAD_COLUMNS)


def default_extra_points_dataframe() -> pd.DataFrame:
    """Empty compact point-load table (dynamic rows)."""
    return pd.DataFrame(
        {
            "Include": pd.Series(dtype=bool),
            "Role": pd.Series(dtype=str),
            "P_kN": pd.Series(dtype="Int64"),
            "LocationMode": pd.Series(dtype=str),
            "Location": pd.Series(dtype=float),
            "Axial_kN": pd.Series(dtype="Int64"),
            "Notes": pd.Series(dtype=str),
        }
    )


def default_combo_dataframe(
    edition: ASCEEdition | str = ASCEEdition.ASCE7_22,
    method: str = "LRFD",
) -> pd.DataFrame:
    """Built-in ASCE 7 LRFD or ASD combinations for the editor."""
    if isinstance(edition, str):
        edition = ASCEEdition.ASCE7_22 if edition.endswith("22") else ASCEEdition.ASCE7_16
    combos = builtin_combinations_for_table(edition, method)
    rows = []
    for c in combos:
        row = {
            "Name": c.name,
            "Method": c.method,
            "Include": True,
        }
        for k in COMBO_FACTOR_COLS:
            row[k] = float(c.factor(k))
        rows.append(row)
    return pd.DataFrame(rows, columns=COMBO_COLUMNS)


# ---------------------------------------------------------------------------
# Parse results
# ---------------------------------------------------------------------------

@dataclass
class ParsedLoads:
    """Mapped load-table result ready for ``DesignInputs``."""

    w_SDL_kNpm: float = 0.0
    w_LL_kNpm: float = 0.0
    w_construction_kNpm: float = 0.0
    w_W_kNpm: float = 0.0
    w_E_kNpm: float = 0.0
    points_LL: list[PointLoad] = field(default_factory=list)
    points_DL: list[PointLoad] = field(default_factory=list)
    points_C: list[PointLoad] = field(default_factory=list)
    points_W: list[PointLoad] = field(default_factory=list)
    points_E: list[PointLoad] = field(default_factory=list)
    Pu_kN: float = 0.0
    include_beam_self_weight: bool = True
    include_slab_self_weight: bool = True
    notes: list[str] = field(default_factory=list)

    def as_design_kwargs(self) -> dict[str, Any]:
        return {
            "w_SDL_kNpm": self.w_SDL_kNpm,
            "w_LL_kNpm": self.w_LL_kNpm,
            "w_construction_kNpm": self.w_construction_kNpm,
            "w_W_kNpm": self.w_W_kNpm,
            "w_E_kNpm": self.w_E_kNpm,
            "points_LL": list(self.points_LL),
            "points_DL": list(self.points_DL),
            "points_C": list(self.points_C),
            "points_W": list(self.points_W),
            "points_E": list(self.points_E),
            "Pu_kN": self.Pu_kN,
            "include_beam_self_weight": self.include_beam_self_weight,
            "include_slab_self_weight": self.include_slab_self_weight,
        }


@dataclass
class ParsedCombos:
    occupancy: list[Combination] = field(default_factory=list)
    construction: list[Combination] = field(default_factory=list)
    custom_count: int = 0
    notes: list[str] = field(default_factory=list)

    def occupancy_or_none(self) -> Optional[list[Combination]]:
        return list(self.occupancy)

    def construction_or_none(self) -> Optional[list[Combination]]:
        """Empty list → None so the engine falls back to built-in wet+C."""
        return list(self.construction) if self.construction else None


def parse_load_table(
    df: pd.DataFrame,
    L_mm: float = 0.0,
    extra_points: Optional[pd.DataFrame] = None,
) -> ParsedLoads:
    """Map an edited load dataframe (+ optional extra points) to engine inputs.

    ``Pu_kN`` is the sum of ``Axial_kN`` on every included row (dedicated
    Axial row plus any per-case axial). Self-weight Include maps to both
    beam and slab auto-SW flags.
    """
    out = ParsedLoads()
    if df is None or df.empty:
        out.include_beam_self_weight = True
        out.include_slab_self_weight = True
        out.notes.append("Empty load table — defaults to auto self-weight only.")
        return out

    work = df.copy()
    for col in LOAD_COLUMNS:
        if col not in work.columns:
            if col == "Include":
                work[col] = True
            elif col == "Type":
                work[col] = "UDL"
            elif col == "LocationMode":
                work[col] = "Ratio"
            elif col == "Location":
                work[col] = 0.5
            elif col in {"w_kNpm", "P_kN", "Axial_kN"}:
                work[col] = 0
            else:
                work[col] = ""

    sw_seen = False
    for _, row in work.iterrows():
        name = _as_str(row.get("Case"), "")
        if not name:
            continue
        included = _as_bool(row.get("Include"), False)
        role = _CASE_ROLE.get(name)
        if role is None:
            # Extra named row: treat as live UDL/point if included
            role = "L"
        if name == "Self-weight" or role == "SW":
            sw_seen = True
            out.include_beam_self_weight = included
            out.include_slab_self_weight = included
            if included:
                out.Pu_kN += float(_as_int(row.get("Axial_kN"), 0))
            continue
        if not included:
            continue

        out.Pu_kN += float(_as_int(row.get("Axial_kN"), 0))
        is_pt = _is_point(row.get("Type"))
        w = float(_as_int(row.get("w_kNpm"), 0))

        if role == "P":
            # Dedicated axial — magnitude already in Pu sum; ignore w/P.
            continue
        if role == "T":
            out.notes.append(
                f"Thermal '{name}' included but not enveloped (no T combination role)."
            )
            continue

        if is_pt:
            pt = _point_from_row(row, L_mm)
            if role == "D":
                out.points_DL.append(pt)
            elif role == "L":
                out.points_LL.append(pt)
            elif role == "C":
                out.points_C.append(pt)
            elif role == "W":
                out.points_W.append(pt)
            elif role == "E":
                out.points_E.append(pt)
        else:
            if role == "D":
                out.w_SDL_kNpm += w
            elif role == "L":
                out.w_LL_kNpm += w
            elif role == "C":
                out.w_construction_kNpm += w
            elif role == "W":
                out.w_W_kNpm += w
            elif role == "E":
                out.w_E_kNpm += w

    if not sw_seen:
        out.include_beam_self_weight = True
        out.include_slab_self_weight = True

    if extra_points is not None and not extra_points.empty:
        _absorb_extra_points(out, extra_points, L_mm)

    out.notes.append(
        "Pu_kN = sum of Axial_kN on included rows "
        f"({out.Pu_kN:.0f} kN). Misc D/L UDLs are folded into SDL/LL totals."
    )
    return out


def _absorb_extra_points(out: ParsedLoads, df: pd.DataFrame, L_mm: float) -> None:
    role_map = {
        "DL": "D",
        "D": "D",
        "DEAD": "D",
        "LL": "L",
        "L": "L",
        "LIVE": "L",
        "C": "C",
        "CONSTRUCTION": "C",
        "W": "W",
        "WIND": "W",
        "E": "E",
        "SEISMIC": "E",
    }
    for _, row in df.iterrows():
        if not _as_bool(row.get("Include"), False):
            continue
        role = role_map.get(_as_str(row.get("Role"), "LL").upper(), "L")
        # Extra-points table is always points
        fake = {
            "P_kN": row.get("P_kN"),
            "LocationMode": row.get("LocationMode", "Ratio"),
            "Location": row.get("Location", 0.5),
            "Axial_kN": row.get("Axial_kN"),
            "Case": _as_str(row.get("Notes"), "extra"),
            "Notes": row.get("Notes"),
        }
        pt = _point_from_row(fake, L_mm)
        out.Pu_kN += float(_as_int(row.get("Axial_kN"), 0))
        if role == "D":
            out.points_DL.append(pt)
        elif role == "C":
            out.points_C.append(pt)
        elif role == "W":
            out.points_W.append(pt)
        elif role == "E":
            out.points_E.append(pt)
        else:
            out.points_LL.append(pt)


def parse_combo_table(
    df: pd.DataFrame,
    method: str = "LRFD",
    edition: ASCEEdition | str = ASCEEdition.ASCE7_22,
    max_custom: int = 5,
) -> ParsedCombos:
    """Build occupancy / construction ``Combination`` lists from the editor.

    Blank names become CUSTOM1…CUSTOM5. At most ``max_custom`` extra
    (non-built-in) rows are accepted. Construction = included rows with
    a C factor (or 'wet' in the name).
    """
    if isinstance(edition, str):
        ed_enum = ASCEEdition.ASCE7_22 if edition.endswith("22") else ASCEEdition.ASCE7_16
        ed_str = ed_enum.value
    else:
        ed_enum = edition
        ed_str = edition.value

    builtin_names = {c.name for c in builtin_combinations_for_table(ed_enum, method)}
    # Also recognise gravity-only names as built-in
    from composite_beam.combinations.asce7 import (
        asd_gravity_combinations,
        construction_combinations,
        lrfd_gravity_combinations,
    )

    for src in (
        lrfd_gravity_combinations(ed_enum),
        asd_gravity_combinations(ed_enum),
        construction_combinations(ed_enum),
    ):
        builtin_names.update(c.name for c in src)

    out = ParsedCombos()
    if df is None or df.empty:
        out.notes.append("Empty combo table.")
        return out

    work = df.copy()
    for col in COMBO_COLUMNS:
        if col not in work.columns:
            work[col] = 0.0 if col in COMBO_FACTOR_COLS else (True if col == "Include" else "")

    custom_n = 0
    for _, row in work.iterrows():
        included = _as_bool(row.get("Include"), False)
        name = _as_str(row.get("Name"), "")
        factors = {k: _as_float(row.get(k), 0.0) for k in COMBO_FACTOR_COLS}
        all_zero = all(abs(v) < 1e-15 for v in factors.values())
        if not included:
            continue
        if not name and all_zero:
            continue

        is_builtin = name in builtin_names
        if not is_builtin:
            custom_n += 1
            if custom_n > max_custom:
                out.notes.append(f"Skipped extra custom row beyond {max_custom}: {name!r}")
                continue
            if not name:
                name = f"CUSTOM{custom_n}"

        row_method = _as_str(row.get("Method"), method) or method
        factors_nz = {k: v for k, v in factors.items() if abs(v) > 1e-15}
        combo = Combination(
            name=name,
            factors=factors_nz,
            method=row_method.upper(),
            edition=ed_str,
        )
        is_construction = combo.factor("C") > 0 or "wet" in name.lower()
        if is_construction and combo.factor("L") == 0:
            out.construction.append(combo)
        elif is_construction:
            out.construction.append(combo)
            out.occupancy.append(combo)
        else:
            out.occupancy.append(combo)

    out.custom_count = custom_n
    out.notes.append(
        f"{len(out.occupancy)} occupancy + {len(out.construction)} construction "
        f"combo(s); {out.custom_count} custom row(s)."
    )
    return out


# ---------------------------------------------------------------------------
# Streamlit editors
# ---------------------------------------------------------------------------

def render_load_tables(L_mm: float) -> ParsedLoads:
    """Draw the load-case + extra-points editors; return parsed engine loads."""
    import streamlit as st
    st.subheader("Loads (service / nominal)")
    st.caption(
        "Excel-like table. Integer cells for kN, kN/m, mm. "
        "Location is a ratio 0–1 when LocationMode=Ratio (decimal exception), "
        "or mm when LocationMode=Absolute_mm. "
        "E/W/T rows may be UDL or Point."
    )

    # Persist DataFrames explicitly: view switchers unmount widgets (unlike st.tabs),
    # and data_editor state is fragile on remount — always seed from saved DF.
    if "load_df_persisted" not in st.session_state:
        st.session_state["load_df_persisted"] = default_load_dataframe()
    if "extra_points_persisted" not in st.session_state:
        st.session_state["extra_points_persisted"] = default_extra_points_dataframe()

    edited = st.data_editor(
        st.session_state["load_df_persisted"],
        key="load_case_editor",
        hide_index=True,
        num_rows="fixed",
        use_container_width=True,
        column_config={
            "Case": st.column_config.TextColumn("Case", disabled=True, width="medium"),
            "Include": st.column_config.CheckboxColumn("Include", default=False),
            "Type": st.column_config.SelectboxColumn("Type", options=["UDL", "Point"]),
            "w_kNpm": st.column_config.NumberColumn(
                "w (kN/m)", min_value=0, max_value=200, step=1, format="%d"
            ),
            "P_kN": st.column_config.NumberColumn(
                "P (kN)", min_value=-2200, max_value=2200, step=1, format="%d"
            ),
            "LocationMode": st.column_config.SelectboxColumn(
                "LocationMode", options=["Ratio", "Absolute_mm"]
            ),
            "Location": st.column_config.NumberColumn(
                "Location",
                min_value=0.0,
                max_value=40000.0,
                step=0.01,
                help="x/L (0–1) or x_mm depending on LocationMode",
            ),
            "Axial_kN": st.column_config.NumberColumn(
                "Axial (kN)", min_value=-9000, max_value=9000, step=1, format="%d"
            ),
            "Notes": st.column_config.TextColumn("Notes", width="large"),
        },
    )
    st.session_state["load_df_persisted"] = edited.copy()

    st.markdown("**Extra point loads** (optional compact table — not a vertical list)")
    extra = st.data_editor(
        st.session_state["extra_points_persisted"],
        key="extra_points_editor",
        hide_index=True,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Include": st.column_config.CheckboxColumn("Include", default=True),
            "Role": st.column_config.SelectboxColumn(
                "Role", options=["LL", "DL", "C", "W", "E"]
            ),
            "P_kN": st.column_config.NumberColumn(
                "P (kN)", min_value=-2200, max_value=2200, step=1, format="%d"
            ),
            "LocationMode": st.column_config.SelectboxColumn(
                "LocationMode", options=["Ratio", "Absolute_mm"]
            ),
            "Location": st.column_config.NumberColumn(
                "Location", min_value=0.0, max_value=40000.0, step=0.01
            ),
            "Axial_kN": st.column_config.NumberColumn(
                "Axial (kN)", min_value=-9000, max_value=9000, step=1, format="%d"
            ),
            "Notes": st.column_config.TextColumn("Notes"),
        },
    )
    st.session_state["extra_points_persisted"] = extra.copy()

    parsed = parse_load_table(edited, L_mm=float(L_mm), extra_points=extra)
    st.caption(WIRING_CAPTION)
    st.caption(
        f"Mapped: SDL={parsed.w_SDL_kNpm:.0f} kN/m · "
        f"L={parsed.w_LL_kNpm:.0f} kN/m · C={parsed.w_construction_kNpm:.0f} kN/m · "
        f"W={parsed.w_W_kNpm:.0f} kN/m · E={parsed.w_E_kNpm:.0f} kN/m · "
        f"Pu={parsed.Pu_kN:.0f} kN · "
        f"pts DL/LL/C/W/E = "
        f"{len(parsed.points_DL)}/{len(parsed.points_LL)}/"
        f"{len(parsed.points_C)}/{len(parsed.points_W)}/{len(parsed.points_E)} · "
        f"auto SW={'on' if parsed.include_beam_self_weight else 'off'}"
    )
    return parsed


def render_combo_table(edition: ASCEEdition | str, method: str) -> ParsedCombos:
    """Draw the ASCE combination editor; return occupancy + construction lists."""
    import streamlit as st

    if isinstance(edition, str):
        edition = ASCEEdition.ASCE7_22 if edition.endswith("22") else ASCEEdition.ASCE7_16

    st.subheader("Design load combinations")
    st.caption(
        f"Built-in **{edition.value}** {method} combinations (ASCE 7 §2.3.1 / §2.4.1) "
        "plus the matching construction combo. Edit factors and Include flags. "
        "Add up to 5 custom rows (blank Name → CUSTOM1…). "
        "Decimal exception: load factors. "
        "If no construction combo is included, the engine falls back to the "
        "built-in wet+C combination."
    )

    sig = f"{edition.value}|{method.upper()}"
    if st.session_state.get("_combo_table_sig") != sig:
        st.session_state["_combo_table_sig"] = sig
        # Drop the editor widget state so factors reload from the new edition/method
        st.session_state.pop("combo_table_editor", None)
        st.session_state["combo_df_persisted"] = default_combo_dataframe(edition, method)
    if "combo_df_persisted" not in st.session_state:
        st.session_state["combo_df_persisted"] = default_combo_dataframe(edition, method)

    factor_cfg = {
        k: st.column_config.NumberColumn(k, min_value=0.0, max_value=2.5, step=0.05, format="%.2f")
        for k in COMBO_FACTOR_COLS
    }
    edited = st.data_editor(
        st.session_state["combo_df_persisted"],
        key="combo_table_editor",
        hide_index=True,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Name": st.column_config.TextColumn("Name", width="medium"),
            "Method": st.column_config.SelectboxColumn("Method", options=["LRFD", "ASD"]),
            "Include": st.column_config.CheckboxColumn("Include", default=True),
            **factor_cfg,
        },
    )
    st.session_state["combo_df_persisted"] = edited.copy()
    parsed = parse_combo_table(edited, method=method, edition=edition)
    for n in parsed.notes:
        st.caption(n)
    return parsed
