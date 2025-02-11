FROM python:3.10 AS base

WORKDIR /app

COPY requirements.txt /app
RUN pip install -r requirements.txt

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
