# Arquitetura

## Componentes

```mermaid
flowchart TB
    SGS["API SGS do Banco Central"]
    YAML[/"config/series.yaml"/]

    subgraph AIRFLOW["Apache Airflow 3 · DAG bcb_indicadores · LocalExecutor"]
        direction LR
        P["preparar_series"] --> E["extrair_raw × N"]
        E --> C["carregar_staging × N"]
        C --> Q["checar_qualidade × N"]
        Q --> M["atualizar_marts"]
    end

    subgraph WAREHOUSE["Postgres · warehouse"]
        direction LR
        RAW[("raw<br/>payload bruto")] --> STG[("staging<br/>tipado · PK serie_id + data")]
        STG --> MARTS[("marts<br/>materialized views")]
    end

    META[("Postgres<br/>metadata do Airflow")]
    API["API Django + DRF<br/>somente leitura"]
    USER(["curl · Swagger UI"])

    SGS -- "JSON em janelas de 5 anos<br/>timeout + retry com backoff" --> AIRFLOW
    YAML -. "uma task por série" .-> AIRFLOW
    AIRFLOW --- META
    AIRFLOW -- "insert idempotente · upsert · refresh" --> WAREHOUSE
    WAREHOUSE -- "usuário bcb_api (read only)" --> API
    API --> USER
```

| Task | Lê | Escreve |
|---|---|---|
| `preparar_series` | `config/series.yaml` | `staging.serie` (catálogo) |
| `extrair_raw` × N | API SGS | `raw.sgs_payload` (`ON CONFLICT DO NOTHING`, dedup por sha256) |
| `carregar_staging` × N | `raw.sgs_payload` | `staging.serie_valor` (upsert pela PK) |
| `checar_qualidade` × N | `staging.serie_valor` | nada; falha a task se houver violação |
| `atualizar_marts` | `staging.serie_valor` | `marts.*` (`REFRESH MATERIALIZED VIEW CONCURRENTLY`) |

- Dois Postgres separados: o metadata do Airflow e o warehouse têm credenciais, volumes
  e ciclos de vida independentes.
- Toda a lógica fica em `src/bcb_pipeline/`, sem dependência do Airflow. A DAG
  (`dags/bcb_indicadores.py`) só orquestra.
- A API conecta com um usuário que só tem `SELECT` em `marts` e `staging` (sem acesso a
  `raw`) e com `default_transaction_read_only = on`.

## Uma execução da DAG

```mermaid
sequenceDiagram
    autonumber
    participant S as Scheduler
    participant T as Task extrair_raw (série N)
    participant B as API SGS
    participant W as Warehouse

    S->>T: run diária 09:00 (America/Sao_Paulo)
    T->>W: max(data) da série em staging
    W-->>T: última data carregada (ou nada)
    Note over T: incremental: da última data (inclusive) até hoje<br/>sem dados: desde carga_inicial do YAML<br/>backfill: o dia da data lógica
    loop uma janela de até 5 anos
        T->>B: GET dataInicial/dataFinal
        alt 200 com lista
            B-->>T: registros
        else "Value(s) not found" (404 ou 200)
            B-->>T: janela vazia
        else 429, 5xx, timeout ou página HTML
            B-->>T: erro transitório, nova tentativa com backoff
        end
        T->>W: INSERT raw ... ON CONFLICT DO NOTHING
    end
    T-->>S: ids das linhas de raw (XCom)
    Note over S,W: carregar_staging: upsert pela PK (serie_id, data)<br/>checar_qualidade: falha = task falha, sem retry<br/>atualizar_marts: só se todas as séries passarem
```

## Modelo de dados

```mermaid
erDiagram
    SGS_PAYLOAD {
        bigint id PK
        int serie_id
        date janela_inicio
        date janela_fim
        jsonb payload
        text payload_sha256 "único por série + janela"
        int qtd_registros
        text run_id
        timestamptz ingerido_em
    }
    SERIE {
        int serie_id PK "código SGS"
        text nome
        text periodicidade "diaria ou mensal"
        text unidade
        timestamptz atualizado_em
    }
    SERIE_VALOR {
        int serie_id PK, FK
        date data PK
        numeric valor "sem precisão fixa"
        timestamptz carregado_em
        timestamptz atualizado_em "muda só em revisão real"
    }
    SERIE ||--o{ SERIE_VALOR : "tem"
    SGS_PAYLOAD }o..|| SERIE : "origem de"
```

Os marts são materialized views sobre `staging.serie_valor`, cada uma com um índice
único, que é o requisito do `REFRESH CONCURRENTLY`:

| Mart | Chave | Conteúdo |
|---|---|---|
| `marts.ipca_mensal` | `mes` | variação mensal, acumulado no ano e em 12 meses (só com 12 meses consecutivos) |
| `marts.cdi_mensal` | `mes` | CDI composto no mês, dias úteis e última data (o mês corrente é parcial) |
| `marts.dolar_diario` | `data` | cotação de venda e variação sobre o dia útil anterior |
| `marts.dolar_mensal` | `mes` | fechamento (último dia útil) e variação sobre o mês anterior |

O acumulado de taxas é `prod(1 + r/100) - 1`, calculado como `exp(sum(ln(1 + r/100))) - 1`,
porque o Postgres não tem agregado de produto. Os resultados foram conferidos com os números
oficiais: IPCA de 4,62% em 2023 e 4,83% em 2024, e CDI de 0,97% em janeiro de 2024.
