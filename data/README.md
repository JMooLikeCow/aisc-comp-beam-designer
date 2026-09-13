# Data files

## `w_shapes.csv`

Wide-flange (W) shapes filtered from the **AISC Shapes Database v15.0** CSV extract
published at [ambaker1/aisc-csv](https://github.com/ambaker1/aisc-csv)
(`v15.0/Shapes-US.csv` + `v15.0/Shapes-SI.csv`, row-aligned).

- **Filter:** `Type == W` only (~283 current Manual W-shapes).
- **US properties** come from `Shapes-US.csv` (in, in², in³, in⁴, in⁶, lb/ft).
- **`designation_metric`** is the AISC SI dual label from `Shapes-SI.csv`
  (e.g. `W18X35` → `W460X52`). Soft conversion is not used when the SI file provides a label.
- Schema matches `composite_beam.sections.w_shapes.WShapeDatabase` /
  `shape_from_row`.

Not affiliated with or endorsed by AISC; redistributed for engineering software use
consistent with the publicly available AISC shapes database.

## `deck_catalog.json`

**Tata Steel ComFlor®** composite floor deck product range (Building Systems UK),
plus a solid-slab option and a manual/custom override entry.

Primary citation: [ComFlor® range overview](https://www.tatasteeluk.com/construction/products/flooring/comflor/metal-composite-floor-decking-range-overview)
and the ComFlor® technical manual.

Fields are SI-first (`hr_mm`, `wr_mm`, `cover_width_mm`, `pitch_mm`, `gauges_mm`).
`wr_mm` is an approximate average rib/trough width for AISC §I8 Rg/Rp context —
confirm against the manufacturer drawing for final design.

## `steel_grades.json`

ASTM structural steel grade Fy/Fu data used by the materials module.
