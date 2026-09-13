"""Graphical one-page design summary for the Streamlit Summary tab."""

from __future__ import annotations

from typing import TYPE_CHECKING

from composite_beam.reporting.charts import (
    cross_section_stress_figure,
    cumulative_action_figure,
    interaction_figure,
    moment_display_kNm,
    moment_shear_figures,
    stud_layout_figure,
)
from composite_beam.reporting.section_stress import peak_elastic_stress_MPa
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



def _moment_chart_for_selection(result: "DesignResult", fig_m, default_x: int, L_mm_int: int):
    """Add selectable markers, station cursor, and customdata (x_mm) to the moment figure."""
    import numpy as np
    import plotly.graph_objects as go
    import streamlit as st

    d = result.diagram
    if d is None:
        return fig_m
    M_analysis = d.M_kNmm / 1000.0
    M_display = moment_display_kNm(M_analysis)
    fig_m.data[0].mode = "lines+markers"
    fig_m.data[0].marker = dict(size=8, color="rgba(31,78,121,0.3)")
    # Keep customdata as x_mm (mm) for point selection; analysis sign in hover text
    fig_m.data[0].customdata = np.asarray(d.x_mm)
    hovertext = [
        (
            f"M_display={md:.1f} kN·m<br>"
            f"M_analysis={ma:+.1f} kN·m "
            f"({'sagging' if ma >= 0 else 'hogging'})"
        )
        for ma, md in zip(M_analysis, M_display)
    ]
    fig_m.data[0].text = hovertext
    fig_m.data[0].hovertemplate = (
        "x=%{x:.3f} m<br>%{text}<br>x=%{customdata:.0f} mm"
        "<extra>click to set station</extra>"
    )
    # Ensure plotted y stays on tension-face (display) values
    fig_m.data[0].y = M_display
    x_preview = int(np.clip(st.session_state.get("stress_viewer_x_mm", default_x), 0, L_mm_int))
    M_at_disp = float(np.interp(x_preview, d.x_mm, M_display))
    M_at_an = float(np.interp(x_preview, d.x_mm, M_analysis))
    sag = "sagging" if M_at_an >= 0 else "hogging"
    fig_m.add_vline(x=x_preview / 1000.0, line=dict(color="#e09f3e", width=2, dash="dot"))
    fig_m.add_trace(
        go.Scatter(
            x=[x_preview / 1000.0],
            y=[M_at_disp],
            mode="markers",
            marker=dict(size=12, color="#e09f3e", symbol="diamond"),
            name="station",
            customdata=[[float(x_preview)]],
            hovertemplate=(
                f"x={x_preview:.0f} mm<br>"
                f"M_display={M_at_disp:.1f} kN·m<br>"
                f"M_analysis={M_at_an:+.1f} kN·m ({sag})"
                "<extra>station</extra>"
            ),
        )
    )
    # Legend above chart so station marker / vline never overlaps it
    fig_m.update_layout(
        margin=dict(l=70, r=140, t=70, b=60),
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1.0,
            x=1.02,
            xanchor="left",
            xref="paper",
            yref="paper",
            bgcolor="rgba(255,255,255,0.92)",
        ),
        showlegend=True,
    )
    return fig_m


def _x_mm_from_plotly_selection(event, L_mm_int: int):
    """Extract station x (mm) from st.plotly_chart selection event, or None."""
    if event is None:
        return None
    try:
        sel = getattr(event, "selection", None)
        if sel is None and isinstance(event, dict):
            sel = event.get("selection")
        if sel is None:
            return None
        pts = getattr(sel, "points", None)
        if pts is None and isinstance(sel, dict):
            pts = sel.get("points")
        if not pts:
            return None
        pt = pts[0]
        if not isinstance(pt, dict):
            return None
        x_sel = None
        cd = pt.get("customdata")
        if cd is not None:
            try:
                if hasattr(cd, "__len__") and not isinstance(cd, (str, bytes)):
                    x_sel = float(cd[0])
                else:
                    x_sel = float(cd)
            except Exception:
                x_sel = None
        if x_sel is None and pt.get("x") is not None:
            x_sel = float(pt["x"]) * 1000.0  # chart axis is meters
        if x_sel is None:
            return None
        return int(round(max(0, min(L_mm_int, x_sel))))
    except Exception:
        return None


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
    fig_c = cumulative_action_figure(result)

    L_mm = float(result.inputs_summary.get("L_mm", 0.0) or 0.0)
    L_mm_int = max(1, int(round(L_mm)))
    default_x = int(round(L_mm / 2.0)) if L_mm > 0 else 0
    if result.diagram is not None:
        default_x = int(round(float(result.diagram.M_max_x_mm)))

    r1c1, r1c2 = st.columns(2)
    with r1c1:
        if figs:
            fig_m = _moment_chart_for_selection(result, figs[0], default_x, L_mm_int)
            event = st.plotly_chart(
                fig_m,
                use_container_width=True,
                key="moment_station_select",
                on_select="rerun",
                selection_mode="points",
            )
            st.caption(
                "BMD drawn on the tension face: sagging below baseline, hogging above "
                "(display M = −M_analysis; analysis +sagging / −hogging)."
            )
            x_from_sel = _x_mm_from_plotly_selection(event, L_mm_int)
            if x_from_sel is not None:
                st.session_state.stress_viewer_x_mm = x_from_sel
        else:
            st.caption("Moment diagram unavailable.")
    with r1c2:
        if len(figs) > 1:
            st.plotly_chart(figs[1], use_container_width=True)
        else:
            st.caption("Shear diagram unavailable.")

    # --- Cross-section stress viewer (station from click or scrubber) ---
    st.caption(
        "Click a point on the moment diagram (or scrub x) to view the "
        "cross-section stress distribution."
    )
    st.subheader("Cross-section stress viewer")
    if "stress_viewer_x_mm" not in st.session_state:
        st.session_state.stress_viewer_x_mm = default_x
    # Clamp if span changed
    st.session_state.stress_viewer_x_mm = int(
        max(0, min(L_mm_int, int(st.session_state.stress_viewer_x_mm)))
    )
    x_mm = st.slider(
        "x (mm)",
        min_value=0,
        max_value=L_mm_int,
        step=1,
        key="stress_viewer_x_mm",
        help="Station along the span (whole mm). Synced from moment-diagram point selection.",
    )
    show_plastic = st.checkbox(
        "Show plastic stress blocks (I3.2a schematic)",
        value=False,
        key="stress_viewer_plastic",
        help="Capacity-shape plastic stress blocks at PNA; annotated with M/Mn at this station.",
    )
    if result.diagram is not None and getattr(result, "shape", None) is not None:
        # Fixed stress-axis scale from span peak |σ| (cached once per dashboard render)
        cache_key = "peak_sigma_MPa"
        result_id = id(result)
        if (
            st.session_state.get("_peak_sigma_result_id") != result_id
            or cache_key not in st.session_state
        ):
            st.session_state[cache_key] = peak_elastic_stress_MPa(result)
            st.session_state["_peak_sigma_result_id"] = result_id
        sigma_max = float(st.session_state[cache_key])
        fig_xs = cross_section_stress_figure(
            result,
            float(x_mm),
            show_plastic_blocks=show_plastic,
            sigma_axis_MPa=sigma_max,
        )
        st.plotly_chart(fig_xs, use_container_width=True, key="cross_section_stress")
    else:
        st.caption("Cross-section stress viewer requires a governing diagram and section geometry.")
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
    if fig_c is not None:
        st.plotly_chart(fig_c, use_container_width=True)
        cum = result.cumulative
        st.caption(
            f"Accumulation origins: left = {cum.origin_left_mm/1000:.2f} m, "
            f"right = {cum.origin_right_mm/1000:.2f} m "
            f"(supports or contraflexure). F_req uses moment-proportional "
            f"C·M(x)/M_max toward max +M (AISC I3.2d / I8 detailing). "
            f"Force curves drawn on the tension face (same sense as BMD: "
            f"sagging below baseline). α = ΣQn/C_full. "
            f"Not a substitute for the discrete half-span stud count."
        )
    else:
        st.caption("Cumulative composite-action plot unavailable (no governing diagram).")

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
