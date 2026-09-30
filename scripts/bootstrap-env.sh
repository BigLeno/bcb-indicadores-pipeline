#!/usr/bin/env sh
# Cria o .env a partir do .env.example, com o UID do host e segredos aleatórios.
# Não sobrescreve um .env existente.
set -eu

cd "$(dirname "$0")/.."

if [ -f .env ]; then
    echo ".env já existe; nada a fazer."
    exit 0
fi

command -v openssl >/dev/null || { echo "openssl é necessário para gerar os segredos" >&2; exit 1; }

random_hex() { openssl rand -hex 24; }
# Chave Fernet: 32 bytes em base64 url-safe.
fernet_key() { openssl rand -base64 32 | tr '+/' '-_'; }

sed \
    -e "s|^AIRFLOW_UID=.*|AIRFLOW_UID=$(id -u)|" \
    -e "s|^AIRFLOW_ADMIN_PASSWORD=.*|AIRFLOW_ADMIN_PASSWORD=$(random_hex)|" \
    -e "s|^AIRFLOW_FERNET_KEY=.*|AIRFLOW_FERNET_KEY=$(fernet_key)|" \
    -e "s|^AIRFLOW_API_SECRET_KEY=.*|AIRFLOW_API_SECRET_KEY=$(random_hex)|" \
    -e "s|^AIRFLOW_JWT_SECRET=.*|AIRFLOW_JWT_SECRET=$(random_hex)|" \
    -e "s|^AIRFLOW_DB_PASSWORD=.*|AIRFLOW_DB_PASSWORD=$(random_hex)|" \
    -e "s|^WAREHOUSE_PASSWORD=.*|WAREHOUSE_PASSWORD=$(random_hex)|" \
    .env.example > .env
chmod 600 .env

echo ".env criado. A senha do admin da UI está em AIRFLOW_ADMIN_PASSWORD."
