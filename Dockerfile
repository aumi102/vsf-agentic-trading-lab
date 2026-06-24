FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV QUESTDB_URL=http://questdb:9000
ENV VSF_DEEPAGENTS_MODEL=gpt-4.1-mini

WORKDIR /app

RUN python -m pip install --no-cache-dir --upgrade pip

COPY requirements.txt requirements.txt
COPY requirements-research.txt requirements-research.txt
RUN python -m pip install --no-cache-dir -r requirements.txt -r requirements-research.txt

COPY src src
COPY scripts scripts
COPY docs docs

EXPOSE 8010

CMD ["sh", "-c", "python scripts/run_questdb_agent_backend.py --host 0.0.0.0 --port ${PORT:-8010} --questdb-url ${QUESTDB_URL:-http://questdb:9000}"]
