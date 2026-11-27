-- Estado "antes" da migração: o sistema como o hub.csv o exporta (processo só com dígitos,
-- porque o CHAR(20) do schema.sql não comporta a máscara). Rodar depois de case-candidato/schema.sql.

INSERT INTO precatorio (numero_processo, ente_devedor, valor_face) VALUES
 ('00123451020198260053','MUNICIPIO DE SAO PAULO',45000.00),
 ('00234562120208260053','Município de São Paulo',31000.00),
 ('00345673220188260405','Estado de São Paulo',12500.00),
 ('00456784320215020011','Município de Santos',9800.00),
 ('00567895420174036100','Estado de São Paulo',22000.00);
INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em) VALUES
 (1,'ev-001','pagamento',15000,'2025-03-10'),
 (1,'ev-002','pagamento',2500.50,'2025-04-10'),
 (2,'ev-003','pagamento',8000,'2025-05-02');
