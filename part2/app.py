#!/usr/bin/env python3

import os

from flask import Flask, render_template_string, request

from db import get_conn, init_db
from ingest import ingest_pdf
from rag import answer

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev")
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024
init_db()

PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Consulta de manuales</title>
<style>
body{font-family:sans-serif;max-width:900px;margin:auto;padding:20px}
table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px;text-align:left}
.pasaje{background:#f4f4f4;padding:10px;margin:8px 0;border-left:4px solid #357}
textarea{width:100%}
</style></head><body>
<h1>Consulta de manuales</h1>

<h2>1. Cargar PDF</h2>
<form method="post" action="/upload" enctype="multipart/form-data">
  <input type="file" name="pdfs" accept="application/pdf" multiple required>
  <button type="submit">Procesar</button>
</form>
{% if results %}
<table>
<tr><th>Archivo</th><th>Estado</th><th>Páginas</th><th>Fragmentos</th><th>Sin texto</th><th>Errores</th></tr>
{% for r in results %}
<tr><td>{{ r.archivo }}</td><td>{{ r.estado }}</td><td>{{ r.paginas }}</td><td>{{ r.fragmentos }}</td>
<td>{{ r.paginas_sin_texto|join(', ') }}</td><td>{{ r.errores|join('; ') }}</td></tr>
{% endfor %}
</table>
{% endif %}

<h2>2. Preguntar</h2>
<form method="post" action="/ask">
  <textarea name="question" rows="3" required>{{ question or '' }}</textarea>
  <p>Documentos:
  <select name="doc_id">
    <option value="">Los tres documentos</option>
    {% for d in docs %}
    <option value="{{ d.id }}" {% if d.id == selected %}selected{% endif %}>{{ d.filename }} ({{ d.page_count }} págs.)</option>
    {% endfor %}
  </select></p>
  <button type="submit">Preguntar</button>
</form>

{% if answer %}
<h2>Respuesta</h2>
<div style="white-space:pre-wrap">{{ answer.respuesta }}</div>
<h3>Pasajes utilizados</h3>
{% for p in answer.pasajes %}
<div class="pasaje"><b>{{ p.doc }}, p. {{ p.page }}</b> (similitud {{ '%.2f'|format(p.score) }})<br>{{ p.text }}</div>
{% else %}
<p>No hay pasajes que superen el umbral de similitud.</p>
{% endfor %}
{% endif %}
</body></html>"""


def list_documents():
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, filename, page_count FROM documents ORDER BY id")
        return [{"id": r[0], "filename": r[1], "page_count": r[2]} for r in cur.fetchall()]


def render(**kwargs):
    return render_template_string(PAGE, docs=list_documents(), **kwargs)


@app.route("/")
def index():
    return render()


@app.route("/upload", methods=["POST"])
def upload():
    results = []
    for f in request.files.getlist("pdfs"):
        if f.filename.lower().endswith(".pdf"):
            results.append(ingest_pdf(f.filename, f.read()))
    return render(results=results)


@app.route("/ask", methods=["POST"])
def ask():
    question = request.form.get("question", "").strip()
    doc_id = request.form.get("doc_id") or None
    doc_id = int(doc_id) if doc_id else None
    result = answer(question, doc_id) if question else None
    return render(answer=result, question=question, selected=doc_id)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
