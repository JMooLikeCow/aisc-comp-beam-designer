# AISC Comp Beam Designer

Production-oriented **Python + Streamlit** toolkit for **AISC 360** steel–concrete composite beam design, with **ASCE 7** gravity combinations.

Primary units: **SI (kN, mm, kPa, MPa)** with **US customary in brackets** in the UI and reports.

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io)

Deploy on **Streamlit Community Cloud** from this repo: set the main file to `streamlit_app.py` (repo root). Dependencies are in `requirements.txt`. Optional theme lives in `.streamlit/config.toml`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run locally

```bash
streamlit run streamlit_app.py
```

Tabs: **Input** · **Summary** · **Detailed Calculations** (AISC section citations + 360-16 vs 22 / ASCE 7-16 vs 22 flags).

Summary is a one-page graphical results sheet (header, DCR KPI bars, 2×2 diagrams, capacity table, passing shapes) with **Excel** and **HTML** (`aisc_comp_beam_results.html`) download.

## Run tests

```bash
pytest -q
```

P0 acceptance fixtures: (a) full composite compact + solid slab, (b) partial ~50% deck perpendicular, (c) edge beam \(b_\mathrm{eff}\), (d) unshored construction LTB pass/fail, (e) stud \(Q_n\) concrete vs steel governing.

P1 tests: continuous analysis (fixed-fixed / fixed-pinned), Chapter H smoke, welded box properties, punching formula, four-zone stud count.

## Package layout

```
composite_beam/     # typed library
app/streamlit_app.py
streamlit_app.py    # Streamlit Cloud entry (delegates to app/)
data/               # full AISC W-shapes CSV, ComFlor® deck_catalog.json, steel_grades.json
tests/
.streamlit/config.toml
```

## Implemented

| Feature | Status |
|--------|--------|
| Simply supported beam, UDL + point loads | Done (P0) |
| Excel-like **load-case table** (SW/SDL/misc D/L, C, E, W, T, axial) + compact extra points | Done |
| Graphical Summary results sheet + HTML download | Done |
| Fixed-fixed and fixed-pinned continuous analysis; variable end moments; UDL + points | Done (P1) |
| ASCE 7-16 / 7-22 LRFD (+ ASD) gravity + W/E combo **table** (editable factors, Include, ≤5 custom) | Done |
| Construction combos separate from occupancy | Done |
| Full AISC W-shape CSV (~283) + custom I-section + **custom welded box** | Done |
| Steel grades A992 / A572-50 / A36 (thickness-aware Fy) | Done |
| Solid slab / **Tata Steel ComFlor®** deck catalog + manual; Ec ACI / EC2 / NZS stubs | Done |
| \(n=E_s/E_c\) auto + override | Done |
| Effective width AISC I2.1a interior & edge; 16 vs 22 flags; override | Done |
| Full & partial composite; \(\sum Q_n/C\); studs from target ratio or check layout | Done |
| **Four stud-spacing zones** with independent spacing | Done (P1) |
| Stud \(Q_n\) with \(R_g,R_p\), deck orientation, \(d_s\le 2.5 t_f\) (I8) | Done |
| Positive \(M_n\): plastic I3.2a if compact else elastic I3.2b; **both reported** | Done |
| **Negative moment**: steel-only Chapter F (LTB, FLB, WLB); optional residual concrete tension | Done (P1) |
| Section classification Table B4.1b (I-shape and box cases) | Done |
| Unshored construction steel-alone LTB; deck brace toggle (sagging only) | Done |
| **Chapter H** interaction (H1-1a/b) + E3 \(P_n\); Chapter I composite notes | Done (P1) |
| **Slab punching** around studs (ACI 318-19 §22.6) | Done (P1) |
| Serviceability \(\Delta_{LL}=L/360\), \(\Delta_{tot}=L/240\); \(I_\mathrm{eff}\); shored vs unshored | Done |
| Camber manual + 80% DL suggestion; warn if >100% DL Δ | Done |
| Design check DCRs + up to 10 passing W shapes lightest→heaviest | Done |
| **Excel export** from Summary (openpyxl) | Done (P1) |
| **HTML results sheet** (`aisc_comp_beam_results.html`) | Done |
| **Graphics**: M/V diagrams, H interaction, stud layout (plotly) | Done (P1) |

## Data sources

- **W-shapes:** AISC Shapes Database v15.0 CSV extract ([ambaker1/aisc-csv](https://github.com/ambaker1/aisc-csv)); see `data/README.md`.
- **Deck catalog:** Tata Steel **ComFlor®** composite floor decking range (overview / technical manual).

## Limitations (honest — not hidden)

- **No cantilevers.**
- **Hogging is steel-only Chapter F by default.** AISC I3 plastic/elastic composite PNA is implemented for *positive* flexure only. A full I3 negative-flexure PNA (longitudinal slab reinforcement, rebar PNA) is **not** implemented. The optional “residual concrete tension” toggle adds a stud-limited cracked-slab couple and is **not** a substitute for I3 hogging provisions — see detailed notes.
- **Chapter I composite beam-columns (I2 / I5 / I6)** are not designed. Chapter H is applied to steel \(\phi_c P_n\) (E3) and the available flexural strengths already computed. Conservative for incidental axial in a floor beam.
- **Punching** uses ACI 318-19/318M two-way shear around the stud (not an AISC I8 check). Thin solid thicknesses often fail vs a ¾ in stud \(Q_n\) — that is intentional, not a code skip.
- Continuous-span deflections use M/EI integration of the elastic diagram (FEM end moments). Patterned live load / settlement / support flexibility are not modeled; override end moments if you have a frame analysis.
- Floor vibration, fire, and full lateral (W/E) combination detailing remain out of scope.
- Passing-shape search still keys on flexure + construction + deflection (P0). Punching / H / hogging are reported on the selected section.

## Out of scope

- Cantilevers
- Floor vibration
- Fire design
- AISC I3 hogging PNA with slab rebar
- Encased/filled composite beam-columns (I2, I5, I6)

## Engineering rules locked in code

1. \(\phi M_n\) plastic **I3.2a only when compact**; else elastic **I3.2b** — both always reported.
2. Partial \(\sum Q_n/C\) reduces \(M_n\) and uses \(I_\mathrm{eff}\) (Eq. I3-1), not full \(I\).
3. Effective width interior vs edge per **I2.1a**.
4. Stud \(Q_n\) with \(R_g/R_p\), deck orientation, I8 diameter limit.
5. Unshored construction: steel-alone **Chapter F LTB**. Deck brace applies to *sagging* (top flange) only.
6. Hogging: steel **Chapter F** (bottom flange in compression). No full-composite hogging PNA without I3 rebar provisions.
7. Construction vs service deflection paths separated.
8. Construction load combinations ≠ occupancy combinations in tests/reporting.
9. AISC 360-16 vs 360-22 and ASCE 7-16 vs 7-22 edition flags surfaced in detailed calcs. H1, E3, F2–F7, I3.2, I8 formulas used here are numerically the same across those two AISC editions.
10. Combined axial + flexure: **H1-1a / H1-1b** on steel available strengths.

## Conservative assumptions / ambiguities

- Web \(h/t_w\) approximated as \((d-2t_f)/t_w\) (slightly conservative vs filleted clear distance).
- Plastic PNA-in-steel case uses an approximate force couple when \(a > t_\mathrm{solid}\).
- Deck-brace toggle models continuous lateral brace (\(L_b\to 0\)) of the *top* flange; no explicit deck attachment stiffness check.
- Rib concrete neglected in transformed \(I\) (solid thickness only) — common simplification.
- \(C_b=1.14\) default for uniform-load simply supported construction LTB; continuous spans use F1-1 from the diagram or 1.0.
- Elastic I3.2b concrete stress limit taken as \(0.70f'_c\).
- Welded-box \(J\) is Bredt (closed); \(C_w \approx 0\). Box LTB uses **F7.4**.
- Residual hogging tension cap: \(\min(n_\mathrm{hog} Q_n,\; 0.10 A_s F_y,\; 0.10\sqrt{f'_c}\,A_c)\).
- Punching \(d\) = solid thickness; group perimeter engaged when \(s < 4d\).

## License

Apache License 2.0 (see `LICENSE`).
