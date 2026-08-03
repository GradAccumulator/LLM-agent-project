from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from src.memory import LocalMemoryStore, MemoryStoreConfig


class MemoryV2StoreTests(unittest.TestCase):
    def _config(self, root: Path, **overrides) -> MemoryStoreConfig:
        values = {
            "database": root / "memory.db",
            "context_limit": 20,
            "max_context_characters": 4000,
            "max_entries": 100,
            "stale_after_days": 30,
        }
        values.update(overrides)
        return MemoryStoreConfig(**values)

    def test_project_snapshot_and_todo_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with LocalMemoryStore(self._config(Path(directory))) as store:
                store.remember_item(
                    kind="project",
                    scope="Jarvis",
                    name="현재 상태",
                    value="Planner V2 완료",
                    notes="다음은 Memory V2",
                    status="active",
                    importance=5,
                    confidence=1.0,
                    replace_existing=False,
                )
                store.remember_item(
                    kind="todo",
                    scope="Jarvis",
                    name="Memory V2 구현",
                    value="구조화 메모리 추가",
                    notes="",
                    status="pending",
                    importance=5,
                    confidence=1.0,
                    replace_existing=False,
                )
                snapshot = store.project_snapshot(
                    scope="Jarvis",
                    include_completed=False,
                    limit=50,
                )
                self.assertEqual(len(snapshot["project"]), 1)
                self.assertEqual(len(snapshot["todos"]), 1)

                changed = store.set_item_status(
                    kind="todo",
                    scope="Jarvis",
                    name="Memory V2 구현",
                    status="completed",
                )
                self.assertEqual(changed.status, "completed")
                hidden = store.project_snapshot(
                    scope="Jarvis",
                    include_completed=False,
                    limit=50,
                )
                self.assertEqual(hidden["todos"], [])

    def test_conflict_requires_explicit_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with LocalMemoryStore(self._config(Path(directory))) as store:
                first = store.remember_item(
                    kind="decision",
                    scope="LLM",
                    name="Attention 구조",
                    value="GQA 사용",
                    notes="KV 메모리 절약",
                    status="active",
                    importance=5,
                    confidence=1.0,
                    replace_existing=False,
                )
                self.assertTrue(first.stored)
                conflict = store.remember_item(
                    kind="decision",
                    scope="LLM",
                    name="Attention 구조",
                    value="MHA 사용",
                    notes="정확도 우선",
                    status="active",
                    importance=5,
                    confidence=0.9,
                    replace_existing=False,
                )
                self.assertFalse(conflict.stored)
                self.assertIsNotNone(conflict.conflict)
                self.assertEqual(
                    store.get_structured(
                        "decision",
                        "LLM",
                        "Attention 구조",
                    ).value,
                    "GQA 사용",
                )
                resolved = store.resolve_conflict(
                    conflict_id=conflict.conflict.id,
                    resolution="use_candidate",
                    merged_value="",
                    merged_notes="",
                    merged_status="active",
                    merged_importance=5,
                    merged_confidence=1.0,
                )
                self.assertTrue(resolved["resolved"])
                self.assertEqual(
                    store.get_structured(
                        "decision",
                        "LLM",
                        "Attention 구조",
                    ).value,
                    "MHA 사용",
                )
                self.assertEqual(
                    len(
                        store.history(
                            kind="decision",
                            scope="LLM",
                            name="Attention 구조",
                            limit=10,
                        )
                    ),
                    1,
                )

    def test_relevance_context_is_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with LocalMemoryStore(
                self._config(
                    Path(directory),
                    max_context_characters=900,
                )
            ) as store:
                store.remember_item(
                    kind="project",
                    scope="Jarvis",
                    name="음성 입력",
                    value="BlackShark callback 방식",
                    notes="WDM-KS",
                    status="active",
                    importance=4,
                    confidence=1.0,
                    replace_existing=False,
                )
                store.remember_item(
                    kind="project",
                    scope="입시",
                    name="지원 상태",
                    value="모의지원 확인",
                    notes="",
                    status="active",
                    importance=3,
                    confidence=0.8,
                    replace_existing=False,
                )
                encoded = store.prompt_context(query="Jarvis 마이크 상태")
                payload = json.loads(encoded)
                names = {
                    item["name"]
                    for item in payload["relevant_structured"]
                }
                self.assertIn("음성 입력", names)
                self.assertNotIn("지원 상태", names)
                self.assertLessEqual(len(encoded), 900)

    def test_stale_memory_health(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root, stale_after_days=7)
            with LocalMemoryStore(config) as store:
                result = store.remember_item(
                    kind="project",
                    scope="Jarvis",
                    name="상태",
                    value="초기 상태",
                    notes="",
                    status="active",
                    importance=3,
                    confidence=0.8,
                    replace_existing=False,
                )
                old = (
                    datetime.now(timezone.utc) - timedelta(days=20)
                ).isoformat(timespec="seconds")
                connection = sqlite3.connect(config.database)
                connection.execute(
                    "UPDATE structured_memories SET updated_at = ? WHERE id = ?",
                    (old, result.record.id),
                )
                connection.commit()
                connection.close()
                health = store.memory_health(scope="Jarvis", limit=50)
                self.assertEqual(health["stale_count"], 1)


if __name__ == "__main__":
    unittest.main()
