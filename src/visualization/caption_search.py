"""
Caption indexing and search utilities.
"""
from __future__ import annotations

import glob
import hashlib
import json
import logging
import math
import os
import re
import sqlite3
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Iterable, List, Optional

logger = logging.getLogger(__name__)

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

EMBEDDING_DIM = 768
MODEL_NAME = "gemini-embedding-2-preview"

_client: Optional[genai.Client] = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable not set")
        _client = genai.Client(api_key=api_key)
    return _client

@dataclass
class CaptionSearchSelection:
    video_id: str
    video_path: str
    start_time: str
    end_time: str

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())

def _embed_texts(texts: List[str], ignore_errors: bool = True) -> List[List[float]]:
    """Embed a batch of texts using Gemini Embedding 2."""
    if not texts:
        return []

    client = _get_client()
    try:
        response = client.models.embed_content(
            model=MODEL_NAME,
            contents=texts,
            config=types.EmbedContentConfig(
                output_dimensionality=EMBEDDING_DIM
            )
        )
        return [emb.values for emb in response.embeddings]
    except Exception as e:
        print(f"Embedding failed: {e}")
        if ignore_errors:
            # Return zero vectors as fallback if necessary, or re-raise
            return [[0.0] * EMBEDDING_DIM for _ in texts]
        raise e


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def _coerce_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        flattened: list[str] = []
        for item in value:
            if isinstance(item, dict):
                flattened.extend(str(v) for v in item.values() if v is not None)
            elif item is not None:
                flattened.append(str(item))
        return " ".join(flattened)
    if isinstance(value, dict):
        return " ".join(str(v) for v in value.values() if v is not None)
    return str(value)


def _snippet_with_highlight(text: str, match_start: int, match_end: int, context_words: int = 3) -> str:
    words = list(re.finditer(r"\S+", text))
    if not words:
        return ""

    center_idx = 0
    for idx, word in enumerate(words):
        if word.start() <= match_start < word.end() or word.start() < match_end <= word.end():
            center_idx = idx
            break
    start_idx = max(0, center_idx - context_words)
    end_idx = min(len(words) - 1, center_idx + context_words)

    snippet_start = words[start_idx].start()
    snippet_end = words[end_idx].end()
    snippet = text[snippet_start:snippet_end]

    rel_start = max(0, match_start - snippet_start)
    rel_end = max(rel_start, min(len(snippet), match_end - snippet_start))

    before = escape(snippet[:rel_start])
    middle = escape(snippet[rel_start:rel_end])
    after = escape(snippet[rel_end:])
    prefix = "… " if snippet_start > 0 else ""
    suffix = " …" if snippet_end < len(text) else ""
    return f"{prefix}{before}<mark>{middle}</mark>{after}{suffix}"


def _semantic_preview(text: str, words: int = 8) -> str:
    tokens = text.split()
    if len(tokens) <= words:
        return text
    return " ".join(tokens[:words]) + "…"


def _caption_files(workspace_root: str) -> Iterable[str]:
    pattern = os.path.join(workspace_root, "**", "*_caption_narrations.json")
    return glob.iglob(pattern, recursive=True)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS segment_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            segment_uid TEXT NOT NULL,
            video_id TEXT NOT NULL,
            video_path TEXT,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            key_name TEXT NOT NULL,
            text_value TEXT NOT NULL,
            embedding_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_segment_uid ON segment_keys(segment_uid)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_key_name ON segment_keys(key_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_id ON segment_keys(video_id)")
    conn.commit()


def build_caption_index(workspace_root: str, db_path: str) -> dict:
    workspace_root = str(Path(workspace_root).resolve())
    db_path = str(Path(db_path).resolve())
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        _ensure_schema(conn)
        conn.execute("DELETE FROM segment_keys")

        files_processed = 0
        rows_inserted = 0
        segments_seen = 0

        BATCH_SIZE = 100
        batch_records = []

        def flush_batch():
            nonlocal rows_inserted
            if not batch_records:
                return
            
            texts = [r['text'] for r in batch_records]
            embeddings = _embed_texts(texts, ignore_errors=False)
            
            insert_data = []
            for record, embedding in zip(batch_records, embeddings):
                insert_data.append((
                    record['segment_uid'],
                    record['video_id'],
                    record['video_path'],
                    record['start_time'],
                    record['end_time'],
                    record['key_name'],
                    record['text'],
                    json.dumps(embedding),
                ))
                
            conn.executemany(
                """
                INSERT INTO segment_keys (
                    segment_uid, video_id, video_path, start_time, end_time,
                    key_name, text_value, embedding_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                insert_data
            )
            rows_inserted += len(insert_data)
            batch_records.clear()

        for file_path in _caption_files(workspace_root):
            files_processed += 1
            with open(file_path, "r", encoding="utf-8") as f:
                payload = json.load(f)

            video_id = str(payload.get("video_id", "")).strip()
            video_path = str(payload.get("video_path", "")).strip()
            chunks = payload.get("chunks", []) or []

            for chunk in chunks:
                chunk_index = int(chunk.get("chunk_index", 0) or 0)
                segments = (chunk.get("caption") or {}).get("segments", []) or []
                for segment_index, segment in enumerate(segments):
                    time_span = segment.get("time_span") or {}
                    start_time = str(time_span.get("start_time", "") or "")
                    end_time = str(time_span.get("end_time", "") or "")
                    if not start_time and not end_time:
                        continue

                    description = segment.get("description") or {}
                    segment_uid = f"{video_id}:{chunk_index}:{segment_index}:{start_time}:{end_time}"
                    segments_seen += 1

                    for key_name, raw in description.items():
                        text_value = _coerce_text(raw).strip()
                        if not text_value:
                            continue
                        
                        batch_records.append({
                            'segment_uid': segment_uid,
                            'video_id': video_id,
                            'video_path': video_path,
                            'start_time': start_time,
                            'end_time': end_time,
                            'key_name': key_name,
                            'text': text_value
                        })
                        
                        if len(batch_records) >= BATCH_SIZE:
                            flush_batch()

        # Flush any remaining records
        flush_batch()
        conn.commit()
        return {
            "success": True,
            "workspace_root": workspace_root,
            "db_path": db_path,
            "files_processed": files_processed,
            "segments_seen": segments_seen,
            "rows_indexed": rows_inserted,
        }
    finally:
        conn.close()


def available_caption_keys(db_path: str) -> list[str]:
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT DISTINCT key_name FROM segment_keys ORDER BY key_name ASC"
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def search_captions(
    db_path: str,
    query: str,
    *,
    use_regex: bool = True,
    use_semantic: bool = True,
    keys: list[str] | None = None,
    page: int = 1,
    per_page: int = 20,
    semantic_limit: int = 5,
    semantic_threshold: float = 0.65,
) -> dict:
    query = (query or "").strip()
    if not query:
        return {
            "results": [],
            "total": 0,
            "page": page,
            "per_page": per_page,
            "available_keys": available_caption_keys(db_path),
        }

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Caption index not found: {db_path}")

    key_filter = [k for k in (keys or []) if k]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        where_parts = ["text_value != ''"]
        params: list[object] = []
        if key_filter:
            placeholders = ",".join("?" for _ in key_filter)
            where_parts.append(f"key_name IN ({placeholders})")
            params.extend(key_filter)

        where_clause = " AND ".join(where_parts)
        rows = conn.execute(
            f"""
            SELECT segment_uid, video_id, video_path, start_time, end_time,
                   key_name, text_value, embedding_json
            FROM segment_keys
            WHERE {where_clause}
            """,
            params,
        ).fetchall()

        dedup: dict[str, dict] = {}

        if use_regex:
            # Use escaped pattern to avoid regex-injection/ReDoS from untrusted input.
            regex = re.compile(re.escape(query), flags=re.IGNORECASE)
            for row in rows:
                text_value = row["text_value"] or ""
                match = regex.search(text_value)
                if not match:
                    continue
                segment_uid = row["segment_uid"]
                card = dedup.setdefault(
                    segment_uid,
                    {
                        "segment_uid": segment_uid,
                        "video_id": row["video_id"],
                        "video_path": row["video_path"],
                        "start_time": row["start_time"],
                        "end_time": row["end_time"],
                        "score": 0.0,
                        "matches": [],
                    },
                )
                card["score"] = max(card["score"], 1.0)
                card["matches"].append(
                    {
                        "key": row["key_name"],
                        "mode": "regex",
                        "snippet_html": _snippet_with_highlight(
                            text_value, match.start(), match.end()
                        ),
                        "full_text": text_value,
                    }
                )

        if use_semantic:
            try:
                embeddings = _embed_texts([query])
                query_embedding = embeddings[0] if embeddings else None
            except Exception as e:
                logger.warning("Query embedding failed: %s", e)
                query_embedding = None

            if query_embedding:
                # Collect per-row similarity scores (no threshold filter here;
                # we take the top-N by score after deduplication instead)
                row_hits: list[tuple[float, sqlite3.Row]] = []
                for row in rows:
                    try:
                        embedding = json.loads(row["embedding_json"] or "[]")
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(embedding, list):
                        continue
                    sim = _cosine_similarity(query_embedding, embedding)
                    if sim <= 0:
                        continue
                    row_hits.append((sim, row))

                # Deduplicate by segment_uid, keeping the best score per segment
                best_per_segment: dict[str, tuple[float, list[tuple[float, sqlite3.Row]]]] = {}
                for sim, row in row_hits:
                    uid = row["segment_uid"]
                    if uid not in best_per_segment:
                        best_per_segment[uid] = (sim, [(sim, row)])
                    else:
                        prev_best, prev_rows = best_per_segment[uid]
                        prev_rows.append((sim, row))
                        best_per_segment[uid] = (max(prev_best, sim), prev_rows)

                # Sort segments by best score, take top semantic_limit
                top_segments = sorted(
                    best_per_segment.items(),
                    key=lambda item: item[1][0],
                    reverse=True,
                )[:semantic_limit]

                logger.info(
                    "Semantic search: %d row hits, %d unique segments, returning top %d (limit=%d, threshold=%.2f)",
                    len(row_hits), len(best_per_segment), len(top_segments),
                    semantic_limit, semantic_threshold,
                )

                for segment_uid, (best_score, segment_rows) in top_segments:
                    card = dedup.setdefault(
                        segment_uid,
                        {
                            "segment_uid": segment_uid,
                            "video_id": segment_rows[0][1]["video_id"],
                            "video_path": segment_rows[0][1]["video_path"],
                            "start_time": segment_rows[0][1]["start_time"],
                            "end_time": segment_rows[0][1]["end_time"],
                            "score": 0.0,
                            "matches": [],
                        },
                    )
                    card["score"] = max(card["score"], float(best_score))
                    for sim, row in segment_rows:
                        card["matches"].append(
                            {
                                "key": row["key_name"],
                                "mode": "semantic",
                                "semantic_preview": _semantic_preview(row["text_value"]),
                                "full_text": row["text_value"],
                                "score": float(sim),
                            }
                        )

        cards = list(dedup.values())
        cards.sort(key=lambda c: c["score"], reverse=True)

        # Hard cap: when only semantic search is active, enforce the limit
        if use_semantic and not use_regex:
            cards = cards[:semantic_limit]
            logger.info("Semantic-only mode: hard-capped results to %d (limit=%d)", len(cards), semantic_limit)

        total = len(cards)

        page = max(1, int(page or 1))
        per_page = max(1, min(100, int(per_page or 20)))
        start = (page - 1) * per_page
        end = start + per_page
        return {
            "results": cards[start:end],
            "total": total,
            "page": page,
            "per_page": per_page,
            "available_keys": available_caption_keys(db_path),
        }
    finally:
        conn.close()


def parse_search_request_args(args: dict) -> dict:
    raw_keys = args.get("keys", "")
    if isinstance(raw_keys, str):
        key_list = [k.strip() for k in raw_keys.split(",") if k.strip()]
    else:
        key_list = []
    return {
        "query": args.get("q", "") or args.get("query", ""),
        "use_regex": _parse_bool(args.get("regex"), True),
        "use_semantic": _parse_bool(args.get("semantic"), True),
        "keys": key_list,
        "page": int(args.get("page", 1) or 1),
        "per_page": int(args.get("per_page", 20) or 20),
    }
