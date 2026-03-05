#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List

import chromadb
from qdrant_client import QdrantClient, models


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "chroma_db"
DEFAULT_TARGET = REPO_ROOT / "qdrant_db"


def _payload(document: str, metadata: Dict[str, Any] | None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"page_content": document or ""}
    for key, value in (metadata or {}).items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            payload[key] = value
        else:
            payload[key] = json.dumps(value, sort_keys=True, default=str)
    return payload


def _point_id(collection_name: str, chroma_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{collection_name}:{chroma_id}"))


def _batched_points(
    collection_name: str,
    ids: List[str],
    documents: List[str],
    metadatas: List[Dict[str, Any] | None],
    embeddings: List[List[float]],
) -> Iterable[List[models.PointStruct]]:
    batch: List[models.PointStruct] = []
    for chroma_id, document, metadata, embedding in zip(ids, documents, metadatas, embeddings):
        batch.append(
            models.PointStruct(
                id=_point_id(collection_name, chroma_id),
                vector=embedding,
                payload=_payload(document, metadata),
            )
        )
        if len(batch) >= 256:
            yield batch
            batch = []
    if batch:
        yield batch


def migrate(source: Path, target: Path, reset_target: bool) -> Dict[str, int]:
    if not source.exists():
        raise FileNotFoundError(f"Chroma source directory not found: {source}")
    if reset_target and target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)

    chroma_client = chromadb.PersistentClient(path=str(source))
    qdrant_client = QdrantClient(path=str(target))

    migrated: Dict[str, int] = {}
    for collection_stub in chroma_client.list_collections():
        collection = chroma_client.get_collection(collection_stub.name)
        data = collection.get(include=["documents", "metadatas", "embeddings"])
        ids_raw = data.get("ids")
        documents_raw = data.get("documents")
        metadatas_raw = data.get("metadatas")
        embeddings_raw = data.get("embeddings")
        ids = list(ids_raw) if ids_raw is not None else []
        documents = list(documents_raw) if documents_raw is not None else []
        metadatas = list(metadatas_raw) if metadatas_raw is not None else []
        embeddings = list(embeddings_raw) if embeddings_raw is not None else []
        if not ids:
            migrated[collection.name] = 0
            continue

        vector_size = len(embeddings[0])
        if qdrant_client.collection_exists(collection.name):
            qdrant_client.delete_collection(collection.name)
        qdrant_client.create_collection(
            collection_name=collection.name,
            vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        )

        count = 0
        for points in _batched_points(collection.name, ids, documents, metadatas, embeddings):
            qdrant_client.upsert(collection_name=collection.name, points=points, wait=True)
            count += len(points)
        migrated[collection.name] = count
    return migrated


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate local Chroma collections into local Qdrant.")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--target", default=str(DEFAULT_TARGET))
    parser.add_argument("--keep-target", action="store_true", help="Do not delete the target directory before migration.")
    args = parser.parse_args()

    migrated = migrate(
        source=Path(args.source),
        target=Path(args.target),
        reset_target=not args.keep_target,
    )
    print(json.dumps(migrated, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
