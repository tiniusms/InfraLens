# Portable public API image.
# Contents: source, the committed evaluation summary, and requirements-api.txt.
# The four local EIA/PJM artifacts are not copied. Build context exclusions are
# in .dockerignore. This image was not published from this checkpoint.
FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    INFRALENS_ROOT=/app

WORKDIR /app

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin infralens

COPY requirements-api.txt pyproject.toml README.md ./
COPY src ./src
COPY docs/final_eia_holdout_oneshot.json ./docs/final_eia_holdout_oneshot.json
COPY deploy/start_api.sh ./deploy/start_api.sh

RUN pip install --no-cache-dir --no-deps -r requirements-api.txt \
    && pip install --no-cache-dir --no-deps . \
    && chmod 755 /app/deploy/start_api.sh \
    && chown -R root:root /app \
    && chmod -R a-w /app

USER infralens

EXPOSE 8000

CMD ["/app/deploy/start_api.sh"]
