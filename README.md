# bcb-indicadores-pipeline

Pipeline orquestrado pelo Apache Airflow que ingere séries econômicas da API pública SGS do
Banco Central do Brasil e as modela em camadas (`raw` → `staging` → `marts`) no PostgreSQL.

> Em construção. A documentação completa (arquitetura, decisões técnicas, prints) vem numa fase
> posterior.

## Como rodar

Requisitos: Docker com Compose v2, `make` e `openssl`.

```bash
make up        # gera o .env, sobe tudo e espera os serviços ficarem saudáveis
make trigger   # despausa a DAG bcb_indicadores e dispara uma execução
make test      # testes do pipeline e da API, nos containers
make lint      # ruff
```

Na primeira execução a DAG faz a carga histórica a partir de `carga_inicial`
(`config/series.yaml`). As seguintes são incrementais: começam na última data já carregada.
Para reprocessar um período: `make backfill FROM=2024-01-01 TO=2024-01-31`.

A UI do Airflow fica em <http://localhost:8080>. O usuário é `admin`, e a senha está em
`AIRFLOW_ADMIN_PASSWORD` no `.env`.

A API REST (somente leitura) fica em <http://localhost:8000/api/>, com a documentação
OpenAPI em <http://localhost:8000/api/docs/>. Exemplo:

```bash
curl "http://localhost:8000/api/marts/ipca-mensal/?data_inicio=2024-01-01&data_fim=2024-12-31"
```
