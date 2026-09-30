# bcb-indicadores-pipeline

Pipeline orquestrado pelo Apache Airflow que ingere séries econômicas da API pública SGS do
Banco Central do Brasil e as modela em camadas (`raw` → `staging` → `marts`) no PostgreSQL.

> Em construção. A documentação completa (arquitetura, decisões técnicas, prints) vem numa fase
> posterior.

## Como rodar

Requisitos: Docker com Compose v2, `make` e `openssl`.

```bash
make up     # gera o .env, sobe tudo e espera os serviços ficarem saudáveis
make test   # testes no container
make lint   # ruff
```

A UI do Airflow fica em <http://localhost:8080>. O usuário é `admin`, e a senha está em
`AIRFLOW_ADMIN_PASSWORD` no `.env`.
