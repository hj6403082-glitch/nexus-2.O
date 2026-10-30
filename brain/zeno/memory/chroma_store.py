"""ChromaDB (embedded) implementation of VectorStore."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api import ClientAPI
from chromadb.config import Settings as ChromaSettings
from chromadb.errors import ChromaError

from zeno.memory.base import Kind, MemoryRecord, MemoryStoreError, ScoredRecord

DEFAULT_COLLECTION = "zeno-memory"


def chroma_settings() -> ChromaSettings:
    # Memory is private: never send usage telemetry. allow_reset lets tests wipe.
    return ChromaSettings(anonymized_telemetry=False, allow_reset=True)


def ephemeral_client() -> ClientAPI:
    """In-memory client. Instances in one process share data; use unique collections."""
    return chromadb.EphemeralClient(settings=chroma_settings())


def open_persistent_store(path: Path, collection: str = DEFAULT_COLLECTION) -> "ChromaVectorStore":
    path.mkdir(parents=True, exist_ok=True)
    return ChromaVectorStore(
        chromadb.PersistentClient(path=str(path), settings=chroma_settings()), collection
    )


class ChromaVectorStore:
    def __init__(self, client: ClientAPI, collection: str) -> None:
        self._client = client
        self._name = collection
        self._collection = self._open()

    def add(self, records: Sequence[MemoryRecord], embeddings: Sequence[Sequence[float]]) -> None:
        if len(records) != len(embeddings):
            raise ValueError("records and embeddings must have the same length")
        if not records:
            return
        with _wrapped():
            self._collection.upsert(
                ids=[r.id for r in records],
                embeddings=[list(e) for e in embeddings],
                documents=[r.text for r in records],
                metadatas=[_metadata(r) for r in records],
            )

    def get(self, ids: Sequence[str]) -> list[MemoryRecord]:
        if not ids:
            return []
        with _wrapped():
            found = self._collection.get(ids=list(ids), include=["documents", "metadatas"])
        return _records(found)

    def query(
        self,
        embedding: Sequence[float],
        *,
        limit: int,
        kind: Kind | None = None,
        source: str | None = None,
    ) -> list[ScoredRecord]:
        if self._collection.count() == 0:
            return []
        with _wrapped():
            result = self._collection.query(
                query_embeddings=[list(embedding)],
                n_results=limit,
                where=_where(kind, source),
                include=["documents", "metadatas", "distances"],
            )
        ids = result["ids"][0]
        documents = (result["documents"] or [[]])[0]
        metadatas = (result["metadatas"] or [[]])[0]
        distances = (result["distances"] or [[]])[0]
        hits = []
        for id_, doc, meta, distance in zip(ids, documents, metadatas, distances, strict=True):
            similarity = 1.0 - float(distance)  # cosine distance
            hits.append(ScoredRecord(_record(id_, doc, meta), similarity, similarity))
        return hits

    def all(self, *, kind: Kind | None = None) -> list[MemoryRecord]:
        with _wrapped():
            found = self._collection.get(
                where=_where(kind, None), include=["documents", "metadatas"]
            )
        return _records(found)

    def count(self, *, kind: Kind | None = None) -> int:
        if kind is None:
            return int(self._collection.count())
        with _wrapped():
            return len(self._collection.get(where=_where(kind, None), include=[])["ids"])

    def delete(self, ids: Sequence[str]) -> None:
        if ids:
            with _wrapped():
                self._collection.delete(ids=list(ids))

    def clear(self) -> None:
        with _wrapped():
            self._client.delete_collection(self._name)
            self._collection = self._open()

    def _open(self) -> Any:  # chromadb's Collection type is not exported stably
        return self._client.get_or_create_collection(
            self._name, metadata={"hnsw:space": "cosine"}, embedding_function=None
        )


class _wrapped:
    """Turns ChromaDB errors into MemoryStoreError so callers never import chromadb."""

    def __enter__(self) -> None:
        return None

    def __exit__(
        self, kind: type[BaseException] | None, error: BaseException | None, _: Any
    ) -> None:
        if isinstance(error, ChromaError):
            raise MemoryStoreError(str(error)) from error


def _metadata(record: MemoryRecord) -> dict[str, str | float]:
    return {
        "kind": record.kind,
        "source": record.source,
        "session": record.session,
        "created_at": record.created_at,
        "importance": record.importance,
    }


def _where(kind: Kind | None, source: str | None) -> Any:
    conditions = [{k: v} for k, v in (("kind", kind), ("source", source)) if v is not None]
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


def _records(found: Any) -> list[MemoryRecord]:
    metadatas = found["metadatas"] or []
    documents = found["documents"] or []
    return [_record(i, d, m) for i, d, m in zip(found["ids"], documents, metadatas, strict=True)]


def _record(id_: str, document: str | None, meta: Mapping[str, Any] | None) -> MemoryRecord:
    meta = meta or {}
    return MemoryRecord(
        id=id_,
        text=document or "",
        kind=meta.get("kind", "episode"),
        created_at=float(meta.get("created_at", 0.0)),
        importance=float(meta.get("importance", 0.5)),
        source=str(meta.get("source", "")),
        session=str(meta.get("session", "")),
    )
