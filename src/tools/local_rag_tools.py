from __future__ import annotations

from src.local_rag import LocalRagStore

from .registry import ToolRegistry, ToolSpec


def register_local_rag_tools(
    registry: ToolRegistry,
    store: LocalRagStore,
) -> None:
    def index_local_knowledge(
        paths: list[str],
        collection: str,
        force: bool,
        prune_missing: bool,
    ) -> dict:
        effective_collection = (
            collection.strip() or store.config.default_collection
        )
        return store.index_paths(
            paths=paths,
            collection=effective_collection,
            force=force,
            prune_missing=prune_missing,
        )

    def search_local_knowledge(
        query: str,
        collection: str,
        extension: str,
        limit: int,
    ) -> dict:
        effective_collection = (
            collection.strip() or store.config.default_collection
        )
        effective_limit = (
            limit if limit > 0 else store.config.default_search_limit
        )
        return store.search(
            query=query,
            collection=effective_collection,
            extension=extension,
            limit=effective_limit,
        )

    def get_local_knowledge_chunk(
        chunk_id: int,
    ) -> dict:
        return store.get_chunk(chunk_id)

    def get_local_knowledge_status(
        collection: str,
    ) -> dict:
        effective_collection = (
            collection.strip() or store.config.default_collection
        )
        return store.status(collection=effective_collection)

    registry.register(
        ToolSpec(
            name="index_local_knowledge",
            description=(
                "사용자가 허용된 로컬 폴더나 파일을 검색 가능하게 만들라고 "
                "요청했을 때 PDF, DOCX, 텍스트, Markdown, 코드 파일을 Local RAG "
                "색인에 추가하거나 증분 갱신한다. configured_roots 밖의 경로와 "
                "비밀·자격증명 파일은 거부한다. 단순 질문마다 반복 호출하지 않는다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 1024},
                        "minItems": 1,
                        "maxItems": 20,
                    },
                    "collection": {
                        "type": "string",
                        "maxLength": 100,
                        "description": (
                            "Memory V2 scope와 같은 이름을 권장한다. "
                            "빈 문자열이면 기본 collection을 사용한다."
                        ),
                    },
                    "force": {
                        "type": "boolean",
                    },
                    "prune_missing": {
                        "type": "boolean",
                    },
                },
                "required": [
                    "paths",
                    "collection",
                    "force",
                    "prune_missing",
                ],
                "additionalProperties": False,
            },
            handler=index_local_knowledge,
        )
    )

    registry.register(
        ToolSpec(
            name="search_local_knowledge",
            description=(
                "사용자의 로컬 문서·논문·노트·코드에서 답을 찾아야 할 때 "
                "Local RAG 색인을 검색한다. 결과의 citation과 chunk_id를 근거로 "
                "답하고, 찾지 못했으면 추측하지 않는다. extension은 all 또는 "
                "pdf, docx, py, md 같은 확장자를 사용한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 1000,
                    },
                    "collection": {
                        "type": "string",
                        "maxLength": 100,
                        "description": (
                            "Memory V2 scope와 같은 이름을 권장한다. "
                            "빈 문자열이면 기본 collection을 사용한다."
                        ),
                    },
                    "extension": {
                        "type": "string",
                        "maxLength": 20,
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                    },
                },
                "required": [
                    "query",
                    "collection",
                    "extension",
                    "limit",
                ],
                "additionalProperties": False,
            },
            handler=search_local_knowledge,
        )
    )

    registry.register(
        ToolSpec(
            name="get_local_knowledge_chunk",
            description=(
                "Local RAG 검색 결과가 잘렸거나 더 정확한 근거가 필요할 때 "
                "chunk_id로 원문 청크와 파일·줄 또는 PDF 페이지 출처를 조회한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "chunk_id": {
                        "type": "integer",
                        "minimum": 1,
                    },
                },
                "required": ["chunk_id"],
                "additionalProperties": False,
            },
            handler=get_local_knowledge_chunk,
        )
    )

    registry.register(
        ToolSpec(
            name="get_local_knowledge_status",
            description=(
                "Local RAG 컬렉션의 문서 수, 청크 수, 마지막 색인 시각, "
                "허용 루트와 지원 확장자를 확인한다. 색인이 비어 있는지 "
                "확인할 때 사용한다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "collection": {
                        "type": "string",
                        "maxLength": 100,
                        "description": (
                            "Memory V2 scope와 같은 이름을 권장한다. "
                            "빈 문자열이면 기본 collection을 사용한다."
                        ),
                    },
                },
                "required": ["collection"],
                "additionalProperties": False,
            },
            handler=get_local_knowledge_status,
        )
    )
