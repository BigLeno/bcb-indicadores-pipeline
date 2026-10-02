FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY pyproject.toml manage.py ./
COPY config ./config
COPY indicadores ./indicadores
# Editável: no docker compose de desenvolvimento o código pode ser montado por cima.
RUN pip install -e .

USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi", "--bind", "0.0.0.0:8000", "--workers", "2", \
     "--access-logfile", "-"]

# pytest e pytest-django ficam fora da imagem de runtime.
FROM runtime AS dev
USER root
RUN pip install -e ".[dev]"
USER app
