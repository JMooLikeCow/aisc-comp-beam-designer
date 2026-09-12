"""Unit and material smoke tests."""

from __future__ import annotations

import pytest

from composite_beam.materials.concrete import ConcreteMaterial, EcCode, compute_Ec
from composite_beam.materials.steel import resolve_steel_grade
from composite_beam.units import ksi_to_mpa, mpa_to_ksi


def test_steel_grades_and_a36_thickness():
    g = resolve_steel_grade("A992")
    assert g.Fy_ksi == 50.0
    a36 = resolve_steel_grade("A36", tf_mm=25.0)
    assert a36.Fy_ksi == 36.0
    a36_thick = resolve_steel_grade("A36", tf_mm=250.0)  # > 8 in
    assert a36_thick.Fy_ksi == 32.0


def test_ec_codes():
    fc = 27.6
    e_aci = compute_Ec(fc, code=EcCode.ACI318)
    e_ec2 = compute_Ec(fc, code=EcCode.EUROCODE2)
    e_nz = compute_Ec(fc, code=EcCode.NZS3101)
    assert e_aci > 0 and e_ec2 > 0 and e_nz > 0
    c = ConcreteMaterial(fc_MPa=fc, Ec_override_MPa=25000.0)
    assert c.Ec_MPa == 25000.0


def test_unit_roundtrip():
    assert mpa_to_ksi(ksi_to_mpa(50.0)) == pytest.approx(50.0)


def test_dual_helpers_si_primary():
    from composite_beam.units import (
        dual_force_kN,
        dual_length_mm,
        dual_line_load_kNpm,
        dual_moment_kNm,
        dual_stress_MPa,
        plf_to_knpm,
    )

    assert dual_length_mm(9144.0) == "9144 mm [360.0 in]"
    assert "MPa" in dual_stress_MPa(345.0) and "ksi" in dual_stress_MPa(345.0)
    assert dual_stress_MPa(345.0).startswith("345")
    s = dual_line_load_kNpm(plf_to_knpm(150.0))
    assert "kN/m" in s and "plf" in s
    assert "kN·m" in dual_moment_kNm(100.0) and "kip·ft" in dual_moment_kNm(100.0)
    assert "kN" in dual_force_kN(44.48) and "kip" in dual_force_kN(44.48)
