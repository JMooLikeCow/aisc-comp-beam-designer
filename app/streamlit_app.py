"""Streamlit UI — Input / Summary / Detailed Calculations views.

SI is the primary input and display system; US customary equivalents update
in real time in brackets next to every dimensional / force / stress / moment quantity.

Whole-number SI inputs (integer widgets) for dimensions, forces, stresses,
moments, and line loads. Decimal exceptions: x/L ratios, K factor, n override,
ASCE load factors.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.components.load_tables import render_combo_table, render_load_tables
from app.components.results_dashboard import render_results_dashboard
from app.components.si_inputs import si_int_input
from composite_beam.analysis.continuous import SupportType
from composite_beam.combinations.asce7 import ASCEEdition
from composite_beam.composite.effective_width import AISCEdition, BeamLocation
from composite_beam.composite.slab import DeckOrientation, SlabConfig, catalog_hr_wr_mm, load_deck_catalog
from composite_beam.composite.stud_layout import StudZone
from composite_beam.composite.studs import StudConfig
from composite_beam.design_engine import DesignEngine, DesignInputs
from composite_beam.materials.concrete import ConcreteMaterial, EcCode
from composite_beam.materials.steel import SteelMaterial, load_steel_grades
from composite_beam.reporting.summary import detailed_lines
from composite_beam.sections.box_sections import box_properties
from composite_beam.sections.w_shapes import WShapeDatabase, custom_w_shape
from composite_beam.serviceability.deflection import DeflectionLimits
from composite_beam.units import (
    dual_length_mm,
    dual_moment_kNm,
    dual_stress_MPa,
)

st.set_page_config(page_title="AISC Comp Beam Designer", layout="wide", page_icon="🏗️")
st.title("AISC Comp Beam Designer")
st.caption(
    "Primary SI (kN, mm, MPa); US customary in brackets. "
    "AISC 360-16/22 · ASCE 7-16/22. Whole-number SI inputs "
    "(decimals kept for x/L, K, n override, load factors). Loads and combinations are Excel-like tables."
)


@st.cache_resource
def get_db() -> WShapeDatabase:
    return WShapeDatabase()


db = get_db()
grades = load_steel_grades()
decks = load_deck_catalog()

_VIEW_LABELS = ("Input", "Summary", "Detailed Calculations")
if "main_view" not in st.session_state:
    st.session_state["main_view"] = "Input"


def _render_main_nav(prefix: str) -> None:
    """Horizontal Input | Summary | Detailed buttons; both ends write main_view."""
    cols = st.columns(len(_VIEW_LABELS))
    for col, label in zip(cols, _VIEW_LABELS):
        with col:
            is_active = st.session_state["main_view"] == label
            if st.button(
                label,
                key=f"nav_{prefix}_{label}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                if st.session_state["main_view"] != label:
                    st.session_state["main_view"] = label
                    st.rerun()


_render_main_nav("top")
st.divider()

run = False
if st.session_state["main_view"] == "Input":
    project_label = st.text_input(
        "Project / beam label",
        value="Composite beam",
        key="project_label",
        help="Printed on the Summary results sheet header.",
    )
    st.subheader("Geometry & codes")
    c1, c2, c3 = st.columns(3)
    with c1:
        L_mm = si_int_input(
            "Span L (mm)", 1500, 36500, 9144, 1, key="L_mm", dual=dual_length_mm
        )
        location = st.selectbox("Beam location", ["interior", "edge"], key="loc")
        aisc_ed = st.selectbox("AISC edition", ["AISC360-22", "AISC360-16"], key="aisc")
        asce_ed = st.selectbox("ASCE 7 edition", ["ASCE7-22", "ASCE7-16"], key="asce")
        method = st.selectbox("Design method", ["LRFD", "ASD"], key="method")
    with c2:
        sL_mm = si_int_input(
            "Spacing / adj. left (mm)",
            300,
            12000,
            3048,
            1,
            key="sL_mm",
            dual=dual_length_mm,
        )
        sR_default = 3048 if location == "interior" else 914
        sR_mm = si_int_input(
            "Spacing right / edge overhang (mm)",
            150,
            12000,
            int(sR_default),
            1,
            key="sR_mm",
            dual=dual_length_mm,
        )
        beff_ov = si_int_input(
            "beff override (mm, 0=auto)",
            0,
            7600,
            0,
            1,
            key="beff_mm",
            dual=dual_length_mm,
        )
        support_label = st.selectbox(
            "Supports (no cantilevers)",
            ["Simply supported", "Fixed-fixed", "Fixed-pinned (left fixed)"],
            key="sup",
        )
        support_map = {
            "Simply supported": SupportType.SIMPLY_SUPPORTED,
            "Fixed-fixed": SupportType.FIXED_FIXED,
            "Fixed-pinned (left fixed)": SupportType.FIXED_PINNED,
        }
        support = support_map[support_label]
    with c3:
        shored = st.checkbox("Shored construction", False, key="shored")
        deck_brace = st.checkbox("Deck braces compression flange (construction sagging)", True, key="deckb")
        camber_mm = si_int_input(
            "Camber (mm)", 0, 150, 0, 1, key="camber_mm", dual=dual_length_mm
        )
        use_fem = st.checkbox("Use elastic FEM end moments", True, key="fem")
        M_left_ov_kNm = si_int_input(
            "M left override (kN·m, hogging −ve; 0=FEM)",
            -30000,
            30000,
            0,
            1,
            key="MLov_kNm",
            dual=dual_moment_kNm,
        )
        M_right_ov_kNm = si_int_input(
            "M right override (kN·m, hogging −ve; 0=FEM)",
            -30000,
            30000,
            0,
            1,
            key="MRov_kNm",
            dual=dual_moment_kNm,
        )

    st.subheader("Steel section")
    sec_mode = st.radio("Section type", ["W-shape catalog", "Custom I-section", "Custom welded box"], horizontal=True)
    shapes_sorted = list(db.lightest_first())
    label_to_us = {s.display_name: s.designation for s in shapes_sorted}
    labels = list(label_to_us.keys())
    default_label = next(
        (s.display_name for s in shapes_sorted if s.designation == "W18X35"),
        labels[0] if labels else "",
    )
    if sec_mode == "W-shape catalog":
        des_label = st.selectbox(
            "W-shape",
            labels,
            index=labels.index(default_label) if default_label in labels else 0,
            key="wdes",
        )
        shape = db.get(label_to_us[des_label])
    elif sec_mode == "Custom I-section":
        cc1, cc2, cc3, cc4 = st.columns(4)
        with cc1:
            d_mm = si_int_input("d (mm)", 100, 1000, 457, 1, key="cd_mm", dual=dual_length_mm)
        with cc2:
            bf_mm = si_int_input("bf (mm)", 100, 600, 152, 1, key="cbf_mm", dual=dual_length_mm)
        with cc3:
            tf_mm = si_int_input("tf (mm)", 5, 75, 11, 1, key="ctf_mm", dual=dual_length_mm)
        with cc4:
            tw_mm = si_int_input("tw (mm)", 4, 50, 8, 1, key="ctw_mm", dual=dual_length_mm)
        shape = custom_w_shape("CUSTOM", float(d_mm), float(bf_mm), float(tf_mm), float(tw_mm))
        st.caption(shape.display_name)
    else:
        bc1, bc2, bc3, bc4 = st.columns(4)
        with bc1:
            H_mm = si_int_input("Box depth H (mm)", 150, 1200, 406, 1, key="bH_mm", dual=dual_length_mm)
        with bc2:
            B_mm = si_int_input("Box width B (mm)", 150, 900, 305, 1, key="bB_mm", dual=dual_length_mm)
        with bc3:
            tfb_mm = si_int_input("Flange tf (mm)", 6, 75, 19, 1, key="btf_mm", dual=dual_length_mm)
        with bc4:
            twb_mm = si_int_input("Web tw (mm, each)", 6, 50, 13, 1, key="btw_mm", dual=dual_length_mm)
        shape = box_properties(float(H_mm), float(B_mm), float(tfb_mm), float(twb_mm), designation="BOX")
        st.caption(shape.display_name)
        st.caption(
            f"A={shape.A_mm2:.0f} mm²; Ix={shape.Ix_mm4:.3e} mm⁴; "
            f"J={shape.J_mm4:.3e} mm⁴ (closed Bredt). Classification uses Table B4.1b cases 12/19."
        )

    gkey = st.selectbox("Steel grade", list(grades.keys()), index=0, key="grade")
    Fy_ov = si_int_input(
        "Fy override (MPa, 0=catalog)",
        0,
        690,
        0,
        1,
        key="Fyov_MPa",
        dual=dual_stress_MPa,
    )
    steel = SteelMaterial.from_grade(
        gkey,
        tf_mm=shape.tf_mm,
        Fy_override_MPa=float(Fy_ov) if Fy_ov > 0 else None,
    )
    st.write(f"Fy = {dual_stress_MPa(steel.Fy_MPa)}")

    st.subheader("Slab / deck / concrete")
    st.caption(
        "Deck catalog: **Tata Steel ComFlor®** composite floor decking "
        "(range overview / technical manual). Selecting a profile auto-fills "
        "rib depth (hr) and average trough width (wr). Use **manual** for custom values."
    )
    deck_keys = list(decks.keys())
    deck_labels = [f"{k} — {decks[k].get('name', k)}" for k in deck_keys]
    d_idx = st.selectbox(
        "Deck catalog",
        range(len(deck_keys)),
        format_func=lambda i: deck_labels[i],
        index=0,
        key="deck_idx",
    )
    dkey = deck_keys[d_idx]
    entry = decks[dkey]
    cat_hr, cat_wr = catalog_hr_wr_mm(entry)

    # Auto-fill hr/wr from catalog whenever selection changes
    if st.session_state.get("_deck_key_prev") != dkey:
        st.session_state["hr_mm"] = int(round(cat_hr))
        st.session_state["wr_mm"] = int(round(cat_wr))
        st.session_state["_deck_key_prev"] = dkey
        # Also sync orientation default when catalog changes
        st.session_state["orient"] = entry.get("orientation", "none")

    t_solid_mm = si_int_input(
        "Solid thickness above deck / total solid (mm)",
        50,
        300,
        100,
        1,
        key="tsol_mm",
        dual=dual_length_mm,
    )
    fc_MPa = si_int_input(
        "f'c (MPa)", 14, 85, 28, 1, key="fc_MPa", dual=dual_stress_MPa
    )
    ec_code = st.selectbox("Ec formula", ["ACI318", "Eurocode2", "NZS3101"], key="ec")
    st.caption("Decimal exception: modular ratio override.")
    n_ov = st.number_input("n = Es/Ec override (0=auto)", 0.0, 20.0, 0.0, 0.1, key="nov")

    orient_opts = ["none", "perpendicular", "parallel"]
    default_orient = entry.get("orientation", "none")
    if "orient" not in st.session_state:
        st.session_state["orient"] = default_orient
    orient = st.selectbox(
        "Deck orientation",
        orient_opts,
        key="orient",
        help="ComFlor® 51+ is re-entrant — perpendicular is typical over beams; parallel also allowed.",
    )
    if entry.get("profile_type") == "re-entrant":
        st.caption("ComFlor® 51+ is a **re-entrant** profile — confirm orientation for Rg/Rp.")

    hr_mm = si_int_input(
        "Rib / deck depth hr (mm)",
        0,
        300,
        int(round(cat_hr)),
        1,
        key="hr_mm",
        dual=dual_length_mm,
        help="Auto-filled from ComFlor® catalog; edit for manual override.",
    )
    wr_mm = si_int_input(
        "Avg rib/trough width wr (mm)",
        0,
        600,
        int(round(cat_wr)),
        1,
        key="wr_mm",
        dual=dual_length_mm,
        help="Approximate average trough width for AISC I8; auto-filled from catalog.",
    )
    if entry.get("pitch_mm") or entry.get("cover_width_mm"):
        gauges = entry.get("gauges_mm") or []
        gtxt = ", ".join(str(g) for g in gauges) if gauges else "—"
        st.caption(
            f"{entry.get('name', dkey)}: pitch {entry.get('pitch_mm', 0)} mm, "
            f"cover {entry.get('cover_width_mm', 0)} mm, gauges [{gtxt}] mm. "
            f"Source: {entry.get('source', 'ComFlor®')}."
        )

    orient_map = {
        "none": DeckOrientation.NONE,
        "perpendicular": DeckOrientation.PERPENDICULAR,
        "parallel": DeckOrientation.PARALLEL,
    }
    slab = SlabConfig(
        t_solid_mm=float(t_solid_mm),
        hr_mm=float(hr_mm),
        wr_mm=float(wr_mm),
        orientation=orient_map[orient],
        fc_MPa=float(fc_MPa),
        catalog_key=dkey,
    )
    concrete = ConcreteMaterial(fc_MPa=slab.fc_MPa, Ec_code=EcCode(ec_code))
    st.write(f"Ec ≈ {concrete.Ec_MPa:.0f} MPa; n_auto ≈ {steel.Es_MPa/concrete.Ec_MPa:.2f}")

    st.subheader("Studs")
    ds_mm = si_int_input(
        "Stud diameter (mm)", 12, 25, 19, 1, key="ds_mm", dual=dual_length_mm
    )
    Fu_stud = si_int_input(
        "Stud Fu (MPa)", 350, 550, 450, 1, key="Fus_MPa", dual=dual_stress_MPa
    )
    use_four = st.checkbox("Four independent stud-spacing zones", False, key="fourz")
    stud_zones = None
    target_ratio = None
    n_studs = None
    if use_four:
        st.caption(
            "Zone ratios of span (decimal exception); spacing in whole mm; "
            "rows = studs across the flange."
        )
        default_s = [305, 305, 305, 305]
        default_r = [(0.0, 0.25), (0.25, 0.50), (0.50, 0.75), (0.75, 1.0)]
        names = ["Z1 left end", "Z2 left mid", "Z3 right mid", "Z4 right end"]
        stud_zones = []
        for i, name in enumerate(names):
            zc1, zc2, zc3, zc4 = st.columns(4)
            a = zc1.number_input(f"{name} start x/L", 0.0, 1.0, default_r[i][0], 0.05, key=f"zs{i}")
            b = zc2.number_input(f"{name} end x/L", 0.0, 1.0, default_r[i][1], 0.05, key=f"ze{i}")
            with zc3:
                s_mm = si_int_input(
                    f"{name} spacing (mm)",
                    50,
                    1200,
                    default_s[i],
                    1,
                    key=f"zsp_mm{i}",
                    dual=dual_length_mm,
                )
            rows = zc4.number_input(f"{name} rows", 1, 4, 1, key=f"zr{i}")
            stud_zones.append(StudZone(name, a, b, float(s_mm), int(rows)))
    else:
        comp_mode = st.radio(
            "Shear connection",
            ["Full composite", "Partial — target %", "Check layout (n studs)"],
            key="compm",
        )
        if comp_mode.startswith("Partial"):
            pct = st.slider("Target ΣQn/C (%)", 25, 100, 50, key="pct")
            target_ratio = pct / 100.0
        elif comp_mode.startswith("Check"):
            n_studs = st.number_input("Studs each side of max M", 1, 200, 20, key="nst")

    st.subheader("Negative moment (continuous)")
    residual = st.checkbox(
        "Optional residual concrete tension in hogging (stud-limited; NOT I3 PNA)",
        False,
        key="resid",
    )
    Lb_neg_mm = si_int_input(
        "Hogging unbraced length Lb− (mm, 0=full span)",
        0,
        36500,
        0,
        1,
        key="Lbneg_mm",
        dual=dual_length_mm,
    )
    st.caption(
        "Default hogging strength is steel-only Chapter F (LTB/FLB/WLB). "
        "Bottom flange is in compression — deck brace does not apply. "
        "Full composite hogging PNA is not assumed (AISC I3 requires longitudinal slab rebar)."
    )

    parsed_loads = render_load_tables(float(L_mm))

    st.subheader("Axial (Chapter H)")
    st.caption(
        "Pr comes from the load table: **Pu_kN = sum of Axial_kN on included rows** "
        "(dedicated Axial row, or per-case axial). "
        "Decimal exception: effective length factor K."
    )
    Kfac = st.number_input("Effective length factor K (E3)", 0.5, 2.0, 1.0, 0.05, key="K")

    parsed_combos = render_combo_table(asce_ed, method)

    run = st.button("Run design", type="primary")

if "result" not in st.session_state:
    st.session_state.result = None

# Run design only when Input view just submitted (inputs in scope)
if run:
    ML = None
    MR = None
    if support != SupportType.SIMPLY_SUPPORTED and not use_fem:
        ML = float(M_left_ov_kNm)
        MR = float(M_right_ov_kNm)
    elif support != SupportType.SIMPLY_SUPPORTED:
        if abs(M_left_ov_kNm) > 1e-9:
            ML = float(M_left_ov_kNm)
        if abs(M_right_ov_kNm) > 1e-9:
            MR = float(M_right_ov_kNm)

    inp = DesignInputs(
        L_mm=float(L_mm),
        shape=shape,
        steel=steel,
        concrete=concrete,
        slab=slab,
        location=BeamLocation(location),
        spacing_left_mm=float(sL_mm),
        spacing_right_mm=float(sR_mm),
        beff_override_mm=float(beff_ov) if beff_ov > 0 else None,
        aisc_edition=AISCEdition.AISC360_22 if aisc_ed.endswith("22") else AISCEdition.AISC360_16,
        asce_edition=ASCEEdition.ASCE7_22 if asce_ed.endswith("22") else ASCEEdition.ASCE7_16,
        stud=StudConfig(diameter_mm=float(ds_mm), Fu_stud_MPa=float(Fu_stud)),
        n_studs_half_span=int(n_studs) if n_studs else None,
        target_composite_ratio=target_ratio,
        n_override=n_ov if n_ov > 0 else None,
        **parsed_loads.as_design_kwargs(),
        shored=shored,
        deck_braces_construction=deck_brace,
        camber_mm=float(camber_mm),
        deflection_limits=DeflectionLimits(),
        method=method,
        occupancy_combinations=parsed_combos.occupancy_or_none(),
        construction_combinations_override=parsed_combos.construction_or_none(),
        support=support,
        M_left_override_kNm=ML,
        M_right_override_kNm=MR,
        K_factor=Kfac,
        project_label=project_label,
        Lb_neg_mm=float(Lb_neg_mm) if Lb_neg_mm > 0 else None,
        include_residual_concrete_tension=residual,
        stud_zones=stud_zones,
    )
    with st.spinner("Designing..."):
        eng = DesignEngine(db)
        st.session_state.result = eng.design(inp, search_passing=True)

if st.session_state["main_view"] == "Summary":
    res = st.session_state.result
    if res is None:
        st.info("Run a design from the Input view.")
    else:
        render_results_dashboard(res, project_label=res.inputs_summary.get("project_label", ""))

if st.session_state["main_view"] == "Detailed Calculations":
    res = st.session_state.result
    if res is None:
        st.info("Run a design from the Input view.")
    else:
        st.markdown("Calculations cite **AISC 360** section numbers and edition flags.")
        st.caption(
            "Interactive cross-section stress viewer (click moment diagram or scrub x) "
            "is on the **Summary** view."
        )
        for line in detailed_lines(res):
            st.text(line)
        if getattr(res, "cumulative", None) is not None:
            st.subheader("Cumulative composite action stations")
            cum = res.cumulative
            st.caption(
                f"Origins: left = {cum.origin_left_mm/1000:.2f} m, "
                f"right = {cum.origin_right_mm/1000:.2f} m · "
                "F_req = C·M(x)/M_max (moment-proportional) from nearer origin · "
                "α = ΣQn/C_full · AISC I3.2d / I8 detailing (not a substitute for half-span stud count)."
            )
            from composite_beam.units import dual_force_kN, dual_length_mm
            st.dataframe(
                [
                    {
                        "x": dual_length_mm(r["x_mm"]),
                        "F_req": dual_force_kN(r["F_req_kN"]),
                        "ΣQn_prov": dual_force_kN(r["SumQn_prov_kN"]),
                        "α": round(r["alpha"], 3),
                        "Shortfall": dual_force_kN(r["shortfall_kN"]),
                        "Status": r["status"],
                    }
                    for r in cum.station_rows()
                ],
                use_container_width=True,
                hide_index=True,
            )

st.divider()
_render_main_nav("bot")
