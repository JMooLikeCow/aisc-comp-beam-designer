"""Text/HTML summary and detailed calculation reporting."""

from __future__ import annotations

from typing import TYPE_CHECKING

from composite_beam.units import format_dual, knm_to_kipft, mm_to_in, kn_to_kip, mpa_to_ksi

if TYPE_CHECKING:
    from composite_beam.design_engine import DesignResult


def summary_lines(result: "DesignResult") -> list[str]:
    r = result
    lines = [
        "=== COMPOSITE BEAM DESIGN SUMMARY ===",
        f"Section: {r.inputs_summary.get('shape')}",
        f"Span: {format_dual(r.inputs_summary['L_mm'], 'mm', mm_to_in(r.inputs_summary['L_mm']), 'in', 0)}",
        f"beff: {format_dual(r.beff.beff_mm, 'mm', mm_to_in(r.beff.beff_mm), 'in', 1)} ({r.beff.location.value})",
        f"n = {r.n:.2f}",
        f"Composite: {'FULL' if r.shear.is_full else f'PARTIAL ({r.shear.ratio*100:.0f}%)'}",
        f"ΣQn/C = {r.shear.ratio:.3f}; studs each side of max M = {r.shear.n_studs_provided}",
        f"Classification: {r.classification.overall.value}",
        f"Mn plastic (I3.2a): {format_dual(r.positive_moment.Mn_plastic_kNm, 'kN·m', knm_to_kipft(r.positive_moment.Mn_plastic_kNm), 'kip·ft')}",
        f"Mn elastic (I3.2b): {format_dual(r.positive_moment.Mn_elastic_kNm, 'kN·m', knm_to_kipft(r.positive_moment.Mn_elastic_kNm), 'kip·ft')}",
        f"Design method: {r.positive_moment.used_method}",
        f"φMn: {format_dual(r.positive_moment.phiMn_kNm, 'kN·m', knm_to_kipft(r.positive_moment.phiMn_kNm), 'kip·ft')}",
        f"Mu: {format_dual(r.Mu_kNm, 'kN·m', knm_to_kipft(r.Mu_kNm), 'kip·ft')}  DCR={r.DCR_flexure:.3f} {'PASS' if r.pass_flexure else 'FAIL'}",
    ]
    if r.construction_LTB:
        lines.append(
            f"Construction φMn: {r.construction_LTB.phiMn_kNm:.1f} kN·m; "
            f"Mu,c={r.Mu_construction_kNm:.1f}; DCR={r.construction_LTB.DCR:.3f} "
            f"{'PASS' if r.pass_construction else 'FAIL'}"
        )
    lines += [
        f"ΔLL={r.deflection.delta_LL_mm:.1f} mm (limit {r.deflection.delta_LL_limit_mm:.1f}) "
        f"{'OK' if r.deflection.LL_OK else 'NG'}",
        f"Δtotal={r.deflection.delta_total_mm:.1f} mm (limit {r.deflection.delta_total_limit_mm:.1f}) "
        f"{'OK' if r.deflection.total_OK else 'NG'}",
        f"Camber: {r.deflection.camber_mm:.1f} mm (suggest {r.deflection.camber_suggested_mm:.1f})"
        + (" ⚠ >100% DL Δ" if r.deflection.camber_warn else ""),
        f"OVERALL: {'PASS' if r.overall_pass else 'FAIL'}",
    ]
    if r.passing_shapes:
        lines.append("--- Passing W-shapes (lightest→heaviest, up to 10) ---")
        for p in r.passing_shapes:
            lines.append(
                f"  {p.designation} ({p.W_lb_ft:.0f} plf): DCR_flex={p.DCR_flexure:.3f}, "
                f"DCR_constr={p.DCR_construction:.3f}"
            )
    return lines


def detailed_lines(result: "DesignResult") -> list[str]:
    lines = ["=== DETAILED CALCULATIONS (AISC citations) ==="]
    lines.extend(result.edition_flags)
    lines.append("")
    for n in result.detailed_notes:
        lines.append(f"• {n}")
    return lines
