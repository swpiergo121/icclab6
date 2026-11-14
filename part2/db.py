#!/usr/bin/env python3

import os
from contextlib import contextmanager
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")
EMBED_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id          SERIAL PRIMARY KEY,
    filename    TEXT NOT NULL,
    sha256      CHAR(64) UNIQUE NOT NULL,
    page_count  INT NOT NULL,
    created_at  TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pages (
    id           SERIAL PRIMARY KEY,
    document_id  INT REFERENCES documents(id) ON DELETE CASCADE,
    page_number  INT NOT NULL,          -- página física, desde 1
    has_text     BOOLEAN NOT NULL,
    text         TEXT,
    UNIQUE (document_id, page_number)
);

CREATE TABLE IF NOT EXISTS chunks (
    id           SERIAL PRIMARY KEY,
    document_id  INT REFERENCES documents(id) ON DELETE CASCADE,
    page_number  INT NOT NULL,
    chunk_index  INT NOT NULL,
    content      TEXT NOT NULL,
    embedding    vector({EMBED_DIM}) NOT NULL,
    UNIQUE (document_id, page_number, chunk_index)
);

CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);
"""


@contextmanager
def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(SCHEMA)
