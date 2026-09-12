"""Streamlit UI — Input / Summary / Detailed Calculations tabs.

SI is the primary input and display system; US customary equivalents update
in real time in brackets next to every dimensional / force / stress / moment quantity.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.components.si_inputs import si_number_input
from composite_beam.analysis.continuous import SupportType
from composite_beam.combinations.asce7 import ASCEEdition, Combination
from composite_beam.composite.effective_width import AISCEdition, BeamLocation
from composite_beam.composite.slab import DeckOrientation, SlabConfig, load_deck_catalog
from composite_beam.composite.stud_layout import StudZone
from composite_beam.composite.studs import StudConfig
from composite_beam.design_engine import DesignEngine, DesignInputs
from composite_beam.loads.load_cases import PointLoad, PointLoadSpec, default_empty_load_set
from composite_beam.materials.concrete import ConcreteMaterial, EcCode
from composite_beam.materials.steel import SteelMaterial, load_steel_grades
from composite_beam.reporting.charts import interaction_figure, moment_shear_figures, stud_layout_figure
from composite_beam.reporting.excel_export import result_to_xlsx_bytes
from composite_beam.reporting.summary import detailed_lines, summary_lines
from composite_beam.sections.box_sections import box_properties
from composite_beam.sections.w_shapes import WShapeDatabase, custom_w_shape
from composite_beam.serviceability.deflection import DeflectionLimits
from composite_beam.units import (
    dual_force_kN,
    dual_length_mm,
    dual_line_load_kNpm,
    dual_moment_kNm,
    dual_stress_MPa,
)

st.set_page_config(page_title="AISC Comp Beam Designer", layout="wide", page_icon="🏗️")
st.title("AISC Comp Beam Designer")
st.caption(
    "Primary SI (kN, mm, MPa); US customary in brackets. "
    "AISC 360-16/22 · ASCE 7-16/22. Keyboard-friendly number inputs."
)


@st.cache_resource
def get_db() -> WShapeDatabase:
    return WShapeDatabase()


db = get_db()
grades = load_steel_grades()
decks = load_deck_catalog()

tab_in, tab_sum, tab_det = st.tabs(["Input", "Summary", "Detailed Calculations"])

with tab_in:
    st.subheader("Geometry & codes")
    c1, c2, c3 = st.columns(3)
    with c1:
        L_mm = si_number_input(
            "Span L (mm)", 1500.0, 36500.0, 9144.0, 50.0, key="L_mm", dual=dual_length_mm
        )
        location = st.selectbox("Beam location", ["interior", "edge"], key="loc")
        aisc_ed = st.selectbox("AISC edition", ["AISC360-22", "AISC360-16"], key="aisc")
        asce_ed = st.selectbox("ASCE 7 edition", ["ASCE7-22", "ASCE7-16"], key="asce")
        method = st.selectbox("Design method", ["LRFD", "ASD"], key="method")
    with c2:
        sL_mm = si_number_input(
            "Spacing / adj. left (mm)",
            300.0,
            12000.0,
            3048.0,
            50.0,
            key="sL_mm",
            dual=dual_length_mm,
        )
        sR_default = 3048.0 if location == "interior" else 914.0
        sR_mm = si_number_input(
            "Spacing right / edge overhang (mm)",
            150.0,
            12000.0,
            sR_default,
            50.0,
            key="sR_mm",
            dual=dual_length_mm,
        )
        beff_ov = si_number_input(
            "beff override (mm, 0=auto)",
            0.0,
            7600.0,
            0.0,
            25.0,
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
        camber_mm = si_number_input(
            "Camber (mm)", 0.0, 150.0, 0.0, 5.0, key="camber_mm", dual=dual_length_mm
        )
        use_fem = st.checkbox("Use elastic FEM end moments", True, key="fem")
        M_left_ov_kNm = si_number_input(
            "M left override (kN·m, hogging −ve; 0=FEM)",
            -30000.0,
            30000.0,
            0.0,
            10.0,
            key="MLov_kNm",
            dual=dual_moment_kNm,
        )
        M_right_ov_kNm = si_number_input(
            "M right override (kN·m, hogging −ve; 0=FEM)",
            -30000.0,
            30000.0,
            0.0,
            10.0,
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
            d_mm = si_number_input("d (mm)", 100.0, 1000.0, 457.0, 5.0, key="cd_mm", dual=dual_length_mm)
        with cc2:
            bf_mm = si_number_input("bf (mm)", 100.0, 600.0, 152.0, 5.0, key="cbf_mm", dual=dual_length_mm)
        with cc3:
            tf_mm = si_number_input("tf (mm)", 5.0, 75.0, 10.8, 0.5, key="ctf_mm", dual=dual_length_mm)
        with cc4:
            tw_mm = si_number_input("tw (mm)", 4.0, 50.0, 7.6, 0.5, key="ctw_mm", dual=dual_length_mm)
        shape = custom_w_shape("CUSTOM", d_mm, bf_mm, tf_mm, tw_mm)
        st.caption(shape.display_name)
    else:
        bc1, bc2, bc3, bc4 = st.columns(4)
        with bc1:
            H_mm = si_number_input("Box depth H (mm)", 150.0, 1200.0, 406.0, 5.0, key="bH_mm", dual=dual_length_mm)
        with bc2:
            B_mm = si_number_input("Box width B (mm)", 150.0, 900.0, 305.0, 5.0, key="bB_mm", dual=dual_length_mm)
        with bc3:
            tfb_mm = si_number_input("Flange tf (mm)", 6.0, 75.0, 19.0, 1.0, key="btf_mm", dual=dual_length_mm)
        with bc4:
            twb_mm = si_number_input("Web tw (mm, each)", 6.0, 50.0, 12.7, 1.0, key="btw_mm", dual=dual_length_mm)
        shape = box_properties(H_mm, B_mm, tfb_mm, twb_mm, designation="BOX")
        st.caption(shape.display_name)
        st.caption(
            f"A={shape.A_mm2:.0f} mm²; Ix={shape.Ix_mm4:.3e} mm⁴; "
            f"J={shape.J_mm4:.3e} mm⁴ (closed Bredt). Classification uses Table B4.1b cases 12/19."
        )

    gkey = st.selectbox("Steel grade", list(grades.keys()), index=0, key="grade")
    Fy_ov = si_number_input(
        "Fy override (MPa, 0=catalog)",
        0.0,
        690.0,
        0.0,
        5.0,
        key="Fyov_MPa",
        dual=dual_stress_MPa,
    )
    steel = SteelMaterial.from_grade(
        gkey,
        tf_mm=shape.tf_mm,
        Fy_override_MPa=Fy_ov if Fy_ov > 0 else None,
    )
    st.write(f"Fy = {dual_stress_MPa(steel.Fy_MPa)}")

    st.subheader("Slab / deck / concrete")
    dkey = st.selectbox("Deck catalog", list(decks.keys()), index=0, key="deck")
    t_solid_mm = si_number_input(
        "Solid thickness above deck / total solid (mm)",
        50.0,
        300.0,
        100.0,
        5.0,
        key="tsol_mm",
        dual=dual_length_mm,
    )
    fc_MPa = si_number_input(
        "f'c (MPa)", 14.0, 85.0, 27.6, 1.0, key="fc_MPa", dual=dual_stress_MPa
    )
    ec_code = st.selectbox("Ec formula", ["ACI318", "Eurocode2", "NZS3101"], key="ec")
    n_ov = st.number_input("n = Es/Ec override (0=auto)", 0.0, 20.0, 0.0, 0.1, key="nov")
    orient_map = {
        "none": DeckOrientation.NONE,
        "perpendicular": DeckOrientation.PERPENDICULAR,
        "parallel": DeckOrientation.PARALLEL,
    }
    default_orient = decks[dkey].get("orientation", "none")
    orient = st.selectbox(
        "Deck orientation",
        ["none", "perpendicular", "parallel"],
        index=["none", "perpendicular", "parallel"].index(default_orient),
        key="orient",
    )
    slab = SlabConfig(
        t_solid_mm=t_solid_mm,
        hr_mm=float(decks[dkey]["hr_in"]) * 25.4,
        wr_mm=float(decks[dkey]["wr_in"]) * 25.4,
        orientation=orient_map[orient],
        fc_MPa=fc_MPa,
        catalog_key=dkey,
    )
    concrete = ConcreteMaterial(fc_MPa=slab.fc_MPa, Ec_code=EcCode(ec_code))
    st.write(f"Ec ≈ {concrete.Ec_MPa:.0f} MPa; n_auto ≈ {steel.Es_MPa/concrete.Ec_MPa:.2f}")

    st.subheader("Studs")
    ds_mm = si_number_input(
        "Stud diameter (mm)", 12.0, 25.0, 19.0, 1.0, key="ds_mm", dual=dual_length_mm
    )
    Fu_stud = si_number_input(
        "Stud Fu (MPa)", 350.0, 550.0, 448.2, 5.0, key="Fus_MPa", dual=dual_stress_MPa
    )
    use_four = st.checkbox("Four independent stud-spacing zones", False, key="fourz")
    stud_zones = None
    target_ratio = None
    n_studs = None
    if use_four:
        st.caption("Zone ratios of span; spacing in mm; rows = studs across the flange.")
        default_s = [305.0, 305.0, 305.0, 305.0]
        default_r = [(0.0, 0.25), (0.25, 0.50), (0.50, 0.75), (0.75, 1.0)]
        names = ["Z1 left end", "Z2 left mid", "Z3 right mid", "Z4 right end"]
        stud_zones = []
        for i, name in enumerate(names):
            zc1, zc2, zc3, zc4 = st.columns(4)
            a = zc1.number_input(f"{name} start x/L", 0.0, 1.0, default_r[i][0], 0.05, key=f"zs{i}")
            b = zc2.number_input(f"{name} end x/L", 0.0, 1.0, default_r[i][1], 0.05, key=f"ze{i}")
            with zc3:
                s_mm = si_number_input(
                    f"{name} spacing (mm)",
                    50.0,
                    1200.0,
                    default_s[i],
                    10.0,
                    key=f"zsp_mm{i}",
                    dual=dual_length_mm,
                )
            rows = zc4.number_input(f"{name} rows", 1, 4, 1, key=f"zr{i}")
            stud_zones.append(StudZone(name, a, b, s_mm, int(rows)))
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
    Lb_neg_mm = si_number_input(
        "Hogging unbraced length Lb− (mm, 0=full span)",
        0.0,
        36500.0,
        0.0,
        50.0,
        key="Lbneg_mm",
        dual=dual_length_mm,
    )
    st.caption(
        "Default hogging strength is steel-only Chapter F (LTB/FLB/WLB). "
        "Bottom flange is in compression — deck brace does not apply. "
        "Full composite hogging PNA is not assumed (AISC I3 requires longitudinal slab rebar)."
    )

    st.subheader("Loads (service / nominal)")
    w_SDL_kNpm = si_number_input(
        "Superimposed dead SDL (kN/m on beam)",
        0.0,
        30.0,
        2.19,
        0.1,
        key="sdl_kNpm",
        dual=dual_line_load_kNpm,
    )
    w_LL_kNpm = si_number_input(
        "Live load L (kN/m on beam)",
        0.0,
        75.0,
        7.3,
        0.1,
        key="ll_kNpm",
        dual=dual_line_load_kNpm,
    )
    w_C_kNpm = si_number_input(
        "Construction live C (kN/m)",
        0.0,
        30.0,
        1.46,
        0.1,
        key="clive_kNpm",
        dual=dual_line_load_kNpm,
    )
    n_pts = st.number_input("Number of LL point loads", 0, 10, 0, key="npts")
    points_LL = []
    for i in range(int(n_pts)):
        pc1, pc2 = st.columns(2)
        with pc1:
            P_kN = si_number_input(
                f"P{i+1} (kN)", 0.0, 2200.0, 44.5, 1.0, key=f"P_kN{i}", dual=dual_force_kN
            )
        ratio = pc2.number_input(f"Location ratio x/L {i+1}", 0.0, 1.0, 0.5, key=f"r{i}")
        points_LL.append(PointLoad(P_kN=P_kN, location=ratio, spec=PointLoadSpec.RATIO))

    st.subheader("Axial (Chapter H)")
    Pu_kN = si_number_input(
        "Required axial Pr (kN, compression +ve; 0=flexure only)",
        -9000.0,
        9000.0,
        0.0,
        10.0,
        key="Pu_kN",
        dual=dual_force_kN,
    )
    Kfac = st.number_input("Effective length factor K (E3)", 0.5, 2.0, 1.0, 0.05, key="K")

    st.subheader("Custom combinations (up to 5)")
    n_custom = st.number_input("Custom combos", 0, 5, 0, key="ncu")
    custom = []
    for i in range(int(n_custom)):
        name = st.text_input(f"Combo {i+1} name", f"CUSTOM{i+1}", key=f"cn{i}")
        fD = st.number_input(f"D factor {i+1}", 0.0, 2.0, 1.2, key=f"cd{i}")
        fL = st.number_input(f"L factor {i+1}", 0.0, 2.0, 1.6, key=f"cl{i}")
        custom.append(Combination(name=name, factors={"D": fD, "L": fL}, method=method, edition=asce_ed))

    st.subheader("Load case scaffold (data model)")
    with st.expander("All load case slots (SW, SDL, misc D/L, E, W, T, C)"):
        ls = default_empty_load_set()
        st.write([c.name for c in ls.cases])

    run = st.button("Run design", type="primary")

if "result" not in st.session_state:
    st.session_state.result = None

if run:
    ML = None
    MR = None
    if support != SupportType.SIMPLY_SUPPORTED and not use_fem:
        ML = M_left_ov_kNm
        MR = M_right_ov_kNm
    elif support != SupportType.SIMPLY_SUPPORTED:
        if abs(M_left_ov_kNm) > 1e-9:
            ML = M_left_ov_kNm
        if abs(M_right_ov_kNm) > 1e-9:
            MR = M_right_ov_kNm

    inp = DesignInputs(
        L_mm=L_mm,
        shape=shape,
        steel=steel,
        concrete=concrete,
        slab=slab,
        location=BeamLocation(location),
        spacing_left_mm=sL_mm,
        spacing_right_mm=sR_mm,
        beff_override_mm=beff_ov if beff_ov > 0 else None,
        aisc_edition=AISCEdition.AISC360_22 if aisc_ed.endswith("22") else AISCEdition.AISC360_16,
        asce_edition=ASCEEdition.ASCE7_22 if asce_ed.endswith("22") else ASCEEdition.ASCE7_16,
        stud=StudConfig(diameter_mm=ds_mm, Fu_stud_MPa=Fu_stud),
        n_studs_half_span=int(n_studs) if n_studs else None,
        target_composite_ratio=target_ratio,
        n_override=n_ov if n_ov > 0 else None,
        w_SDL_kNpm=w_SDL_kNpm,
        w_LL_kNpm=w_LL_kNpm,
        w_construction_kNpm=w_C_kNpm,
        points_LL=points_LL,
        shored=shored,
        deck_braces_construction=deck_brace,
        camber_mm=camber_mm,
        deflection_limits=DeflectionLimits(),
        method=method,
        custom_combinations=custom,
        support=support,
        M_left_override_kNm=ML,
        M_right_override_kNm=MR,
        Pu_kN=Pu_kN,
        K_factor=Kfac,
        Lb_neg_mm=Lb_neg_mm if Lb_neg_mm > 0 else None,
        include_residual_concrete_tension=residual,
        stud_zones=stud_zones,
    )
    with st.spinner("Designing..."):
        eng = DesignEngine(db)
        st.session_state.result = eng.design(inp, search_passing=True)

with tab_sum:
    res = st.session_state.result
    if res is None:
        st.info("Run a design from the Input tab.")
    else:
        for line in summary_lines(res):
            st.text(line)
        st.metric("Overall", "PASS" if res.overall_pass else "FAIL")
        mcols = st.columns(5)
        mcols[0].metric("DCR flexure +", f"{res.DCR_flexure:.3f}")
        if res.construction_LTB:
            mcols[1].metric("DCR construction", f"{res.construction_LTB.DCR:.3f}")
        mcols[2].metric("φMn+", dual_moment_kNm(res.positive_moment.phiMn_kNm))
        if res.negative_moment is not None:
            mcols[3].metric("DCR hogging −", f"{res.negative_moment.DCR:.3f}")
        if res.interaction is not None:
            mcols[4].metric(f"DCR {res.interaction.equation}", f"{res.interaction.DCR:.3f}")
        if res.punching is not None:
            st.caption(
                f"Punching DCR={res.punching.DCR:.3f} (ACI 318-19 §22.6). "
                "Thin slabs often govern around 19 mm studs — increase t_solid or spacing."
            )

        st.subheader("Diagrams")
        for fig in moment_shear_figures(res):
            st.plotly_chart(fig, use_container_width=True)
        fig_h = interaction_figure(res)
        if fig_h is not None:
            st.plotly_chart(fig_h, use_container_width=True)
        else:
            st.caption("Chapter H interaction plot appears when Pr ≠ 0.")
        fig_s = stud_layout_figure(res)
        if fig_s is not None:
            st.plotly_chart(fig_s, use_container_width=True)
        else:
            st.caption("Enable four-zone stud spacing on Input to plot the stud layout.")

        try:
            xls = result_to_xlsx_bytes(res)
            st.download_button(
                "Download Excel report",
                data=xls,
                file_name="aisc_comp_beam_design.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except Exception as exc:  # pragma: no cover
            st.warning(f"Excel export unavailable: {exc}")

        if res.passing_shapes:
            st.subheader("Passing W-shapes (lightest → heaviest)")
            st.table(
                [
                    {
                        "Shape": p.display_name or p.designation,
                        "W (kg/m) [plf]": f"{p.W_lb_ft * 1.4881639:.1f} [{p.W_lb_ft:.0f}]",
                        "DCR_flex": round(p.DCR_flexure, 3),
                        "DCR_constr": round(p.DCR_construction, 3),
                    }
                    for p in res.passing_shapes
                ]
            )

with tab_det:
    res = st.session_state.result
    if res is None:
        st.info("Run a design from the Input tab.")
    else:
        st.markdown("Calculations cite **AISC 360** section numbers and edition flags.")
        for line in detailed_lines(res):
            st.text(line)
