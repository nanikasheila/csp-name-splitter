import unittest

from name_splitter.core.config import MergeConfig, MergeRule
from name_splitter.core.merge import apply_merge_rules
from name_splitter.core.image_read import LayerNode


class MergeTests(unittest.TestCase):
    def test_apply_merge_rules_matches_layers(self) -> None:
        layers = (
            LayerNode(
                name="GroupA",
                kind="group",
                visible=True,
                children=(
                    LayerNode(name="Lines", kind="layer", visible=True),
                    LayerNode(name="Notes", kind="layer", visible=True),
                ),
            ),
        )
        cfg = MergeConfig(
            group_rules=(MergeRule(group_name="GroupA", output_layer="text"),),
            layer_rules=(
                MergeRule(layer_name="Lines", output_layer="lines"),
                MergeRule(layer_name="Notes", output_layer="notes"),
            ),
            include_hidden_layers=True,
        )
        result = apply_merge_rules(layers, cfg)
        self.assertEqual(set(result.outputs.keys()), {"text", "lines", "notes"})
        self.assertEqual(len(result.unmatched), 0)

    def test_apply_merge_rules_skips_hidden(self) -> None:
        layers = (
            LayerNode(name="Hidden", kind="layer", visible=False),
            LayerNode(name="Visible", kind="layer", visible=True),
        )
        cfg = MergeConfig(
            layer_rules=(
                MergeRule(layer_name="Hidden", output_layer="notes"),
                MergeRule(layer_name="Visible", output_layer="lines"),
            ),
            include_hidden_layers=False,
        )
        result = apply_merge_rules(layers, cfg)
        self.assertIn("lines", result.outputs)
        self.assertNotIn("notes", result.outputs)
        self.assertEqual(len(result.unmatched), 0)


if __name__ == "__main__":
    unittest.main()
