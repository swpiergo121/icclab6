#!/usr/bin/env python3

import os
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

EMBED_PROVIDER = os.getenv("EMBED_PROVIDER", "openai")
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")

chat_client = OpenAI(
    base_url=os.getenv("OPENAI_BASE_URL") or None,
    api_key=os.getenv("OPENAI_API_KEY", "no-key"),
)

_local_model = None


def embed_texts(texts, is_query=False):
    """Devuelve una lista de vectores para una lista de textos."""
    global _local_model
    if EMBED_PROVIDER == "local":
        if _local_model is None:
            from sentence_transformers import SentenceTransformer
            _local_model = SentenceTransformer(EMBED_MODEL)
        prefix = ""
        if "e5" in EMBED_MODEL:  # los modelos e5 requieren prefijos
            prefix = "query: " if is_query else "passage: "
        vectors = _local_model.encode(
            [prefix + t for t in texts], normalize_embeddings=True, batch_size=32
        )
        return [v.tolist() for v in vectors]

    vectors = []
    for i in range(0, len(texts), 100):
        resp = chat_client.embeddings.create(model=EMBED_MODEL, input=texts[i:i + 100])
        vectors += [d.embedding for d in resp.data]
    return vectors


def vec_literal(vector):
    return "[" + ",".join(str(x) for x in vector) + "]"
