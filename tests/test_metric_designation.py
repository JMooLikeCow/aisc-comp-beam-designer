"""Metric-first AISC W-shape labeling."""

from composite_beam.sections.box_sections import box_properties
from composite_beam.sections.w_shapes import WShapeDatabase, custom_w_shape, format_section_label


def test_w18x35_display_name_metric_first():
    db = WShapeDatabase()
    s = db.get("W18X35")
    assert s.designation == "W18X35"
    assert s.designation_metric == "W460X52"
    assert s.display_name.startswith("W460")
    assert "W18" in s.display_name.replace("×", "X").upper()
    assert "W18X35" in s.display_name.replace("×", "X").upper()
    assert s.display_name == "W460×52 (W18×35)"


def test_format_section_label_custom_and_box_si_first():
    custom = custom_w_shape("CUSTOM", 400.0, 300.0, 19.0, 12.0)
    label = custom.display_name
    assert label.startswith("CUSTOM 400×300×19×12 mm")
    assert "in)" in label

    box = box_properties(400.0, 300.0, 19.0, 12.0, designation="BOX")
    bl = box.display_name
    assert bl.startswith("BOX 400×300×19×12 mm")
    assert format_section_label("BOX", None, shape=box) == bl
