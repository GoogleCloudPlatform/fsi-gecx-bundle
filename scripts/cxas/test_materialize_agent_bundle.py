#!/usr/bin/env python3
"""Regression tests for clean-checkout CES bundle materialization."""

from pathlib import Path
import tempfile
import unittest

from materialize_agent_bundle import TOOLSET_RELATIVE_PATH, materialize_toolset


class MaterializeAgentBundleTest(unittest.TestCase):
    def test_renders_environment_specific_url_without_unresolved_variables(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            agent_folder = Path(temporary_directory)
            output_path = agent_folder / TOOLSET_RELATIVE_PATH
            template_path = output_path.with_suffix(output_path.suffix + ".tftpl")
            template_path.parent.mkdir(parents=True)
            template_path.write_text(
                "mcpToolset:\n  serverAddress: ${banking_service_url}/api/mcp/\n"
            )

            rendered_path = materialize_toolset(
                agent_folder, "https://banking-service.example/"
            )

            self.assertEqual(output_path, rendered_path)
            self.assertEqual(
                output_path.read_text(),
                "mcpToolset:\n"
                "  serverAddress: https://banking-service.example/api/mcp/\n",
            )

    def test_rejects_non_https_service_url(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ValueError, "absolute HTTPS URL"):
                materialize_toolset(
                    Path(temporary_directory), "http://banking-service.example"
                )


if __name__ == "__main__":
    unittest.main()
