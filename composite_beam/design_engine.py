"""Design engine: orchestrate composite beam checks and section search."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional

from composite_beam.analysis.continuous import (
    SupportType,
    analyze_span,
    cb_from_segment,
    midspan_deflection_from_moment_mm,
)
from composite_beam.analysis.simple_beam import BeamDiagram
from composite_beam.combinations.asce7 import (
    ASCEEdition,
    Combination,
    CombinationSet,
    edition_flags,
)
from composite_beam.composite.effective_width import (
    AISCEdition,
    BeamLocation,
    EffectiveWidthResult,
    effective_width,
)
from composite_beam.composite.punching import PunchingResult, punching_with_group
from composite_beam.composite.cumulative_action import (
    CumulativeCompositeResult,
    cumulative_composite_action,
)
from composite_beam.composite.shear_connection import ShearConnectionResult, shear_connection
from composite_beam.composite.slab import DeckOrientation, SlabConfig
from composite_beam.composite.stud_layout import StudLayoutResult, StudZone, layout_studs
from composite_beam.composite.studs import StudConfig, StudQnResult, stud_Qn
from composite_beam.loads.load_cases import PointLoad
from composite_beam.materials.concrete import ConcreteMaterial, modular_ratio
from composite_beam.materials.steel import SteelMaterial
from composite_beam.sections.classification import ClassificationResult, classify_flexure
from composite_beam.sections.w_shapes import WShape, WShapeDatabase
from composite_beam.serviceability.deflection import (
    DeflectionLimits,
    DeflectionResult,
    compute_deflections,
)
from composite_beam.strength.interaction import (
    InteractionResult,
    chapter_h_interaction,
    compressive_strength_E3,
)
from composite_beam.strength.ltb import LTBResult, construction_LTB
from composite_beam.strength.negative_moment import NegativeMomentResult, negative_flexural_strength
from composite_beam.strength.positive_moment import PositiveMomentResult, positive_flexural_strength
from composite_beam.units import ES_MPA


@dataclass
class DesignInputs:
    """All inputs for a composite beam design (simply supported or continuous)."""

    L_mm: float
    shape: WShape
    steel: SteelMaterial
    concrete: ConcreteMaterial
    slab: SlabConfig
    location: BeamLocation = BeamLocation.INTERIOR
    spacing_left_mm: float = 3000.0
    spacing_right_mm: float = 3000.0
    beff_override_mm: Optional[float] = None
    aisc_edition: AISCEdition = AISCEdition.AISC360_22
    asce_edition: ASCEEdition = ASCEEdition.ASCE7_22
    stud: StudConfig = field(default_factory=StudConfig)
    n_studs_half_span: Optional[int] = None
    target_composite_ratio: Optional[float] = None
    n_override: Optional[float] = None
    # Loads (service / nominal)
    w_SDL_kNpm: float = 0.0
    w_LL_kNpm: float = 0.0
    w_construction_kNpm: float = 0.0  # construction live on wet slab
    points_LL: list[PointLoad] = field(default_factory=list)
    points_DL: list[PointLoad] = field(default_factory=list)
    points_C: list[PointLoad] = field(default_factory=list)
    points_W: list[PointLoad] = field(default_factory=list)
    points_E: list[PointLoad] = field(default_factory=list)
    w_W_kNpm: float = 0.0
    w_E_kNpm: float = 0.0
    include_beam_self_weight: bool = True
    include_slab_self_weight: bool = True
    slab_trib_width_mm: Optional[float] = None  # for slab SW; default beff
    shored: bool = False
    deck_braces_construction: bool = False
    Lb_construction_mm: Optional[float] = None  # default = full span
    camber_mm: float = 0.0
    deflection_limits: DeflectionLimits = field(default_factory=DeflectionLimits)
    method: str = "LRFD"  # LRFD or ASD
    phi_b: float = 0.90
    Omega_b: float = 1.67
    custom_combinations: list[Combination] = field(default_factory=list)
    n_studs_per_rib: int = 1
    # --- P1 ---
    support: SupportType = SupportType.SIMPLY_SUPPORTED
    M_left_override_kNm: Optional[float] = None
    M_right_override_kNm: Optional[float] = None
    Pu_kN: float = 0.0
    K_factor: float = 1.0
    Lb_neg_mm: Optional[float] = None
    include_residual_concrete_tension: bool = False
    stud_zones: Optional[list[StudZone]] = None
    phi_c: float = 0.90
    # UI table overrides (None = use CombinationSet built-ins)
    occupancy_combinations: Optional[list[Combination]] = None
    construction_combinations_override: Optional[list[Combination]] = None
    project_label: str = ""


@dataclass
class PassingShape:
    designation: str
    W_lb_ft: float
    phiMn_kNm: float
    DCR_flexure: float
    DCR_construction: float
    LL_OK: bool
    display_name: str = ""


@dataclass
class DesignResult:
    """Full design output for reporting and UI."""

    inputs_summary: dict
    beff: EffectiveWidthResult
    n: float
    classification: ClassificationResult
    stud_qn: StudQnResult
    shear: ShearConnectionResult
    positive_moment: PositiveMomentResult
    Mu_kNm: float
    Vu_kN: float
    DCR_flexure: float
    construction_LTB: Optional[LTBResult]
    Mu_construction_kNm: float
    deflection: DeflectionResult
    combination_notes: list[str]
    edition_flags: list[str]
    pass_flexure: bool
    pass_construction: bool
    pass_deflection: bool
    overall_pass: bool
    detailed_notes: list[str]
    passing_shapes: list[PassingShape] = field(default_factory=list)
    diagram: Optional[BeamDiagram] = None
    negative_moment: Optional[NegativeMomentResult] = None
    Mu_neg_kNm: float = 0.0
    DCR_neg: float = 0.0
    pass_neg: bool = True
    interaction: Optional[InteractionResult] = None
    pass_interaction: bool = True
    stud_layout: Optional[StudLayoutResult] = None
    punching: Optional[PunchingResult] = None
    pass_punching: bool = True
    cumulative: Optional[CumulativeCompositeResult] = None


def _slab_self_weight_kNpm(slab: SlabConfig, trib_mm: float, density_kNm3: float) -> float:
    """Uniform load from slab self-weight on trib width."""
    t_m = (slab.t_solid_mm + 0.5 * slab.hr_mm) / 1000.0  # approx average thickness
    if slab.orientation == DeckOrientation.NONE:
        t_m = slab.t_solid_mm / 1000.0
    trib_m = trib_mm / 1000.0
    return density_kNm3 * t_m * trib_m


def _phi(inp: DesignInputs) -> float:
    return inp.phi_b if inp.method.upper() == "LRFD" else 1.0 / inp.Omega_b


def _analyze(
    inp: DesignInputs,
    w_kNpm: float,
    points: list[PointLoad],
) -> BeamDiagram:
    return analyze_span(
        inp.L_mm,
        w_kNpm,
        points,
        support=inp.support,
        M_left_override_kNm=inp.M_left_override_kNm,
        M_right_override_kNm=inp.M_right_override_kNm,
    )


def _scaled_points(points: list[PointLoad], factor: float) -> list[PointLoad]:
    if not factor:
        return []
    return [
        PointLoad(
            P_kN=p.P_kN * factor,
            location=p.location,
            spec=p.spec,
            axial_kN=p.axial_kN * factor,
            label=p.label,
        )
        for p in points
    ]


def _factored_analysis(
    inp: DesignInputs,
    w_D_kNpm: float,
    w_L_kNpm: float,
    w_C_kNpm: float,
    points_L: list[PointLoad],
    combo: Combination,
    *,
    points_D: Optional[list[PointLoad]] = None,
    points_C: Optional[list[PointLoad]] = None,
    apply_lateral: bool = True,
) -> BeamDiagram:
    """Apply combination factors to D, L, C (and W/E if present); return the span diagram."""
    w = (
        combo.factor("D") * w_D_kNpm
        + combo.factor("L") * w_L_kNpm
        + combo.factor("C") * w_C_kNpm
    )
    if apply_lateral:
        w += combo.factor("W") * inp.w_W_kNpm
        w += combo.factor("E") * inp.w_E_kNpm
    pts: list[PointLoad] = []
    pts.extend(_scaled_points(points_L, combo.factor("L")))
    pts.extend(_scaled_points(points_D or [], combo.factor("D")))
    pts.extend(_scaled_points(points_C or [], combo.factor("C")))
    if apply_lateral:
        pts.extend(_scaled_points(inp.points_W, combo.factor("W")))
        pts.extend(_scaled_points(inp.points_E, combo.factor("E")))
    return _analyze(inp, w, pts)


class DesignEngine:
    """Run composite beam design for a selected section and optional search."""

    def __init__(self, db: Optional[WShapeDatabase] = None) -> None:
        self.db = db or WShapeDatabase()

    def design(self, inp: DesignInputs, search_passing: bool = True) -> DesignResult:
        notes: list[str] = []
        flags = edition_flags(inp.asce_edition)
        flags.append(f"Locked AISC edition: {inp.aisc_edition.value}")
        flags.append(
            "FLAG AISC 360-16 vs 360-22: I2.1a beff, I3.2a/b flexure, I8 studs, "
            "F2–F7, E3, and H1 equations used here are numerically the same; "
            "360-22 cleaned up I2.1a edge-beam wording and Chapter I user notes."
        )
        if inp.support != SupportType.SIMPLY_SUPPORTED:
            flags.append(
                f"Support: {inp.support.value} (elastic FEM end moments; "
                "overrides applied if provided). Cantilevers are out of scope."
            )

        beff_res = effective_width(
            inp.L_mm,
            inp.spacing_left_mm,
            inp.spacing_right_mm,
            inp.location,
            inp.aisc_edition,
            inp.beff_override_mm,
        )
        slab = SlabConfig(
            t_solid_mm=inp.slab.t_solid_mm,
            hr_mm=inp.slab.hr_mm,
            wr_mm=inp.slab.wr_mm,
            orientation=inp.slab.orientation,
            fc_MPa=inp.concrete.fc_MPa,
            beff_mm=beff_res.beff_mm,
            catalog_key=inp.slab.catalog_key,
            weight_kNpm2=inp.slab.weight_kNpm2,
        )

        n = modular_ratio(inp.steel.Es_MPa, inp.concrete.Ec_MPa, inp.n_override)
        notes.append(f"n = Es/Ec = {n:.2f}" + (" (override)" if inp.n_override else " (auto)"))

        classification = classify_flexure(inp.shape, inp.steel.Fy_MPa, inp.steel.Es_MPa)

        stud_qn = stud_Qn(
            inp.stud, slab, inp.shape.tf_mm, inp.concrete.Ec_MPa, inp.n_studs_per_rib
        )

        # Dead load assembly (needed for analysis before shear if we want Mmax location)
        trib = inp.slab_trib_width_mm or beff_res.beff_mm
        w_slab = (
            _slab_self_weight_kNpm(slab, trib, inp.concrete.density_kNm3)
            if inp.include_slab_self_weight
            else 0.0
        )
        w_beam = inp.shape.W_kNm if inp.include_beam_self_weight else 0.0
        w_D_wet = w_slab + w_beam
        w_D_service_super = inp.w_SDL_kNpm
        w_D_total = w_D_wet + w_D_service_super
        w_L = inp.w_LL_kNpm
        w_C = inp.w_construction_kNpm
        phi = _phi(inp)

        # Occupancy envelopes
        if inp.occupancy_combinations is not None:
            occupancy_combos = list(inp.occupancy_combinations)
        else:
            occupancy_combos = CombinationSet(
                edition=inp.asce_edition,
                method=inp.method,
                include_construction=False,
                custom=inp.custom_combinations[:5],
            ).all()
        Mu = 0.0
        Mu_neg = 0.0
        Vu = 0.0
        gov_diag: Optional[BeamDiagram] = None
        combo_notes = []
        for combo in occupancy_combos:
            if combo.factor("C") and not (combo.factor("L") or combo.factor("D")):
                continue
            diag = _factored_analysis(
                inp,
                w_D_total,
                w_L,
                0.0,
                inp.points_LL,
                combo,
                points_D=inp.points_DL,
            )
            combo_notes.append(
                f"{combo.name}: Mu+={diag.M_max_kNm:.2f} kN·m, "
                f"Mu−={diag.M_min_kNm:.2f} kN·m, Vu={diag.V_max_kN:.2f} kN"
            )
            if diag.M_max_kNm > Mu:
                Mu, Vu = diag.M_max_kNm, diag.V_max_kN
                gov_diag = diag
            if diag.M_min_kNm < Mu_neg:
                Mu_neg = diag.M_min_kNm
                if gov_diag is None:
                    gov_diag = diag

        # Four-zone studs (optional). When provided, they set n each side of max M.
        stud_layout: Optional[StudLayoutResult] = None
        n_half = inp.n_studs_half_span
        if inp.stud_zones is not None:
            x_mmax = gov_diag.M_max_x_mm if gov_diag is not None else inp.L_mm / 2.0
            hog_x = list(gov_diag.x_mm) if gov_diag is not None else None
            hog_m = list(gov_diag.M_kNmm < -1e-6) if gov_diag is not None else None
            stud_layout = layout_studs(
                inp.L_mm,
                inp.stud_zones,
                x_Mmax_mm=x_mmax,
                hogging_mask_x_mm=hog_x,
                hogging_mask=hog_m,
            )
            n_half = stud_layout.n_left_of_max_M
            notes.extend(stud_layout.notes)

        shear = shear_connection(
            inp.shape,
            inp.steel.Fy_MPa,
            slab,
            stud_qn,
            n_studs_half_span=n_half,
            target_ratio=inp.target_composite_ratio if inp.stud_zones is None else None,
        )

        pos = positive_flexural_strength(
            inp.shape,
            inp.steel.Fy_MPa,
            slab,
            shear,
            classification,
            n,
            phi_b=phi,
        )
        DCR_flex = Mu / pos.phiMn_kNm if pos.phiMn_kNm > 0 else float("inf")

        # Construction LTB (steel alone)
        Lb = inp.Lb_construction_mm if inp.Lb_construction_mm is not None else inp.L_mm
        if inp.construction_combinations_override is not None:
            constr_combos = list(inp.construction_combinations_override)
        else:
            constr_combos = CombinationSet(
                edition=inp.asce_edition, method=inp.method, include_construction=True
            ).all()
        Mu_c = 0.0
        Mu_c_neg = 0.0
        constr_diag: Optional[BeamDiagram] = None
        for combo in constr_combos:
            if combo.factor("C") == 0 and "wet" not in combo.name.lower() and "C" not in combo.name:
                if "1.2Dwet" not in combo.name and "Dwet" not in combo.name:
                    continue
            dgc = _factored_analysis(
                inp,
                w_D_wet,
                0.0,
                w_C,
                [],
                combo,
                points_C=inp.points_C,
                apply_lateral=False,
            )
            if ("wet" in combo.name.lower()) or combo.factor("C") > 0:
                if dgc.M_max_kNm > Mu_c:
                    Mu_c = dgc.M_max_kNm
                    constr_diag = dgc
                if dgc.M_min_kNm < Mu_c_neg:
                    Mu_c_neg = dgc.M_min_kNm
                combo_notes.append(
                    f"CONSTRUCTION {combo.name}: Mu+={dgc.M_max_kNm:.2f}; Mu−={dgc.M_min_kNm:.2f} kN·m"
                )

        Cb_c = 1.14 if inp.support == SupportType.SIMPLY_SUPPORTED else 1.0
        if constr_diag is not None and inp.support != SupportType.SIMPLY_SUPPORTED:
            Cb_c = cb_from_segment(constr_diag.x_mm, constr_diag.M_kNmm, 0.0, inp.L_mm)

        ltb_sag = construction_LTB(
            inp.shape,
            inp.steel.Fy_MPa,
            Lb,
            Mu_c,
            Cb=Cb_c,
            braced_by_deck=inp.deck_braces_construction,
            phi_b=phi,
            E_MPa=inp.steel.Es_MPa,
        )
        ltb = ltb_sag
        if abs(Mu_c_neg) > 1.0:
            # Hogging construction: bottom flange in compression — deck does not brace it
            ltb_hog_c = construction_LTB(
                inp.shape,
                inp.steel.Fy_MPa,
                inp.Lb_neg_mm if inp.Lb_neg_mm is not None else Lb,
                abs(Mu_c_neg),
                Cb=1.0,
                braced_by_deck=False,
                phi_b=phi,
                E_MPa=inp.steel.Es_MPa,
            )
            notes.append(
                "Construction hogging: bottom-flange LTB, deck brace does NOT apply."
            )
            if ltb_hog_c.DCR > ltb.DCR:
                ltb = ltb_hog_c
                notes.append("Governing construction LTB is hogging (bottom flange).")

        # Negative moment (occupancy hogging)
        neg: Optional[NegativeMomentResult] = None
        pass_neg = True
        DCR_neg = 0.0
        if abs(Mu_neg) > 1e-3:
            T_res = 0.0
            lever = slab.total_depth_mm / 2.0 + inp.shape.d_mm / 2.0
            if inp.include_residual_concrete_tension:
                n_hog = stud_layout.n_hogging if stud_layout is not None else 0
                AsFy = inp.shape.A_mm2 * inp.steel.Fy_MPa / 1000.0
                T_fc = 0.10 * (slab.fc_MPa ** 0.5) * slab.beff_mm * slab.t_solid_mm / 1000.0
                T_res = min(n_hog * stud_qn.Qn_kN, 0.10 * AsFy, T_fc)
                notes.append(
                    f"Residual T = min(n_hog Qn, 0.10 AsFy, 0.10√f'c Ac) = {T_res:.1f} kN "
                    f"(n_hog={n_hog}). NOT I3 hogging PNA."
                )
            Cb_neg = 1.0
            if gov_diag is not None:
                Cb_neg = cb_from_segment(gov_diag.x_mm, gov_diag.M_kNmm, 0.0, inp.L_mm * 0.25)
            Lb_neg = inp.Lb_neg_mm if inp.Lb_neg_mm is not None else inp.L_mm
            neg = negative_flexural_strength(
                inp.shape,
                inp.steel.Fy_MPa,
                classification,
                Mu_neg,
                Lb_neg,
                Cb=Cb_neg,
                phi_b=phi,
                E_MPa=inp.steel.Es_MPa,
                include_residual_concrete=inp.include_residual_concrete_tension,
                residual_T_kN=T_res,
                residual_lever_mm=lever,
            )
            pass_neg = neg.passes
            DCR_neg = neg.DCR

        # Chapter H (only required when axial is present)
        inter: Optional[InteractionResult] = None
        pass_inter = True
        if abs(inp.Pu_kN) > 0.01:
            Pn, Pc, Fcr, slend, e_notes = compressive_strength_E3(
                inp.shape,
                inp.steel.Fy_MPa,
                inp.L_mm,
                K=inp.K_factor,
                phi_c=inp.phi_c if inp.method.upper() == "LRFD" else 1.0 / 1.67,
                E_MPa=inp.steel.Es_MPa,
            )
            Mcx = pos.phiMn_kNm
            if neg is not None:
                # Use the smaller available flexural strength about x
                Mcx = min(Mcx, neg.phiMn_kNm)
            Mrx = max(abs(Mu), abs(Mu_neg))
            inter = chapter_h_interaction(
                Pr_kN=inp.Pu_kN,
                Pc_kN=Pc,
                Mrx_kNm=Mrx,
                Mcx_kNm=Mcx,
                Mry_kNm=0.0,
                Mcy_kNm=1.0,
                Pn_kN=Pn,
                KL_r=slend,
                Fcr_MPa=Fcr,
                extra_notes=e_notes,
            )
            pass_inter = inter.passes

        # Punching
        min_s = 1.0e9
        n_rows = 1
        if inp.stud_zones:
            min_s = min(z.spacing_mm for z in inp.stud_zones if z.spacing_mm > 0)
            n_rows = max(z.n_rows for z in inp.stud_zones)
        elif shear.n_studs_provided > 0:
            min_s = inp.L_mm / max(2 * shear.n_studs_provided, 1)
        punch = punching_with_group(
            inp.stud.diameter_mm,
            slab.t_solid_mm,
            slab.fc_MPa,
            stud_qn.Qn_kN,
            min_spacing_mm=min_s,
            n_rows=n_rows,
        )
        pass_punch = punch.passes

        # Deflections
        delf = compute_deflections(
            L_mm=inp.L_mm,
            shape=inp.shape,
            slab=slab,
            n=n,
            shear=shear,
            w_LL_kNpm=w_L,
            w_DL_service_kNpm=w_D_service_super,
            w_DL_construction_kNpm=w_D_wet,
            points_LL=inp.points_LL,
            points_DL=inp.points_DL,
            shored=inp.shored,
            limits=inp.deflection_limits,
            camber_mm=inp.camber_mm,
            E_MPa=inp.steel.Es_MPa,
        )
        if inp.support != SupportType.SIMPLY_SUPPORTED:
            EI_s = inp.steel.Es_MPa * inp.shape.Ix_mm4 / 1000.0
            EI_eff = inp.steel.Es_MPa * delf.I_eff_mm4 / 1000.0
            dLL = _analyze(inp, w_L, inp.points_LL)
            delta_LL = midspan_deflection_from_moment_mm(dLL.x_mm, dLL.M_kNmm, EI_eff)
            dDLc = _analyze(inp, w_D_wet, inp.points_DL)
            dDLs = _analyze(inp, w_D_service_super, [])
            if inp.shored:
                dDLall = _analyze(inp, w_D_wet + w_D_service_super, inp.points_DL)
                delta_DL = midspan_deflection_from_moment_mm(dDLall.x_mm, dDLall.M_kNmm, EI_eff)
                delta_DLc = 0.0
            else:
                delta_DLc = midspan_deflection_from_moment_mm(dDLc.x_mm, dDLc.M_kNmm, EI_s)
                delta_DLs = midspan_deflection_from_moment_mm(dDLs.x_mm, dDLs.M_kNmm, EI_eff)
                delta_DL = delta_DLc + delta_DLs
            delta_tot = delta_DL + delta_LL
            delf.delta_LL_mm = delta_LL
            delf.delta_DL_construction_mm = delta_DLc
            delf.delta_DL_composite_mm = delta_DL - delta_DLc
            delf.delta_total_mm = delta_tot
            delf.LL_OK = delta_LL <= delf.delta_LL_limit_mm + 1e-6
            delf.total_OK = delta_tot <= delf.delta_total_limit_mm + 1e-6
            delf.notes.append(
                f"Continuous-span deflections from M/EI integration "
                f"({inp.support.value}); SS 5/384 not used."
            )

        pass_flex = DCR_flex <= 1.0
        pass_c = ltb.passes
        pass_d = delf.LL_OK and delf.total_OK
        overall = pass_flex and pass_c and pass_d and pass_neg
        if abs(inp.Pu_kN) > 0.01:
            overall = overall and pass_inter
        # Punching is reported and included in overall (slab check)
        overall = overall and pass_punch

        # Cumulative composite action along span (detailing plot)
        cumulative: Optional[CumulativeCompositeResult] = None
        if gov_diag is not None:
            cumulative = cumulative_composite_action(
                inp.L_mm,
                shear.C_full_kN,
                stud_qn.Qn_kN,
                x_mm_diag=gov_diag.x_mm,
                M_kNmm=gov_diag.M_kNmm,
                x_maxM_mm=gov_diag.M_max_x_mm,
                stud_layout=stud_layout,
                n_studs_half_span=shear.n_studs_provided,
                n_rows=inp.n_studs_per_rib,
            )
            notes.extend(cumulative.notes)

        detailed = []
        detailed.extend(flags)
        detailed.extend(beff_res.notes)
        detailed.extend(stud_qn.notes)
        detailed.extend(shear.notes)
        detailed.extend(pos.notes)
        detailed.extend(ltb.notes)
        detailed.extend(delf.notes)
        detailed.extend(combo_notes)
        detailed.extend(notes)
        if neg is not None:
            detailed.extend(neg.notes)
        if inter is not None:
            detailed.extend(inter.notes)
        detailed.extend(punch.notes)

        passing: list[PassingShape] = []
        if search_passing:
            passing = self._search_passing(inp, beff_res, n, max_shapes=10)

        return DesignResult(
            inputs_summary={
                "L_mm": inp.L_mm,
                "shape": getattr(inp.shape, "display_name", None) or inp.shape.designation,
                "Fy_MPa": inp.steel.Fy_MPa,
                "fc_MPa": inp.concrete.fc_MPa,
                "method": inp.method,
                "location": inp.location.value,
                "support": inp.support.value,
                "section_kind": getattr(inp.shape, "section_kind", "W"),
                "project_label": inp.project_label,
                "aisc_edition": inp.aisc_edition.value,
                "asce_edition": inp.asce_edition.value,
            },
            beff=beff_res,
            n=n,
            classification=classification,
            stud_qn=stud_qn,
            shear=shear,
            positive_moment=pos,
            Mu_kNm=Mu,
            Vu_kN=Vu,
            DCR_flexure=DCR_flex,
            construction_LTB=ltb,
            Mu_construction_kNm=Mu_c,
            deflection=delf,
            combination_notes=combo_notes,
            edition_flags=flags,
            pass_flexure=pass_flex,
            pass_construction=pass_c,
            pass_deflection=pass_d,
            overall_pass=overall,
            detailed_notes=detailed,
            passing_shapes=passing,
            diagram=gov_diag,
            negative_moment=neg,
            Mu_neg_kNm=Mu_neg,
            DCR_neg=DCR_neg,
            pass_neg=pass_neg,
            interaction=inter,
            pass_interaction=pass_inter,
            stud_layout=stud_layout,
            punching=punch,
            pass_punching=pass_punch,
            cumulative=cumulative,
        )

    def _search_passing(
        self, base: DesignInputs, beff_res: EffectiveWidthResult, n: float, max_shapes: int = 10
    ) -> list[PassingShape]:
        """Return up to max_shapes passing W shapes lightest → heaviest."""
        out: list[PassingShape] = []
        if getattr(base.shape, "section_kind", "W") == "BOX":
            return out
        for shape in self.db.lightest_first():
            trial = replace(base, shape=shape)
            if base.steel.grade == "custom":
                trial = replace(trial, steel=base.steel)
            else:
                sm = SteelMaterial.from_grade(base.steel.grade, tf_mm=shape.tf_mm)
                trial = replace(
                    trial,
                    steel=SteelMaterial(
                        Fy_MPa=sm.Fy_MPa,
                        Fu_MPa=sm.Fu_MPa,
                        Es_MPa=base.steel.Es_MPa,
                        grade=base.steel.grade,
                    ),
                )
            res = self.design(trial, search_passing=False)
            if res.pass_flexure and res.pass_construction and res.pass_deflection:
                out.append(
                    PassingShape(
                        designation=shape.designation,
                        W_lb_ft=shape.W_lb_ft,
                        phiMn_kNm=res.positive_moment.phiMn_kNm,
                        DCR_flexure=res.DCR_flexure,
                        DCR_construction=res.construction_LTB.DCR if res.construction_LTB else 0.0,
                        LL_OK=res.deflection.LL_OK,
                        display_name=shape.display_name,
                    )
                )
            if len(out) >= max_shapes:
                break
        return out
