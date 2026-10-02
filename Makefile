COMPOSE ?= docker compose
TOOLS   := $(COMPOSE) run --rm tools
NO_DB   := $(COMPOSE) run --rm --no-deps tools
DAG_ID  ?= bcb_indicadores

.DEFAULT_GOAL := help
.PHONY: help up down clean ps logs build migrate test test-pipeline test-api lint format psql trigger backfill

help: ## Lista os comandos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-10s %s\n", $$1, $$2}'

.env:
	@./scripts/bootstrap-env.sh

logs/:
	@mkdir -p logs

up: .env logs/ ## Sobe Airflow + Postgres e espera ficarem saudáveis
	$(COMPOSE) up -d --build --wait
	@echo "Airflow UI: http://localhost:$$(grep -E '^AIRFLOW_HOST_PORT=' .env | cut -d= -f2)"
	@echo "API docs:   http://localhost:$$(grep -E '^API_HOST_PORT=' .env | cut -d= -f2)/api/docs/"

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
	$(COMPOSE) --profile tools build tools api-tools

migrate: .env ## Aplica as migrations pendentes no warehouse
	$(COMPOSE) run --rm warehouse-migrate

test: test-pipeline test-api ## Todos os testes (pipeline + API)

test-pipeline: .env ## Testes do pipeline: unitários + integração (ex.: make test-pipeline ARGS="-m 'not integration'")
	$(TOOLS) pytest $(ARGS)

test-api: .env ## Testes da API Django contra o schema real do warehouse
	$(COMPOSE) run --rm api-tools pytest $(ARGS)

lint: .env ## ruff check + verificação de formatação
	$(NO_DB) sh -c "ruff check . && ruff format --check ."

format: .env ## Corrige lint e formatação
	$(NO_DB) sh -c "ruff format . && ruff check --fix ."

psql: .env ## Abre um psql no warehouse
	$(COMPOSE) exec warehouse sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

trigger: .env ## Despausa e dispara uma execução da DAG
	$(COMPOSE) exec airflow-scheduler airflow dags unpause $(DAG_ID)
	$(COMPOSE) exec airflow-scheduler airflow dags trigger $(DAG_ID)

# Uma run por dia, cada uma buscando o dia da sua data lógica. TO é inclusivo: sem o
# T23:59:59 a run das 09:00 do último dia ficaria fora do intervalo.
backfill: .env ## Reprocessa um período, TO inclusivo (ex.: make backfill FROM=2024-01-01 TO=2024-01-31)
	@test -n "$(FROM)" -a -n "$(TO)" || { echo "uso: make backfill FROM=AAAA-MM-DD TO=AAAA-MM-DD"; exit 1; }
	$(COMPOSE) exec airflow-scheduler airflow backfill create \
		--dag-id $(DAG_ID) --from-date $(FROM) --to-date $(TO)T23:59:59 \
		--reprocess-behavior completed --max-active-runs 1
