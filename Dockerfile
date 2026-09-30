# Imagem do Airflow com o pacote bcb_pipeline instalado.
ARG AIRFLOW_VERSION=3.3.2
ARG PYTHON_VERSION=3.12

FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION} AS runtime
ARG AIRFLOW_VERSION
ARG PYTHON_VERSION
ENV CONSTRAINTS_URL=https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt

# Grupo 0 com escrita: o container roda com UID arbitrário (AIRFLOW_UID) e GID 0.
USER root
RUN install -d -o airflow -g 0 -m 775 /opt/airflow/project
USER airflow

WORKDIR /opt/airflow/project
COPY --chown=airflow:0 pyproject.toml README.md ./
COPY --chown=airflow:0 src ./src
# Instalação editável: no docker compose o diretório src/ é montado por cima,
# então mudanças no código valem sem rebuild. Fixar apache-airflow e usar as
# constraints oficiais impede que o pip troque as versões do próprio Airflow.
RUN pip install --no-cache-dir \
        "apache-airflow==${AIRFLOW_VERSION}" \
        --constraint "${CONSTRAINTS_URL}" \
        -e .
WORKDIR /opt/airflow

# Ferramentas de teste e lint ficam fora da imagem de runtime.
FROM runtime AS dev
WORKDIR /opt/airflow/project
RUN pip install --no-cache-dir \
        "apache-airflow==${AIRFLOW_VERSION}" \
        --constraint "${CONSTRAINTS_URL}" \
        -e ".[dev]"
