# Case técnico: conciliação de precatórios

A operação acha que os números do sistema não batem com os do tribunal. Este repositório tem o diagnóstico, um programa que limpa os arquivos e gera uma base confiável, e as propostas para que os problemas não voltem.

## Onde está cada entrega

| Pedido do enunciado | Onde está |
|---|---|
| Diagnóstico, prevenção e dúvidas | [`relatorio/diagnostico.md`](relatorio/diagnostico.md) |
| SQL da prevenção | No diagnóstico e, pronto para rodar, em [`prevencao/migracao.sql`](prevencao/migracao.sql) |
| Programa de limpeza | [`limpeza/`](limpeza/) |
| Testes | [`tests/`](tests/) |
| Base limpa e relatório gerados | [`saida/`](saida/) (resultado da última execução, já commitado) |
| Arquivos originais do case | [`case-candidato/`](case-candidato/) (sem alteração; o `.gitattributes` impede o Git de converter as quebras de linha) |

## Como rodar

Requer Python 3.10 ou mais recente. O programa usa só a biblioteca padrão.

```bash
python -m limpeza
```

O programa lê `case-candidato/dados/` e grava em `saida/`:

| Arquivo | Conteúdo |
|---|---|
| `precatorios.csv` | Um precatório por linha, cruzando tribunal, hub e apresentações, com prazo recalculado e total pago |
| `pagamentos.csv` | Os eventos aproveitados: válidos, corrigidos e em dúvida |
| `quarentena.csv` | Os eventos descartados, com o motivo e o registro original |
| `relatorio.md` | O que foi corrigido, descartado ou ficou em dúvida, e por quê |

Opções:

- `--entrada PASTA`: pasta com os arquivos originais;
- `--saida PASTA`: pasta onde gravar o resultado;
- `--data-referencia AAAA-MM-DD`: data usada para marcar prazo vencido. O padrão é hoje. A saída commitada usou `2026-11-26`.

Os arquivos de entrada são abertos só para leitura, e o programa recusa uma pasta de saída dentro da pasta de entrada. Rodar de novo, com a mesma data de referência, gera exatamente os mesmos arquivos.

## Como rodar os testes

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows (Git Bash); no PowerShell: .venv\Scripts\Activate.ps1
                                # Linux ou macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

Os testes cobrem as regras de maior risco:

- **prazo:** a fronteira de 2 de abril, o fuso da data de apresentação e o ano bissexto;
- **conversões:** valores como `"2.500,50"` e datas como `10/04/2025`;
- **eventos repetidos:** a escolha da versão mais recente de cada `evento_id`;
- **quarentena:** os eventos que não podem ser aproveitados;
- **arquivos reais do case:** que os originais não mudam, que rodar duas vezes gera exatamente a mesma saída e quais são os totais de cada precatório.

## Como testar o SQL

A migração foi testada num PostgreSQL 16 em Docker, sobre o `schema.sql` original:

```bash
docker run -d --rm --name pg-case -e POSTGRES_PASSWORD=x postgres:16
docker exec -i pg-case psql -U postgres -v ON_ERROR_STOP=1 < case-candidato/schema.sql
docker exec -i pg-case psql -U postgres -v ON_ERROR_STOP=1 < prevencao/teste/1_dados_antes.sql
docker exec -i pg-case psql -U postgres -v ON_ERROR_STOP=1 < prevencao/migracao.sql
docker exec -i pg-case psql -U postgres < prevencao/teste/2_comportamento.sql
docker stop pg-case
```

O script `2_comportamento.sql` confere:

- a conversão de fuso;
- o prazo dos seis precatórios;
- as restrições, recusando processo com máscara e `evento_id` repetido;
- o upsert: reimportar não duplica, e uma versão antiga não sobrescreve a nova;
- o estorno abatendo no total pago;
- a quarentena;
- a conciliação, que aponta só as quatro divergências reais.

Os erros que aparecem nos passos 3, 4 e 8 são esperados: são as restrições recusando dados inválidos.

Também foi testado o caso de um banco que já tem `evento_id` duplicado. A migração para com erro e não aplica nada.

## Decisões principais

- **O que depende do tribunal não é decidido pelo programa.** Isso vale para o estorno do `ev-007`, o valor negativo do `ev-009` e as divergências de valor de face, de ente e de fuso. Esses casos ficam com status `em_duvida` e fora do total confirmado. O relatório mostra o total com e sem eles.
- **Nada é descartado em silêncio.** Todo evento recusado vai para `quarentena.csv`, com o motivo e o registro como veio.
- **O processo é comparado pelos 20 dígitos**, nunca pelo texto como foi escrito. O ente é comparado sem acento e sem diferença de maiúsculas.
- **O script de importação original não foi fornecido.** O que o diagnóstico diz sobre ele vem do fluxo descrito no enunciado e das restrições do `schema.sql`. A parte de importação da prevenção é uma proposta de processo, não uma alteração sobre um código existente.

## Como usei IA

Usei o Claude Code (Anthropic) ao longo do trabalho. A divisão foi esta:

- **Minha:** a primeira leitura do `pagamentos.json` contra a documentação, registrada nas anotações que estão no fim do diagnóstico ("Texto bruto"). Também foram minhas as decisões de cada etapa: o que fazer com os casos em dúvida, o formato da saída, a ferramenta de testes, versionar os arquivos do case e a ordem dos commits.
- **Com a IA:**
  - formatar o diagnóstico a partir das minhas anotações e estendê-lo aos demais arquivos;
  - escrever as seções de prevenção e dúvidas e o SQL;
  - escrever o programa de limpeza e os testes.

Como conferi o que a IA produziu:

- **Evidências contra os arquivos.** Cada linha citada no diagnóstico foi conferida no arquivo original. Essa conferência corrigiu números de linha errados da primeira versão. Também apontou um evento (`ev-004`) que tinha ficado de fora.
- **Diagnóstico contra o programa.** Os números do programa foram comparados com os do diagnóstico, e a comparação mostrou um erro do diagnóstico escrito com IA. O prazo do `0067890` estava como 2024-12-31, mas o correto é 2025-12-31, porque a apresentação foi depois de 2 de abril. O erro foi corrigido num commit próprio.
- **Testes que falham quando a regra quebra.** Troquei de propósito o `<=` por `<` na regra de 2 de abril, que é o erro provável do sistema atual. Três testes falharam, e o código foi restaurado.
- **Os arquivos do case.** Conferi pelo hash que o repositório guarda os arquivos idênticos aos recebidos. Isso mostrou que o Git estava convertendo as quebras de linha, e o problema foi corrigido.

- **SQL executado, não só revisado.** Rodar a migração num PostgreSQL revelou dois defeitos que a revisão não tinha pegado:
  - o upsert ignorava, em silêncio, as linhas gravadas antes da migração, porque a comparação com `atualizado_em` nulo nunca é verdadeira;
  - a conciliação marcava divergências falsas de face e de ente para processos que só existem de um lado.

  Os dois foram corrigidos e testados de novo.
- **Versões do Python e clone limpo.** Os testes rodam no Python 3.13 (Windows) e no 3.10 (imagem `python:3.10-slim` no Docker). Os dois geram a mesma saída que está em `saida/`. Também conferi num clone novo do GitHub que os arquivos do case chegam idênticos aos originais.
