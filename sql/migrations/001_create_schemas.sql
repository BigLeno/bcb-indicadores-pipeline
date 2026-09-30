-- Camadas do pipeline, uma por schema.
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS marts;

COMMENT ON SCHEMA raw IS 'Payloads JSON da API SGS, como recebidos, com metadados da consulta.';
COMMENT ON SCHEMA staging IS 'Séries tipadas e limpas: uma linha por (serie_id, data).';
COMMENT ON SCHEMA marts IS 'Tabelas derivadas, prontas para consumo pela API.';
