from __future__ import annotations

from pathlib import Path
import unittest


class SrcPackageInitTests(
    unittest.TestCase
):
    def test_root_init_does_not_import_edge_modules(
        self,
    ) -> None:
        path = (
            Path(__file__).resolve()
            .parents[1]
            / "src"
            / "__init__.py"
        )
        self.assertEqual(
            path.read_text(
                encoding="utf-8"
            ).strip(),
            "",
        )


if __name__ == "__main__":
    unittest.main()
