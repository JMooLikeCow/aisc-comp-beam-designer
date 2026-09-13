"""Plotly figures for the Summary tab: M/V, H interaction, studs, cumulative action."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from composite_beam.design_engine import DesignResult


def _go():
    import plotly.graph_objects as go
    return go


def moment_display_kNm(M_analysis_kNm):
    """
    Structural convention: draw the BMD on the tension face.

    Analysis sign: +sagging / −hogging. Display = −M_analysis so sagging
    (tension at bottom) appears below the baseline and hogging (tension at top)
    appears above.
    """
    import numpy as np

    return -np.asarray(M_analysis_kNm, dtype=float)


def moment_shear_figures(result: "DesignResult") -> list:
    """Moment and shear diagrams for the governing occupancy combination."""
    go = _go()
    figs = []
    d = result.diagram
    if d is None:
        return figs
    x_m = d.x_mm / 1000.0
    M_analysis = d.M_kNmm / 1000.0  # kN·m, +sagging / −hogging
    M_display = moment_display_kNm(M_analysis)
    hovertext = [
        (
            f"M_display={md:.1f} kN·m<br>"
            f"M_analysis={ma:+.1f} kN·m "
            f"({'sagging' if ma >= 0 else 'hogging'})"
        )
        for ma, md in zip(M_analysis, M_display)
    ]
    figs.append(
        go.Figure(
            data=[
                go.Scatter(
                    x=x_m,
                    y=M_display,
                    mode="lines",
                    name="M (tension face)",
                    fill="tozeroy",
                    line=dict(color="#1f4e79", width=2),
                    customdata=d.x_mm,
                    text=hovertext,
                    hovertemplate=(
                        "x=%{x:.3f} m<br>%{text}<br>x=%{customdata:.0f} mm"
                        "<extra></extra>"
                    ),
                )
            ],
            layout=go.Layout(
                title="Bending moment (governing occupancy combo) — drawn on tension face",
                xaxis_title="x (m) [ft]",
                yaxis_title="M (kN·m) [kip·ft] — drawn on tension face (sagging ↓)",
                template="plotly_white",
                height=320,
                margin=dict(l=50, r=20, t=40, b=40),
            ),
        )
    )
    figs.append(
        go.Figure(
            data=[
                go.Scatter(
                    x=x_m,
                    y=d.V_kN,
                    mode="lines",
                    name="V",
                    fill="tozeroy",
                    line=dict(color="#c0392b", width=2),
                )
            ],
            layout=go.Layout(
                title="Shear (governing occupancy combo)",
                xaxis_title="x (m)",
                yaxis_title="V (kN) [kip]",
                template="plotly_white",
                height=320,
                margin=dict(l=50, r=20, t=40, b=40),
            ),
        )
    )
    return figs


def interaction_figure(result: "DesignResult"):
    """Demand point vs AISC H1 interaction curve in (Pr/Pc, Mr/Mc) space."""
    go = _go()
    inter = result.interaction
    if inter is None:
        return None
    # H1-1b: P/2 + M = 1 → M = 1 − P/2 for P<0.2
    # H1-1a: P + 8/9 M = 1 → M = (9/8)(1−P) for P≥0.2
    ps = [i / 100.0 for i in range(0, 101)]
    ms = []
    for p in ps:
        if p < 0.2:
            ms.append(max(0.0, 1.0 - p / 2.0))
        else:
            ms.append(max(0.0, (9.0 / 8.0) * (1.0 - p)))
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=ps, y=ms, mode="lines", name="H1 capacity", line=dict(color="#1f4e79", width=2))
    )
    fig.add_trace(
        go.Scatter(
            x=[inter.ratio_P],
            y=[inter.ratio_Mx + inter.ratio_My],
            mode="markers",
            name="Demand",
            marker=dict(size=12, color="#c0392b", symbol="x"),
        )
    )
    fig.update_layout(
        title=f"Chapter H interaction ({inter.equation}, DCR={inter.DCR:.3f})",
        xaxis_title="Pr / Pc",
        yaxis_title="Mr / Mc  (x + y)",
        template="plotly_white",
        height=340,
        xaxis=dict(range=[0, 1.05]),
        yaxis=dict(range=[0, 1.15]),
        margin=dict(l=50, r=20, t=40, b=40),
    )
    return fig


def stud_layout_figure(result: "DesignResult"):
    """Stud positions along the beam, colored by zone, with moment overlay."""
    go = _go()
    layout = result.stud_layout
    if layout is None or not layout.positions:
        return None
    fig = go.Figure()
    colors = ["#1f4e79", "#2e86ab", "#e09f3e", "#c0392b"]
    zone_names = []
    for z in layout.zones:
        if z.name not in zone_names:
            zone_names.append(z.name)
    color_of = {n: colors[i % 4] for i, n in enumerate(zone_names)}
    for zname in zone_names:
        xs = [p.x_mm / 1000.0 for p in layout.positions if p.zone_name == zname]
        ys = [p.row for p in layout.positions if p.zone_name == zname]
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="markers",
                name=zname,
                marker=dict(size=9, color=color_of[zname], symbol="diamond"),
            )
        )
    if result.diagram is not None:
        M_analysis = result.diagram.M_kNmm / 1000.0
        M_disp = moment_display_kNm(M_analysis)
        mmax = max(abs(float(M_disp.max())), abs(float(M_disp.min())), 1.0)
        fig.add_trace(
            go.Scatter(
                x=result.diagram.x_mm / 1000.0,
                y=(M_disp / mmax) * 0.8 - 1.2,
                mode="lines",
                name="M (scaled, tension face)",
                line=dict(color="#888", width=1, dash="dot"),
            )
        )
    fig.update_layout(
        title=f"Stud layout ({layout.n_total} studs)",
        xaxis_title="x (m)",
        yaxis_title="row  /  scaled M (kN·m) [kip·ft]",
        template="plotly_white",
        height=320,
        margin=dict(l=50, r=20, t=40, b=40),
    )
    return fig


def cumulative_action_figure(result: "DesignResult"):
    """Provided ΣQn vs required cumulative force along the span (dual-unit axes)."""
    go = _go()
    cum = getattr(result, "cumulative", None)
    if cum is None or len(cum.x_mm) == 0:
        return None

    x_m = cum.x_mm / 1000.0
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_m,
            y=cum.F_req_kN,
            mode="lines",
            name="F_req (moment-prop.)",
            line=dict(color="#c0392b", width=2, dash="dash"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_m,
            y=cum.SumQn_prov_kN,
            mode="lines",
            name="ΣQn provided",
            line=dict(color="#1f4e79", width=2.5),
            fill="tozeroy",
            fillcolor="rgba(31,78,121,0.12)",
        )
    )
    # C_full reference
    fig.add_hline(
        y=cum.C_full_kN,
        line=dict(color="#888", width=1, dash="dot"),
        annotation_text=f"C_full = {cum.C_full_kN:.0f} kN",
        annotation_position="top left",
    )
    # Mark max-M
    fig.add_vline(
        x=cum.x_maxM_mm / 1000.0,
        line=dict(color="#e09f3e", width=1, dash="dot"),
        annotation_text="max +M",
        annotation_position="top",
    )

    fig.update_layout(
        title=(
            "Cumulative composite action — ΣQn provided vs F_req along span "
            "(AISC I3.2d / I8 detailing)"
        ),
        xaxis_title="x (m) [ft]",
        yaxis_title="Force (kN) [kip]",
        template="plotly_white",
        height=380,
        margin=dict(l=50, r=20, t=50, b=70),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    fig.add_annotation(
        text=(
            f"Origins: left={cum.origin_left_mm/1000:.2f} m, "
            f"right={cum.origin_right_mm/1000:.2f} m · "
            "F_req = C·M(x)/M_max from nearer origin · "
            "not a substitute for half-span stud count"
        ),
        xref="paper",
        yref="paper",
        x=0.0,
        y=-0.22,
        showarrow=False,
        font=dict(size=11, color="#555"),
        align="left",
    )
    fig.update_traces(
        hovertemplate="x=%{x:.3f} m<br>F=%{y:.1f} kN<extra>%{fullData.name}</extra>"
    )
    return fig


def cross_section_stress_figure(
    result: "DesignResult",
    x_mm: float,
    *,
    show_plastic_blocks: bool = False,
    sigma_axis_MPa: float | None = None,
):
    """
    Side-by-side cross-section outline + elastic stress distribution at station x.

    Left: slab (gray) + W-shape (blue) to scale (beff may be width-capped).
    Right: material stress vs depth (compression red/orange, tension blue).
    Optional dual panel / overlay of I3.2a plastic stress blocks when toggled.
    """
    import numpy as np
    from plotly.subplots import make_subplots

    from composite_beam.reporting.section_stress import (
        elastic_stress_profile,
        peak_elastic_stress_MPa,
        plastic_block_schematic,
        section_geometry_for_plot,
    )

    go = _go()
    try:
        geom = section_geometry_for_plot(result)
        prof = elastic_stress_profile(result, x_mm)
    except Exception as exc:  # pragma: no cover
        fig = go.Figure()
        fig.update_layout(
            title=f"Cross-section stress unavailable: {exc}",
            template="plotly_white",
            height=400,
        )
        return fig

    if sigma_axis_MPa is None:
        sigma_axis_MPa = peak_elastic_stress_MPa(result)
    sigma_lim = float(sigma_axis_MPa) * 1.05  # 5% pad; fixed while scrubbing x
    if sigma_lim <= 0:
        sigma_lim = 1.0

    shape = geom["shape"]
    t = geom["t_solid_mm"]
    hr = geom["hr_mm"]
    d = geom["d_mm"]
    bf = geom["bf_mm"]
    tf = geom["tf_mm"]
    tw = geom["tw_mm"]
    beff_p = geom["beff_plot_mm"]
    total_h = geom["total_depth_mm"]

    n_cols = 2 if not show_plastic_blocks else 3
    titles = ["Cross-section", "Elastic stress (I3.2b)"]
    if show_plastic_blocks:
        titles.append("Plastic blocks (I3.2a)")

    fig = make_subplots(
        rows=1,
        cols=n_cols,
        shared_yaxes=True,
        subplot_titles=titles,
        horizontal_spacing=0.08,
        column_widths=[0.34, 0.33, 0.33][:n_cols],
    )

    # --- Left: section outline (x = horizontal centerline at 0) ---
    # Slab rectangle
    slab_x = [-beff_p / 2, beff_p / 2, beff_p / 2, -beff_p / 2, -beff_p / 2]
    slab_y = [0, 0, t, t, 0]
    fig.add_trace(
        go.Scatter(
            x=slab_x,
            y=slab_y,
            fill="toself",
            fillcolor="rgba(160,160,160,0.55)",
            line=dict(color="#555", width=1.5),
            name="Concrete slab",
            hoverinfo="skip",
            showlegend=True,
        ),
        row=1,
        col=1,
    )
    # Optional deck haunch schematic (narrower band)
    if hr > 0.5:
        hx = [-bf / 2, bf / 2, bf / 2, -bf / 2, -bf / 2]
        hy = [t, t, t + hr, t + hr, t]
        fig.add_trace(
            go.Scatter(
                x=hx,
                y=hy,
                fill="toself",
                fillcolor="rgba(180,180,180,0.35)",
                line=dict(color="#777", width=1, dash="dot"),
                name="Deck haunch",
                hoverinfo="skip",
                showlegend=True,
            ),
            row=1,
            col=1,
        )

    # Steel W: top flange, web, bottom flange (y from top of slab)
    y_top_fl = t + hr
    y_bot_fl_top = y_top_fl + d - tf
    y_bot = y_top_fl + d

    def _rect(x0, x1, y0, y1, name, showleg=False):
        return go.Scatter(
            x=[x0, x1, x1, x0, x0],
            y=[y0, y0, y1, y1, y0],
            fill="toself",
            fillcolor="rgba(31,78,121,0.85)",
            line=dict(color="#1f4e79", width=1),
            name=name,
            hoverinfo="skip",
            showlegend=showleg,
        )

    fig.add_trace(_rect(-bf / 2, bf / 2, y_top_fl, y_top_fl + tf, "Steel W", True), row=1, col=1)
    fig.add_trace(_rect(-tw / 2, tw / 2, y_top_fl + tf, y_bot_fl_top, "web", False), row=1, col=1)
    fig.add_trace(_rect(-bf / 2, bf / 2, y_bot_fl_top, y_bot, "bf", False), row=1, col=1)

    # NA line on section
    fig.add_trace(
        go.Scatter(
            x=[-beff_p / 2 * 1.05, beff_p / 2 * 1.05],
            y=[prof.y_NA_from_top_mm, prof.y_NA_from_top_mm],
            mode="lines",
            line=dict(color="#e09f3e", width=1.5, dash="dash"),
            name="NA",
            showlegend=True,
        ),
        row=1,
        col=1,
    )

    # --- Right: elastic stress diagram ---
    y = prof.y_from_top_mm
    s = prof.sigma_material_MPa
    # Split compression / tension for coloring
    s_comp = np.where(s < 0, s, 0.0)
    s_tens = np.where(s > 0, s, 0.0)
    fig.add_trace(
        go.Scatter(
            x=s_comp,
            y=y,
            fill="tozerox",
            fillcolor="rgba(231,76,60,0.35)",
            line=dict(color="#e74c3c", width=2),
            name="Compression",
            hovertemplate="y=%{y:.1f} mm<br>σ=%{x:.2f} MPa<extra>comp</extra>",
        ),
        row=1,
        col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=s_tens,
            y=y,
            fill="tozerox",
            fillcolor="rgba(41,128,185,0.35)",
            line=dict(color="#2980b9", width=2),
            name="Tension",
            hovertemplate="y=%{y:.1f} mm<br>σ=%{x:.2f} MPa<extra>tens</extra>",
        ),
        row=1,
        col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=[0, 0],
            y=[0, total_h],
            mode="lines",
            line=dict(color="#333", width=1),
            showlegend=False,
            hoverinfo="skip",
        ),
        row=1,
        col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=[-sigma_lim, sigma_lim],
            y=[prof.y_NA_from_top_mm, prof.y_NA_from_top_mm],
            mode="lines",
            line=dict(color="#e09f3e", width=1.5, dash="dash"),
            showlegend=False,
            hoverinfo="skip",
        ),
        row=1,
        col=2,
    )

    # Annotations for key stresses
    fig.add_annotation(
        x=prof.sigma_c_top_MPa,
        y=0,
        text=f"σc,top={prof.sigma_c_top_MPa:.2f} MPa",
        showarrow=True,
        arrowhead=2,
        ax=40,
        ay=-20,
        xref="x2",
        yref="y2",
        font=dict(size=11),
    )
    fig.add_annotation(
        x=prof.sigma_s_bot_MPa,
        y=total_h,
        text=f"σs,bot={prof.sigma_s_bot_MPa:.2f} MPa",
        showarrow=True,
        arrowhead=2,
        ax=40,
        ay=20,
        xref="x2",
        yref="y2",
        font=dict(size=11),
    )

    # --- Optional plastic blocks panel ---
    if show_plastic_blocks:
        plas = plastic_block_schematic(result, x_mm)
        # Capacity schematic stresses: concrete −0.85fc over depth a; steel +Fy below PNA
        fc_block = -0.85 * geom["slab"].fc_MPa
        Fy = geom["Fy_MPa"]
        if plas.available and not prof.hogging:
            a = min(plas.a_mm, t) if plas.a_mm > 0 else 0.0
            # Concrete block
            fig.add_trace(
                go.Scatter(
                    x=[0, fc_block, fc_block, 0, 0],
                    y=[0, 0, a, a, 0],
                    fill="toself",
                    fillcolor="rgba(230,126,34,0.55)",
                    line=dict(color="#e67e22", width=1.5),
                    name="0.85f'c block",
                    hovertemplate="0.85f'c<br>a=%{y:.1f} mm<extra></extra>",
                ),
                row=1,
                col=3,
            )
            # Steel tension (entire steel in tension when PNA in slab)
            fig.add_trace(
                go.Scatter(
                    x=[0, Fy, Fy, 0, 0],
                    y=[y_top_fl, y_top_fl, y_bot, y_bot, y_top_fl],
                    fill="toself",
                    fillcolor="rgba(41,128,185,0.45)",
                    line=dict(color="#2980b9", width=1.5),
                    name="Fy (steel)",
                    hovertemplate="Fy<extra></extra>",
                ),
                row=1,
                col=3,
            )
            fig.add_annotation(
                text=f"M/Mn,pl={plas.M_over_Mn:.3f}<br>a={plas.a_mm:.1f} mm",
                xref="x3 domain",
                yref="y3 domain",
                x=0.5,
                y=1.08,
                showarrow=False,
                font=dict(size=11),
            )
        else:
            fig.add_annotation(
                text=plas.notes[0] if plas.notes else "Plastic blocks N/A",
                xref="x3 domain",
                yref="y3 domain",
                x=0.5,
                y=0.5,
                showarrow=False,
                font=dict(size=12, color="#777"),
            )

    # Axis: y from top, increasing downward
    fig.update_yaxes(
        title_text="y from top (mm) [in]",
        range=[total_h * 1.02, -total_h * 0.02],
        row=1,
        col=1,
    )
    fig.update_yaxes(range=[total_h * 1.02, -total_h * 0.02], row=1, col=2)
    if show_plastic_blocks:
        fig.update_yaxes(range=[total_h * 1.02, -total_h * 0.02], row=1, col=3)
        fig.update_xaxes(title_text="σ (MPa) [ksi]", row=1, col=3, zeroline=True)

    fig.update_xaxes(title_text="Width (mm) [in]", row=1, col=1, zeroline=True)
    fig.update_xaxes(
        title_text="σ (MPa) [ksi]  −comp / +tens",
        row=1,
        col=2,
        zeroline=True,
        range=[-sigma_lim, sigma_lim],
    )
    if show_plastic_blocks:
        fig.update_xaxes(range=[-sigma_lim, sigma_lim], row=1, col=3)

    # Annotate fixed σ_max used for the axis scale
    fig.add_annotation(
        text=f"σ_max = {float(sigma_axis_MPa):.2f} MPa (span peak, fixed scale)",
        xref="x2 domain",
        yref="y2 domain",
        x=0.5,
        y=-0.14,
        showarrow=False,
        font=dict(size=11, color="#555"),
    )

    hog_note = " · HOGGING (steel-only)" if prof.hogging else ""
    beff_note = (
        f"beff={prof.beff_mm:.0f} mm"
        + (f" (plot {prof.beff_plot_mm:.0f} mm)" if abs(prof.beff_mm - prof.beff_plot_mm) > 1 else "")
    )
    fig.update_layout(
        title=(
            f"Cross-section stress at x={prof.x_mm:.0f} mm "
            f"({prof.x_mm/1000:.3f} m) · M(x)={prof.M_kNm:.1f} kN·m{hog_note}<br>"
            f"<sup>{beff_note} · NA={prof.y_NA_from_top_mm:.1f} mm from top · "
            f"I_tr={prof.I_tr_mm4:.3e} mm⁴</sup>"
        ),
        template="plotly_white",
        height=480,
        margin=dict(l=50, r=30, t=80, b=70),
        legend=dict(orientation="h", yanchor="bottom", y=-0.18, x=0),
    )
    return fig
