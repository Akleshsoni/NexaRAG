FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    FASTEMBED_CACHE_PATH=/opt/fastembed \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model and tokenizer vocabulary into the image so containers
# never download them at runtime (and `docker compose down` doesn't lose them).
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/opt/fastembed')" \
 && python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

COPY app ./app
COPY eval ./eval
COPY migrations ./migrations
COPY alembic.ini .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
