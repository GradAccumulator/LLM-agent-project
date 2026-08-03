from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.local_rag import (
    LocalRagConfig,
    LocalRagError,
    LocalRagStore,
)


class LocalRagStoreTests(unittest.TestCase):
    def _store(self, root: Path) -> LocalRagStore:
        return LocalRagStore(
            LocalRagConfig(
                database=root / "rag.db",
                roots=(root,),
                default_collection="Jarvis",
                chunk_characters=240,
                chunk_overlap_characters=40,
                max_files=100,
                max_chunks=1000,
            )
        )

    def test_indexes_and_returns_line_citations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "attention.py"
            source.write_text(
                "class GroupedQueryAttention:\n"
                "    # GQA shares keys and values.\n"
                "    def forward(self, query, key, value):\n"
                "        return query @ key.transpose(-1, -2)\n",
                encoding="utf-8",
            )
            with self._store(root) as store:
                indexed = store.index_paths(
                    paths=[str(source)],
                    collection="Jarvis",
                    force=False,
                    prune_missing=True,
                )
                self.assertEqual(indexed["indexed_files"], 1)
                self.assertGreater(indexed["chunks_written"], 0)

                result = store.search(
                    query="GQA shares keys values",
                    collection="Jarvis",
                    extension="py",
                    limit=5,
                )
                self.assertEqual(result["count"], 1)
                best = result["results"][0]
                self.assertEqual(best["path"], str(source.resolve()))
                self.assertIn(":L1-L4", best["citation"])
                self.assertIn("GroupedQueryAttention", best["text"])

                chunk = store.get_chunk(best["chunk_id"])
                self.assertEqual(chunk["citation"], best["citation"])

    def test_incremental_update_and_prune(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "notes.md"
            source.write_text("# Model\nLuna is the default model.\n", encoding="utf-8")
            with self._store(root) as store:
                first = store.index_paths(
                    paths=[str(root)],
                    collection="Jarvis",
                    force=False,
                    prune_missing=True,
                )
                self.assertEqual(first["indexed_files"], 1)

                second = store.index_paths(
                    paths=[str(root)],
                    collection="Jarvis",
                    force=False,
                    prune_missing=True,
                )
                self.assertEqual(second["unchanged_files"], 1)

                source.write_text(
                    "# Model\nTerra handles balanced reasoning tasks.\n",
                    encoding="utf-8",
                )
                third = store.index_paths(
                    paths=[str(root)],
                    collection="Jarvis",
                    force=False,
                    prune_missing=True,
                )
                self.assertEqual(third["updated_files"], 1)
                found = store.search(
                    query="Terra balanced reasoning",
                    collection="Jarvis",
                    extension="all",
                    limit=5,
                )
                self.assertEqual(found["count"], 1)

                source.unlink()
                pruned = store.index_paths(
                    paths=[str(root)],
                    collection="Jarvis",
                    force=False,
                    prune_missing=True,
                )
                self.assertEqual(pruned["removed_files"], 1)
                self.assertEqual(
                    store.status(collection="Jarvis")["document_count"],
                    0,
                )

    def test_secret_files_and_secret_content_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("OPENAI_API_KEY=secret", encoding="utf-8")
            (root / "credentials.json").write_text("{}", encoding="utf-8")
            (root / "safe.md").write_text("Transformer architecture notes", encoding="utf-8")
            (root / "leak.md").write_text(
                "key = sk-abcdefghijklmnopqrstuvwxyz123456",
                encoding="utf-8",
            )
            git = root / ".git"
            git.mkdir()
            (git / "config.txt").write_text("ignored", encoding="utf-8")

            with self._store(root) as store:
                result = store.index_paths(
                    paths=[str(root)],
                    collection="Jarvis",
                    force=False,
                    prune_missing=True,
                )
                self.assertEqual(result["indexed_files"], 1)
                self.assertGreaterEqual(
                    result["skipped"].get("sensitive_filename", 0),
                    2,
                )
                self.assertEqual(
                    result["skipped"].get("sensitive_content"),
                    1,
                )
                status = store.status(collection="Jarvis")
                self.assertEqual(status["document_count"], 1)
                self.assertIn(".pdf", status["supported_extensions"])
                self.assertIn(".docx", status["supported_extensions"])

    def test_path_outside_roots_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as allowed_directory, tempfile.TemporaryDirectory() as outside_directory:
            allowed = Path(allowed_directory)
            outside = Path(outside_directory) / "private.txt"
            outside.write_text("not allowed", encoding="utf-8")
            with self._store(allowed) as store:
                with self.assertRaises(LocalRagError):
                    store.index_paths(
                        paths=[str(outside)],
                        collection="Jarvis",
                        force=False,
                        prune_missing=True,
                    )


if __name__ == "__main__":
    unittest.main()
