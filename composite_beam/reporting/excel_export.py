"""Excel workbook export of a DesignResult (openpyxl)."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from composite_beam.design_engine import DesignResult


def result_to_xlsx_bytes(result: "DesignResult") -> bytes:
    """Build a multi-sheet .xlsx workbook and return its bytes."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    from composite_beam.reporting.summary import detailed_lines, summary_lines

    wb = Workbook()
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1F4E79")
    wrap = Alignment(wrap_text=True, vertical="top")

    def _header(ws, headers: list[str]) -> None:
        for col, h in enumerate(headers, start=1):
            cell = ws.cell(1, col, h)
            cell.font = header_font
            cell.fill = header_fill

    # --- Summary ---
    ws = wb.active
    ws.title = "Summary"
    _header(ws, ["Item", "Value"])
    for i, line in enumerate(summary_lines(result), start=2):
        if ": " in line and not line.startswith("=") and not line.startswith("---"):
            k, _, v = line.partition(": ")
            ws.cell(i, 1, k.strip())
            ws.cell(i, 2, v.strip())
        else:
            ws.cell(i, 1, line)
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 72

    # --- Checks ---
    ws2 = wb.create_sheet("Checks")
    _header(ws2, ["Check", "Demand", "Capacity", "DCR", "Pass"])
    rows = [
        (
            "Positive flexure I3",
            result.Mu_kNm,
            result.positive_moment.phiMn_kNm,
            result.DCR_flexure,
            result.pass_flexure,
        ),
    ]
    if result.negative_moment is not None:
        rows.append(
            (
                "Negative flexure Ch.F",
                abs(result.Mu_neg_kNm),
                result.negative_moment.phiMn_kNm,
                result.negative_moment.DCR,
                result.negative_moment.passes,
            )
        )
    if result.construction_LTB is not None:
        rows.append(
            (
                "Construction LTB F2",
                result.Mu_construction_kNm,
                result.construction_LTB.phiMn_kNm,
                result.construction_LTB.DCR,
                result.pass_construction,
            )
        )
    if result.interaction is not None:
        rows.append(
            (
                f"Ch.H {result.interaction.equation}",
                result.interaction.Pr_kN,
                result.interaction.Pc_kN,
                result.interaction.DCR,
                result.interaction.passes,
            )
        )
    if result.punching is not None:
        rows.append(
            (
                "Slab punching (ACI 22.6)",
                result.punching.Vu_kN,
                result.punching.phiVc_kN,
                result.punching.DCR,
                result.punching.passes,
            )
        )
    rows.append(
        (
            "Live deflection",
            result.deflection.delta_LL_mm,
            result.deflection.delta_LL_limit_mm,
            result.deflection.delta_LL_mm / result.deflection.delta_LL_limit_mm
            if result.deflection.delta_LL_limit_mm
            else 0.0,
            result.deflection.LL_OK,
        )
    )
    for i, (chk, dem, cap, dcr, ok) in enumerate(rows, start=2):
        ws2.cell(i, 1, chk)
        ws2.cell(i, 2, round(float(dem), 3))
        ws2.cell(i, 3, round(float(cap), 3))
        ws2.cell(i, 4, round(float(dcr), 3) if dcr != float("inf") else "inf")
        ws2.cell(i, 5, "PASS" if ok else "FAIL")
    for col, w in zip("ABCDE", (28, 14, 14, 10, 10)):
        ws2.column_dimensions[col].width = w

    # --- Detailed ---
    ws3 = wb.create_sheet("Detailed")
    _header(ws3, ["Calculation note"])
    for i, line in enumerate(detailed_lines(result), start=2):
        c = ws3.cell(i, 1, line)
        c.alignment = wrap
    ws3.column_dimensions["A"].width = 120

    # --- Diagram ---
    ws4 = wb.create_sheet("Diagram")
    _header(ws4, ["x_mm", "V_kN", "M_kNm"])
    if result.diagram is not None:
        x = result.diagram.x_mm
        V = result.diagram.V_kN
        M = result.diagram.M_kNmm / 1000.0
        for i, (xi, vi, mi) in enumerate(zip(x, V, M), start=2):
            ws4.cell(i, 1, float(xi))
            ws4.cell(i, 2, float(vi))
            ws4.cell(i, 3, float(mi))

    # --- Studs ---
    ws5 = wb.create_sheet("Studs")
    _header(ws5, ["x_mm", "zone", "row"])
    if result.stud_layout is not None:
        for i, p in enumerate(result.stud_layout.positions, start=2):
            ws5.cell(i, 1, p.x_mm)
            ws5.cell(i, 2, p.zone_name)
            ws5.cell(i, 3, p.row)

    # --- Passing shapes ---
    ws6 = wb.create_sheet("PassingShapes")
    _header(ws6, ["Shape", "plf", "phiMn_kNm", "DCR_flex", "DCR_constr", "LL_OK"])
    for i, p in enumerate(result.passing_shapes, start=2):
        ws6.cell(i, 1, p.designation)
        ws6.cell(i, 2, p.W_lb_ft)
        ws6.cell(i, 3, round(p.phiMn_kNm, 2))
        ws6.cell(i, 4, round(p.DCR_flexure, 3))
        ws6.cell(i, 5, round(p.DCR_construction, 3))
        ws6.cell(i, 6, p.LL_OK)

    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()
