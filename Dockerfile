FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV QUESTDB_URL=http://questdb:9000
ENV VSF_DEEPAGENTS_MODEL=gpt-4.1-mini

WORKDIR /app
ARG INSTALL_DEEPAGENTS=false

RUN python -m pip install --no-cache-dir --upgrade pip

COPY requirements-backend.txt requirements-backend.txt
COPY requirements-deepagents.txt requirements-deepagents.txt
RUN python -m pip install --no-cache-dir --retries 10 --timeout 120 -r requirements-backend.txt \
    && if [ "$INSTALL_DEEPAGENTS" = "true" ]; then \
        python -m pip install --no-cache-dir --retries 10 --timeout 120 -r requirements-deepagents.txt; \
    fi

COPY src src
COPY scripts scripts
COPY docs docs

EXPOSE 8010

CMD ["sh", "-c", "python scripts/run_questdb_agent_backend.py --host 0.0.0.0 --port ${PORT:-8010} --questdb-url ${QUESTDB_URL:-http://questdb:9000}"]
