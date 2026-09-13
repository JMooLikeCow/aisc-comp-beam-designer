"""One-page HTML graphical results sheet for a DesignResult."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING, Optional

from composite_beam.reporting.summary import summary_lines
from composite_beam.units import (
    dual_force_kN,
    dual_length_mm,
    dual_moment_kNm,
)

if TYPE_CHECKING:
    from composite_beam.design_engine import DesignResult

_KG_M_PER_PLF = 1.4881639437


def _dcr_color(dcr: float) -> str:
    if dcr > 1.0 + 1e-9:
        return "#c0392b"
    if dcr >= 0.85:
        return "#d68910"
    return "#1e8449"


def _badge(ok: bool) -> str:
    if ok:
        return '<span class="badge pass">PASS</span>'
    return '<span class="badge fail">FAIL</span>'


def _bar(dcr: float) -> str:
    pct = max(0.0, min(dcr * 100.0, 100.0))
    color = _dcr_color(dcr)
    label = "∞" if dcr == float("inf") else f"{dcr:.3f}"
    return (
        f'<div class="bar-wrap"><div class="bar" style="width:{pct:.1f}%;'
        f'background:{color}"></div></div>'
        f'<div class="bar-label" style="color:{color}">{label}</div>'
    )


def _kpi_cards(result: "DesignResult") -> str:
    cards = [
        ("Flexure +", result.DCR_flexure, result.pass_flexure),
        (
            "Construction",
            result.construction_LTB.DCR if result.construction_LTB else 0.0,
            result.pass_construction,
        ),
        (
            "Deflection",
            (
                max(
                    result.deflection.delta_LL_mm / result.deflection.delta_LL_limit_mm
                    if result.deflection.delta_LL_limit_mm
                    else 0.0,
                    result.deflection.delta_total_mm / result.deflection.delta_total_limit_mm
                    if result.deflection.delta_total_limit_mm
                    else 0.0,
                )
            ),
            result.pass_deflection,
        ),
        ("Hogging −", result.DCR_neg, result.pass_neg),
        (
            "Ch. H",
            result.interaction.DCR if result.interaction is not None else 0.0,
            result.pass_interaction,
        ),
        (
            "Punching",
            result.punching.DCR if result.punching is not None else 0.0,
            result.pass_punching,
        ),
    ]
    parts = []
    for title, dcr, ok in cards:
        parts.append(
            "<div class='kpi'>"
            f"<div class='kpi-title'>{escape(title)} {_badge(ok)}</div>"
            f"{_bar(float(dcr) if dcr == dcr else 0.0)}"
            "</div>"
        )
    return "<div class='kpi-row'>" + "".join(parts) + "</div>"


def _capacity_rows(result: "DesignResult") -> list[tuple[str, str, str, str, bool]]:
    rows: list[tuple[str, str, str, str, bool]] = [
        (
            "Positive flexure I3  φMn+ / Mu+",
            dual_moment_kNm(result.Mu_kNm),
            dual_moment_kNm(result.positive_moment.phiMn_kNm),
            f"{result.DCR_flexure:.3f}",
            result.pass_flexure,
        )
    ]
    if result.negative_moment is not None:
        rows.append(
            (
                "Negative flexure Ch.F  φMn− / |Mu−|",
                dual_moment_kNm(abs(result.Mu_neg_kNm)),
                dual_moment_kNm(result.negative_moment.phiMn_kNm),
                f"{result.negative_moment.DCR:.3f}",
                result.negative_moment.passes,
            )
        )
    if result.construction_LTB is not None:
        rows.append(
            (
                "Construction LTB F2",
                dual_moment_kNm(result.Mu_construction_kNm),
                dual_moment_kNm(result.construction_LTB.phiMn_kNm),
                f"{result.construction_LTB.DCR:.3f}",
                result.pass_construction,
            )
        )
    rows.append(
        (
            "Shear demand Vu (Chapter G φVn not checked)",
            dual_force_kN(result.Vu_kN),
            "—",
            "—",
            True,
        )
    )
    rows.append(
        (
            "Live deflection ΔLL",
            dual_length_mm(result.deflection.delta_LL_mm, precision=1),
            dual_length_mm(result.deflection.delta_LL_limit_mm, precision=1),
            (
                f"{result.deflection.delta_LL_mm / result.deflection.delta_LL_limit_mm:.3f}"
                if result.deflection.delta_LL_limit_mm
                else "—"
            ),
            result.deflection.LL_OK,
        )
    )
    rows.append(
        (
            "Total deflection Δtot",
            dual_length_mm(result.deflection.delta_total_mm, precision=1),
            dual_length_mm(result.deflection.delta_total_limit_mm, precision=1),
            (
                f"{result.deflection.delta_total_mm / result.deflection.delta_total_limit_mm:.3f}"
                if result.deflection.delta_total_limit_mm
                else "—"
            ),
            result.deflection.total_OK,
        )
    )
    rows.append(
        (
            "Shear connection ΣQn / C  (studs each side of max M)",
            f"{result.shear.ratio * 100:.0f}%",
            f"{result.shear.n_studs_provided} studs",
            f"{result.shear.ratio:.3f}",
            True,
        )
    )
    if result.interaction is not None:
        rows.append(
            (
                f"Chapter H {result.interaction.equation}",
                dual_force_kN(result.interaction.Pr_kN),
                dual_force_kN(result.interaction.Pc_kN),
                f"{result.interaction.DCR:.3f}",
                result.interaction.passes,
            )
        )
    if result.punching is not None:
        rows.append(
            (
                "Slab punching ACI 22.6",
                dual_force_kN(result.punching.Vu_kN),
                dual_force_kN(result.punching.phiVc_kN),
                f"{result.punching.DCR:.3f}",
                result.punching.passes,
            )
        )
    return rows


def _table(headers: list[str], rows: list[list[str]], row_ok: Optional[list[bool]] = None) -> str:
    th = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = []
    for i, r in enumerate(rows):
        cls = ""
        if row_ok is not None and i < len(row_ok) and not row_ok[i]:
            cls = " class='fail-row'"
        tds = "".join(f"<td>{c}</td>" for c in r)
        body.append(f"<tr{cls}>{tds}</tr>")
    return f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _plotly_divs(result: "DesignResult") -> str:
    try:
        from composite_beam.reporting.charts import (
            interaction_figure,
            moment_shear_figures,
            stud_layout_figure,
        )
    except Exception:  # pragma: no cover
        return ""
    figs = []
    figs.extend(moment_shear_figures(result))
    h = interaction_figure(result)
    if h is not None:
        figs.append(h)
    s = stud_layout_figure(result)
    if s is not None:
        figs.append(s)
    if not figs:
        return "<p class='muted'>No diagrams (run a design first).</p>"
    chunks = []
    for i, fig in enumerate(figs):
        fig.update_layout(height=320, margin=dict(l=50, r=20, t=40, b=40))
        chunks.append(
            fig.to_html(
                full_html=False,
                include_plotlyjs=(True if i == 0 else False),
                config={"displayModeBar": False},
            )
        )
    return "<div class='charts'>" + "".join(f"<div class='chart'>{c}</div>" for c in chunks) + "</div>"


def result_to_html(
    result: "DesignResult",
    project_label: str = "",
    *,
    include_charts: bool = True,
) -> str:
    """Return a self-contained one-page HTML results sheet."""
    s = result.inputs_summary
    label = project_label or s.get("project_label") or "Composite beam"
    shape = s.get("shape", "—")
    span = dual_length_mm(float(s.get("L_mm", 0.0)))
    method = s.get("method", "LRFD")
    aisc = s.get("aisc_edition", "AISC360-22")
    asce = s.get("asce_edition", "ASCE7-22")
    overall = "PASS" if result.overall_pass else "FAIL"
    overall_cls = "pass" if result.overall_pass else "fail"

    cap_rows = _capacity_rows(result)
    cap_html = _table(
        ["Check", "Demand (SI [US])", "Capacity (SI [US])", "DCR", "Status"],
        [
            [
                escape(n),
                escape(d),
                escape(c),
                escape(r),
                "PASS" if ok else "FAIL",
            ]
            for n, d, c, r, ok in cap_rows
        ],
        [ok for *_rest, ok in cap_rows],
    )

    pass_html = ""
    if result.passing_shapes:
        pass_html = "<h2>Passing W-shapes (lightest → heaviest)</h2>" + _table(
            ["Shape", "W (kg/m) [plf]", "φMn+", "DCR flex", "DCR constr", "LL OK"],
            [
                [
                    escape(p.display_name or p.designation),
                    f"{p.W_lb_ft * _KG_M_PER_PLF:.1f} [{p.W_lb_ft:.0f}]",
                    escape(dual_moment_kNm(p.phiMn_kNm)),
                    f"{p.DCR_flexure:.3f}",
                    f"{p.DCR_construction:.3f}",
                    "OK" if p.LL_OK else "NG",
                ]
                for p in result.passing_shapes
            ],
        )

    charts = _plotly_divs(result) if include_charts else ""
    notes = "".join(f"<li>{escape(line)}</li>" for line in summary_lines(result)[:8])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>AISC Comp Beam — {escape(str(label))}</title>
<style>
  :root {{ --navy:#1f4e79; --line:#d5d8dc; --bg:#f7f9fb; }}
  body {{ font-family: "Segoe UI", Helvetica, Arial, sans-serif; margin: 24px;
         color:#1b1b1b; background:#fff; }}
  .header {{ display:flex; justify-content:space-between; align-items:center;
             background:var(--navy); color:#fff; padding:18px 22px; border-radius:8px; }}
  .header h1 {{ margin:0; font-size:20px; }}
  .header .meta {{ opacity:0.9; font-size:13px; margin-top:4px; }}
  .badge {{ display:inline-block; padding:3px 10px; border-radius:4px; font-weight:700;
            font-size:12px; letter-spacing:0.04em; }}
  .badge.pass, .overall.pass {{ background:#1e8449; color:#fff; }}
  .badge.fail, .overall.fail {{ background:#c0392b; color:#fff; }}
  .overall {{ font-size:22px; font-weight:800; padding:8px 18px; border-radius:6px; }}
  .kpi-row {{ display:flex; flex-wrap:wrap; gap:10px; margin:18px 0; }}
  .kpi {{ flex:1 1 140px; border:1px solid var(--line); border-radius:8px;
          padding:10px 12px; background:var(--bg); }}
  .kpi-title {{ font-size:12px; color:#555; display:flex; justify-content:space-between; }}
  .bar-wrap {{ height:8px; background:#e5e8eb; border-radius:4px; margin:8px 0 4px; }}
  .bar {{ height:8px; border-radius:4px; }}
  .bar-label {{ font-size:18px; font-weight:700; }}
  h2 {{ color:var(--navy); font-size:16px; margin:22px 0 8px; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; }}
  th, td {{ border:1px solid var(--line); padding:6px 8px; text-align:left; }}
  th {{ background:var(--navy); color:#fff; }}
  tr.fail-row td {{ background:#fdecea; }}
  .charts {{ display:flex; flex-wrap:wrap; gap:8px; }}
  .chart {{ flex:1 1 420px; min-width:320px; }}
  .muted {{ color:#777; font-size:13px; }}
  footer {{ margin-top:28px; font-size:11px; color:#777; }}
  @media print {{ body {{ margin:12px; }} .chart {{ break-inside:avoid; }} }}
</style>
</head>
<body>
  <div class="header">
    <div>
      <h1>{escape(str(label))}</h1>
      <div class="meta">{escape(str(shape))} · Span {escape(span)}</div>
      <div class="meta">{escape(str(method))} · {escape(str(aisc))} · {escape(str(asce))}</div>
    </div>
    <div class="overall {overall_cls}">{overall}</div>
  </div>
  {_kpi_cards(result)}
  <h2>Diagrams</h2>
  {charts}
  <h2>Capacity vs demand</h2>
  {cap_html}
  {pass_html}
  <h2>Headline notes</h2>
  <ul>{notes}</ul>
  <footer>AISC Comp Beam Designer — one-page results sheet. SI primary; US customary in brackets.
  Vu is demand only (no Chapter G φVn). E/W envelope only when those factors and loads are present.</footer>
</body>
</html>
"""


def result_to_html_bytes(result: "DesignResult", project_label: str = "") -> bytes:
    return result_to_html(result, project_label=project_label).encode("utf-8")
