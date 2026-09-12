# AISC Steel–Concrete Composite Beam Design Tool

Production-oriented **Python + Streamlit** toolkit for **AISC 360** steel–concrete composite beam design (simply supported happy path), with **ASCE 7** gravity combinations.

Primary units: **SI (kN, mm, kPa, MPa)** with **US customary in brackets** in the UI and reports.

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://blank-app-template.streamlit.app/)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run the app

```bash
streamlit run streamlit_app.py
```

Tabs: **Input** · **Summary** · **Detailed Calculations** (AISC section citations + edition flags).

## Run tests

```bash
pytest -q
```

Acceptance fixtures cover: (a) full composite compact + solid slab, (b) partial ~50% deck perpendicular, (c) edge beam \(b_\mathrm{eff}\), (d) unshored construction LTB pass/fail, (e) stud \(Q_n\) concrete vs steel governing.

## Package layout

```
composite_beam/     # typed library (loads, sections, materials, analysis,
                    # composite, strength, serviceability, combinations, reporting)
app/streamlit_app.py
data/               # w_shapes.csv, steel_grades.json, deck_catalog.json
tests/
```

## Implemented (P0 vertical slice)

| Feature | Status |
|--------|--------|
| Simply supported beam, UDL + point loads | Done |
| ASCE 7-16 / 7-22 LRFD (+ ASD) gravity combos + ≤5 custom | Done |
| Construction combos separate from occupancy | Done |
| W-shape CSV + custom I-section properties | Done |
| Steel grades A992 / A572-50 / A36 (thickness-aware Fy) | Done |
| Solid slab / metal deck catalog + manual; Ec ACI / EC2 / NZS stubs | Done |
| \(n=E_s/E_c\) auto + override | Done |
| Effective width AISC I2.1a interior & edge; 16 vs 22 flags; override | Done |
| Full & partial composite; \(\sum Q_n/C\); studs from target ratio or check layout | Done |
| Stud \(Q_n\) with \(R_g,R_p\), deck orientation, \(d_s\le 2.5 t_f\) (I8) | Done |
| Positive \(M_n\): plastic I3.2a if compact else elastic I3.2b; **both reported** | Done |
| Section classification Table B4.1b | Done |
| Unshored construction steel-alone LTB; deck brace toggle | Done |
| Serviceability \(\Delta_{LL}=L/360\), \(\Delta_{tot}=L/240\); \(I_\mathrm{eff}\); shored vs unshored paths | Done |
| Camber manual + 80% DL suggestion; warn if >100% DL Δ | Done |
| Design check DCRs + up to 10 passing W shapes lightest→heaviest | Done |
| Load-case data model (SW, SDL, misc D/L, E, W, T, C, …) | Done (scaffold) |

## Deferred (P1 / later)

- Fixed-fixed / fixed-pinned continuous analysis; negative moment (Ch. F + I3)
- Chapter H axial interaction
- Four stud spacing zones; punching shear around studs
- Custom welded box sections
- Excel export; Plotly/matplotlib charts
- Full lateral (W/E) combination detailing beyond gravity

## Out of scope

- Cantilevers
- Floor vibration
- Fire design

## Engineering rules locked in code

1. \(\phi M_n\) plastic **I3.2a only when compact**; else elastic **I3.2b** — both always reported.
2. Partial \(\sum Q_n/C\) reduces \(M_n\) and uses \(I_\mathrm{eff}\) (Eq. I3-1), not full \(I\).
3. Effective width interior vs edge per **I2.1a**.
4. Stud \(Q_n\) with \(R_g/R_p\), deck orientation, I8 diameter limit.
5. Unshored construction: steel-alone **Chapter F LTB**.
6. Construction vs service deflection paths separated.
7. Construction load combinations ≠ occupancy combinations in tests/reporting.
8. AISC 360-16 vs 360-22 and ASCE 7-16 vs 7-22 edition flags surfaced in detailed calcs.

## Conservative assumptions / ambiguities

- Web \(h/t_w\) approximated as \((d-2t_f)/t_w\) (slightly conservative vs filleted clear distance).
- Plastic PNA-in-steel case uses an approximate force couple when \(a > t_\mathrm{solid}\).
- Deck-brace toggle models continuous lateral brace (\(L_b\to 0\)); no explicit deck attachment stiffness check.
- Rib concrete neglected in transformed \(I\) (solid thickness only) — common simplification.
- \(C_b=1.14\) default for uniform-load simply supported construction LTB.
- Elastic I3.2b concrete stress limit taken as \(0.70f'_c\).

## License

Apache License 2.0 (see `LICENSE`).
