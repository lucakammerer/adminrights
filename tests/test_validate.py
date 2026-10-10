"""validate.material_mismatch on synthetic attributes (I11).

Run from the repo root: uv run --project agent --no-sync python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from validate import material_mismatch  # noqa: E402

REQUIREMENT = {"bore_mm": 40, "stroke_mm": 150, "pressure_bar": 160, "mounting": "Flansch",
               "certification": "keine gefordert"}


class MaterialMismatch(unittest.TestCase):
    def test_same_attributes_as_pages_write_them(self):
        found = {"bore_mm": "40 mm", "stroke_mm": 150.0, "pressure_bar": "160 bar", "mounting": "flansch",
                 "certification": "Keine"}
        self.assertEqual(material_mismatch(REQUIREMENT, found), [])

    def test_look_alike_differs_in_stroke_and_certification(self):
        found = {"bore_mm": 40, "stroke_mm": 175, "pressure_bar": 160, "mounting": "Flansch",
                 "certification": "EN 9999"}
        self.assertEqual(len(material_mismatch(REQUIREMENT, found)), 2)

    def test_unread_attribute_never_blocks(self):
        self.assertEqual(material_mismatch(REQUIREMENT, {"bore_mm": None, "mounting": None}), [])


if __name__ == "__main__":
    unittest.main()
