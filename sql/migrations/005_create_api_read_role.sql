-- Papel de leitura usado pela API (Django). Sem LOGIN: o usuário que a API usa para
-- conectar é criado à parte, com senha vinda do ambiente (bcb_pipeline.acesso), e
-- recebe este papel. Assim nenhuma senha fica versionada.
--
-- Papéis são do cluster, não do banco: o IF NOT EXISTS deixa a migration rodar de novo
-- em outro banco do mesmo servidor (os bancos descartáveis dos testes, por exemplo).
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'api_leitura') THEN
        CREATE ROLE api_leitura NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA marts, staging TO api_leitura;
GRANT SELECT ON ALL TABLES IN SCHEMA marts TO api_leitura;
GRANT SELECT ON staging.serie, staging.serie_valor TO api_leitura;

-- Marts criados por migrations futuras já nascem legíveis pela API.
ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT SELECT ON TABLES TO api_leitura;
