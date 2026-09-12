"""Plotly figures for the Summary tab: M/V diagrams, H interaction, stud layout."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from composite_beam.design_engine import DesignResult


def _go():
    import plotly.graph_objects as go
    return go


def moment_shear_figures(result: "DesignResult") -> list:
    """Moment and shear diagrams for the governing occupancy combination."""
    go = _go()
    figs = []
    d = result.diagram
    if d is None:
        return figs
    x_m = d.x_mm / 1000.0
    figs.append(
        go.Figure(
            data=[
                go.Scatter(
                    x=x_m,
                    y=d.M_kNmm / 1000.0,
                    mode="lines",
                    name="M",
                    fill="tozeroy",
                    line=dict(color="#1f4e79", width=2),
                )
            ],
            layout=go.Layout(
                title="Bending moment (governing occupancy combo)",
                xaxis_title="x (m) [ft]",
                yaxis_title="M (kN·m) [kip·ft]  +sagging / −hogging",
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
        M = result.diagram.M_kNmm / 1000.0
        mmax = max(abs(float(M.max())), 1.0)
        fig.add_trace(
            go.Scatter(
                x=result.diagram.x_mm / 1000.0,
                y=(M / mmax) * 0.8 - 1.2,
                mode="lines",
                name="M (scaled)",
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
