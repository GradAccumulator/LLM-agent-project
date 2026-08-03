from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from src.llm import (
    AgentConfig,
    JarvisAgent,
)


class AgentTrustedImageToolTests(
    unittest.TestCase
):
    def _agent(self):
        agent = JarvisAgent.__new__(
            JarvisAgent
        )
        agent.config = AgentConfig()
        return agent

    def test_edge_capture_is_attached(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tab.png"
            path.write_bytes(b"PNG")
            output = json.dumps(
                {
                    "image_path": str(path),
                    "mime_type": "image/png",
                    "title": "Example",
                }
            )

            content = (
                self._agent()
                ._tool_output_content(
                    tool_name=(
                        "edge_cdp_capture_tab"
                    ),
                    success=True,
                    output=output,
                )
            )
            self.assertIsInstance(
                content,
                list,
            )
            self.assertEqual(
                content[1]["type"],
                "input_image",
            )

    def test_untrusted_tool_path_is_not_attached(
        self,
    ) -> None:
        output = json.dumps(
            {
                "image_path": (
                    "C:/secret.png"
                )
            }
        )
        content = (
            self._agent()
            ._tool_output_content(
                tool_name="random_tool",
                success=True,
                output=output,
            )
        )
        self.assertEqual(
            content,
            output,
        )


if __name__ == "__main__":
    unittest.main()
