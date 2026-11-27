# Relatório da limpeza

Data de referência para prazo vencido: **2026-11-26**.

Gerado por `python -m limpeza`. Os arquivos de entrada foram lidos sem alteração; o hash
SHA-256 de cada um está abaixo, para conferir que são os originais.

| Arquivo | Registros | SHA-256 |
|---|---|---|
| `pagamentos.json` | 13 | `83e761b199bfea3413e4b614ac2c55643f2ccd0bd294d365af02a839de8f2cf8` |
| `tribunal.csv` | 5 | `0ce8aab43966f28bb12920956b38bb2573454c49c997f20e0dae07a8c7b2c841` |
| `hub.csv` | 5 | `75fcf6e07dc05078c35b5c7d4a3b1d38cfb3df165ab05cf5d73e155a73b83108` |
| `apresentacoes.json` | 6 | `0da8be22859b58fa618fae00fedad2afead6605da6c6184e7de8e8d26a93ccc2` |

## Resumo

| Eventos de pagamento | Quantidade |
|---|---|
| Lidos | 13 |
| Válidos, sem alteração | 4 |
| Corrigidos | 3 |
| Em dúvida (fora do total confirmado) | 2 |
| Descartados (em `quarentena.csv`) | 4 |

| Precatórios | Quantidade |
|---|---|
| No total, unindo as fontes | 6 |
| Válidos | 1 |
| Corrigidos | 1 |
| Em dúvida | 4 |

## Avisos sobre os arquivos

Desvios do leiaute que atingem o arquivo inteiro, não um registro.

- tribunal.csv: não está em UTF-8, como diz a documentação; lido como Windows-1252 (ISO-8859-1), padrão do Excel em português
- tribunal.csv: quebras de linha CRLF (Windows)
- tribunal.csv: separador ';', mas a documentação diz ','
- tribunal.csv: 5 valores de face com vírgula decimal e ponto de milhar (ex.: 45.000,00), mas a documentação pede ponto decimal; convertidos
- pagamentos.json: datas de pagamento de 2025-02-20 a 2025-08-10, não só os últimos 7 dias descritos no fluxo; como cada evento é deduplicado por evento_id, isso não infla o total

## Precatórios

Total confirmado: soma dos eventos válidos e corrigidos. Ajustes em dúvida: eventos que
dependem de resposta do tribunal (estorno abate o valor; negativo entra com o sinal).

| Processo | Ente | Valor de face | Prazo | Vencido | Total confirmado | Ajustes em dúvida | Status |
|---|---|---|---|---|---|---|---|
| `0012345-10.2019.8.26.0053` | Município de São Paulo | 45.000,00 | 2026-12-31 | não | 18.000,50 | — | corrigido |
| `0023456-21.2020.8.26.0053` | Município de São Paulo | — | 2027-12-31 | não | 9.200,00 | — | em_duvida |
| `0034567-32.2018.8.26.0405` | Estado de São Paulo | 12.500,00 | 2025-12-31 | sim | 5.000,00 | -5.000,00 | valido |
| `0045678-43.2021.5.02.0011` | — | 9.800,00 | 2026-12-31 | não | 3.000,00 | — | em_duvida |
| `0056789-54.2017.4.03.6100` | Estado de São Paulo | 22.000,00 | 2026-12-31 | não | 0,00 | -200,00 | em_duvida |
| `0067890-65.2016.8.26.0053` | Município de São Paulo | 7.000,00 | 2025-12-31 | sim | 4.000,00 | — | em_duvida |

Total pago confirmado: **39.200,50**. Com os ajustes em dúvida: **34.000,50**.

## Eventos corrigidos

Vieram fora do leiaute e foram convertidos com uma regra segura. Entram no total confirmado.

| Evento | Linha | Processo | Valor | Por quê |
|---|---|---|---|---|
| `ev-002` | 11 | `0012345-10.2019.8.26.0053` | 2.500,50 | valor veio como texto ('2.500,50'); convertido para 2500.50; data '10/04/2025' lida como DD/MM/AAAA (2025-04-10); confere com atualizado_em |
| `ev-005` | 43 | `0023456-21.2020.8.26.0053` | 1.200,00 | processo sem máscara CNJ (00234562120208260053); normalizado pelos dígitos |
| `ev-001` | 67 | `0012345-10.2019.8.26.0053` | 15.500,00 | ev-001 aparece 2 vezes com conteúdo diferente; ficou a versão de atualizado_em mais recente |

## Eventos descartados

Não podem ser aproveitados. Estão em `quarentena.csv`, com o registro original, para tratamento pela operação ou devolução ao tribunal. Não entram em nenhum total.

| Evento | Linha | Processo | Valor | Por quê |
|---|---|---|---|---|
| `ev-001` | 3 | `0012345-10.2019.8.26.0053` | `15000.0` (como veio) | versão antiga do ev-001; substituída pela da linha 67 (atualizado_em mais recente) |
| `ev-002` | 27 | `0012345-10.2019.8.26.0053` | `2.500,50` (como veio) | cópia idêntica do ev-002 da linha 11; contado uma vez |
| `ev-004` | 35 | `0023456-21.2020.8.26.0053` | — | valor nulo |
| `ev-010` | 91 | — | 750,00 | número do processo vazio |

## Eventos em dúvida

Foram lidos, mas o efeito no total depende de resposta do tribunal. Estão em `pagamentos.csv` com status `em_duvida` e ficam fora do total confirmado.

| Evento | Linha | Processo | Valor | Por quê |
|---|---|---|---|---|
| `ev-007` | 59 | `0034567-32.2018.8.26.0405` | 5.000,00 | tipo estorno não está na documentação; não se sabe se abate um pagamento |
| `ev-009` | 83 | `0056789-54.2017.4.03.6100` | -200,00 | valor negativo (-200.00) com tipo pagamento: estorno, erro de sinal ou outro lançamento? |

## Precatórios corrigidos ou em dúvida

| Processo | Status | Por quê |
|---|---|---|
| `0012345-10.2019.8.26.0053` | corrigido | ente escrito de outra forma no hub ('MUNICIPIO DE SAO PAULO'); mesmo ente, mantida a grafia do tribunal; prazo do hub 2027-12-31 recalculado para 2026-12-31 (apresentado em 2025-04-02, regra de 2 de abril) |
| `0023456-21.2020.8.26.0053` | em_duvida | hub.csv, linha 3: processo sem máscara CNJ (00234562120208260053); normalizado pelos dígitos; valor de face diferente: tribunal 30000.00, hub 31000.00 |
| `0045678-43.2021.5.02.0011` | em_duvida | ente diferente: tribunal 'União', hub 'Município de Santos' |
| `0056789-54.2017.4.03.6100` | em_duvida | está no hub, mas não na lista do tribunal; '2025-04-03T01:00:00Z' está em outro fuso; no horário de Brasília é 2025-04-02, não 2025-04-03; pelo horário de Brasília o prazo é 2026-12-31, pela data escrita seria 2027-12-31; prazo do hub 2027-12-31 recalculado para 2026-12-31 (apresentado em 2025-04-02, regra de 2 de abril) |
| `0067890-65.2016.8.26.0053` | em_duvida | está na lista do tribunal, mas não no hub |
