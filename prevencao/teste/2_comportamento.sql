-- Teste de comportamento da migração. Rodar depois de 1_dados_antes.sql e de migracao.sql.
-- Os passos 3, 4 e 8 terminam com ERROR de propósito: mostram as restrições recusando dados inválidos.

\pset footer off
\echo '== 1. Conversao de fuso (0056789)'
SELECT ('2025-04-03T01:00:00Z'::timestamptz AT TIME ZONE 'America/Sao_Paulo')::date AS brasilia;

\echo '== 2. Prazo pela view'
INSERT INTO precatorio (numero_processo, ente_devedor, valor_face) VALUES ('00678906520168260053','Município de São Paulo',7000);
UPDATE precatorio p SET data_apresentacao = v.d FROM (VALUES
 ('00123451020198260053','2025-04-02'::date), ('00234562120208260053','2025-04-03'),
 ('00345673220188260405','2024-02-29'), ('00456784320215020011','2025-04-02'),
 ('00567895420174036100','2025-04-02'), ('00678906520168260053','2023-12-31')) v(n,d)
WHERE p.numero_processo = v.n;
SELECT numero_cnj, data_apresentacao, prazo_pagamento, vencido FROM vw_precatorio_prazo ORDER BY 1;

\echo '== 3. CHECK recusa processo com mascara'
\set ON_ERROR_STOP 0
INSERT INTO precatorio (numero_processo, ente_devedor, valor_face) VALUES ('0012345-10.2019.8.2','x',1);
\echo '== 4. UNIQUE recusa evento_id repetido'
INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em) VALUES (1,'ev-003','pagamento',1,'2025-01-01');
\set ON_ERROR_STOP 1

\echo '== 5. Upsert sobre linha antiga (atualizado_em NULL, antes do preenchimento)'
PREPARE gravar(bigint, text, text, numeric, date, timestamptz, bigint) AS
INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em, atualizado_em, arquivo_id)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (evento_id) DO UPDATE
SET precatorio_id = EXCLUDED.precatorio_id, tipo = EXCLUDED.tipo, valor = EXCLUDED.valor,
    pago_em = EXCLUDED.pago_em, atualizado_em = EXCLUDED.atualizado_em, arquivo_id = EXCLUDED.arquivo_id
WHERE pagamento.atualizado_em IS NULL OR EXCLUDED.atualizado_em > pagamento.atualizado_em;
EXECUTE gravar(1,'ev-001','pagamento',15500,'2025-03-10','2025-03-11T09:00:00-03:00',NULL);
SELECT evento_id, valor, atualizado_em FROM pagamento WHERE evento_id='ev-001';

\echo '== 6. Upsert depois do preenchimento: reimportar, versao nova, versao velha'
UPDATE pagamento SET atualizado_em = '2025-03-10T10:00:00-03:00' WHERE atualizado_em IS NULL;
EXECUTE gravar(1,'ev-001','pagamento',15500,'2025-03-10','2025-03-11T09:00:00-03:00',NULL);
SELECT 'versao nova' AS caso, valor FROM pagamento WHERE evento_id='ev-001';
EXECUTE gravar(1,'ev-001','pagamento',15500,'2025-03-10','2025-03-11T09:00:00-03:00',NULL);
EXECUTE gravar(1,'ev-001','pagamento',15500,'2025-03-10','2025-03-11T09:00:00-03:00',NULL);
SELECT 'reimportado 2x' AS caso, count(*) AS linhas, sum(valor) FROM pagamento WHERE evento_id='ev-001';
EXECUTE gravar(1,'ev-001','pagamento',15000,'2025-03-10','2025-03-10T10:00:00-03:00',NULL);
SELECT 'versao velha depois' AS caso, valor FROM pagamento WHERE evento_id='ev-001';

\echo '== 7. Total pago com estorno'
EXECUTE gravar(3,'ev-006','pagamento',5000,'2025-02-20','2025-02-20T10:00:00-03:00',NULL);
EXECUTE gravar(3,'ev-007','estorno',5000,'2025-02-21','2025-02-21T10:00:00-03:00',NULL);
SELECT numero_cnj, valor_face, total_pago FROM vw_total_pago ORDER BY 1;

\echo '== 8. Quarentena: reprocessar nao duplica; resolver exige resolvido_em (o UPDATE abaixo deve falhar)'
INSERT INTO arquivo_recebido (tipo, nome, sha256, conteudo) VALUES ('pagamentos','pagamentos.json',repeat('a',64),'\x00');
INSERT INTO evento_rejeitado (arquivo_id, posicao, evento_id, conteudo, motivo) VALUES (1, 4, 'ev-004', '{"valor": null}', 'valor_nulo')
ON CONFLICT (arquivo_id, posicao) DO NOTHING;
INSERT INTO evento_rejeitado (arquivo_id, posicao, evento_id, conteudo, motivo) VALUES (1, 4, 'ev-004', '{"valor": null}', 'valor_nulo')
ON CONFLICT (arquivo_id, posicao) DO NOTHING;
SELECT count(*) AS rejeitados FROM evento_rejeitado;
\set ON_ERROR_STOP 0
UPDATE evento_rejeitado SET status = 'descartado';
\set ON_ERROR_STOP 1

\echo '== 9. Conciliacao com o tribunal'
INSERT INTO ente_devedor (nome, esfera) VALUES ('Município de São Paulo','municipal'),('Estado de São Paulo','estadual'),('União','federal'),('Município de Santos','municipal');
INSERT INTO ente_devedor_nome VALUES ('MUNICIPIO DE SAO PAULO',1),('ESTADO DE SAO PAULO',2),('UNIAO',3),('MUNICIPIO DE SANTOS',4);
UPDATE precatorio p SET ente_id = n.ente_id FROM ente_devedor_nome n
 WHERE n.nome_normalizado = upper(translate(p.ente_devedor, 'áãâéêíóôõúçÁÃÂÉÊÍÓÔÕÚÇ', 'aaaeeiooouuAAAEEIOOOUC'));
INSERT INTO arquivo_recebido (tipo, nome, sha256, conteudo, status) VALUES ('tribunal','tribunal.csv',repeat('b',64),'\x00','processado');
INSERT INTO tribunal_precatorio VALUES
 (2,'00123451020198260053','Município de São Paulo',1,45000),
 (2,'00234562120208260053','Município de São Paulo',1,30000),
 (2,'00345673220188260405','Estado de São Paulo',2,12500),
 (2,'00456784320215020011','União',3,9800),
 (2,'00678906520168260053','Município de São Paulo',1,7000);
-- 0067890 nao esta no sistema: para o teste, tirar do precatorio
DELETE FROM precatorio WHERE numero_processo='00678906520168260053';
SELECT numero_processo, so_no_tribunal, so_no_sistema, valor_face_diferente, ente_diferente
FROM vw_conciliacao_tribunal ORDER BY 1;

\echo '== 10. SET NOT NULL finais (apos preenchimento)'
ALTER TABLE precatorio ALTER COLUMN ente_id SET NOT NULL;
ALTER TABLE precatorio ALTER COLUMN data_apresentacao SET NOT NULL;
ALTER TABLE pagamento ALTER COLUMN atualizado_em SET NOT NULL;
\echo 'ok'
