COMPOSE ?= docker compose
TOOLS   := $(COMPOSE) run --rm tools
DAG_ID  ?= bcb_indicadores

.DEFAULT_GOAL := help
.PHONY: help up down clean ps logs build migrate test lint format psql backfill

help: ## Lista os comandos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-10s %s\n", $$1, $$2}'

.env:
	@./scripts/bootstrap-env.sh

logs/:
	@mkdir -p logs

up: .env logs/ ## Sobe Airflow + Postgres e espera ficarem saudáveis
	$(COMPOSE) up -d --build --wait
	@echo "Airflow UI: http://localhost:$$(grep -E '^AIRFLOW_HOST_PORT=' .env | cut -d= -f2)"

down: ## Para os containers (mantém os dados)
	$(COMPOSE) down

clean: ## Para os containers e APAGA os volumes (metadata e warehouse)
	$(COMPOSE) down --volumes --remove-orphans

ps: ## Estado dos serviços
	$(COMPOSE) ps

logs: ## Acompanha os logs (ex.: make logs S=airflow-scheduler)
	$(COMPOSE) logs -f $(S)

build: .env ## Reconstrói as imagens
	$(COMPOSE) build
	$(COMPOSE) --profile tools build tools

migrate: .env ## Aplica as migrations pendentes no warehouse
	$(COMPOSE) run --rm warehouse-migrate

test: .env ## Roda o pytest no container de ferramentas
	$(TOOLS) pytest $(ARGS)

lint: .env ## ruff check + verificação de formatação
	$(TOOLS) sh -c "ruff check . && ruff format --check ."

format: .env ## Corrige lint e formatação
	$(TOOLS) sh -c "ruff check --fix . && ruff format ."

psql: .env ## Abre um psql no warehouse
	$(COMPOSE) exec warehouse sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

backfill: .env ## Backfill agendado pelo scheduler (ex.: make backfill FROM=2024-01-01 TO=2024-01-31)
	@test -n "$(FROM)" -a -n "$(TO)" || { echo "uso: make backfill FROM=AAAA-MM-DD TO=AAAA-MM-DD"; exit 1; }
	$(COMPOSE) exec airflow-scheduler airflow backfill create \
		--dag-id $(DAG_ID) --from-date $(FROM) --to-date $(TO) \
		--reprocess-behavior completed --max-active-runs 1
