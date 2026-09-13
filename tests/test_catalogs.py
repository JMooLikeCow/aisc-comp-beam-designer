"""Catalog smoke tests: expanded W-shapes + ComFlor® deck."""

from composite_beam.composite.slab import catalog_hr_wr_mm, load_deck_catalog, slab_from_catalog
from composite_beam.sections.w_shapes import WShapeDatabase


def test_w_shape_catalog_expanded():
    db = WShapeDatabase()
    assert len(db) >= 200
    s = db.get("W18X35")
    assert s.designation_metric == "W460X52"
    assert s.display_name == "W460×52 (W18×35)"
    # Spot-check a few more Manual shapes
    for des in ("W21X44", "W12X26", "W8X10", "W36X150", "W4X13"):
        assert db.get(des).designation == des


def test_comflor_deck_catalog():
    cat = load_deck_catalog()
    assert "solid" in cat
    assert "manual" in cat
    for key in (
        "comflor_46",
        "comflor_51_plus",
        "comflor_60",
        "comflor_60_closed",
        "comflor_80",
        "comflor_80_closed",
        "comflor_100",
        "comflor_210",
        "comflor_225",
    ):
        assert key in cat
        e = cat[key]
        assert "hr_mm" in e and "wr_mm" in e
        assert "source" in e and "ComFlor" in e["source"]
    hr, wr = catalog_hr_wr_mm(cat["comflor_60"])
    assert hr == 60
    assert wr == 150
    slab = slab_from_catalog("comflor_51_plus", t_solid_mm=100.0, fc_MPa=28.0)
    assert slab.hr_mm == 51
    assert slab.catalog_key == "comflor_51_plus"
