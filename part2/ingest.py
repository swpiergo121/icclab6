#!/usr/bin/env python3

import glob
import hashlib
import io
import os

from psycopg2.extras import execute_values
from pypdf import PdfReader

from db import get_conn, init_db
from llm import embed_texts, vec_literal

MAX_PAGES_FILE = 300
MAX_PAGES_TOTAL = 900
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))


def chunk_text(text):
    chunks, start, n = [], 0, len(text)
    while start < n:
        end = min(start + CHUNK_SIZE, n)
        if end < n:  # cortar en un espacio para no partir palabras
            cut = text.rfind(" ", start + CHUNK_SIZE // 2, end)
            if cut != -1:
                end = cut
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def _result(filename, estado, paginas=0, fragmentos=0, sin_texto=None, errores=None):
    return {
        "archivo": filename,
        "estado": estado,
        "paginas": paginas,
        "fragmentos": fragmentos,
        "paginas_sin_texto": sin_texto or [],
        "errores": errores or [],
    }


def _result_from_db(cur, doc_id, filename, estado):
    cur.execute("SELECT page_count FROM documents WHERE id=%s", (doc_id,))
    paginas = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chunks WHERE document_id=%s", (doc_id,))
    fragmentos = cur.fetchone()[0]
    cur.execute(
        "SELECT page_number FROM pages WHERE document_id=%s AND NOT has_text ORDER BY page_number",
        (doc_id,),
    )
    sin_texto = [r[0] for r in cur.fetchall()]
    return _result(filename, estado, paginas, fragmentos, sin_texto)


def ingest_pdf(filename, raw):
    """Procesa un PDF en bytes. Es idempotente: el mismo contenido no se duplica."""
    sha = hashlib.sha256(raw).hexdigest()

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM documents WHERE sha256=%s", (sha,))
        row = cur.fetchone()
        if row:
            return _result_from_db(cur, row[0], filename, "ya_indexado")

    errors = []
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            reader.decrypt("")
        total = len(reader.pages)
    except Exception as exc:
        return _result(filename, "error_lectura", errores=[str(exc)])

    if total > MAX_PAGES_FILE:
        return _result(filename, "rechazado_mas_de_300_paginas", paginas=total)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COALESCE(SUM(page_count), 0) FROM documents")
        used = cur.fetchone()[0]
    if used + total > MAX_PAGES_TOTAL:
        return _result(filename, "rechazado_limite_900_paginas", paginas=total)

    pages, empty = [], []
    for num, page in enumerate(reader.pages, start=1):
        try:
            text = " ".join((page.extract_text() or "").split())
        except Exception as exc:
            text = ""
            errors.append(f"página {num}: {exc}")
        if not text:
            empty.append(num)
        pages.append((num, text))

    pieces = [(num, i, c) for num, text in pages for i, c in enumerate(chunk_text(text))]

    try:
        vectors = embed_texts([p[2] for p in pieces]) if pieces else []
    except Exception as exc:
        return _result(filename, "error_embeddings", paginas=total,
                       sin_texto=empty, errores=[str(exc)])

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO documents (filename, sha256, page_count) VALUES (%s, %s, %s) "
            "ON CONFLICT (sha256) DO NOTHING RETURNING id",
            (filename, sha, total),
        )
        row = cur.fetchone()
        if row is None:  # otro proceso lo insertó al mismo tiempo
            return _result(filename, "ya_indexado", paginas=total)
        doc_id = row[0]

        execute_values(
            cur,
            "INSERT INTO pages (document_id, page_number, has_text, text) VALUES %s",
            [(doc_id, num, bool(t), t) for num, t in pages],
        )
        execute_values(
            cur,
            "INSERT INTO chunks (document_id, page_number, chunk_index, content, embedding) VALUES %s",
            [(doc_id, num, i, c, vec_literal(v)) for (num, i, c), v in zip(pieces, vectors)],
            template="(%s, %s, %s, %s, %s::vector)",
        )

    return _result(filename, "procesado", total, len(pieces), empty, errors)


def ingest_folder(folder):
    results = []
    for path in sorted(glob.glob(os.path.join(folder, "*.pdf"))):
        with open(path, "rb") as f:
            results.append(ingest_pdf(os.path.basename(path), f.read()))
    return results


if __name__ == "__main__":
    init_db()
    for r in ingest_folder(os.getenv("PDF_DIR", "pdfs")):
        print(r)
