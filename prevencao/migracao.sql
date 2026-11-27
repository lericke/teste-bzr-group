-- Migração de prevenção sobre case-candidato/schema.sql (PostgreSQL).
-- Mesmo SQL da seção "Prevenção > No banco (SQL)" de relatorio/diagnostico.md.
-- Os números entre parênteses são os problemas do diagnóstico.
--
-- Roda numa transação: se qualquer passo falhar, nada é aplicado.
-- Dois passos ficam para depois do preenchimento dos dados antigos (ver o fim do arquivo).

BEGIN;

-- 1. Arquivos recebidos: guarda o original e o hash (9).
CREATE TABLE arquivo_recebido (
    id            BIGSERIAL   PRIMARY KEY,
    tipo          TEXT        NOT NULL CHECK (tipo IN ('pagamentos', 'tribunal', 'apresentacoes')),
    nome          TEXT        NOT NULL,
    sha256        CHAR(64)    NOT NULL UNIQUE,  -- o mesmo arquivo não é registrado duas vezes
    conteudo      BYTEA       NOT NULL,         -- exatamente como chegou
    recebido_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processado_em TIMESTAMPTZ,
    status        TEXT        NOT NULL DEFAULT 'recebido'
                  CHECK (status IN ('recebido', 'processado', 'recusado'))
);

-- 2. Número do processo: só os 20 dígitos, máscara gerada para exibir (10, 13).
-- CHAR completa com espaços; VARCHAR não. Os dados atuais já cabem em 20 caracteres.
ALTER TABLE precatorio ALTER COLUMN numero_processo TYPE VARCHAR(20);

ALTER TABLE precatorio
    ADD CONSTRAINT precatorio_numero_processo_digitos
    CHECK (numero_processo ~ '^[0-9]{20}$');

-- NNNNNNN-DD.AAAA.J.TR.OOOO
ALTER TABLE precatorio
    ADD COLUMN numero_cnj TEXT GENERATED ALWAYS AS (
        substr(numero_processo, 1, 7)  || '-' ||
        substr(numero_processo, 8, 2)  || '.' ||
        substr(numero_processo, 10, 4) || '.' ||
        substr(numero_processo, 14, 1) || '.' ||
        substr(numero_processo, 15, 2) || '.' ||
        substr(numero_processo, 17, 4)
    ) STORED;

-- 3. Ente devedor: cadastro canônico e nomes como chegam de cada fonte (4, 8).
CREATE TABLE ente_devedor (
    id     BIGSERIAL PRIMARY KEY,
    nome   TEXT NOT NULL UNIQUE,  -- "Município de São Paulo"
    esfera TEXT NOT NULL CHECK (esfera IN ('federal', 'estadual', 'municipal'))
);

-- "MUNICIPIO DE SAO PAULO" e "Município de São Paulo" apontam para o mesmo ente.
-- A importação proposta grava o nome em maiúsculas e sem acento; um nome desconhecido vai para a quarentena.
CREATE TABLE ente_devedor_nome (
    nome_normalizado TEXT   PRIMARY KEY,
    ente_id          BIGINT NOT NULL REFERENCES ente_devedor (id)
);

-- Preenchida a partir de ente_devedor (texto) e depois tornada NOT NULL.
ALTER TABLE precatorio ADD COLUMN ente_id BIGINT REFERENCES ente_devedor (id);

-- 4. Data de apresentação e prazo (3).
ALTER TABLE precatorio
    ADD COLUMN apresentado_em_original TEXT,  -- "2025-04-03T01:00:00Z", como veio
    ADD COLUMN data_apresentacao       DATE;  -- convertida para America/Sao_Paulo

-- Conversão que a importação proposta usa para valores com hora:
--   ('2025-04-03T01:00:00Z'::timestamptz AT TIME ZONE 'America/Sao_Paulo')::date  -> 2025-04-02

-- Até 2 de abril (inclusive): 31/12 do ano seguinte. Depois: 31/12 do ano subsequente ao seguinte.
CREATE VIEW vw_precatorio_prazo AS
SELECT
    p.id,
    p.numero_cnj,
    p.data_apresentacao,
    c.prazo_pagamento,
    c.prazo_pagamento < current_date AS vencido
FROM precatorio p
CROSS JOIN LATERAL (
    SELECT make_date(
        EXTRACT(YEAR FROM p.data_apresentacao)::int
        + CASE WHEN p.data_apresentacao <= make_date(EXTRACT(YEAR FROM p.data_apresentacao)::int, 4, 2)
               THEN 1 ELSE 2 END,
        12, 31) AS prazo_pagamento
) c;

-- 5. Pagamento: um registro por evento, na versão mais recente (1, 6).
ALTER TABLE pagamento
    ADD COLUMN atualizado_em TIMESTAMPTZ,
    ADD COLUMN arquivo_id    BIGINT REFERENCES arquivo_recebido (id);

-- As duplicatas já gravadas precisam ser resolvidas antes da restrição.
-- Em vez de apagar linhas, a migração para e lista o que precisa ser refeito
-- a partir da base limpa. Para ver os detalhes:
--   SELECT evento_id, count(*) AS vezes, sum(valor) AS valor_somado
--   FROM pagamento GROUP BY evento_id HAVING count(*) > 1;
DO $$
DECLARE
    duplicados TEXT;
BEGIN
    SELECT string_agg(evento_id, ', ' ORDER BY evento_id) INTO duplicados
    FROM (SELECT evento_id FROM pagamento GROUP BY evento_id HAVING count(*) > 1) d;

    IF duplicados IS NOT NULL THEN
        RAISE EXCEPTION 'evento_id duplicado em pagamento: %. Refaça a tabela a partir da base limpa antes de migrar.', duplicados;
    END IF;
END
$$;

ALTER TABLE pagamento ADD CONSTRAINT pagamento_evento_id_unico UNIQUE (evento_id);

-- Comando que a importação proposta usaria para gravar cada evento ($1 a $7 são os parâmetros).
-- O script atual não foi fornecido; isto descreve o processo proposto, não uma alteração nele.
-- Reimportar não duplica, e só uma versão mais nova substitui a gravada:
--
--   INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em, atualizado_em, arquivo_id)
--   VALUES ($1, $2, $3, $4, $5, $6, $7)
--   ON CONFLICT (evento_id) DO UPDATE
--   SET precatorio_id = EXCLUDED.precatorio_id,
--       tipo          = EXCLUDED.tipo,
--       valor         = EXCLUDED.valor,
--       pago_em       = EXCLUDED.pago_em,
--       atualizado_em = EXCLUDED.atualizado_em,
--       arquivo_id    = EXCLUDED.arquivo_id
--   WHERE pagamento.atualizado_em IS NULL  -- linha gravada antes da migração
--      OR EXCLUDED.atualizado_em > pagamento.atualizado_em;

-- 6. Quarentena: nenhum evento recusado some sem registro (2).
CREATE TABLE evento_rejeitado (
    id            BIGSERIAL   PRIMARY KEY,
    arquivo_id    BIGINT      NOT NULL REFERENCES arquivo_recebido (id),
    posicao       INT         NOT NULL,  -- índice do evento no arquivo
    evento_id     TEXT,                  -- pode vir vazio
    conteudo      JSONB       NOT NULL,  -- o registro exatamente como veio
    motivo        TEXT        NOT NULL,  -- valor_nulo, valor_negativo, processo_vazio...
    status        TEXT        NOT NULL DEFAULT 'pendente'
                  CHECK (status IN ('pendente', 'corrigido', 'descartado', 'devolvido_ao_tribunal')),
    resolvido_por TEXT,
    resolvido_em  TIMESTAMPTZ,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (arquivo_id, posicao),        -- reprocessar não duplica a quarentena
    CHECK ((status = 'pendente') = (resolvido_em IS NULL))
);

-- 7. Total pago calculado, não acumulado (1, 7).
-- Supõe que o estorno abate o pagamento (dúvida 5 do diagnóstico).
CREATE VIEW vw_total_pago AS
SELECT
    p.id AS precatorio_id,
    p.numero_cnj,
    p.valor_face,
    COALESCE(SUM(CASE g.tipo WHEN 'estorno' THEN -g.valor ELSE g.valor END), 0) AS total_pago
FROM precatorio p
LEFT JOIN pagamento g ON g.precatorio_id = p.id
GROUP BY p.id, p.numero_cnj, p.valor_face;

-- Alerta (consulta para o relatório diário, não faz parte da migração):
--   SELECT * FROM vw_total_pago WHERE total_pago < 0 OR total_pago > valor_face;

-- 8. Conciliação com o tribunal (4, 5, 8).
CREATE TABLE tribunal_precatorio (
    arquivo_id      BIGINT        NOT NULL REFERENCES arquivo_recebido (id),
    numero_processo VARCHAR(20)   NOT NULL CHECK (numero_processo ~ '^[0-9]{20}$'),
    ente_recebido   TEXT          NOT NULL,  -- como veio, para auditoria
    ente_id         BIGINT        NOT NULL REFERENCES ente_devedor (id),
    valor_face      NUMERIC(15,2) NOT NULL CHECK (valor_face > 0),
    PRIMARY KEY (arquivo_id, numero_processo)
);

CREATE VIEW vw_conciliacao_tribunal AS
WITH ultima_lista AS (
    SELECT t.*
    FROM tribunal_precatorio t
    WHERE t.arquivo_id = (
        SELECT max(id) FROM arquivo_recebido
        WHERE tipo = 'tribunal' AND status = 'processado'
    )
)
-- Face e ente só são comparados quando o processo está dos dois lados;
-- senão a comparação contra NULL marcaria uma divergência falsa.
SELECT
    COALESCE(t.numero_processo, p.numero_processo) AS numero_processo,
    p.id IS NULL                                    AS so_no_tribunal,
    t.numero_processo IS NULL                       AS so_no_sistema,
    COALESCE(t.valor_face <> p.valor_face, false)   AS valor_face_diferente,
    COALESCE(t.ente_id IS DISTINCT FROM p.ente_id AND p.id IS NOT NULL
             AND t.numero_processo IS NOT NULL, false) AS ente_diferente,
    t.valor_face AS face_tribunal,
    p.valor_face AS face_sistema,
    t.ente_id    AS ente_tribunal,
    p.ente_id    AS ente_sistema
FROM ultima_lista t
FULL JOIN precatorio p ON p.numero_processo = t.numero_processo;

COMMIT;

-- Depois de preencher os dados antigos (ente_id, data_apresentacao e atualizado_em),
-- tornar as colunas obrigatórias:
--
--   ALTER TABLE precatorio ALTER COLUMN ente_id           SET NOT NULL;
--   ALTER TABLE precatorio ALTER COLUMN data_apresentacao SET NOT NULL;
--   ALTER TABLE pagamento  ALTER COLUMN atualizado_em     SET NOT NULL;
