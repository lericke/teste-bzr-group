"""Escrita da base limpa (CSV) e do relatório (Markdown).

Os CSV saem em UTF-8, separados por vírgula, com ponto decimal e datas
ISO: o leiaute que a documentação do tribunal promete e não cumpre.
A saída é determinística: os mesmos arquivos de entrada e a mesma data
de referência produzem exatamente os mesmos bytes.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from .fontes import Fonte
from .pagamentos import CORRIGIDO, DESCARTADO, EM_DUVIDA, VALIDO, Evento
from .precatorios import Precatorio, Rejeicao

ZERO = Decimal("0.00")


@dataclass
class Totais:
    confirmado: Decimal
    em_duvida: Decimal

    @property
    def com_duvidas(self) -> Decimal:
        return self.confirmado + self.em_duvida


def totais_por_processo(eventos: list[Evento]) -> dict[str, Totais]:
    """Total confirmado (válidos e corrigidos) e ajustes em dúvida, por processo."""
    totais: dict[str, Totais] = {}
    for ev in eventos:
        if ev.status == DESCARTADO or ev.processo is None or ev.valor_com_sinal is None:
            continue
        t = totais.setdefault(ev.processo, Totais(ZERO, ZERO))
        if ev.status in (VALIDO, CORRIGIDO):
            t.confirmado += ev.valor_com_sinal
        else:
            t.em_duvida += ev.valor_com_sinal
    return totais


def _num(valor: Decimal | None) -> str:
    return "" if valor is None else f"{valor:.2f}"


def _data(valor: date | None) -> str:
    return "" if valor is None else valor.isoformat()


def _br(valor: Decimal | None) -> str:
    """Valor para leitura humana no relatório: 2.500,50."""
    if valor is None:
        return "—"
    texto = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-{texto}" if valor < 0 else texto


def _motivos(motivos) -> str:
    return " | ".join(m.texto for m in motivos)


def _escrever_csv(caminho: Path, cabecalho: list[str], linhas: list[list[str]]) -> None:
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f, lineterminator="\n")
        escritor.writerow(cabecalho)
        escritor.writerows(linhas)


def escrever(
    pasta: Path,
    fontes: dict[str, Fonte],
    eventos: list[Evento],
    precatorios: dict[str, Precatorio],
    rejeicoes: list[Rejeicao],
    referencia: date,
) -> dict[str, Totais]:
    pasta.mkdir(parents=True, exist_ok=True)
    totais = totais_por_processo(eventos)

    _escrever_csv(
        pasta / "precatorios.csv",
        [
            "numero_processo", "numero_cnj", "ente_devedor", "valor_face", "data_apresentacao",
            "prazo_pagamento", "vencido", "total_pago_confirmado", "ajustes_em_duvida",
            "status", "motivos", "fontes", "ente_tribunal", "ente_hub",
            "valor_face_tribunal", "valor_face_hub", "apresentado_em_original", "prazo_hub",
        ],
        [
            [
                p.numero_processo, p.numero_cnj, p.ente_devedor or "", _num(p.valor_face),
                _data(p.data_apresentacao), _data(p.prazo_pagamento),
                {True: "sim", False: "nao", None: ""}[p.vencido(referencia)],
                _num(totais.get(p.numero_processo, Totais(ZERO, ZERO)).confirmado),
                _num(totais.get(p.numero_processo, Totais(ZERO, ZERO)).em_duvida),
                p.status, _motivos(p.motivos), ";".join(p.fontes),
                p.ente_tribunal or "", p.ente_hub or "", _num(p.face_tribunal), _num(p.face_hub),
                p.apresentado_em_original or p.apresentado_em_hub or "", p.prazo_hub or "",
            ]
            for p in precatorios.values()
        ],
    )

    aproveitados = [ev for ev in eventos if ev.status != DESCARTADO]
    _escrever_csv(
        pasta / "pagamentos.csv",
        [
            "evento_id", "numero_processo", "numero_cnj", "tipo", "valor", "efeito_no_total",
            "data_pagamento", "atualizado_em", "status", "motivos", "linha_origem",
        ],
        [
            [
                ev.evento_id or "", ev.processo or "",
                precatorios[ev.processo].numero_cnj if ev.processo in precatorios else "",
                ev.tipo or "", _num(ev.valor), _num(ev.valor_com_sinal), _data(ev.data_pagamento),
                ev.atualizado_em.isoformat() if ev.atualizado_em else "", ev.status,
                _motivos(ev.motivos), "" if ev.linha is None else str(ev.linha),
            ]
            for ev in aproveitados
        ],
    )

    descartados = [ev for ev in eventos if ev.status == DESCARTADO]
    _escrever_csv(
        pasta / "quarentena.csv",
        ["fonte", "linha_origem", "evento_id", "motivo_codigo", "motivo", "registro_original"],
        [
            [
                fontes["pagamentos"].nome, "" if ev.linha is None else str(ev.linha),
                ev.evento_id or "",
                ",".join(m.codigo for m in ev.motivos if m.categoria == "descarte"),
                _motivos([m for m in ev.motivos if m.categoria == "descarte"]),
                json.dumps(ev.bruto, ensure_ascii=False, sort_keys=True),
            ]
            for ev in descartados
        ]
        + [
            [r.fonte, "" if r.linha is None else str(r.linha), "", r.codigo, r.texto,
             json.dumps(r.dados, ensure_ascii=False, sort_keys=True)]
            for r in rejeicoes
        ],
    )

    (pasta / "relatorio.md").write_text(
        _relatorio(fontes, eventos, precatorios, rejeicoes, totais, referencia),
        encoding="utf-8",
        newline="\n",
    )
    return totais


def _relatorio(
    fontes: dict[str, Fonte],
    eventos: list[Evento],
    precatorios: dict[str, Precatorio],
    rejeicoes: list[Rejeicao],
    totais: dict[str, Totais],
    referencia: date,
) -> str:
    linhas: list[str] = []
    add = linhas.append

    def contar(status: str) -> int:
        return sum(1 for ev in eventos if ev.status == status)

    add("# Relatório da limpeza")
    add("")
    add(f"Data de referência para prazo vencido: **{referencia.isoformat()}**.")
    add("")
    add("Gerado por `python -m limpeza`. Os arquivos de entrada foram lidos sem alteração; o hash")
    add("SHA-256 de cada um está abaixo, para conferir que são os originais.")
    add("")
    add("| Arquivo | Registros | SHA-256 |")
    add("|---|---|---|")
    for f in fontes.values():
        add(f"| `{f.nome}` | {len(f.registros)} | `{f.sha256}` |")
    add("")

    add("## Resumo")
    add("")
    add("| Eventos de pagamento | Quantidade |")
    add("|---|---|")
    add(f"| Lidos | {len(eventos)} |")
    add(f"| Válidos, sem alteração | {contar(VALIDO)} |")
    add(f"| Corrigidos | {contar(CORRIGIDO)} |")
    add(f"| Em dúvida (fora do total confirmado) | {contar(EM_DUVIDA)} |")
    add(f"| Descartados (em `quarentena.csv`) | {contar(DESCARTADO)} |")
    add("")
    add("| Precatórios | Quantidade |")
    add("|---|---|")
    add(f"| No total, unindo as fontes | {len(precatorios)} |")
    for status, rotulo in ((VALIDO, "Válidos"), (CORRIGIDO, "Corrigidos"), (EM_DUVIDA, "Em dúvida")):
        add(f"| {rotulo} | {sum(1 for p in precatorios.values() if p.status == status)} |")
    add("")

    avisos = [a for f in fontes.values() for a in f.avisos]
    datas = sorted(ev.data_pagamento for ev in eventos if ev.data_pagamento)
    if datas:
        avisos.append(
            f"pagamentos.json: datas de pagamento de {datas[0].isoformat()} a {datas[-1].isoformat()}, "
            "não só os últimos 7 dias descritos no fluxo; como cada evento é deduplicado por "
            "evento_id, isso não infla o total"
        )
    add("## Avisos sobre os arquivos")
    add("")
    add("Desvios do leiaute que atingem o arquivo inteiro, não um registro.")
    add("")
    for a in avisos:
        add(f"- {a}")
    add("")

    add("## Precatórios")
    add("")
    add("Total confirmado: soma dos eventos válidos e corrigidos. Ajustes em dúvida: eventos que")
    add("dependem de resposta do tribunal (estorno abate o valor; negativo entra com o sinal).")
    add("")
    add("| Processo | Ente | Valor de face | Prazo | Vencido | Total confirmado | Ajustes em dúvida | Status |")
    add("|---|---|---|---|---|---|---|---|")
    for p in precatorios.values():
        t = totais.get(p.numero_processo, Totais(ZERO, ZERO))
        vencido = {True: "sim", False: "não", None: "—"}[p.vencido(referencia)]
        add(
            f"| `{p.numero_cnj}` | {p.ente_devedor or '—'} | {_br(p.valor_face)} | "
            f"{_data(p.prazo_pagamento) or '—'} | {vencido} | {_br(t.confirmado)} | "
            f"{_br(t.em_duvida) if t.em_duvida else '—'} | {p.status} |"
        )
    soma_conf = sum((t.confirmado for t in totais.values()), ZERO)
    soma_duv = sum((t.em_duvida for t in totais.values()), ZERO)
    add("")
    add(f"Total pago confirmado: **{_br(soma_conf)}**. Com os ajustes em dúvida: **{_br(soma_conf + soma_duv)}**.")
    add("")

    def secao_eventos(titulo: str, status: str, explicacao: str, categoria: str | None = None) -> None:
        add(f"## {titulo}")
        add("")
        add(explicacao)
        add("")
        selecionados = [ev for ev in eventos if ev.status == status]
        if not selecionados:
            add("Nenhum.")
            add("")
            return
        add("| Evento | Linha | Processo | Valor | Por quê |")
        add("|---|---|---|---|---|")
        for ev in selecionados:
            motivos = [m for m in ev.motivos if categoria is None or m.categoria == categoria]
            processo = f"`{precatorios[ev.processo].numero_cnj}`" if ev.processo in precatorios else (
                f"`{ev.bruto.get('processo')!s}`" if ev.bruto.get("processo") else "—")
            # Versões substituídas e cópias não chegam a ser validadas: mostra o valor como veio.
            valor = _br(ev.valor) if ev.valor is not None else (
                "—" if ev.bruto.get("valor") is None else f"`{ev.bruto.get('valor')}` (como veio)")
            add(
                f"| `{ev.evento_id or '—'}` | {ev.linha or '—'} | {processo} | {valor} | "
                f"{'; '.join(m.texto for m in motivos)} |"
            )
        add("")

    secao_eventos(
        "Eventos corrigidos", CORRIGIDO,
        "Vieram fora do leiaute e foram convertidos com uma regra segura. Entram no total confirmado.",
        "correcao",
    )
    secao_eventos(
        "Eventos descartados", DESCARTADO,
        "Não podem ser aproveitados. Estão em `quarentena.csv`, com o registro original, para "
        "tratamento pela operação ou devolução ao tribunal. Não entram em nenhum total.",
        "descarte",
    )
    secao_eventos(
        "Eventos em dúvida", EM_DUVIDA,
        "Foram lidos, mas o efeito no total depende de resposta do tribunal. Estão em "
        "`pagamentos.csv` com status `em_duvida` e ficam fora do total confirmado.",
    )

    add("## Precatórios corrigidos ou em dúvida")
    add("")
    add("| Processo | Status | Por quê |")
    add("|---|---|---|")
    for p in precatorios.values():
        if p.motivos:
            add(f"| `{p.numero_cnj}` | {p.status} | {'; '.join(m.texto for m in p.motivos)} |")
    add("")

    if rejeicoes:
        add("## Linhas de precatório não aproveitadas")
        add("")
        for r in rejeicoes:
            add(f"- `{r.fonte}`, linha {r.linha}: {r.texto}")
        add("")

    return "\n".join(linhas)
