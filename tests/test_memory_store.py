from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.memory import (
    LocalMemoryStore,
    MemoryError,
    MemoryStoreConfig,
)


class MemoryStoreTests(unittest.TestCase):
    def _config(self, root: Path) -> MemoryStoreConfig:
        return MemoryStoreConfig(
            database=root / 'memory.db',
            context_limit=20,
            max_context_characters=4000,
            max_entries=10,
        )

    def test_alias_and_preference_persist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            with LocalMemoryStore(config) as store:
                store.remember_alias(
                    '학교 사이트',
                    'https://www.inha.ac.kr',
                    'url',
                )
                store.remember_preference(
                    'search_engine',
                    'google',
                )

            with LocalMemoryStore(config) as reopened:
                alias = reopened.resolve_alias(
                    '학교 사이트'
                )
                self.assertIsNotNone(alias)
                self.assertEqual(
                    alias.value_type,
                    'url',
                )
                self.assertEqual(
                    reopened.get_preference(
                        'search_engine'
                    ),
                    'google',
                )

    def test_upsert_keeps_single_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with LocalMemoryStore(
                self._config(Path(directory))
            ) as store:
                store.remember_alias(
                    '학교 사이트',
                    'https://example.com',
                    'url',
                )
                store.remember_alias(
                    '학교 사이트',
                    'https://www.inha.ac.kr',
                    'url',
                )
                self.assertEqual(store.count(), 1)
                self.assertEqual(
                    store.resolve_alias(
                        '학교 사이트'
                    ).value,
                    'https://www.inha.ac.kr',
                )

    def test_forget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with LocalMemoryStore(
                self._config(Path(directory))
            ) as store:
                store.remember_preference(
                    'search_engine',
                    'google',
                )
                self.assertTrue(
                    store.forget(
                        'preference',
                        'search_engine',
                    )
                )
                self.assertIsNone(
                    store.get_preference(
                        'search_engine'
                    )
                )

    def test_secrets_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with LocalMemoryStore(
                self._config(Path(directory))
            ) as store:
                with self.assertRaises(MemoryError):
                    store.remember_preference(
                        'OpenAI API key',
                        'sk-abcdefghijklmnopqrstuvwxyz123456',
                    )
                with self.assertRaises(MemoryError):
                    store.remember_alias(
                        '환경 파일',
                        r'C:\Project\.env',
                        'path',
                    )

    def test_prompt_context_is_json_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with LocalMemoryStore(
                self._config(Path(directory))
            ) as store:
                store.remember_alias(
                    '학교 사이트',
                    'https://www.inha.ac.kr',
                    'url',
                )
                context = store.prompt_context()
                self.assertIn('학교 사이트', context)
                self.assertIn('https://www.inha.ac.kr', context)


if __name__ == '__main__':
    unittest.main()
