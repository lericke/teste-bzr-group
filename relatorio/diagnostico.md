# Diagnóstico

Escopo desta versão: `case-candidato/dados/pagamentos.json` confrontado com `case-candidato/DOCUMENTACAO_TRIBUNAL.md` (versão 2.1) e com o fluxo descrito em `case-candidato/ENUNCIADO.md`. Ainda não cruza `tribunal.csv`, `hub.csv`, `apresentacoes.json` nem `schema.sql`.

O texto das seções seguintes foi formatado com IA a partir das anotações brutas, para cumprir o que o enunciado pede: evidência (arquivo, registro, linha), impacto para o negócio e se o achado é causa ou consequência de outro. A ordem dos problemas é da maior gravidade para a menor, pelo efeito no total pago. As anotações originais estão na seção [Texto bruto](#texto-bruto), para o avaliador ver o que foi ajustado.

Ajustes em relação ao texto bruto:

- Os itens 2 e 9 descrevem o mesmo registro (`ev-010`, processo vazio). Entraram como um problema só.
- Os itens 4 e 7 descrevem o par `ev-006` / `ev-007`. O fato fica no problema do `estorno`. A pergunta sobre ignorar o `estorno` e somar só o `pagamento` fica em Dúvidas.
- No item 7, o evento com `tipo` `pagamento` é o `ev-006`. O `tipo` `estorno` é o `ev-007`. Os dois têm o processo `0034567-32.2018.8.26.0405`.
- A ordem da anotação foi reordenada por gravidade.

## Problemas

### 1. `ev-001` aparece duas vezes, com o valor alterado

**Evidência.** `DOCUMENTACAO_TRIBUNAL.md` define `evento_id` como identificador único e `atualizado_em` como a última alteração do registro. Em `pagamentos.json`:

- linhas 2–9: `ev-001`, processo `0012345-10.2019.8.26.0053`, `valor` 15000.0, `data_pagamento` `2025-03-10`, `atualizado_em` `2025-03-10T10:00:00-03:00`
- linhas 67–73: o mesmo `ev-001`, o mesmo processo e a mesma data, `valor` 15500.0, `atualizado_em` `2025-03-11T09:00:00-03:00`

O enunciado diz que o script soma cada valor ao total pago do processo.

**Impacto.** A segunda ocorrência parece correção da primeira: o valor sobe 500 no dia seguinte. Somar as duas linhas grava 30.500. Ficar só com a primeira grava 15.000 e perde a correção. O total que a operação compara com o tribunal muda em 15.000 ou em 500, conforme a regra usada. Reprocessar o arquivo soma de novo.

**Causa ou consequência.** As duas versões no mesmo arquivo são a causa. O total inflado é consequência de somar um `evento_id` que a documentação trata como único, em vez de ficar com o `atualizado_em` mais recente.

### 2. `ev-007` veio com `tipo` "estorno"

**Evidência.** A documentação diz que `tipo` é sempre `pagamento`. `ev-007`, linhas 59–65: processo `0034567-32.2018.8.26.0405`, `valor` 5000, `data_pagamento` `2025-02-21`, `tipo` `estorno`. `ev-006`, linhas 51–57: o mesmo processo, `valor` 5000, `data_pagamento` `2025-02-20`, `tipo` `pagamento`. O enunciado diz que evento que não pode ser importado é ignorado, sem aviso.

**Impacto.** Há 5.000 lançados como pagamento e, no dia seguinte, 5.000 com tipo que o contrato não prevê. Se a importação só soma `pagamento`, o estorno some e o precatório continua com 5.000 pagos. Se soma qualquer linha, o total vai a 10.000. A operação não é avisada de qual dos dois caminhos ocorreu.

**Causa ou consequência.** O `tipo` `estorno` no `ev-007` é a causa. O `ev-006` cumpre o leiaute; ele entra na conta porque é o pagamento do mesmo processo. O total errado é consequência de não haver regra documentada para estorno e de a falha ser silenciosa.

### 3. `ev-002` tem valor em texto, com vírgula decimal, e está duplicado

**Evidência.** A documentação pede `valor` numérico, com ponto como separador decimal, e `evento_id` único. `ev-002` está nas linhas 11–17 e, igual, nas linhas 27–33. Nas duas, `"valor": "2.500,50"` (linhas 14 e 30), processo `0012345-10.2019.8.26.0053`. O mesmo registro também traz a data fora do padrão, tratada no problema 7.

**Impacto.** A leitura do valor pode falhar: string com ponto de milhar e vírgula decimal não é o número que o leiaute descreve. O pagamento de 2.500,50 fica de fora, ou entra como 2.5 ou 250050, conforme a conversão. A cópia idêntica faz o mesmo valor ser lido duas vezes se a conversão passar. O enunciado manda ignorar o que não importa, sem avisar, e somar de novo se o operador reprocessar o arquivo.

**Causa ou consequência.** O tipo string e a vírgula são a causa da leitura errada. A segunda cópia é causa de contagem dupla, no mesmo `evento_id`. As duas falhas estão no mesmo registro; uma não explica a outra.

### 4. `ev-005` está fora do mascaramento CNJ

**Evidência.** A documentação pede processo no formato `NNNNNNN-DD.AAAA.J.TR.OOOO`. `ev-005`, linhas 43–49: `"processo": "00234562120208260053"`, `valor` 1200.0, `data_pagamento` `2025-06-01`. Sem a pontuação, `0023456-21.2020.8.26.0053` (`ev-003`, linhas 19–25) produz os mesmos dígitos.

**Impacto.** São 1.200 associados a um texto que não é o CNJ do precatório. Se a conferência usar o número exatamente como está escrito, como o enunciado descreve entre tribunal e hub, esse valor não se junta ao processo mascarado. O pago fica em duas chaves, ou o evento é descartado por formato.

**Causa ou consequência.** A ausência da máscara é a causa. O total partido é consequência de comparar o processo como texto, sem normalizar os dígitos.

### 5. `ev-009` tem valor negativo

**Evidência.** `ev-009`, linhas 83–89: processo `0056789-54.2017.4.03.6100`, `"valor": -200`, `data_pagamento` `2025-07-20`, `tipo` `pagamento`. A documentação descreve o valor pago em reais e não prevê negativo. O outro sinal de baixa no arquivo é o `estorno` do problema 2, com valor positivo e outro `tipo`.

**Impacto.** Somar -200 reduz o total desse processo. Descartar a linha esconde uma baixa de 200. O arquivo usa dois jeitos de registrar saída de valor (`estorno` e número negativo), e o total muda conforme o script aceite um, o outro, ou os dois.

**Causa ou consequência.** O valor negativo é um problema do dado. Convive com o problema 2 e não é consequência dele: aqui o `tipo` continua `pagamento` e o sinal está no valor.

### 6. `ev-010` veio sem número de processo

**Evidência.** `ev-010`, linhas 91–97: `"processo": ""`, `valor` 750, `data_pagamento` `2025-08-01`, `tipo` `pagamento`. A documentação exige o número CNJ. Nas anotações brutas isso aparece duas vezes: evento sem número de processo e processo vazio. É o mesmo campo, no mesmo registro.

**Impacto.** Os 750 não têm precatório. Se a linha entrar com chave vazia, surge um total pago sem processo. Se for ignorada, os 750 saem da conciliação e ninguém é avisado.

**Causa ou consequência.** O processo vazio é a causa. O sumiço silencioso, quando a importação descarta a linha, é consequência do fluxo descrito no enunciado.

### 7. Data de pagamento fora do padrão no `ev-002`

**Evidência.** A documentação pede `data_pagamento` em `AAAA-MM-DD`. `ev-002`, linhas 15 e 31: `"data_pagamento": "10/04/2025"`. É o mesmo registro do problema 3, nas duas cópias.

**Impacto.** A data pode fazer a importação recusar o evento, junto com o valor em texto. Lida como dia/mês, 10/04/2025 é 10 de abril de 2025. Lida como mês/dia, o mês 10 e o dia 4 trocam de lugar. O efeito em reais é o do problema 3: o pagamento de cerca de 2.500,50, uma vez. Esta data não abre um segundo furo de valor.

**Causa ou consequência.** O formato `DD/MM/AAAA` é defeito do registro. No `ev-002` ele acompanha o valor em string e a duplicata. É outra quebra de leiaute no mesmo evento, com o mesmo impacto financeiro do problema 3.

### 8. A janela do arquivo não é de 7 dias

**Evidência.** O enunciado diz que o arquivo diário traz os eventos dos últimos 7 dias. Em `pagamentos.json`, `data_pagamento` vai de `2025-02-20` (`ev-006`, linha 55) a `2025-08-10` (`ev-011`, linha 103).

**Impacto.** Se este arquivo fosse a carga de um dia e o script somasse todas as linhas, pagamentos de vários meses entrariam juntos, e de novo a cada reprocessamento. O intervalo pode existir porque o arquivo do case não é um recorte real de produção. Confirmar isso evita tratar a janela como falha do tribunal.

**Causa ou consequência.** É diferença entre o processo descrito e o arquivo entregue. Fica como o item menos grave enquanto não se sabe se os dados são um dia operacional ou uma amostra. Se forem uma carga real fora da janela, a soma indevida é consequência, ampliada pela regra de reprocessar somando.

## Eventos aderentes à documentação

Estes registros cumprem, campo a campo, o leiaute de `DOCUMENTACAO_TRIBUNAL.md`: processo no formato CNJ, valor numérico, data em `AAAA-MM-DD`, `tipo` `pagamento` e `atualizado_em` preenchido. Ainda não foram cruzados com `tribunal.csv` nem com `hub.csv`.

| Registro | Linhas | Processo | Valor | Data |
|---|---|---|---|---|
| `ev-003` | 19–25 | `0023456-21.2020.8.26.0053` | 8000 | 2025-05-02 |
| `ev-006` | 51–57 | `0034567-32.2018.8.26.0405` | 5000 | 2025-02-20 |
| `ev-008` | 75–81 | `0045678-43.2021.5.02.0011` | 3000 | 2025-07-15 |
| `ev-011` | 99–105 | `0067890-65.2016.8.26.0053` | 4000 | 2025-08-10 |

`ev-006` está na tabela porque os campos dele seguem a documentação. A dúvida é o par com o `ev-007`, no problema 2.

A primeira ocorrência de `ev-001` (linhas 2–9, valor 15000.0) também segue o leiaute. Ela entra no problema 1 porque o mesmo `evento_id` volta nas linhas 67–73 com outro valor.

Valores inteiros (`8000`, `5000`, `3000`, `4000` e `750` no `ev-010`) são números JSON. A documentação pede ponto como separador decimal; inteiro sem casa decimal continua sendo número. Isso não foi tratado como inconsistência.

`ev-008` é da Justiça do Trabalho (`J` = 5). A documentação do pagamento não restringe o segmento. Máscara válida não significa que o precatório esteja na lista do tribunal.

## Dúvidas

Perguntas para o tribunal ou para a operação, antes de fechar a regra de limpeza. A pergunta do item 7 das anotações brutas está na dúvida 3.

1. A segunda ocorrência do `ev-001` é uma correção e o total deve ficar em 15.500, substituindo os 15.000?
2. `"2.500,50"` deve entrar como 2500.50? A cópia idêntica do `ev-002` deve ser contada uma vez?
3. No par `ev-006` / `ev-007`, ignoramos o `tipo` `estorno` e somamos só o `pagamento`, ou o estorno abate os 5.000?
4. `10/04/2025` no `ev-002` é 10 de abril de 2025?
5. O valor -200 do `ev-009` é estorno, erro de sinal ou outro lançamento?
6. O que fazer com o `ev-010`, de 750 e processo vazio: descartar, deixar em quarentena, ou o número do processo vem de outro arquivo?
7. O intervalo de `2025-02-20` a `2025-08-10` existe porque este arquivo não é um recorte real de 7 dias?

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
