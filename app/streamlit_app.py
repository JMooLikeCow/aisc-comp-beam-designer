"""Streamlit UI — Input / Summary / Detailed Calculations tabs."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from composite_beam.combinations.asce7 import ASCEEdition, Combination
from composite_beam.composite.effective_width import AISCEdition, BeamLocation
from composite_beam.composite.slab import DeckOrientation, SlabConfig, load_deck_catalog
from composite_beam.composite.studs import StudConfig
from composite_beam.design_engine import DesignEngine, DesignInputs
from composite_beam.loads.load_cases import PointLoad, PointLoadSpec, default_empty_load_set
from composite_beam.materials.concrete import ConcreteMaterial, EcCode
from composite_beam.materials.steel import SteelMaterial, load_steel_grades
from composite_beam.reporting.summary import detailed_lines, summary_lines
from composite_beam.sections.w_shapes import WShapeDatabase, custom_w_shape
from composite_beam.serviceability.deflection import DeflectionLimits
from composite_beam.units import format_dual, in_to_mm, knm_to_kipft, ksi_to_mpa, mm_to_in

st.set_page_config(page_title="Composite Beam Design", layout="wide", page_icon="🏗️")
st.title("AISC Steel–Concrete Composite Beam Design")
st.caption("Primary SI (kN, mm, MPa); US customary in brackets. AISC 360-22 / ASCE 7.")


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
        L_ft = st.number_input("Span L (ft)", 5.0, 120.0, 30.0, 0.5)
        L_mm = in_to_mm(L_ft * 12.0)
        st.write(format_dual(L_mm, "mm", L_ft * 12.0, "in", 0))
        location = st.selectbox("Beam location", ["interior", "edge"])
        aisc_ed = st.selectbox("AISC edition", ["AISC360-22", "AISC360-16"])
        asce_ed = st.selectbox("ASCE 7 edition", ["ASCE7-22", "ASCE7-16"])
        method = st.selectbox("Design method", ["LRFD", "ASD"])
    with c2:
        sL_ft = st.number_input("Spacing / adj. left (ft)", 1.0, 40.0, 10.0, 0.5)
        sR_ft = st.number_input(
            "Spacing right / edge overhang (ft)",
            0.5,
            40.0,
            10.0 if location == "interior" else 3.0,
            0.5,
        )
        beff_ov = st.number_input("beff override (in, 0=auto)", 0.0, 300.0, 0.0, 1.0)
    with c3:
        shored = st.checkbox("Shored construction", False)
        deck_brace = st.checkbox("Deck braces compression flange (construction)", True)
        camber_in = st.number_input("Camber (in)", 0.0, 6.0, 0.0, 0.125)

    st.subheader("Steel section")
    use_custom = st.checkbox("Custom section properties", False)
    designations = [s.designation for s in db.lightest_first()]
    if not use_custom:
        des = st.selectbox("W-shape", designations, index=designations.index("W18X35") if "W18X35" in designations else 0)
        shape = db.get(des)
    else:
        cc1, cc2, cc3, cc4 = st.columns(4)
        d_in = cc1.number_input("d (in)", 4.0, 40.0, 18.0)
        bf_in = cc2.number_input("bf (in)", 4.0, 24.0, 6.0)
        tf_in = cc3.number_input("tf (in)", 0.2, 3.0, 0.425)
        tw_in = cc4.number_input("tw (in)", 0.15, 2.0, 0.30)
        shape = custom_w_shape(
            "CUSTOM",
            in_to_mm(d_in),
            in_to_mm(bf_in),
            in_to_mm(tf_in),
            in_to_mm(tw_in),
        )

    gkey = st.selectbox("Steel grade", list(grades.keys()), index=0)
    Fy_ov = st.number_input("Fy override (ksi, 0=catalog)", 0.0, 100.0, 0.0)
    steel = SteelMaterial.from_grade(
        gkey,
        tf_mm=shape.tf_mm,
        Fy_override_MPa=ksi_to_mpa(Fy_ov) if Fy_ov > 0 else None,
    )
    st.write(f"Fy = {format_dual(steel.Fy_MPa, 'MPa', steel.Fy_MPa/6.894757, 'ksi')}")

    st.subheader("Slab / deck / concrete")
    dkey = st.selectbox("Deck catalog", list(decks.keys()), index=0)
    t_solid_in = st.number_input("Solid thickness above deck / total solid (in)", 2.0, 12.0, 4.0, 0.25)
    fc_ksi = st.number_input("f'c (ksi)", 2.0, 12.0, 4.0, 0.5)
    ec_code = st.selectbox("Ec formula", ["ACI318", "Eurocode2", "NZS3101"])
    n_ov = st.number_input("n = Es/Ec override (0=auto)", 0.0, 20.0, 0.0, 0.1)
    orient_map = {"none": DeckOrientation.NONE, "perpendicular": DeckOrientation.PERPENDICULAR, "parallel": DeckOrientation.PARALLEL}
    default_orient = decks[dkey].get("orientation", "none")
    orient = st.selectbox(
        "Deck orientation",
        ["none", "perpendicular", "parallel"],
        index=["none", "perpendicular", "parallel"].index(default_orient),
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
    ds_in = st.number_input("Stud diameter (in)", 0.5, 1.0, 0.75, 0.125)
    Fu_stud = st.number_input("Stud Fu (ksi)", 50.0, 80.0, 65.0)
    comp_mode = st.radio("Shear connection", ["Full composite", "Partial — target %", "Check layout (n studs)"])
    target_ratio = None
    n_studs = None
    if comp_mode.startswith("Partial"):
        pct = st.slider("Target ΣQn/C (%)", 25, 100, 50)
        target_ratio = pct / 100.0
    elif comp_mode.startswith("Check"):
        n_studs = st.number_input("Studs each side of max M", 1, 200, 20)

    st.subheader("Loads (service / nominal)")
    w_SDL_plf = st.number_input("Superimposed dead SDL (plf on beam)", 0.0, 2000.0, 150.0)
    w_LL_plf = st.number_input("Live load L (plf on beam)", 0.0, 5000.0, 500.0)
    w_C_plf = st.number_input("Construction live C (plf)", 0.0, 2000.0, 100.0)
    # plf → kN/m: 1 plf = 0.0145939 kN/m
    plf_to_kNpm = 0.0145939
    n_pts = st.number_input("Number of LL point loads", 0, 10, 0)
    points_LL = []
    for i in range(int(n_pts)):
        pc1, pc2 = st.columns(2)
        P_kip = pc1.number_input(f"P{i+1} (kip)", 0.0, 500.0, 10.0, key=f"P{i}")
        ratio = pc2.number_input(f"Location ratio x/L {i+1}", 0.0, 1.0, 0.5, key=f"r{i}")
        points_LL.append(PointLoad(P_kN=P_kip * 4.4482216152605, location=ratio, spec=PointLoadSpec.RATIO))

    st.subheader("Custom combinations (up to 5)")
    n_custom = st.number_input("Custom combos", 0, 5, 0)
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

if tab_in and run:
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
        c1, c2, c3 = st.columns(3)
        c1.metric("DCR flexure", f"{res.DCR_flexure:.3f}")
        if res.construction_LTB:
            c2.metric("DCR construction", f"{res.construction_LTB.DCR:.3f}")
        c3.metric(
            "φMn",
            f"{res.positive_moment.phiMn_kNm:.1f} kN·m",
            f"{knm_to_kipft(res.positive_moment.phiMn_kNm):.1f} kip·ft",
        )
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
