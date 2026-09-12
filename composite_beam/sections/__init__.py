"""Steel section database and classification."""

from composite_beam.sections.box_sections import WeldedBoxDims, box_properties
from composite_beam.sections.classification import ClassificationResult, Compactness, classify_flexure
from composite_beam.sections.w_shapes import WShape, WShapeDatabase, custom_w_shape, format_section_label

__all__ = [
    "WShape",
    "WShapeDatabase",
    "custom_w_shape",
    "format_section_label",
    "WeldedBoxDims",
    "box_properties",
    "ClassificationResult",
    "Compactness",
    "classify_flexure",
]
