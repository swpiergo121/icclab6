#!/usr/bin/env python3

import os

from db import get_conn
from llm import CHAT_MODEL, chat_client, embed_texts, vec_literal

TOP_K = int(os.getenv("TOP_K", "6"))
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.30"))  # ajústalo con tus preguntas de prueba

SYSTEM_PROMPT = """Eres un asistente de una empresa de transporte. Responde SIEMPRE en español.
Usa únicamente los pasajes proporcionados.
Cada afirmación relevante debe citar documento y página con el formato (NombreArchivo.pdf, p. N),
usando los datos que aparecen en el encabezado del pasaje.
Si los pasajes no contienen evidencia suficiente, comienza la respuesta con "Evidencia insuficiente:"
y explica qué información falta. No inventes datos."""


def retrieve(question, doc_id=None, k=TOP_K):
    qv = vec_literal(embed_texts([question], is_query=True)[0])
    where = "WHERE c.document_id = %s" if doc_id else ""
    params = [qv] + ([doc_id] if doc_id else []) + [qv, k]
    sql = f"""
        SELECT d.filename, c.page_number, c.content,
               1 - (c.embedding <=> %s::vector) AS score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        {where}
        ORDER BY c.embedding <=> %s::vector
        LIMIT %s
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [{"doc": r[0], "page": r[1], "text": r[2], "score": float(r[3])} for r in rows]


def answer(question, doc_id=None):
    passages = retrieve(question, doc_id)
    relevant = [p for p in passages if p["score"] >= MIN_SCORE]

    if not relevant:
        return {
            "respuesta": "Evidencia insuficiente: no se encontraron pasajes relacionados "
                         "con la pregunta en los documentos seleccionados.",
            "pasajes": [],
        }

    context = "\n\n".join(
        f"[Pasaje {i}] Documento: {p['doc']} | Página: {p['page']}\n{p['text']}"
        for i, p in enumerate(relevant, start=1)
    )
    resp = chat_client.chat.completions.create(
        model=CHAT_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Pasajes:\n{context}\n\nPregunta: {question}"},
        ],
    )
    return {"respuesta": resp.choices[0].message.content, "pasajes": relevant}
