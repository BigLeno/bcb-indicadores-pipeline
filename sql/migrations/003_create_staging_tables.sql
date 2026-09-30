-- Catálogo das séries, sincronizado a partir de config/series.yaml.
CREATE TABLE staging.serie (
    serie_id       integer PRIMARY KEY,
    nome           text        NOT NULL,
    periodicidade  text        NOT NULL,
    unidade        text        NOT NULL,
    atualizado_em  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT serie_periodicidade_valida CHECK (periodicidade IN ('diaria', 'mensal'))
);

COMMENT ON TABLE staging.serie IS 'Séries configuradas no pipeline; serie_id é o código SGS.';

-- Valores tipados. A PK garante no máximo uma observação por série e data,
-- e é o alvo do upsert (INSERT ... ON CONFLICT).
CREATE TABLE staging.serie_valor (
    serie_id       integer     NOT NULL REFERENCES staging.serie (serie_id),
    data           date        NOT NULL,
    valor          numeric     NOT NULL,
    carregado_em   timestamptz NOT NULL DEFAULT now(),
    atualizado_em  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (serie_id, data)
);

COMMENT ON TABLE staging.serie_valor IS 'Observações das séries SGS, uma por (serie_id, data).';
COMMENT ON COLUMN staging.serie_valor.valor IS 'numeric sem precisão fixa: guarda o valor exato publicado pelo BCB.';
COMMENT ON COLUMN staging.serie_valor.atualizado_em IS 'Muda só quando o valor muda (revisão do BCB).';
