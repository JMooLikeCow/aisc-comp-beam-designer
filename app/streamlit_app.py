"""Streamlit UI — Input / Summary / Detailed Calculations tabs."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
from composite_beam.units import format_dual, in_to_mm, knm_to_kipft, ksi_to_mpa

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
        L_ft = st.number_input("Span L (ft)", 5.0, 120.0, 30.0, 0.5, key="L_ft")
        L_mm = in_to_mm(L_ft * 12.0)
        st.write(format_dual(L_mm, "mm", L_ft * 12.0, "in", 0))
        location = st.selectbox("Beam location", ["interior", "edge"], key="loc")
        aisc_ed = st.selectbox("AISC edition", ["AISC360-22", "AISC360-16"], key="aisc")
        asce_ed = st.selectbox("ASCE 7 edition", ["ASCE7-22", "ASCE7-16"], key="asce")
        method = st.selectbox("Design method", ["LRFD", "ASD"], key="method")
    with c2:
        sL_ft = st.number_input("Spacing / adj. left (ft)", 1.0, 40.0, 10.0, 0.5, key="sL")
        sR_ft = st.number_input(
            "Spacing right / edge overhang (ft)",
            0.5,
            40.0,
            10.0 if location == "interior" else 3.0,
            0.5,
            key="sR",
        )
        beff_ov = st.number_input("beff override (in, 0=auto)", 0.0, 300.0, 0.0, 1.0, key="beff")
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
        camber_in = st.number_input("Camber (in)", 0.0, 6.0, 0.0, 0.125, key="camber")
        use_fem = st.checkbox("Use elastic FEM end moments", True, key="fem")
        M_left_ov_kft = st.number_input(
            "M left override (kip·ft, hogging −ve; 0=FEM)",
            -20000.0,
            20000.0,
            0.0,
            1.0,
            key="MLov",
        )
        M_right_ov_kft = st.number_input(
            "M right override (kip·ft, hogging −ve; 0=FEM)",
            -20000.0,
            20000.0,
            0.0,
            1.0,
            key="MRov",
        )

    st.subheader("Steel section")
    sec_mode = st.radio("Section type", ["W-shape catalog", "Custom I-section", "Custom welded box"], horizontal=True)
    designations = [s.designation for s in db.lightest_first()]
    if sec_mode == "W-shape catalog":
        des = st.selectbox(
            "W-shape",
            designations,
            index=designations.index("W18X35") if "W18X35" in designations else 0,
            key="wdes",
        )
        shape = db.get(des)
    elif sec_mode == "Custom I-section":
        cc1, cc2, cc3, cc4 = st.columns(4)
        d_in = cc1.number_input("d (in)", 4.0, 40.0, 18.0, key="cd")
        bf_in = cc2.number_input("bf (in)", 4.0, 24.0, 6.0, key="cbf")
        tf_in = cc3.number_input("tf (in)", 0.2, 3.0, 0.425, key="ctf")
        tw_in = cc4.number_input("tw (in)", 0.15, 2.0, 0.30, key="ctw")
        shape = custom_w_shape(
            "CUSTOM",
            in_to_mm(d_in),
            in_to_mm(bf_in),
            in_to_mm(tf_in),
            in_to_mm(tw_in),
        )
    else:
        bc1, bc2, bc3, bc4 = st.columns(4)
        H_in = bc1.number_input("Box depth H (in)", 6.0, 48.0, 16.0, key="bH")
        B_in = bc2.number_input("Box width B (in)", 6.0, 36.0, 12.0, key="bB")
        tfb_in = bc3.number_input("Flange tf (in)", 0.25, 3.0, 0.75, key="btf")
        twb_in = bc4.number_input("Web tw (in, each)", 0.25, 2.0, 0.5, key="btw")
        shape = box_properties(
            in_to_mm(H_in),
            in_to_mm(B_in),
            in_to_mm(tfb_in),
            in_to_mm(twb_in),
            designation="BOX",
        )
        st.caption(
            f"A={shape.A_mm2:.0f} mm²; Ix={shape.Ix_mm4:.3e} mm⁴; "
            f"J={shape.J_mm4:.3e} mm⁴ (closed Bredt). Classification uses Table B4.1b cases 12/19."
        )

    gkey = st.selectbox("Steel grade", list(grades.keys()), index=0, key="grade")
    Fy_ov = st.number_input("Fy override (ksi, 0=catalog)", 0.0, 100.0, 0.0, key="Fyov")
    steel = SteelMaterial.from_grade(
        gkey,
        tf_mm=shape.tf_mm,
        Fy_override_MPa=ksi_to_mpa(Fy_ov) if Fy_ov > 0 else None,
    )
    st.write(f"Fy = {format_dual(steel.Fy_MPa, 'MPa', steel.Fy_MPa/6.894757, 'ksi')}")

    st.subheader("Slab / deck / concrete")
    dkey = st.selectbox("Deck catalog", list(decks.keys()), index=0, key="deck")
    t_solid_in = st.number_input("Solid thickness above deck / total solid (in)", 2.0, 12.0, 4.0, 0.25, key="tsol")
    fc_ksi = st.number_input("f'c (ksi)", 2.0, 12.0, 4.0, 0.5, key="fc")
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
        t_solid_mm=in_to_mm(t_solid_in),
        hr_mm=float(decks[dkey]["hr_in"]) * 25.4,
        wr_mm=float(decks[dkey]["wr_in"]) * 25.4,
        orientation=orient_map[orient],
        fc_MPa=ksi_to_mpa(fc_ksi),
        catalog_key=dkey,
    )
    concrete = ConcreteMaterial(fc_MPa=slab.fc_MPa, Ec_code=EcCode(ec_code))
    st.write(f"Ec ≈ {concrete.Ec_MPa:.0f} MPa; n_auto ≈ {steel.Es_MPa/concrete.Ec_MPa:.2f}")

    st.subheader("Studs")
    ds_in = st.number_input("Stud diameter (in)", 0.5, 1.0, 0.75, 0.125, key="ds")
    Fu_stud = st.number_input("Stud Fu (ksi)", 50.0, 80.0, 65.0, key="Fus")
    use_four = st.checkbox("Four independent stud-spacing zones", False, key="fourz")
    stud_zones = None
    target_ratio = None
    n_studs = None
    if use_four:
        st.caption("Zone ratios of span; spacing in inches; rows = studs across the flange.")
        default_s = [12.0, 12.0, 12.0, 12.0]
        default_r = [(0.0, 0.25), (0.25, 0.50), (0.50, 0.75), (0.75, 1.0)]
        names = ["Z1 left end", "Z2 left mid", "Z3 right mid", "Z4 right end"]
        stud_zones = []
        for i, name in enumerate(names):
            zc1, zc2, zc3, zc4 = st.columns(4)
            a = zc1.number_input(f"{name} start x/L", 0.0, 1.0, default_r[i][0], 0.05, key=f"zs{i}")
            b = zc2.number_input(f"{name} end x/L", 0.0, 1.0, default_r[i][1], 0.05, key=f"ze{i}")
            s_in = zc3.number_input(f"{name} spacing (in)", 2.0, 48.0, default_s[i], 0.5, key=f"zsp{i}")
            rows = zc4.number_input(f"{name} rows", 1, 4, 1, key=f"zr{i}")
            stud_zones.append(StudZone(name, a, b, in_to_mm(s_in), int(rows)))
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
    Lb_neg_ft = st.number_input(
        "Hogging unbraced length Lb− (ft, 0=full span)",
        0.0,
        120.0,
        0.0,
        0.5,
        key="Lbneg",
    )
    st.caption(
        "Default hogging strength is steel-only Chapter F (LTB/FLB/WLB). "
        "Bottom flange is in compression — deck brace does not apply. "
        "Full composite hogging PNA is not assumed (AISC I3 requires longitudinal slab rebar)."
    )

    st.subheader("Loads (service / nominal)")
    w_SDL_plf = st.number_input("Superimposed dead SDL (plf on beam)", 0.0, 2000.0, 150.0, key="sdl")
    w_LL_plf = st.number_input("Live load L (plf on beam)", 0.0, 5000.0, 500.0, key="ll")
    w_C_plf = st.number_input("Construction live C (plf)", 0.0, 2000.0, 100.0, key="clive")
    plf_to_kNpm = 0.0145939
    n_pts = st.number_input("Number of LL point loads", 0, 10, 0, key="npts")
    points_LL = []
    for i in range(int(n_pts)):
        pc1, pc2 = st.columns(2)
        P_kip = pc1.number_input(f"P{i+1} (kip)", 0.0, 500.0, 10.0, key=f"P{i}")
        ratio = pc2.number_input(f"Location ratio x/L {i+1}", 0.0, 1.0, 0.5, key=f"r{i}")
        points_LL.append(
            PointLoad(P_kN=P_kip * 4.4482216152605, location=ratio, spec=PointLoadSpec.RATIO)
        )

    st.subheader("Axial (Chapter H)")
    Pu_kip = st.number_input("Required axial Pr (kip, compression +ve; 0=flexure only)", -2000.0, 2000.0, 0.0, key="Pu")
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
    kipft_to_knm = 1.3558179483314
    ML = None
    MR = None
    if support != SupportType.SIMPLY_SUPPORTED and not use_fem:
        ML = M_left_ov_kft * kipft_to_knm
        MR = M_right_ov_kft * kipft_to_knm
    elif support != SupportType.SIMPLY_SUPPORTED:
        if abs(M_left_ov_kft) > 1e-9:
            ML = M_left_ov_kft * kipft_to_knm
        if abs(M_right_ov_kft) > 1e-9:
            MR = M_right_ov_kft * kipft_to_knm

    inp = DesignInputs(
        L_mm=L_mm,
        shape=shape,
        steel=steel,
        concrete=concrete,
        slab=slab,
        location=BeamLocation(location),
        spacing_left_mm=in_to_mm(sL_ft * 12),
        spacing_right_mm=in_to_mm(sR_ft * 12),
        beff_override_mm=in_to_mm(beff_ov) if beff_ov > 0 else None,
        aisc_edition=AISCEdition.AISC360_22 if aisc_ed.endswith("22") else AISCEdition.AISC360_16,
        asce_edition=ASCEEdition.ASCE7_22 if asce_ed.endswith("22") else ASCEEdition.ASCE7_16,
        stud=StudConfig(diameter_mm=in_to_mm(ds_in), Fu_stud_MPa=ksi_to_mpa(Fu_stud)),
        n_studs_half_span=int(n_studs) if n_studs else None,
        target_composite_ratio=target_ratio,
        n_override=n_ov if n_ov > 0 else None,
        w_SDL_kNpm=w_SDL_plf * plf_to_kNpm,
        w_LL_kNpm=w_LL_plf * plf_to_kNpm,
        w_construction_kNpm=w_C_plf * plf_to_kNpm,
        points_LL=points_LL,
        shored=shored,
        deck_braces_construction=deck_brace,
        camber_mm=in_to_mm(camber_in),
        deflection_limits=DeflectionLimits(),
        method=method,
        custom_combinations=custom,
        support=support,
        M_left_override_kNm=ML,
        M_right_override_kNm=MR,
        Pu_kN=Pu_kip * 4.4482216152605,
        K_factor=Kfac,
        Lb_neg_mm=in_to_mm(Lb_neg_ft * 12.0) if Lb_neg_ft > 0 else None,
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
        mcols[2].metric(
            "φMn+",
            f"{res.positive_moment.phiMn_kNm:.1f} kN·m",
            f"{knm_to_kipft(res.positive_moment.phiMn_kNm):.1f} kip·ft",
        )
        if res.negative_moment is not None:
            mcols[3].metric("DCR hogging −", f"{res.negative_moment.DCR:.3f}")
        if res.interaction is not None:
            mcols[4].metric(f"DCR {res.interaction.equation}", f"{res.interaction.DCR:.3f}")
        if res.punching is not None:
            st.caption(
                f"Punching DCR={res.punching.DCR:.3f} (ACI 318-19 §22.6). "
                "Thin slabs often govern around ¾ in studs — increase t_solid or spacing."
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
                        "Shape": p.designation,
                        "plf": p.W_lb_ft,
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
