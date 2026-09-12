"""Text/HTML summary and detailed calculation reporting."""

from __future__ import annotations

from typing import TYPE_CHECKING

from composite_beam.units import (
    dual_force_kN,
    dual_length_mm,
    dual_moment_kNm,
)

if TYPE_CHECKING:
    from composite_beam.design_engine import DesignResult

# lb/ft → kg/m
_KG_M_PER_PLF = 1.4881639437


def summary_lines(result: "DesignResult") -> list[str]:
    r = result
    lines = [
        "=== COMPOSITE BEAM DESIGN SUMMARY ===",
        f"Section: {r.inputs_summary.get('shape')}",
        f"Span: {dual_length_mm(r.inputs_summary['L_mm'])}",
        f"Supports: {r.inputs_summary.get('support', 'simply_supported')}",
        f"beff: {dual_length_mm(r.beff.beff_mm, precision=1)} ({r.beff.location.value})",
        f"n = {r.n:.2f}",
        f"Composite: {'FULL' if r.shear.is_full else f'PARTIAL ({r.shear.ratio*100:.0f}%)'}",
        f"ΣQn/C = {r.shear.ratio:.3f}; studs each side of max M = {r.shear.n_studs_provided}",
    ]
    if r.stud_layout is not None:
        lines.append(
            f"Four-zone studs: total {r.stud_layout.n_total}; "
            f"left of max M {r.stud_layout.n_left_of_max_M}"
        )
    lines += [
        f"Classification: {r.classification.overall.value}",
        f"Mn plastic (I3.2a): {dual_moment_kNm(r.positive_moment.Mn_plastic_kNm)}",
        f"Mn elastic (I3.2b): {dual_moment_kNm(r.positive_moment.Mn_elastic_kNm)}",
        f"Design method: {r.positive_moment.used_method}",
        f"φMn+: {dual_moment_kNm(r.positive_moment.phiMn_kNm)}",
        f"Mu+: {dual_moment_kNm(r.Mu_kNm)}  DCR={r.DCR_flexure:.3f} "
        f"{'PASS' if r.pass_flexure else 'FAIL'}",
    ]
    if r.negative_moment is not None:
        lines.append(
            f"φMn− (Ch.F steel): {dual_moment_kNm(r.negative_moment.phiMn_kNm)}; "
            f"|Mu−|={dual_moment_kNm(abs(r.Mu_neg_kNm))}; DCR={r.negative_moment.DCR:.3f} "
            f"{'PASS' if r.negative_moment.passes else 'FAIL'}"
            + (" + residual concrete T" if r.negative_moment.used_residual_concrete else "")
        )
    if r.construction_LTB:
        lines.append(
            f"Construction φMn: {dual_moment_kNm(r.construction_LTB.phiMn_kNm)}; "
            f"Mu,c={dual_moment_kNm(r.Mu_construction_kNm)}; DCR={r.construction_LTB.DCR:.3f} "
            f"{'PASS' if r.pass_construction else 'FAIL'}"
        )
    if r.interaction is not None:
        lines.append(
            f"Ch.H {r.interaction.equation}: DCR={r.interaction.DCR:.3f} "
            f"{'PASS' if r.interaction.passes else 'FAIL'} "
            f"(Pr/Pc={r.interaction.ratio_P:.3f}, Mr/Mc={r.interaction.ratio_Mx:.3f}; "
            f"Pr={dual_force_kN(r.interaction.Pr_kN)})"
        )
    if r.punching is not None:
        lines.append(
            f"Punching φVc={dual_force_kN(r.punching.phiVc_kN)}; "
            f"Vu={dual_force_kN(r.punching.Vu_kN)}; "
            f"DCR={r.punching.DCR:.3f} {'PASS' if r.punching.passes else 'FAIL'}"
        )
    lines += [
        f"ΔLL={dual_length_mm(r.deflection.delta_LL_mm, precision=1)} "
        f"(limit {dual_length_mm(r.deflection.delta_LL_limit_mm, precision=1)}) "
        f"{'OK' if r.deflection.LL_OK else 'NG'}",
        f"Δtotal={dual_length_mm(r.deflection.delta_total_mm, precision=1)} "
        f"(limit {dual_length_mm(r.deflection.delta_total_limit_mm, precision=1)}) "
        f"{'OK' if r.deflection.total_OK else 'NG'}",
        f"Camber: {dual_length_mm(r.deflection.camber_mm, precision=1)} "
        f"(suggest {dual_length_mm(r.deflection.camber_suggested_mm, precision=1)})"
        + (" ⚠ >100% DL Δ" if r.deflection.camber_warn else ""),
        f"OVERALL: {'PASS' if r.overall_pass else 'FAIL'}",
    ]
    if r.passing_shapes:
        lines.append("--- Passing W-shapes (lightest→heaviest, up to 10) ---")
        for p in r.passing_shapes:
            kg_m = p.W_lb_ft * _KG_M_PER_PLF
            lines.append(
                f"  {(p.display_name or p.designation)} ({kg_m:.1f} kg/m [{p.W_lb_ft:.0f} plf]): "
                f"DCR_flex={p.DCR_flexure:.3f}, DCR_constr={p.DCR_construction:.3f}"
            )
    return lines


def detailed_lines(result: "DesignResult") -> list[str]:
    lines = ["=== DETAILED CALCULATIONS (AISC citations) ==="]
    lines.extend(result.edition_flags)
    lines.append("")
    for n in result.detailed_notes:
        lines.append(f"• {n}")
    return lines
