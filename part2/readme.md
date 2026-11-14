# RAG de libros y manuales en español

Aplicación en Python que responde preguntas en español con evidencia de PDF de texto seleccionable. Cada respuesta cita el documento y la página física, y muestra los pasajes utilizados. Si la evidencia es insuficiente, lo indica.

## Características

- Ingesta de PDF de texto seleccionable, por lote o desde la interfaz web.
- Fragmentos que pertenecen a una sola página física (numerada desde 1).
- Reporte por archivo: páginas, fragmentos, páginas sin texto y errores de lectura.
- Persistencia en PostgreSQL con **pgvector**. El índice sobrevive a los reinicios.
- Idempotencia: el mismo archivo (hash SHA-256) no duplica documentos ni fragmentos.
- Búsqueda por similitud coseno, sobre todos los documentos o filtrada por uno.
- Embeddings y generación con la API de OpenAI o con modelos locales.
- Límite total de 900 páginas entre todos los documentos (configurable).

## Estructura

```
rag-libros/
├── app.py            # Interfaz web Flask
├── db.py             # Conexión y esquema PostgreSQL + pgvector
├── ingest.py         # Lectura de PDF, fragmentación y persistencia
├── llm.py            # Embeddings y generación (OpenAI o local)
├── rag.py            # Recuperación vectorial y respuesta con citas
├── requirements.txt
├── Dockerfile
├── .dockerignore
├── .env              # Configuración y secretos (no subir a Git ni a Docker Hub)
└── pdfs/             # Opcional: PDF para ingesta por lote
```

## Requisitos

- Python 3.10 o superior, o Docker.
- PostgreSQL 15 o superior con la extensión `vector` disponible (en RDS, `CREATE EXTENSION vector;`).
- Clave de API de OpenAI, o un servidor local compatible con la API de OpenAI.

## Configuración

Crea un archivo `.env` en la raíz. No pongas comentarios en la misma línea que un valor.

```env
SECRET_KEY=valor-aleatorio-largo
DATABASE_URL=postgresql://USUARIO:PASSWORD_URL_ENCODED@ENDPOINT-RDS:5432/BASE?sslmode=require

EMBED_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536

OPENAI_API_KEY=sk-...
CHAT_MODEL=gpt-4o-mini

TOP_K=6
MIN_SCORE=0.30
CHUNK_SIZE=1000
CHUNK_OVERLAP=150
MAX_PAGES_TOTAL=900
PDF_DIR=pdfs
```

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `DATABASE_URL` | Cadena de conexión. Usa `postgresql://` (no `postgresql+psycopg2://`) | Obligatoria |
| `EMBED_PROVIDER` | `openai` o `local` | `openai` |
| `EMBEDDING_MODEL` | Modelo de embeddings | `text-embedding-3-small` |
| `EMBEDDING_DIM` | Dimensión del vector. Debe coincidir con el modelo | `1536` |
| `OPENAI_API_KEY` | Clave de OpenAI | Obligatoria con `openai` |
| `OPENAI_BASE_URL` | URL compatible con OpenAI (p. ej. `http://localhost:11434/v1` para Ollama) | Vacío |
| `CHAT_MODEL` | Modelo de generación | `gpt-4o-mini` |
| `TOP_K` | Fragmentos recuperados | `6` |
| `MIN_SCORE` | Similitud mínima para usar un fragmento | `0.30` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | Tamaño y solapamiento de fragmentos, en caracteres | `1000` / `150` |
| `MAX_PAGES_TOTAL` | Límite de páginas entre todos los documentos | `900` |
| `PDF_DIR` | Carpeta para la ingesta por lote | `pdfs` |

Las contraseñas con símbolos deben codificarse en URL (`@` → `%40`, `#` → `%23`, `$` → `%24`).

### Modelos locales

```env
EMBED_PROVIDER=local
EMBEDDING_MODEL=intfloat/multilingual-e5-base
EMBEDDING_DIM=768
```

Descomenta `sentence-transformers` en `requirements.txt`. Los modelos e5 usan los prefijos `query:` y `passage:`, que el código añade solo.

> **Importante:** si cambias `EMBEDDING_MODEL` o `EMBEDDING_DIM`, borra la tabla `chunks` y vuelve a ingerir. Los vectores de distinta dimensión no se pueden mezclar.

## Instalación

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

### Ingesta por lote

Copia los PDF a `pdfs/` y ejecuta:

```bash
python ingest.py
```

### Interfaz web

```bash
python app.py
```

Abre `http://127.0.0.1:5000`. Sube los PDF, revisa el resultado de la ingesta y haz preguntas sobre todos los documentos o sobre uno.

Para producción:

```bash
gunicorn --bind 0.0.0.0:8000 --workers 2 --timeout 600 app:app
```

## Docker

```bash
# Construir y subir (en tu equipo)
docker login -u <USUARIO_DOCKERHUB>
docker buildx build --platform linux/amd64 -t <USUARIO_DOCKERHUB>/rag-libros:1.0 --push .

# Ejecutar en la EC2
docker pull <USUARIO_DOCKERHUB>/rag-libros:1.0
docker run -d --name rag-libros -p 80:8000 \
  --env-file ~/.env --restart unless-stopped \
  <USUARIO_DOCKERHUB>/rag-libros:1.0
docker logs -f rag-libros
```

## Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `role "swp" does not exist` o conexión por socket | `DATABASE_URL` no se carga desde `.env` | Revisa `load_dotenv()` en `db.py` y `echo $DATABASE_URL` |
| `Connection timed out` | Security group o red bloquean 5432 | Revisa reglas de entrada de RDS y prueba `nc -vz <ENDPOINT> 5432` |
| `cryptography>=3.1 is required for AES algorithm` | PDF cifrado con AES | Instala `cryptography` (ya está en `requirements.txt`) |
| Páginas en `paginas_sin_texto` | Páginas escaneadas o imágenes | Aplica OCR (p. ej. Tesseract) |
| `ya_indexado` | Comportamiento esperado | El archivo ya estaba guardado |
| `rechazado_limite_total` | Se superaría `MAX_PAGES_TOTAL` | Aumenta el valor o elimina documentos |
| "Evidencia insuficiente" con preguntas válidas | `MIN_SCORE` muy alto | Revisa las similitudes y ajusta el valor |

## Limitaciones

- Solo procesa PDF con texto seleccionable. No hace OCR.
- Las respuestas dependen de los fragmentos recuperados. Revisa siempre las citas.
- La interfaz web no tiene autenticación. Restringe el acceso con el security group o protégela antes de publicarla.

## Evaluación

Prepara preguntas con la respuesta y la página esperadas. Comprueba que la página aparezca entre los pasajes recuperados (recall@k) y que la respuesta coincida con el PDF.

