-- Marts: materialized views sobre staging.serie_valor, atualizadas pela DAG com
-- REFRESH MATERIALIZED VIEW CONCURRENTLY (exige o índice único de cada uma).
--
-- Taxas compostas: o acumulado de taxas percentuais r_i é prod(1 + r_i/100) - 1.
-- Postgres não tem agregado de produto, então usa-se exp(sum(ln(1 + r_i/100))).
-- ln/exp sobre numeric são exatos o bastante para 6 casas decimais.
--
-- Os códigos SGS (433, 12, 1) são identificadores públicos e estáveis do BCB.

-- IPCA (433): variação mensal, acumulada no ano e em 12 meses.
CREATE MATERIALIZED VIEW marts.ipca_mensal AS
WITH base AS (
    SELECT data AS mes,
           valor AS variacao_mensal_pct,
           ln(1 + valor / 100) AS log_fator
      FROM staging.serie_valor
     WHERE serie_id = 433
)
SELECT mes,
       variacao_mensal_pct,
       round((exp(sum(log_fator) OVER ano) - 1) * 100, 6) AS acumulado_ano_pct,
       -- RANGE por intervalo (e não ROWS) para um mês faltando não deslocar a janela;
       -- só há acumulado quando os 12 meses estão presentes.
       CASE WHEN count(*) OVER doze_meses = 12
            THEN round((exp(sum(log_fator) OVER doze_meses) - 1) * 100, 6)
       END AS acumulado_12m_pct
  FROM base
WINDOW ano AS (PARTITION BY date_trunc('year', mes) ORDER BY mes),
       doze_meses AS (ORDER BY mes RANGE BETWEEN INTERVAL '11 months' PRECEDING AND CURRENT ROW);

CREATE UNIQUE INDEX ipca_mensal_mes_uidx ON marts.ipca_mensal (mes);
COMMENT ON MATERIALIZED VIEW marts.ipca_mensal IS
    'IPCA (SGS 433): variação mensal e acumulados no ano e em 12 meses, em %.';

-- CDI (12): acumulado em cada mês, composto dia a dia.
CREATE MATERIALIZED VIEW marts.cdi_mensal AS
SELECT date_trunc('month', data)::date AS mes,
       count(*) AS dias_uteis,
       round((exp(sum(ln(1 + valor / 100))) - 1) * 100, 6) AS acumulado_mes_pct,
       max(data) AS ultima_data
  FROM staging.serie_valor
 WHERE serie_id = 12
 GROUP BY 1;

CREATE UNIQUE INDEX cdi_mensal_mes_uidx ON marts.cdi_mensal (mes);
COMMENT ON MATERIALIZED VIEW marts.cdi_mensal IS
    'CDI (SGS 12) acumulado no mês, em %. O mês corrente é parcial até ultima_data.';

-- Dólar (1): cotação diária e variação em relação ao dia útil anterior.
CREATE MATERIALIZED VIEW marts.dolar_diario AS
SELECT data,
       valor AS cotacao,
       lag(valor) OVER w AS cotacao_anterior,
       round((valor / lag(valor) OVER w - 1) * 100, 6) AS variacao_diaria_pct
  FROM staging.serie_valor
 WHERE serie_id = 1
WINDOW w AS (ORDER BY data);

CREATE UNIQUE INDEX dolar_diario_data_uidx ON marts.dolar_diario (data);
COMMENT ON MATERIALIZED VIEW marts.dolar_diario IS
    'Dólar comercial de venda (SGS 1) e variação diária, em %.';

-- Dólar (1): fechamento do mês (último dia útil) e variação sobre o fechamento anterior.
CREATE MATERIALIZED VIEW marts.dolar_mensal AS
WITH fechamento AS (
    SELECT DISTINCT ON (date_trunc('month', data))
           date_trunc('month', data)::date AS mes,
           data AS data_fechamento,
           valor AS cotacao_fechamento
      FROM staging.serie_valor
     WHERE serie_id = 1
     ORDER BY date_trunc('month', data), data DESC
)
SELECT mes,
       data_fechamento,
       cotacao_fechamento,
       round((cotacao_fechamento / lag(cotacao_fechamento) OVER (ORDER BY mes) - 1) * 100, 6)
           AS variacao_mensal_pct
  FROM fechamento;

CREATE UNIQUE INDEX dolar_mensal_mes_uidx ON marts.dolar_mensal (mes);
COMMENT ON MATERIALIZED VIEW marts.dolar_mensal IS
    'Dólar (SGS 1): fechamento mensal e variação sobre o mês anterior, em %. '
    'O mês corrente usa a última cotação disponível.';
