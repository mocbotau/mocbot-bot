FROM python:3.10 AS base

RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /root/.local/bin/poetry /usr/local/bin/poetry

WORKDIR /app

COPY pyproject.toml poetry.lock /app/

RUN poetry config virtualenvs.create false && \
    poetry install --no-root --only main

COPY . /app

FROM python:3.10-slim AS runtime

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
WORKDIR /app

RUN mkdir logs && chown -R appuser:appgroup /app/logs
# SwagLyrics library needs this directory to write to
RUN mkdir /nonexistent && chown -R appuser:appgroup /nonexistent

COPY --from=base /app /app
COPY --from=base /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages

USER appuser

CMD ["python3", "launcher.py"]
