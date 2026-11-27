# Diagnóstico

## Como ler este documento

**Escopo.** Todos os arquivos de `case-candidato/`: `dados/pagamentos.json`, `dados/tribunal.csv`, `dados/hub.csv`, `dados/apresentacoes.json`, `schema.sql`, `DOCUMENTACAO_TRIBUNAL.md` (versão 2.1) e o fluxo operacional de `ENUNCIADO.md`.

**Estrutura.**

1. [Resumo](#resumo): todos os problemas numa tabela, do mais grave para o menos grave.
2. [Como os problemas se ligam](#como-os-problemas-se-ligam): quais são causa e quais são consequência.
3. [Visão por precatório](#visão-por-precatório): o mesmo processo nas quatro fontes, lado a lado.
4. [Problemas](#problemas): o detalhe de cada um, sempre com **Evidência**, **Impacto** e **Causa ou consequência**.
5. [Prevenção](#prevenção): o que mudar no processo e no banco, com o SQL, e uma proposta de como a importação deveria funcionar.
6. [Dúvidas](#dúvidas): o que perguntar ao tribunal, à operação e a quem mantém o sistema antes de pôr a limpeza em produção.
7. [Texto bruto](#texto-bruto): as anotações originais.

**Convenções.**

- Linhas citadas são as do arquivo original. Em `pagamentos.json`, o intervalo de um evento vai da linha do `evento_id` à do `atualizado_em`. Quando o problema está num campo, a linha do campo é citada à parte.
- "Passo N" é o passo do fluxo operacional em `ENUNCIADO.md`.
- Gravidade: **Crítica** distorce todos os números ou a priorização inteira; **Alta** distorce um precatório inteiro ou um valor grande; **Média** afeta um registro ou depende de como o script lê; **Baixa** não muda valor ou ainda precisa de confirmação.

**Limite da análise: o script de importação não foi fornecido.** O case não inclui o código do script que importa o `pagamentos.json`, nem o código que calcula o prazo ou gera o `hub.csv`. Tudo o que este documento diz sobre o script vem de duas fontes indiretas:

- **o que o enunciado descreve:** o script soma cada valor ao total pago (Passo 2), é rodado de novo com o mesmo arquivo quando falha (Passo 2) e ignora, sem aviso, o evento que não consegue importar (Passo 5);
- **o que o `schema.sql` permite:** qualquer script que grave nessas tabelas tem os eventos recusados pelas restrições do banco, seja qual for o código.

Quando um impacto depende de como o script foi escrito (por exemplo, como ele converte `"2.500,50"` ou procura o precatório), o texto diz isso e trata as alternativas como possibilidades. Pelo mesmo motivo, a parte da importação na [Prevenção](#prevenção) não é uma lista de alterações sobre um código existente. É uma proposta de como o processo de importação deveria funcionar. As perguntas sobre o código atual estão nas dúvidas 22 e 23.

**Uso de IA.** A primeira versão (só `pagamentos.json`) foi formatada com IA a partir das anotações brutas, que estão no fim do documento. Nesta revisão, com apoio de IA, foram corrigidos os números de linha, incluído o `ev-004` (que estava nas anotações pessoais de trabalho, não versionadas, mas tinha ficado de fora) e estendida a análise aos demais arquivos. Cada evidência foi conferida contra o arquivo original. As seções de Prevenção e Dúvidas também foram escritas com apoio de IA, a partir do diagnóstico.

## Resumo

| # | Gravidade | Problema | Onde | Papel |
|---|---|---|---|---|
| 1 | Crítica | A importação soma de novo a cada execução, e o banco não impede | Passo 2, `schema.sql` | Causa raiz |
| 2 | Crítica | Evento recusado some sem aviso | Passo 5, `schema.sql` | Causa raiz |
| 3 | Crítica | Prazo de pagamento calculado errado em 2 precatórios | `hub.csv`, `apresentacoes.json` | Causa |
| 4 | Alta | Conciliação semanal por texto exato | Passo 3 | Causa raiz |
| 5 | Alta | Precatórios que existem só de um lado (um deles já vencido) | `tribunal.csv`, `hub.csv` | Causa |
| 6 | Alta | `ev-001` duas vezes, com valor corrigido | `pagamentos.json` | Causa |
| 7 | Alta | `ev-007` é estorno; documentação e banco discordam sobre estorno | `pagamentos.json`, documentação, `schema.sql` | Causa |
| 8 | Alta | Valor de face e ente diferentes entre tribunal e hub | `tribunal.csv`, `hub.csv` | Causa |
| 9 | Média | `tribunal.csv` fora do leiaute (separador, codificação, decimal) | `tribunal.csv`, Passo 3 | Consequência provável do Passo 3 |
| 10 | Média | `numero_processo CHAR(20)` não cabe o CNJ com máscara | `schema.sql` | Causa |
| 11 | Média | `ev-002`: valor em texto com vírgula, e registro duplicado | `pagamentos.json` | Causa |
| 12 | Média | `ev-004`: valor nulo | `pagamentos.json` | Causa |
| 13 | Média | `ev-005` e `hub.csv`: processo sem máscara CNJ | `pagamentos.json`, `hub.csv` | Causa |
| 14 | Média | `ev-009`: valor negativo, em processo ausente do tribunal | `pagamentos.json` | Causa |
| 15 | Média | `ev-010`: processo vazio | `pagamentos.json` | Causa |
| 16 | Baixa | `ev-002`: data fora do padrão | `pagamentos.json` | Causa |
| 17 | Baixa | Arquivo diário não cobre só 7 dias | `pagamentos.json`, Passo 1 | A confirmar |

## Como os problemas se ligam

Quatro problemas de processo e de banco explicam a maior parte dos defeitos nos dados:

- **1 (soma sem idempotência)** transforma 6 (`ev-001` corrigido) e 11 (`ev-002` duplicado) em total pago inflado. Todo reprocessamento (Passo 2) repete o efeito.
- **2 (recusa silenciosa)** transforma 7, 11, 12, 13, 14, 15 e 16 em dinheiro que some da conciliação sem ninguém saber.
- **4 (comparação por texto exato)**, somado a 9 (arquivo alterado no Excel) e a 10 (coluna que não cabe a máscara), transforma 8 e 13 em divergências falsas e esconde divergências reais.
- **3 (prazo)** e **5 (cadastro faltando)** afetam diretamente o uso que a equipe faz do sistema: priorizar a carteira pelo prazo (Passo 4).

A frase da operação, "os números não batem", é a consequência somada desses quatro grupos.

## Visão por precatório

Prazo esperado: a regra do enunciado aplicada à data de apresentação, no horário de Brasília (ver problema 3).

| Processo | `tribunal.csv` (linha · ente · face) | `hub.csv` (linha · ente · face) | Apresentado em | Prazo no hub | Prazo esperado | Eventos em `pagamentos.json` |
|---|---|---|---|---|---|---|
| `0012345-10.2019.8.26.0053` | 2 · Município de São Paulo · 45.000,00 | 2 · MUNICIPIO DE SAO PAULO · 45000.00 | 2025-04-02 | 2027-12-31 ❌ | 2026-12-31 | `ev-001` (×2), `ev-002` (×2) |
| `0023456-21.2020.8.26.0053` | 3 · Município de São Paulo · 30.000,00 | 3 · **sem máscara** · Município de São Paulo · **31000.00** | 2025-04-03 | 2027-12-31 | 2027-12-31 | `ev-003`, `ev-004`, `ev-005` (sem máscara) |
| `0034567-32.2018.8.26.0405` | 4 · Estado de São Paulo · 12.500,00 | 4 · Estado de São Paulo · 12500.00 | 2024-02-29 | 2025-12-31 | 2025-12-31 | `ev-006`, `ev-007` (estorno) |
| `0045678-43.2021.5.02.0011` | 5 · **União** · 9.800,00 | 5 · **Município de Santos** · 9800.00 | 2025-04-02T23:30:00-03:00 | 2026-12-31 | 2026-12-31 | `ev-008` |
| `0056789-54.2017.4.03.6100` | **não existe** | 6 · Estado de São Paulo · 22000.00 | 2025-04-03T01:00:00Z | 2027-12-31 ❌ | 2026-12-31 | `ev-009` (negativo) |
| `0067890-65.2016.8.26.0053` | 6 · Município de São Paulo · 7.000,00 | **não existe** | 2023-12-31 | — | 2024-12-31 (**vencido**) | `ev-011` |
| *(vazio)* | — | — | — | — | — | `ev-010` |

Em `apresentacoes.json`, as datas estão nas linhas 4, 8, 12, 16, 20 e 24, na ordem da tabela.

## Problemas

### Crítica

#### 1. A importação soma de novo a cada execução, e o banco não impede

**Evidência.**

- Passo 2: o script "soma cada valor ao total pago". Quando falha no meio, o operador "roda o script de novo com o mesmo arquivo".
- `schema.sql`, linha 11: `evento_id TEXT NOT NULL`, sem `UNIQUE`. Nada no banco impede gravar o mesmo evento duas vezes.
- `schema.sql`, linhas 8–16: a tabela `pagamento` não tem `atualizado_em`. O banco não guarda qual versão de um evento é a mais recente, embora a documentação defina esse campo como "momento da última alteração do registro".
- Passo 1: cada arquivo diário traz os últimos 7 dias. Arquivos consecutivos repetem até 6 dias de eventos.
- O próprio arquivo já traz `evento_id` repetido: `ev-001` (problema 6) e `ev-002` (problema 11).

**Impacto.** Cada reprocessamento soma de novo os eventos que já tinham entrado antes da falha. Cada arquivo diário soma de novo os dias que repete do arquivo anterior. O total pago no sistema cresce sem que exista pagamento novo, e isso atinge todos os precatórios da carteira, não só os registros com defeito.

**Causa ou consequência.** Causa raiz. Os totais inflados dos problemas 6 e 11 são consequência dela.

#### 2. Evento recusado some sem aviso

**Evidência.**

- Passo 5: "Quando um evento não pode ser importado, o script ignora e segue. Ninguém é avisado."
- **Recusados com certeza, pelo `schema.sql`,** seja qual for o script:
  - linha 13, `valor NUMERIC(15,2) NOT NULL CHECK (valor > 0)`: recusa o `ev-004` (nulo) e o `ev-009` (-200);
  - linha 10, `precatorio_id BIGINT NOT NULL REFERENCES precatorio (id)`: recusa o `ev-010` (processo vazio), porque não há precatório para associar.
- **Recusados ou não, dependendo do script** (que não foi fornecido):
  - `ev-005` (processo sem máscara): depende de o script procurar o precatório pelo texto ou pelos dígitos;
  - `ev-002` (valor `"2.500,50"`, data `10/04/2025`): depende de como o script converte valor e data;
  - `ev-007` (`estorno`): o banco aceita o tipo, mas o script pode filtrar só `pagamento`.

**Impacto.** Somem com certeza 200 (`ev-009`), 750 (`ev-010`) e um valor desconhecido (`ev-004`). Podem sumir também 2.500,50 (`ev-002`), 1.200 (`ev-005`) e o estorno de 5.000 (`ev-007`), conforme o script. O total pago do sistema fica menor que o do tribunal, e ninguém sabe dizer quais eventos explicam a diferença. É exatamente o sintoma relatado pela operação.

**Causa ou consequência.** Causa raiz. Transforma os defeitos de dado dos problemas 7, 11, 12, 13, 14, 15 e 16 em dinheiro faltando sem explicação.

#### 3. Prazo de pagamento calculado errado em 2 precatórios

**Evidência.** Regra do enunciado: apresentado até 2 de abril, o prazo é 31 de dezembro do ano seguinte; depois disso, 31 de dezembro do ano subsequente ao seguinte.

- `0012345-10.2019.8.26.0053`: `apresentacoes.json` linha 4 e `hub.csv` linha 2 dizem `2025-04-02`. Está dentro do limite, então o prazo é **2026-12-31**. O hub mostra `2027-12-31`.
- `0056789-54.2017.4.03.6100`: `apresentacoes.json` linha 20 e `hub.csv` linha 6 dizem `2025-04-03T01:00:00Z`. Em UTC é 3 de abril; no horário de Brasília (UTC-3) é **2 de abril às 22h**, então o prazo seria **2026-12-31**. O hub mostra `2027-12-31`.
- A regra também não é aplicada de forma consistente. `0045678-43.2021.5.02.0011` (`hub.csv` linha 5, `2025-04-02T23:30:00-03:00`) tem a mesma data de calendário que o `0012345` e recebeu `2026-12-31`, que está certo. O `0012345` recebeu `2027-12-31`.
- As datas de apresentação misturam três formatos: só data (`2025-04-02`), data e hora com fuso de Brasília (`-03:00`) e data e hora em UTC (`Z`). `hub.csv` grava esse texto como veio, na coluna `apresentado_em`.

**Impacto.** A equipe usa o prazo para priorizar a carteira (Passo 4). Nos dois casos, o prazo aparece **um ano depois** do correto, e o precatório cai na fila de priorização. Exatamente nos casos de fronteira (2 de abril, apresentação perto da meia-noite), o resultado depende do fuso, e nenhum documento define qual fuso vale.

**Causa ou consequência.** Causa. O formato misto das datas e a falta de definição do fuso explicam o caso do `0056789`. O caso do `0012345` sugere comparação "antes de 2 de abril" em vez de "até 2 de abril", mas a diferença em relação ao `0045678` mostra que não é só isso. O código do cálculo não foi fornecido; a dúvida 22 pede para vê-lo.

### Alta

#### 4. Conciliação semanal por texto exato

**Evidência.** Passo 3: o operador compara `tribunal.csv` com `hub.csv` "procurando o nome do ente e o número do processo exatamente como estão escritos". Nos arquivos:

- o ente do mesmo processo está escrito de formas diferentes: `Município de São Paulo` (`tribunal.csv` linha 2) contra `MUNICIPIO DE SAO PAULO` (`hub.csv` linha 2);
- o processo aparece com e sem máscara: `0023456-21.2020.8.26.0053` (`tribunal.csv` linha 3) contra `00234562120208260053` (`hub.csv` linha 3);
- `tribunal.csv` está em ISO-8859-1. Lido como UTF-8, como a documentação manda, `Município` vira `Munic�pio` e não bate com nada (problema 9).

**Impacto.** A busca por texto exato aponta como divergentes precatórios que são iguais (linhas 2 e 3). O ruído esconde as divergências reais: valor de face e ente diferentes (problema 8) e precatórios faltando (problema 5). A conciliação manual não consegue dizer "onde nem por quê", que é a queixa da operação.

**Causa ou consequência.** Causa raiz. Os problemas 9, 10 e 13 alimentam o ruído. Os problemas 5 e 8 são as divergências reais que ele encobre.

#### 5. Precatórios que existem só de um lado (um deles já vencido)

**Evidência.**

- `0067890-65.2016.8.26.0053` está em `tribunal.csv` (linha 6, face 7.000,00), em `apresentacoes.json` (linha 24, apresentado em `2023-12-31`) e em `pagamentos.json` (`ev-011`, linhas 99–104, 4.000). **Não está em `hub.csv`.**
- `0056789-54.2017.4.03.6100` está em `hub.csv` (linha 6, face 22000.00), em `apresentacoes.json` (linha 20) e em `pagamentos.json` (`ev-009`, linhas 83–88). **Não está em `tribunal.csv`.**

**Impacto.**

- `0067890`: apresentado em 2023-12-31, o prazo seria **2024-12-31**. O precatório já está vencido e não aparece na carteira, então não entra na priorização. Como `precatorio_id` é obrigatório (`schema.sql` linha 10), o pagamento de 4.000 do `ev-011` não tem onde ser gravado e cai no problema 2.
- `0056789`: o sistema acompanha um precatório de 22.000 que o tribunal não lista. Pode ser precatório já quitado, cancelado ou fora do recorte do tribunal. É também o processo do valor negativo (problema 14).

**Causa ou consequência.** Causa. A conciliação por texto (problema 4) não deixa claro se a ausência é real ou se é só diferença de escrita.

#### 6. `ev-001` aparece duas vezes, com o valor alterado

**Evidência.** `DOCUMENTACAO_TRIBUNAL.md` define `evento_id` como identificador único e `atualizado_em` como a última alteração do registro. Em `pagamentos.json`:

- linhas 3–8: `ev-001`, processo `0012345-10.2019.8.26.0053`, `valor` 15000.0 (linha 5), `data_pagamento` `2025-03-10`, `atualizado_em` `2025-03-10T10:00:00-03:00` (linha 8);
- linhas 67–72: o mesmo `ev-001`, o mesmo processo e a mesma data, `valor` 15500.0 (linha 69), `atualizado_em` `2025-03-11T09:00:00-03:00` (linha 72).

**Impacto.** A segunda ocorrência parece correção da primeira: o valor sobe 500 no dia seguinte. Somar as duas linhas grava 30.500. Ficar só com a primeira grava 15.000 e perde a correção. O total que a operação compara com o tribunal fica errado em 15.000 ou em 500, conforme a regra usada. Reprocessar o arquivo soma de novo.

**Causa ou consequência.** As duas versões no mesmo arquivo são a causa. O total inflado é consequência do problema 1: o banco não tem `atualizado_em` nem unicidade de `evento_id` para ficar com a versão mais recente.

#### 7. `ev-007` é estorno; documentação e banco discordam sobre estorno

**Evidência.**

- `DOCUMENTACAO_TRIBUNAL.md`: `tipo` é "sempre pagamento".
- `ev-007`, linhas 59–64: processo `0034567-32.2018.8.26.0405`, `valor` 5000 (linha 61), `data_pagamento` `2025-02-21`, `tipo` `estorno` (linha 63).
- `ev-006`, linhas 51–56: o mesmo processo, `valor` 5000, `data_pagamento` `2025-02-20`, `tipo` `pagamento`.
- `schema.sql` linha 12: `CHECK (tipo IN ('pagamento', 'estorno'))`. O banco **prevê** estorno, com valor positivo (linha 13). A documentação diz que estorno não existe.

**Impacto.** Há 5.000 lançados como pagamento e, no dia seguinte, 5.000 de estorno. O resultado correto provavelmente é 0 pago. O banco aceita o `estorno`, mas não se sabe o que o script faz com ele. Se o script só aceita `pagamento`, o estorno é ignorado (problema 2) e o precatório fica com 5.000 pagos. Se soma qualquer linha sem olhar o `tipo`, o total vai a 10.000. A operação não é avisada de qual dos dois caminhos ocorreu.

**Causa ou consequência.** Causa: documentação desatualizada em relação ao banco e ao arquivo real. O `ev-006` cumpre o leiaute e só entra aqui por ser o pagamento que o estorno parece desfazer.

#### 8. Valor de face e ente diferentes entre tribunal e hub

**Evidência.**

- `0023456-21.2020.8.26.0053`: valor de face **30.000,00** em `tribunal.csv` (linha 3) contra **31000.00** em `hub.csv` (linha 3).
- `0045678-43.2021.5.02.0011`: ente **União** em `tribunal.csv` (linha 5) contra **Município de Santos** em `hub.csv` (linha 5). O processo é da Justiça do Trabalho (`J` = 5, TRT da 2ª Região).

**Impacto.**

- O valor de face errado em 1.000 distorce o saldo a receber do precatório e qualquer indicador sobre ele.
- O ente devedor errado põe o precatório no devedor errado. A priorização e a análise de risco dependem de quem paga, porque União e município têm capacidade e histórico de pagamento muito diferentes.

**Causa ou consequência.** Causa. São as divergências reais que a comparação por texto exato do problema 4 mistura com diferenças só de escrita.

### Média

#### 9. `tribunal.csv` fora do leiaute documentado

**Evidência.** `DOCUMENTACAO_TRIBUNAL.md` diz: CSV em UTF-8, campos separados por vírgula, `valor_face` com ponto decimal. O arquivo tem:

- separador `;` (linha 1: `numero_processo;ente_devedor;valor_face`);
- codificação ISO-8859-1 (Latin-1), com quebra de linha CRLF. Lido como UTF-8, `Município` vira `Munic�pio` e `União` vira `Uni�o`;
- valor com ponto de milhar e vírgula decimal: `45.000,00` (linha 2) e os demais.

`hub.csv`, por contraste, está em UTF-8, com vírgula como separador e ponto decimal.

**Impacto.** Um leitor que siga a documentação não separa as colunas, corrompe os acentos e não converte o valor de face. A comparação com o hub falha em todas as linhas, mesmo quando os dados batem.

**Causa ou consequência.** Consequência provável do Passo 3: separador `;`, vírgula decimal, Latin-1 e CRLF são exatamente o que o Excel em português grava ao salvar um CSV. Não dá para saber se o tribunal mandou assim ou se o arquivo foi alterado no Excel, porque o arquivo original não é guardado antes de ser aberto. Em qualquer caso, é causa do ruído do problema 4.

#### 10. `numero_processo CHAR(20)` não cabe o CNJ com máscara

**Evidência.** `schema.sql` linha 3: `numero_processo CHAR(20) NOT NULL UNIQUE`. O formato CNJ da documentação (`NNNNNNN-DD.AAAA.J.TR.OOOO`) tem **25** caracteres; só os dígitos têm 20. `tribunal.csv` e quase todo `pagamentos.json` usam a máscara. `hub.csv` mistura os dois formatos (linha 3 sem máscara, as demais com).

**Impacto.** O banco só aceita o número sem máscara. Não se sabe se o script remove a máscara antes de procurar o precatório. Se ele procura com o processo como veio do tribunal (com máscara), a busca não acha nada. O evento cai no problema 2, ou alguém remove a máscara à mão e de forma inconsistente, o que explicaria a linha 3 do hub.

**Causa ou consequência.** Causa. Ajuda a explicar a mistura de formatos dos problemas 4 e 13.

#### 11. `ev-002`: valor em texto com vírgula, e registro duplicado

**Evidência.** A documentação pede `valor` numérico, com ponto decimal, e `evento_id` único. `ev-002` está nas linhas 11–16 e, idêntico, nas linhas 27–32. Nas duas cópias, `"valor": "2.500,50"` (linhas 13 e 29), processo `0012345-10.2019.8.26.0053`. A data também está fora do padrão (problema 16).

**Impacto.** A conversão do valor pode falhar, porque é uma string com ponto de milhar e vírgula decimal. O pagamento de 2.500,50 fica de fora (problema 2) ou entra como 2,5 ou 250.050, conforme a conversão. Se a conversão funcionar, a cópia idêntica faz o valor entrar duas vezes (problema 1).

**Causa ou consequência.** O tipo string com vírgula é causa da leitura errada. A segunda cópia é causa de contagem dupla. As duas falhas estão no mesmo registro; uma não explica a outra.

#### 12. `ev-004`: valor nulo

**Evidência.** `ev-004`, linhas 35–40: processo `0023456-21.2020.8.26.0053` (linha 36), `"valor": null` (linha 37), `data_pagamento` `2025-05-03`, `tipo` `pagamento`. A documentação exige valor numérico, e `schema.sql` linha 13 exige `NOT NULL`.

**Impacto.** Existe um evento de pagamento sem valor, no dia seguinte ao `ev-003` (8.000, mesmo processo). Pode ser um pagamento cujo valor não foi preenchido, um cancelamento ou um evento ainda em processamento. O banco recusa a linha e, pelo Passo 5, ninguém é avisado. Se for um pagamento real, o total do precatório fica menor que o do tribunal num valor que não é possível estimar.

**Causa ou consequência.** Causa: defeito no dado do tribunal. O sumiço silencioso é consequência do problema 2.

#### 13. `ev-005` e `hub.csv`: processo sem máscara CNJ

**Evidência.** A documentação pede processo no formato `NNNNNNN-DD.AAAA.J.TR.OOOO`.

- `ev-005`, linhas 43–48: `"processo": "00234562120208260053"` (linha 44), `valor` 1200.0, `data_pagamento` `2025-06-01`.
- `hub.csv` linha 3: o mesmo `00234562120208260053`.
- Os dígitos são os mesmos de `0023456-21.2020.8.26.0053` (`tribunal.csv` linha 3; `ev-003` e `ev-004`).

**Impacto.** São 1.200 associados a um texto que não é o CNJ como o tribunal escreve. Comparado como texto, esse pagamento não se junta ao processo mascarado: o total pago fica dividido em duas chaves, ou o evento é descartado (problema 2). O mesmo vale para a linha 3 do hub na conciliação semanal (problema 4).

**Causa ou consequência.** A falta de máscara é a causa. O total dividido é consequência de comparar o processo como texto, sem normalizar os dígitos (problema 4), e o problema 10 é a explicação provável de por que o hub tem esse formato.

#### 14. `ev-009`: valor negativo, em processo ausente do tribunal

**Evidência.** `ev-009`, linhas 83–88: processo `0056789-54.2017.4.03.6100` (linha 84), `"valor": -200` (linha 85), `data_pagamento` `2025-07-20`, `tipo` `pagamento`. A documentação não prevê valor negativo, e `schema.sql` linha 13 exige `valor > 0`. O processo não está em `tribunal.csv` (problema 5).

**Impacto.** O arquivo tem dois jeitos de registrar uma baixa: `tipo` `estorno` com valor positivo (`ev-007`) e valor negativo com `tipo` `pagamento` (`ev-009`). O banco aceita o primeiro e recusa o segundo, então os -200 são descartados em silêncio (problema 2). Se fossem aceitos, reduziriam em 200 o total de um precatório que o tribunal nem lista.

**Causa ou consequência.** Causa: defeito no dado. Convive com o problema 7, mas não é consequência dele, porque aqui o `tipo` continua `pagamento` e a baixa está no sinal do valor.

#### 15. `ev-010`: processo vazio

**Evidência.** `ev-010`, linhas 91–96: `"processo": ""` (linha 92), `valor` 750, `data_pagamento` `2025-08-01`, `tipo` `pagamento`. A documentação exige o número CNJ, e `schema.sql` linha 10 exige `precatorio_id`.

**Impacto.** Os 750 não têm precatório. O banco recusa a linha, e pelo Passo 5 o valor some da conciliação sem aviso. Se o script gravasse com uma chave vazia, apareceria um total pago sem dono.

**Causa ou consequência.** O processo vazio é a causa. O sumiço silencioso é consequência do problema 2.

### Baixa

#### 16. `ev-002`: data de pagamento fora do padrão

**Evidência.** A documentação pede `data_pagamento` em `AAAA-MM-DD`. `ev-002`, linhas 14 e 30: `"data_pagamento": "10/04/2025"`. É o mesmo registro do problema 11, nas duas cópias.

**Impacto.** A data pode fazer a importação recusar o evento, junto com o valor em texto. Lida como dia/mês, é 10 de abril de 2025, e coincide com o `atualizado_em` do registro (`2025-04-10`). Lida como mês/dia, seria 4 de outubro de 2025. O efeito em reais é o do problema 11: o pagamento de 2.500,50, uma vez. Esta data não abre um segundo furo de valor.

**Causa ou consequência.** Defeito do registro. Acompanha o valor em string e a duplicata do problema 11.

#### 17. Arquivo diário não cobre só 7 dias

**Evidência.** Passo 1: o arquivo diário traz os eventos dos últimos 7 dias. Em `pagamentos.json`, `data_pagamento` vai de `2025-02-20` (`ev-006`, linha 54) a `2025-08-10` (`ev-011`, linha 102).

**Impacto.** Se este arquivo fosse a carga de um dia e o script somasse todas as linhas, pagamentos de vários meses entrariam juntos, e de novo a cada reprocessamento (problema 1). O intervalo pode existir porque o arquivo do case é uma amostra, e não um recorte real de produção.

**Causa ou consequência.** Diferença entre o processo descrito e o arquivo entregue. Fica como o item menos grave até confirmar se é uma carga real ou uma amostra.

## Conferidos sem problema

**Eventos de `pagamentos.json` aderentes ao leiaute.** Processo no formato CNJ, valor numérico, data em `AAAA-MM-DD`, `tipo` `pagamento` e `atualizado_em` preenchido.

| Registro | Linhas | Processo | Valor | Data | Observação |
|---|---|---|---|---|---|
| `ev-003` | 19–24 | `0023456-21.2020.8.26.0053` | 8000 | 2025-05-02 | Valor de face diverge entre as fontes (problema 8) |
| `ev-006` | 51–56 | `0034567-32.2018.8.26.0405` | 5000 | 2025-02-20 | Par com o estorno `ev-007` (problema 7) |
| `ev-008` | 75–80 | `0045678-43.2021.5.02.0011` | 3000 | 2025-07-15 | Ente diverge entre as fontes (problema 8) |
| `ev-011` | 99–104 | `0067890-65.2016.8.26.0053` | 4000 | 2025-08-10 | Processo ausente do hub (problema 5) |

A primeira ocorrência de `ev-001` (linhas 3–8) também segue o leiaute. Ela está no problema 6 porque o mesmo `evento_id` volta nas linhas 67–72 com outro valor.

**Observações que não foram tratadas como problema.**

- Valores inteiros (`8000`, `5000`, `3000`, `4000`, `750`) são números JSON válidos. A documentação pede ponto decimal; um inteiro sem casa decimal continua sendo número.
- `0034567-32.2018.8.26.0405` foi apresentado em `2024-02-29`. A data existe (2024 é bissexto) e o prazo do hub, `2025-12-31`, está correto. Vale como caso de teste.
- Os dígitos verificadores (`DD`) de nenhum dos seis processos passam no cálculo do CNJ (módulo 97). Como o enunciado avisa que os processos são fictícios, isso não foi tratado como defeito, mas a validação não deve entrar como regra de descarte sem confirmar com a operação.

## Prevenção

### Princípios

As propostas estão em três frentes:

- **Processo** e **banco:** mudanças sobre o que foi recebido, isto é, o fluxo descrito no enunciado e o `schema.sql`. O banco tem SQL pronto.
- **Importação:** como o script não foi fornecido (ver [Limite da análise](#como-ler-este-documento)), não há alteração sobre um código existente. É uma proposta de como o processo de importação deveria funcionar, escrita a partir do comportamento descrito nos Passos 2 e 5. Ela vale tanto para corrigir o script atual quanto para escrever um novo.

Quatro regras orientam as três frentes. Cada uma ataca uma causa raiz do diagnóstico.

1. **O total pago é calculado a partir dos eventos, nunca acumulado.** O banco guarda um evento por `evento_id`, na versão mais recente. O total é uma consulta sobre esses eventos. Assim, importar o mesmo arquivo duas vezes não muda nada (problemas 1, 6 e 11).
2. **Nada é descartado sem registro.** Todo evento que não pode ser importado vai para uma quarentena, com o registro original e o motivo, e alguém é avisado (problema 2).
3. **O arquivo recebido é guardado como veio e nunca é editado.** Toda leitura parte do original. Ninguém abre, salva ou corrige o arquivo à mão (problema 9).
4. **Cada regra de negócio fica num lugar só, com testes.** A normalização do processo e do ente e o cálculo do prazo são definidos uma vez e reaproveitados por importação, conciliação e relatórios (problemas 3, 4, 10 e 13).

### Problema e medida

| # | Processo | Importação (proposta) | Banco |
|---|---|---|---|
| 1 | Reprocessar passa a ser seguro | Uma transação por arquivo; upsert por `evento_id` | `UNIQUE (evento_id)`, `atualizado_em`, total por view |
| 2 | Relatório diário de quarentena, com responsável | Toda recusa vira registro com motivo | Tabela `evento_rejeitado` |
| 3 | Fuso e regra de 2 de abril definidos por escrito | Converter a apresentação para data de Brasília | `data_apresentacao DATE` e view de prazo |
| 4 | Conciliação automática, sem comparação manual | Comparar por dígitos do processo e por ente canônico | Tabela `tribunal_precatorio` e view de conciliação |
| 5 | Tratar a lista de divergências toda semana | Listar o que só existe de um lado | Mesma view de conciliação |
| 6 | Tribunal confirma a regra de correção | Ficar com o maior `atualizado_em` | Upsert condicionado a `atualizado_em` |
| 7 | Tribunal atualiza a documentação sobre estorno | Validar o `tipo` contra a lista acordada | `CHECK` de `tipo` mantido; estorno abate na view |
| 8 | Divergência de face ou ente vai para análise | Sinalizar sem sobrescrever o cadastro | View de conciliação |
| 9 | Arquivo chega por canal automático, não por Excel | Exigir codificação e separador; recusar o resto | Tabela `arquivo_recebido` com o original e o hash |
| 10 | — | Normalizar o processo para 20 dígitos | `VARCHAR(20)` com `CHECK`; máscara gerada |
| 11, 16 | Tribunal confirma os formatos aceitos | Converter só variantes conhecidas e marcar como corrigido | `NUMERIC` e `DATE` garantem o tipo final |
| 12, 14, 15 | Quarentena com prazo de tratamento | Recusar com motivo específico | `CHECK` e `NOT NULL` mantidos |
| 13 | — | Normalizar o processo antes de procurar | Busca sempre pelos 20 dígitos |
| 17 | Confirmar a janela do arquivo | Aceitar qualquer janela, porque o upsert é idempotente | — |

### No processo

- **Receber os arquivos sem passar pelo Excel.** O anexo é salvo automaticamente numa pasta de entrada (ou o tribunal envia por SFTP ou API) e registrado com hash antes de qualquer leitura. Se alguém precisar conferir, abre uma cópia ou o relatório gerado, nunca o original.
- **Trocar a conciliação manual por um relatório.** Um programa compara a lista do tribunal com o sistema pelos dígitos do processo e pelo ente canônico. O relatório separa as divergências reais (só de um lado, valor de face diferente, ente diferente) das que eram só de escrita. A operação passa a tratar uma lista curta, e não a procurar texto.
- **Quarentena com dono.** Todo dia sai um relatório com os eventos recusados, o motivo e o registro original. Um responsável da operação decide, dentro de um prazo combinado, se o evento é corrigido, descartado ou devolvido ao tribunal. Nenhum evento fica parado sem decisão.
- **Reprocessar sem medo.** Com a importação idempotente, rodar o mesmo arquivo de novo não altera os totais. O operador continua podendo reprocessar, e o sistema registra cada execução.
- **Fechar o contrato com o tribunal.** Pedir uma versão 2.2 da documentação que trate o estorno, o valor negativo, a codificação, o separador, o fuso das datas e a regra de correção de um `evento_id`. Devolver ao tribunal, periodicamente, a lista do que foi recusado por quebra de leiaute.
- **Avisar quando o prazo mudar.** A correção do cálculo muda a prioridade de alguns precatórios (problema 3). A equipe de carteira recebe a lista do que mudou antes da troca.

### Na importação (proposta de processo)

O script atual não foi fornecido. O que se sabe dele está no enunciado: ele soma cada valor ao total pago, é rodado de novo quando falha e ignora, sem aviso, o que não consegue importar. Os oito passos abaixo descrevem como a importação deveria funcionar para que os problemas do diagnóstico não voltem. Antes de implementar, é preciso comparar essa proposta com o código atual (dúvidas 22 e 23) para saber o que já existe e o que falta.

1. **Registrar o arquivo antes de ler.** Calcular o SHA-256, gravar em `arquivo_recebido` com o conteúdo original e só depois interpretar.
2. **Ler com regras explícitas.** O CSV é lido com codificação e separador declarados. Se o arquivo não estiver no leiaute, a importação recusa o arquivo inteiro e avisa, em vez de adivinhar. Variantes conhecidas, como `"2.500,50"` e `10/04/2025`, só são convertidas se estiverem numa lista de exceções acordada com o tribunal, e o evento fica marcado como corrigido no relatório.
3. **Validar campo a campo, contra o leiaute.** Cada evento passa por uma validação. O que falhar vai para `evento_rejeitado` com um motivo específico, como `valor_nulo`, `valor_negativo`, `processo_vazio`, `processo_invalido`, `precatorio_inexistente` ou `tipo_desconhecido`.
4. **Normalizar antes de comparar.** O processo é reduzido aos 20 dígitos. O ente passa por uma tabela de nomes conhecidos. A data de apresentação é convertida para a data civil em `America/Sao_Paulo`, e uma data sem hora é tratada como data local.
5. **Deduplicar dentro do arquivo.** Para cada `evento_id`, ficar com o registro de maior `atualizado_em`. Cópias idênticas viram uma só, e o relatório conta quantas foram descartadas.
6. **Gravar numa transação por arquivo, com upsert.** Ou o arquivo entra inteiro, ou não entra nada. O upsert só substitui um evento quando o `atualizado_em` recebido é mais novo que o gravado.
7. **Nunca somar na importação.** A importação só grava eventos. O total pago e o prazo vêm das views do banco.
8. **Terminar com um relatório e um código de saída.** O relatório traz quantos eventos foram lidos, inseridos, atualizados, ignorados por duplicata e mandados para a quarentena. Se houver quarentena, o código de saída é diferente de zero e o alerta é enviado.

### No banco (SQL)

PostgreSQL, compatível com o `schema.sql` atual. É uma migração em cima das tabelas existentes, não uma recriação.

O mesmo SQL está, pronto para rodar, em [`prevencao/migracao.sql`](../prevencao/migracao.sql). O arquivo roda numa transação única. Ele tem duas diferenças em relação aos trechos abaixo:

- em vez de só listar os `evento_id` duplicados, a migração **para com erro** quando eles existem, para não criar a restrição sobre dados inconsistentes;
- o upsert e a consulta de alerta ficam como comentário, porque são comandos da importação proposta e do relatório diário, e não parte da migração.

Se um dos dois arquivos mudar, o outro precisa mudar junto.

**1. Arquivos recebidos.** Guarda o original e o hash, para rastrear cada número até o arquivo de onde veio.

```sql
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
```

**2. Número do processo (problemas 10 e 13).** Guarda só os 20 dígitos, rejeita qualquer outro formato e gera a versão com máscara para exibir.

```sql
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
```

**3. Ente devedor (problemas 4 e 8).** Um cadastro canônico de entes e uma tabela com os nomes como chegam de cada fonte.

```sql
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
```

**4. Data de apresentação e prazo (problema 3).** Guarda o texto original e a data civil em Brasília. O prazo é calculado numa view, num lugar só.

```sql
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
```

**5. Pagamento: um registro por evento, na versão mais recente (problemas 1 e 6).**

```sql
ALTER TABLE pagamento
    ADD COLUMN atualizado_em TIMESTAMPTZ,
    ADD COLUMN arquivo_id    BIGINT REFERENCES arquivo_recebido (id);

-- Antes da restrição, as duplicatas já gravadas precisam ser resolvidas.
-- Esta consulta lista quais são; a base limpa (etapa 2) é a fonte para refazê-las.
SELECT evento_id, count(*) AS vezes, sum(valor) AS valor_somado
FROM pagamento
GROUP BY evento_id
HAVING count(*) > 1;

ALTER TABLE pagamento ADD CONSTRAINT pagamento_evento_id_unico UNIQUE (evento_id);
-- Depois de preencher atualizado_em nas linhas antigas:
ALTER TABLE pagamento ALTER COLUMN atualizado_em SET NOT NULL;
```

Comando que a importação proposta usaria para gravar cada evento. Reimportar não duplica, e só uma versão mais nova substitui a gravada:

```sql
INSERT INTO pagamento (precatorio_id, evento_id, tipo, valor, pago_em, atualizado_em, arquivo_id)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (evento_id) DO UPDATE
SET precatorio_id = EXCLUDED.precatorio_id,
    tipo          = EXCLUDED.tipo,
    valor         = EXCLUDED.valor,
    pago_em       = EXCLUDED.pago_em,
    atualizado_em = EXCLUDED.atualizado_em,
    arquivo_id    = EXCLUDED.arquivo_id
WHERE EXCLUDED.atualizado_em > pagamento.atualizado_em;
```

**6. Quarentena (problema 2).** Todo evento recusado fica registrado, com o conteúdo original e o motivo, até alguém decidir o que fazer.

```sql
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
```

**7. Total pago calculado, não acumulado (problemas 1 e 7).** Supõe que o estorno abate o pagamento, o que ainda depende da dúvida 5.

```sql
CREATE VIEW vw_total_pago AS
SELECT
    p.id AS precatorio_id,
    p.numero_cnj,
    p.valor_face,
    COALESCE(SUM(CASE g.tipo WHEN 'estorno' THEN -g.valor ELSE g.valor END), 0) AS total_pago
FROM precatorio p
LEFT JOIN pagamento g ON g.precatorio_id = p.id
GROUP BY p.id, p.numero_cnj, p.valor_face;

-- Alerta: total negativo ou maior que o valor de face.
SELECT * FROM vw_total_pago
WHERE total_pago < 0 OR total_pago > valor_face;
```

**8. Conciliação com o tribunal (problemas 4, 5 e 8).** A lista semanal é gravada como veio, já normalizada. A view compara com o sistema pelos dígitos e pelo ente canônico.

```sql
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
SELECT
    COALESCE(t.numero_processo, p.numero_processo) AS numero_processo,
    p.id IS NULL                                    AS so_no_tribunal,
    t.numero_processo IS NULL                       AS so_no_sistema,
    t.valor_face IS DISTINCT FROM p.valor_face      AS valor_face_diferente,
    t.ente_id    IS DISTINCT FROM p.ente_id         AS ente_diferente,
    t.valor_face AS face_tribunal,
    p.valor_face AS face_sistema,
    t.ente_id    AS ente_tribunal,
    p.ente_id    AS ente_sistema
FROM ultima_lista t
FULL JOIN precatorio p ON p.numero_processo = t.numero_processo;
```

Aplicada aos arquivos do case, essa view mostraria só as divergências reais:

| Processo | Resultado |
|---|---|
| `0023456` | face diferente |
| `0045678` | ente diferente |
| `0056789` | só no sistema |
| `0067890` | só no tribunal |

As diferenças de escrita das linhas 2 e 3 deixariam de aparecer.

### Ordem de implantação

1. **Primeiro, parar de piorar.** Registrar os arquivos recebidos, criar a quarentena e tornar a importação idempotente (itens 1, 5 e 6 do SQL). A partir daí, nenhum total infla e nada some sem aviso.
2. **Depois, corrigir o passado.** Refazer a tabela `pagamento` a partir da base limpa (etapa 2) e só então criar `UNIQUE (evento_id)`.
3. **Em seguida, prazo e conciliação.** Criar as views de prazo e conciliação (itens 4 e 8) e avisar a equipe de carteira sobre os prazos que mudarem.
4. **Por último, o contrato.** Fechar com o tribunal a versão 2.2 da documentação e trocar o canal de envio.

## Dúvidas

Perguntas a responder antes de pôr a limpeza em produção, agrupadas por quem pode respondê-las. Entre colchetes está o problema a que cada uma se refere. A pergunta do item 7 das anotações brutas está na dúvida 5.

### Para o tribunal

1. **[6]** A segunda ocorrência do `ev-001` é uma correção, e o total deve ficar em 15.500, substituindo os 15.000?
2. **[1, 6]** Uma correção sempre mantém o mesmo `evento_id`, com um `atualizado_em` maior? O `evento_id` é único em todo o histórico ou só dentro de um arquivo? Como é sinalizado um evento cancelado?
3. **[11]** `"2.500,50"` deve entrar como 2500.50? A cópia idêntica do `ev-002` deve ser contada uma vez?
4. **[16]** `10/04/2025` no `ev-002` é 10 de abril de 2025?
5. **[7]** No par `ev-006` / `ev-007`, ignoramos o `tipo` `estorno` e somamos só o `pagamento`, ou o estorno abate os 5.000? Se o estorno é um tipo válido, a documentação será atualizada? Um estorno sempre se refere a um pagamento anterior e, se sim, qual campo liga os dois?
6. **[14]** O valor -200 do `ev-009` é um estorno, um erro de sinal ou outro tipo de lançamento?
7. **[12]** O `ev-004`, com valor nulo, é um pagamento sem valor preenchido, um cancelamento ou um evento pendente? O tribunal reenvia o evento com o valor depois?
8. **[15]** O `ev-010`, de 750 e processo vazio, pode ser reenviado com o processo? Existe outro campo ou arquivo que o identifique?
9. **[9]** O `tribunal.csv` sai do tribunal em UTF-8 e com vírgula como separador, como diz a documentação, ou já sai com `;`, Latin-1 e vírgula decimal? É possível receber os arquivos por um canal automático (SFTP ou API) em vez de e-mail?
10. **[8]** No `0023456-21.2020.8.26.0053`, o valor de face certo é 30.000,00 ou 31.000,00? O valor de face do arquivo é o original ou já vem atualizado?
11. **[8]** No `0045678-43.2021.5.02.0011`, o ente devedor é a União ou o Município de Santos? O tribunal pode enviar o CNPJ ou um código do ente, em vez de só o nome?
12. **[5]** Quais tribunais a lista cobre? O `0056789-54.2017.4.03.6100` é da Justiça Federal, 3ª Região (`J` = 4, `TR` = 03), e a lista traz processos do TJSP (`8.26`) e do TRT da 2ª Região (`5.02`). Ele ficou de fora por ser de outro tribunal, ou por ter sido quitado ou cancelado?
13. **[3]** Qual fuso vale para a data de apresentação? Uma apresentação às 22h de 2 de abril, no horário de Brasília, conta como "até 2 de abril"? Por que as datas vêm em três formatos (só data, `-03:00` e `Z`)?
14. **[observação]** Os números de processo reais passam no cálculo do dígito verificador do CNJ? Se sim, essa validação pode virar regra de recusa.

### Para a operação

15. **[17]** O `pagamentos.json` do case é a carga de um dia, ou uma amostra montada com vários meses?
16. **[1]** Quantas vezes, em média, um arquivo é reprocessado? Existe registro disso? A resposta permite estimar quanto os totais atuais estão inflados.
17. **[2]** Quem deve receber o relatório diário de eventos recusados, e em quanto tempo eles precisam ser tratados?
18. **[9]** Quando o operador abre o `tribunal.csv` no Excel, ele salva por cima do anexo? O anexo original dos e-mails anteriores ainda existe?
19. **[5]** Por que o `0067890-65.2016.8.26.0053` não está no hub? Ele nunca foi cadastrado, ou foi removido? Pelo enunciado, o prazo venceu em 2024-12-31: a equipe sabe disso?
20. **[3]** Quem precisa ser avisado quando a correção do cálculo mudar o prazo, e portanto a prioridade, de um precatório?

### Para quem mantém o sistema

21. **[3, 10]** O `hub.csv` traz `apresentado_em` e `prazo_pagamento`, mas o `schema.sql` não tem essas colunas. De onde vêm esses dados? O `schema.sql` é o banco que gera o hub?
22. **[3]** Onde está o código que calcula o prazo? É preciso entender por que `0012345` e `0045678`, os dois apresentados em 2 de abril, receberam prazos diferentes.
23. **[2, 7, 10, 11, 13]** Podemos ver o código do script de importação atual? Ele não foi fornecido, e o diagnóstico precisou supor o comportamento dele. As perguntas principais são:
    - ele procura o precatório pelo texto do processo como veio ou pelos dígitos?
    - como ele converte valor e data fora do padrão?
    - o que ele faz com `tipo` `estorno`?
    - como os números com máscara caberiam num `CHAR(20)`?
24. **[1]** Os arquivos de pagamento antigos estão guardados? Sem eles, não dá para refazer o total pago desde o início, só a partir de agora.

## Ajustes em relação ao texto bruto

- Os itens 2 e 9 descrevem o mesmo registro (`ev-010`, processo vazio). Entraram como um problema só (15).
- Os itens 4 e 7 descrevem o par `ev-006` / `ev-007`. O fato fica no problema 7. A pergunta sobre ignorar o `estorno` e somar só o `pagamento` fica nas Dúvidas.
- No item 7, o evento com `tipo` `pagamento` é o `ev-006`. O `tipo` `estorno` é o `ev-007`. Os dois têm o processo `0034567-32.2018.8.26.0405`.
- O `ev-004` (valor nulo) estava nas anotações pessoais de trabalho (não versionadas), mas tinha ficado de fora do texto bruto e da primeira versão deste documento. Entrou como problema 12.
- Os números de linha da primeira versão foram corrigidos. Os campos `valor` e `data_pagamento` do `ev-002` e as datas do `ev-006` e do `ev-011` estavam uma linha abaixo da real.
- A ordem da anotação foi reorganizada por gravidade, considerando todos os arquivos.

## Texto bruto

Anotações como foram escritas, sem o ajuste da IA.

```text
Inconsistencias encontradas

1. Data de pagamento despadronizada: (ev-002)

2. Um dos eventos de pagamentos veio sem o numero do processo (ev-010)

3. evento (ev-002) veio com o valor no tipo string, alem de virgula no valor e não apenas o ponto decimal, o que pode ter dado problema na leitura do dado e o mesmo evento está duplicado

4. evento (ev-007) com o tipo: "estorno" ao invés de pagamento

5. evento (ev-001) com 2 ocorrencia com valor de pagamento alterado, podendo ser correção.

6. Evento (ev-005) sem o padrão de mascaramento CNJ no processo

7. evento (ev-006) contem o mesmo numero de processo, porem sem o tipo estorno, devemos apenas ignorar o com o tipo "estorno"? e somar o tipo "pagamento"

8. evento (ev-009) com valor negativo "-200"

9. evento (ev-010) com o processo vazio

10. A Janela de dados não é de 7 dias, o periodo esta entre 2025-02-20 (ev-006) a 2025-08-10 (ev-011), avaliar se o problema tem relação ao fato de não ser dados reais
```
