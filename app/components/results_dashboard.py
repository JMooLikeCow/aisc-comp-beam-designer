"""Graphical one-page design summary for the Streamlit Summary tab."""

from __future__ import annotations

from typing import TYPE_CHECKING

from composite_beam.reporting.charts import (
    interaction_figure,
    moment_shear_figures,
    stud_layout_figure,
)
from composite_beam.reporting.excel_export import result_to_xlsx_bytes
from composite_beam.reporting.html_report import result_to_html_bytes
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


def _header_html(result: "DesignResult", project_label: str) -> str:
    s = result.inputs_summary
    label = project_label or s.get("project_label") or "Composite beam"
    shape = s.get("shape", "—")
    span = dual_length_mm(float(s.get("L_mm", 0.0)))
    method = s.get("method", "LRFD")
    aisc = s.get("aisc_edition", "")
    asce = s.get("asce_edition", "")
    support = s.get("support", "")
    overall = "PASS" if result.overall_pass else "FAIL"
    bg = "#1e8449" if result.overall_pass else "#c0392b"
    return f"""
    <div style="display:flex;justify-content:space-between;align-items:center;
                background:#1f4e79;color:#fff;padding:16px 20px;border-radius:8px;
                margin-bottom:12px;">
      <div>
        <div style="font-size:12px;opacity:0.8;letter-spacing:0.06em;">PROJECT / BEAM</div>
        <div style="font-size:20px;font-weight:700;">{label}</div>
        <div style="font-size:14px;margin-top:4px;">{shape} · {span}</div>
        <div style="font-size:12px;opacity:0.9;">{method} · {aisc} · {asce} · {support}</div>
      </div>
      <div style="background:{bg};padding:10px 22px;border-radius:6px;
                  font-size:22px;font-weight:800;letter-spacing:0.06em;">{overall}</div>
    </div>
    """


def _kpi_html(title: str, dcr: float, ok: bool) -> str:
    color = _dcr_color(dcr)
    pct = max(0.0, min(dcr * 100.0, 100.0))
    label = "∞" if dcr == float("inf") else f"{dcr:.3f}"
    badge = "PASS" if ok else "FAIL"
    badge_bg = "#1e8449" if ok else "#c0392b"
    return f"""
    <div style="border:1px solid #d5d8dc;border-radius:8px;padding:10px 12px;background:#f7f9fb;">
      <div style="display:flex;justify-content:space-between;font-size:12px;color:#555;">
        <span>{title}</span>
        <span style="background:{badge_bg};color:#fff;padding:1px 8px;border-radius:4px;
                     font-weight:700;font-size:11px;">{badge}</span>
      </div>
      <div style="height:8px;background:#e5e8eb;border-radius:4px;margin:8px 0 4px;">
        <div style="width:{pct:.1f}%;height:8px;background:{color};border-radius:4px;"></div>
      </div>
      <div style="font-size:20px;font-weight:700;color:{color};">{label}</div>
    </div>
    """


def _defl_dcr(result: "DesignResult") -> float:
    d = result.deflection
    vals = []
    if d.delta_LL_limit_mm:
        vals.append(d.delta_LL_mm / d.delta_LL_limit_mm)
    if d.delta_total_limit_mm:
        vals.append(d.delta_total_mm / d.delta_total_limit_mm)
    return max(vals) if vals else 0.0


def _capacity_records(result: "DesignResult") -> list[dict]:
    rows = [
        {
            "Check": "Positive flexure I3  φMn+ / Mu+",
            "Demand": dual_moment_kNm(result.Mu_kNm),
            "Capacity": dual_moment_kNm(result.positive_moment.phiMn_kNm),
            "DCR": round(result.DCR_flexure, 3),
            "Status": "PASS" if result.pass_flexure else "FAIL",
        }
    ]
    if result.negative_moment is not None:
        rows.append(
            {
                "Check": "Negative flexure Ch.F  φMn− / |Mu−|",
                "Demand": dual_moment_kNm(abs(result.Mu_neg_kNm)),
                "Capacity": dual_moment_kNm(result.negative_moment.phiMn_kNm),
                "DCR": round(result.negative_moment.DCR, 3),
                "Status": "PASS" if result.negative_moment.passes else "FAIL",
            }
        )
    if result.construction_LTB is not None:
        rows.append(
            {
                "Check": "Construction LTB F2",
                "Demand": dual_moment_kNm(result.Mu_construction_kNm),
                "Capacity": dual_moment_kNm(result.construction_LTB.phiMn_kNm),
                "DCR": round(result.construction_LTB.DCR, 3),
                "Status": "PASS" if result.pass_construction else "FAIL",
            }
        )
    rows.append(
        {
            "Check": "Shear demand Vu (Ch. G φVn not checked)",
            "Demand": dual_force_kN(result.Vu_kN),
            "Capacity": "—",
            "DCR": "—",
            "Status": "note",
        }
    )
    d = result.deflection
    ll_dcr = d.delta_LL_mm / d.delta_LL_limit_mm if d.delta_LL_limit_mm else 0.0
    tot_dcr = d.delta_total_mm / d.delta_total_limit_mm if d.delta_total_limit_mm else 0.0
    rows.append(
        {
            "Check": "Live deflection ΔLL",
            "Demand": dual_length_mm(d.delta_LL_mm, precision=1),
            "Capacity": dual_length_mm(d.delta_LL_limit_mm, precision=1),
            "DCR": round(ll_dcr, 3),
            "Status": "PASS" if d.LL_OK else "FAIL",
        }
    )
    rows.append(
        {
            "Check": "Total deflection Δtot",
            "Demand": dual_length_mm(d.delta_total_mm, precision=1),
            "Capacity": dual_length_mm(d.delta_total_limit_mm, precision=1),
            "DCR": round(tot_dcr, 3),
            "Status": "PASS" if d.total_OK else "FAIL",
        }
    )
    rows.append(
        {
            "Check": "Shear connection (studs each side of max M)",
            "Demand": f"{result.shear.ratio * 100:.0f}% composite",
            "Capacity": f"{result.shear.n_studs_provided} studs",
            "DCR": round(result.shear.ratio, 3),
            "Status": "FULL" if result.shear.is_full else "PARTIAL",
        }
    )
    if result.interaction is not None:
        rows.append(
            {
                "Check": f"Chapter H {result.interaction.equation}",
                "Demand": dual_force_kN(result.interaction.Pr_kN),
                "Capacity": dual_force_kN(result.interaction.Pc_kN),
                "DCR": round(result.interaction.DCR, 3),
                "Status": "PASS" if result.interaction.passes else "FAIL",
            }
        )
    if result.punching is not None:
        rows.append(
            {
                "Check": "Slab punching ACI 22.6",
                "Demand": dual_force_kN(result.punching.Vu_kN),
                "Capacity": dual_force_kN(result.punching.phiVc_kN),
                "DCR": round(result.punching.DCR, 3),
                "Status": "PASS" if result.punching.passes else "FAIL",
            }
        )
    return rows


def render_results_dashboard(
    result: "DesignResult",
    project_label: str = "",
) -> None:
    """Render the graphical Summary tab (header, KPIs, plots, tables, downloads)."""
    import streamlit as st

    st.markdown(_header_html(result, project_label), unsafe_allow_html=True)

    kpis = [
        ("Flexure +", result.DCR_flexure, result.pass_flexure),
        (
            "Construction",
            result.construction_LTB.DCR if result.construction_LTB else 0.0,
            result.pass_construction,
        ),
        ("Deflection", _defl_dcr(result), result.pass_deflection),
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
    cols = st.columns(len(kpis))
    for col, (title, dcr, ok) in zip(cols, kpis):
        with col:
            st.markdown(_kpi_html(title, float(dcr), ok), unsafe_allow_html=True)

    st.subheader("Diagrams")
    figs = moment_shear_figures(result)
    fig_h = interaction_figure(result)
    fig_s = stud_layout_figure(result)
    r1c1, r1c2 = st.columns(2)
    with r1c1:
        if figs:
            st.plotly_chart(figs[0], use_container_width=True)
        else:
            st.caption("Moment diagram unavailable.")
    with r1c2:
        if len(figs) > 1:
            st.plotly_chart(figs[1], use_container_width=True)
        else:
            st.caption("Shear diagram unavailable.")
    r2c1, r2c2 = st.columns(2)
    with r2c1:
        if fig_h is not None:
            st.plotly_chart(fig_h, use_container_width=True)
        else:
            st.caption("Chapter H interaction appears when Pr ≠ 0.")
    with r2c2:
        if fig_s is not None:
            st.plotly_chart(fig_s, use_container_width=True)
        else:
            st.caption("Enable four-zone stud spacing on Input to plot the stud layout.")

    st.subheader("Capacity vs demand  (SI [US])")
    st.dataframe(_capacity_records(result), use_container_width=True, hide_index=True)

    if result.passing_shapes:
        st.subheader("Passing W-shapes (lightest → heaviest, metric-first names)")
        st.dataframe(
            [
                {
                    "Shape": p.display_name or p.designation,
                    "W (kg/m) [plf]": f"{p.W_lb_ft * _KG_M_PER_PLF:.1f} [{p.W_lb_ft:.0f}]",
                    "φMn+": dual_moment_kNm(p.phiMn_kNm),
                    "DCR_flex": round(p.DCR_flexure, 3),
                    "DCR_constr": round(p.DCR_construction, 3),
                    "LL_OK": p.LL_OK,
                }
                for p in result.passing_shapes
            ],
            use_container_width=True,
            hide_index=True,
        )

    dl1, dl2 = st.columns(2)
    with dl1:
        try:
            xls = result_to_xlsx_bytes(result)
            st.download_button(
                "Download Excel report",
                data=xls,
                file_name="aisc_comp_beam_design.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except Exception as exc:  # pragma: no cover
            st.warning(f"Excel export unavailable: {exc}")
    with dl2:
        try:
            html = result_to_html_bytes(result, project_label=project_label)
            st.download_button(
                "Download results sheet (HTML)",
                data=html,
                file_name="aisc_comp_beam_results.html",
                mime="text/html",
            )
        except Exception as exc:  # pragma: no cover
            st.warning(f"HTML results sheet unavailable: {exc}")
