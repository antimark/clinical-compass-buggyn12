# Linux/arm64 jury runtime: image digests resolved and recorded on 2026-10-27.
FROM node:22.23.4-bookworm-slim@sha256:ceb43e5c219139035fb742900629e4abed89fe0997f7c03250c499e1f2710c9e AS node_runtime
FROM python:3.11.17-slim-bookworm@sha256:8f51ccb8569b75cf967ffe3e1638b9953042bf36142d7032cbb6f0696c9cd2c6
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend:/app/docker:/app CC_WORKSPACE=/workspace
WORKDIR /app
COPY docker/requirements.lock /app/docker/requirements.lock
RUN python -m pip install --no-cache-dir -r /app/docker/requirements.lock \
    && python -m pip check \
    && groupadd --gid 10001 compass \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin compass \
    && install -d -m 0700 -o 10001 -g 10001 /workspace
# Node is used by the shipped source contract tests; no frontend build/framework swap.
COPY --from=node_runtime /usr/local/bin/node /usr/local/bin/node
COPY --chown=10001:10001 backend /app/backend
COPY --chown=10001:10001 frontend /app/frontend
COPY --chown=10001:10001 migrations /app/migrations
COPY --chown=10001:10001 clinical_catalog_data /app/clinical_catalog_data
COPY --chown=10001:10001 research_data /app/research_data
COPY --chown=10001:10001 contracts /app/contracts
COPY --chown=10001:10001 reference /app/reference
COPY --chown=10001:10001 scripts /app/scripts
COPY --chown=10001:10001 tests /app/tests
COPY --chown=10001:10001 tests_e2e /app/tests_e2e
COPY --chown=10001:10001 tests_ui /app/tests_ui
COPY --chown=10001:10001 demo_completion /app/demo_completion
COPY --chown=10001:10001 docs /app/docs
COPY --chown=10001:10001 docker /app/docker
COPY --chown=10001:10001 AGENTS.md README.md EVALUATION_POLICY_ADDENDUM.md alembic.ini pytest.ini environment.yml evaluation.config.example .gitignore /app/
USER 10001:10001
EXPOSE 8766
HEALTHCHECK --interval=15s --timeout=4s --start-period=30s --retries=3 CMD ["python", "/app/docker/healthcheck.py"]
ENTRYPOINT ["/bin/sh", "/app/docker/entrypoint.sh"]
CMD ["python", "-m", "gunicorn", "--config", "/app/docker/gunicorn.conf.py", "wsgi:app"]
