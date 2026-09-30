-- Uma linha por resposta da API: uma série e uma janela de datas.
-- O payload fica intacto para permitir reprocessar o staging sem chamar a API de novo.
CREATE TABLE raw.sgs_payload (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    serie_id        integer     NOT NULL,
    janela_inicio   date        NOT NULL,
    janela_fim      date        NOT NULL,
    payload         jsonb       NOT NULL,
    payload_sha256  text        NOT NULL,
    qtd_registros   integer     NOT NULL,
    run_id          text,
    ingerido_em     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sgs_payload_janela_valida CHECK (janela_inicio <= janela_fim),
    -- Idempotência: a mesma resposta para a mesma janela é gravada uma vez só.
    -- Uma resposta diferente (o BCB revisou valores) vira uma linha nova e fica no histórico.
    CONSTRAINT sgs_payload_resposta_unica UNIQUE (serie_id, janela_inicio, janela_fim, payload_sha256)
);

CREATE INDEX sgs_payload_serie_ingerido_idx ON raw.sgs_payload (serie_id, ingerido_em DESC);

COMMENT ON TABLE raw.sgs_payload IS 'Respostas da API SGS do BCB, uma por série e janela consultada.';
COMMENT ON COLUMN raw.sgs_payload.payload IS 'Lista [{"data": "dd/MM/aaaa", "valor": "..."}] como veio da API.';
COMMENT ON COLUMN raw.sgs_payload.run_id IS 'run_id do Airflow que fez a ingestão.';
