"""Design engine: orchestrate P0 composite beam checks and section search."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from composite_beam.analysis.simple_beam import analyze_simply_supported
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
from composite_beam.composite.shear_connection import ShearConnectionResult, shear_connection
from composite_beam.composite.slab import DeckOrientation, SlabConfig
from composite_beam.composite.studs import StudConfig, StudQnResult, stud_Qn
from composite_beam.loads.load_cases import LoadCase, LoadSet, PointLoad, PointLoadSpec, UDL
from composite_beam.materials.concrete import ConcreteMaterial, EcCode, modular_ratio
from composite_beam.materials.steel import SteelMaterial
from composite_beam.sections.classification import ClassificationResult, classify_flexure
from composite_beam.sections.w_shapes import WShape, WShapeDatabase
from composite_beam.serviceability.deflection import (
    DeflectionLimits,
    DeflectionResult,
    compute_deflections,
)
from composite_beam.strength.ltb import LTBResult, construction_LTB
from composite_beam.strength.positive_moment import PositiveMomentResult, positive_flexural_strength
from composite_beam.units import ES_MPA


@dataclass
class DesignInputs:
    """All inputs for a simply-supported composite beam design."""

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


@dataclass
class PassingShape:
    designation: str
    W_lb_ft: float
    phiMn_kNm: float
    DCR_flexure: float
    DCR_construction: float
    LL_OK: bool


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


def _slab_self_weight_kNpm(slab: SlabConfig, trib_mm: float, density_kNm3: float) -> float:
    """Uniform load from slab self-weight on trib width."""
    t_m = (slab.t_solid_mm + 0.5 * slab.hr_mm) / 1000.0  # approx average thickness
    # For solid: t_solid; for deck: solid + half rib fill approx
    if slab.orientation == DeckOrientation.NONE:
        t_m = slab.t_solid_mm / 1000.0
    trib_m = trib_mm / 1000.0
    return density_kNm3 * t_m * trib_m


def _factored_moment(
    L_mm: float,
    w_D_kNpm: float,
    w_L_kNpm: float,
    w_C_kNpm: float,
    points_L: list[PointLoad],
    combo: Combination,
) -> tuple[float, float]:
    """Apply combination factors to D, L, C roles; return Mu_kNm, Vu_kN."""
    w = (
        combo.factor("D") * w_D_kNpm
        + combo.factor("L") * w_L_kNpm
        + combo.factor("C") * w_C_kNpm
    )
    pts: list[PointLoad] = []
    fL = combo.factor("L")
    if fL:
        for p in points_L:
            pts.append(
                PointLoad(P_kN=p.P_kN * fL, location=p.location, spec=p.spec, label=p.label)
            )
    diag = analyze_simply_supported(L_mm, w, pts)
    return diag.M_max_kNm, diag.V_max_kN


class DesignEngine:
    """Run P0 composite beam design for a selected section and optional search."""

    def __init__(self, db: Optional[WShapeDatabase] = None) -> None:
        self.db = db or WShapeDatabase()

    def design(self, inp: DesignInputs, search_passing: bool = True) -> DesignResult:
        notes: list[str] = []
        flags = edition_flags(inp.asce_edition)
        flags.append(f"Locked AISC edition: {inp.aisc_edition.value}")

        # Effective width
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

        shear = shear_connection(
            inp.shape,
            inp.steel.Fy_MPa,
            slab,
            stud_qn,
            n_studs_half_span=inp.n_studs_half_span,
            target_ratio=inp.target_composite_ratio,
        )

        pos = positive_flexural_strength(
            inp.shape,
            inp.steel.Fy_MPa,
            slab,
            shear,
            classification,
            n,
            phi_b=inp.phi_b if inp.method.upper() == "LRFD" else 1.0 / inp.Omega_b,
        )

        # Dead load assembly
        trib = inp.slab_trib_width_mm or beff_res.beff_mm
        w_slab = (
            _slab_self_weight_kNpm(slab, trib, inp.concrete.density_kNm3)
            if inp.include_slab_self_weight
            else 0.0
        )
        w_beam = inp.shape.W_kNm if inp.include_beam_self_weight else 0.0
        w_D_wet = w_slab + w_beam  # construction dead (wet concrete + beam)
        w_D_service_super = inp.w_SDL_kNpm  # superimposed after composite
        w_D_total = w_D_wet + w_D_service_super
        w_L = inp.w_LL_kNpm
        w_C = inp.w_construction_kNpm

        # Governing occupancy combo (exclude construction-only)
        cset = CombinationSet(
            edition=inp.asce_edition,
            method=inp.method,
            include_construction=False,
            custom=inp.custom_combinations[:5],
        )
        Mu = 0.0
        Vu = 0.0
        combo_notes = []
        for combo in cset.all():
            if combo.factor("C") and not (combo.factor("L") or combo.factor("D")):
                continue
            m, v = _factored_moment(
                inp.L_mm, w_D_total, w_L, 0.0, inp.points_LL, combo
            )
            combo_notes.append(f"{combo.name}: Mu={m:.2f} kN·m, Vu={v:.2f} kN")
            if m > Mu:
                Mu, Vu = m, v

        # ASD uses allowable stress design factor already in pos.phi as 1/Ω
        DCR_flex = Mu / pos.phiMn_kNm if pos.phiMn_kNm > 0 else float("inf")

        # Construction LTB
        Lb = inp.Lb_construction_mm if inp.Lb_construction_mm is not None else inp.L_mm
        constr_combos = CombinationSet(
            edition=inp.asce_edition, method=inp.method, include_construction=True
        ).all()
        Mu_c = 0.0
        for combo in constr_combos:
            if combo.factor("C") == 0 and "wet" not in combo.name.lower() and "C" not in combo.name:
                # only construction-tagged
                if "1.2Dwet" not in combo.name and "Dwet" not in combo.name:
                    continue
            m, _ = _factored_moment(inp.L_mm, w_D_wet, 0.0, w_C, [], combo)
            if ("wet" in combo.name.lower()) or combo.factor("C") > 0:
                Mu_c = max(Mu_c, m)
                combo_notes.append(f"CONSTRUCTION {combo.name}: Mu={m:.2f} kN·m")

        ltb = construction_LTB(
            inp.shape,
            inp.steel.Fy_MPa,
            Lb,
            Mu_c,
            Cb=1.14,  # approximate for uniform load simply supported
            braced_by_deck=inp.deck_braces_construction,
            phi_b=inp.phi_b if inp.method.upper() == "LRFD" else 1.0 / inp.Omega_b,
            E_MPa=inp.steel.Es_MPa,
        )

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

        pass_flex = DCR_flex <= 1.0
        pass_c = ltb.passes
        pass_d = delf.LL_OK and delf.total_OK
        overall = pass_flex and pass_c and pass_d

        detailed = []
        detailed.extend(flags)
        detailed.extend(beff_res.notes)
        detailed.extend(stud_qn.notes)
        detailed.extend(shear.notes)
        detailed.extend(pos.notes)
        detailed.extend(ltb.notes)
        detailed.extend(delf.notes)
        detailed.extend(combo_notes)

        passing: list[PassingShape] = []
        if search_passing:
            passing = self._search_passing(inp, beff_res, n, max_shapes=10)

        return DesignResult(
            inputs_summary={
                "L_mm": inp.L_mm,
                "shape": inp.shape.designation,
                "Fy_MPa": inp.steel.Fy_MPa,
                "fc_MPa": inp.concrete.fc_MPa,
                "method": inp.method,
                "location": inp.location.value,
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
        )

    def _search_passing(
        self, base: DesignInputs, beff_res: EffectiveWidthResult, n: float, max_shapes: int = 10
    ) -> list[PassingShape]:
        """Return up to max_shapes passing W shapes lightest → heaviest."""
        out: list[PassingShape] = []
        for shape in self.db.lightest_first():
            if shape.designation == base.shape.designation and len(out) == 0:
                pass  # still evaluate
            trial = DesignInputs(
                L_mm=base.L_mm,
                shape=shape,
                steel=base.steel,
                concrete=base.concrete,
                slab=base.slab,
                location=base.location,
                spacing_left_mm=base.spacing_left_mm,
                spacing_right_mm=base.spacing_right_mm,
                beff_override_mm=base.beff_override_mm,
                aisc_edition=base.aisc_edition,
                asce_edition=base.asce_edition,
                stud=base.stud,
                n_studs_half_span=base.n_studs_half_span,
                target_composite_ratio=base.target_composite_ratio,
                n_override=base.n_override,
                w_SDL_kNpm=base.w_SDL_kNpm,
                w_LL_kNpm=base.w_LL_kNpm,
                w_construction_kNpm=base.w_construction_kNpm,
                points_LL=base.points_LL,
                shored=base.shored,
                deck_braces_construction=base.deck_braces_construction,
                Lb_construction_mm=base.Lb_construction_mm,
                method=base.method,
                n_studs_per_rib=base.n_studs_per_rib,
            )
            # Fix steel: keep Fy from base for catalog grades with thickness rules
            if base.steel.grade == "custom":
                trial.steel = base.steel
            else:
                sm = SteelMaterial.from_grade(base.steel.grade, tf_mm=shape.tf_mm)
                trial.steel = SteelMaterial(
                    Fy_MPa=sm.Fy_MPa,
                    Fu_MPa=sm.Fu_MPa,
                    Es_MPa=base.steel.Es_MPa,
                    grade=base.steel.grade,
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
                    )
                )
            if len(out) >= max_shapes:
                break
        return out
