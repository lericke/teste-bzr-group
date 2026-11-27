"""Regras dos eventos de pagamento.

Ordem de aplicação:

1. ``evento_id`` e ``atualizado_em`` precisam existir: sem eles não dá para
   saber se um registro é versão de outro.
2. Deduplicação por ``evento_id``: cópias idênticas viram uma só; versões
   diferentes ficam com a de maior ``atualizado_em``. Duas versões
   diferentes com o mesmo ``atualizado_em`` ficam em dúvida.
3. Validação campo a campo da versão que ficou.

Cada evento termina com um status:

- ``valido``: segue o leiaute;
- ``corrigido``: veio fora do leiaute e foi convertido com segurança;
- ``em_duvida``: depende de resposta do tribunal; fica fora do total confirmado;
- ``descartado``: não pode ser aproveitado; vai para a quarentena, com o motivo.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

from . import regras
from .fontes import Registro
from .regras import RegraViolada

VALIDO = "valido"
CORRIGIDO = "corrigido"
EM_DUVIDA = "em_duvida"
DESCARTADO = "descartado"


@dataclass
class Motivo:
    categoria: str  # "correcao", "duvida" ou "descarte"
    codigo: str
    texto: str


@dataclass
class Evento:
    registro: Registro
    evento_id: str | None = None
    processo: str | None = None
    valor: Decimal | None = None
    data_pagamento: date | None = None
    tipo: str | None = None
    atualizado_em: datetime | None = None
    motivos: list[Motivo] = field(default_factory=list)

    @property
    def linha(self) -> int | None:
        return self.registro.linha

    @property
    def bruto(self) -> dict[str, Any]:
        return self.registro.dados

    @property
    def status(self) -> str:
        categorias = {m.categoria for m in self.motivos}
        if "descarte" in categorias:
            return DESCARTADO
        if "duvida" in categorias:
            return EM_DUVIDA
        if "correcao" in categorias:
            return CORRIGIDO
        return VALIDO

    @property
    def valor_com_sinal(self) -> Decimal | None:
        """Efeito no total pago: estorno abate, pagamento soma (com o sinal que veio)."""
        if self.valor is None:
            return None
        return -self.valor if self.tipo == "estorno" else self.valor

    def anotar(self, categoria: str, codigo: str, texto: str) -> None:
        self.motivos.append(Motivo(categoria, codigo, texto))


def _onde(linha: int | None) -> str:
    return f"linha {linha}" if linha is not None else "posição desconhecida"


def _mesmo_conteudo(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def _identificar(evento: Evento) -> None:
    """Passo 1: evento_id e atualizado_em."""
    bruto = evento.bruto
    evento_id = bruto.get("evento_id")
    if not isinstance(evento_id, str) or not evento_id.strip():
        evento.anotar("descarte", "evento_id_vazio", "evento sem evento_id")
    else:
        evento.evento_id = evento_id.strip()
    try:
        evento.atualizado_em = regras.converter_atualizado_em(bruto.get("atualizado_em"))
    except RegraViolada as erro:
        evento.anotar("descarte", erro.codigo, erro.texto)


def _deduplicar(eventos: list[Evento]) -> list[Evento]:
    """Passo 2. Marca os descartados e devolve os que seguem para validação."""
    grupos: OrderedDict[str, list[Evento]] = OrderedDict()
    for ev in eventos:
        if ev.status != DESCARTADO:
            grupos.setdefault(ev.evento_id, []).append(ev)  # type: ignore[arg-type]

    seguem: list[Evento] = []
    for evento_id, grupo in grupos.items():
        # Cópias idênticas: fica a primeira ocorrência.
        distintos: list[Evento] = []
        for ev in grupo:
            original = next((d for d in distintos if _mesmo_conteudo(d.bruto, ev.bruto)), None)
            if original is None:
                distintos.append(ev)
            else:
                ev.anotar(
                    "descarte",
                    "duplicata_identica",
                    f"cópia idêntica do {evento_id} da {_onde(original.linha)}; contado uma vez",
                )

        if len(distintos) == 1:
            seguem.append(distintos[0])
            continue

        mais_recente = max(ev.atualizado_em for ev in distintos)  # type: ignore[type-var]
        vencedores = [ev for ev in distintos if ev.atualizado_em == mais_recente]
        if len(vencedores) > 1:
            linhas = ", ".join(_onde(ev.linha) for ev in vencedores)
            for ev in vencedores:
                ev.anotar(
                    "duvida",
                    "versoes_conflitantes",
                    f"{evento_id} tem versões diferentes com o mesmo atualizado_em ({linhas})",
                )
        vencedor = vencedores[0]
        for ev in distintos:
            if ev.atualizado_em != mais_recente:
                ev.anotar(
                    "descarte",
                    "versao_substituida",
                    f"versão antiga do {evento_id}; substituída pela da {_onde(vencedor.linha)} "
                    f"(atualizado_em mais recente)",
                )
        if len(vencedores) == 1:
            vencedor.anotar(
                "correcao",
                "versao_mais_recente",
                f"{evento_id} aparece {len(distintos)} vezes com conteúdo diferente; "
                f"ficou a versão de atualizado_em mais recente",
            )
        seguem.extend(vencedores)
    return seguem


def _validar(evento: Evento, processos_conhecidos: set[str]) -> None:
    """Passo 3: campo a campo, acumulando todos os motivos."""
    bruto = evento.bruto

    try:
        conv = regras.normalizar_processo(bruto.get("processo"))
        evento.processo = conv.valor
        if conv.corrigido:
            evento.anotar("correcao", "processo_sem_mascara", conv.nota)
        if conv.valor not in processos_conhecidos:
            evento.anotar(
                "descarte",
                "precatorio_inexistente",
                f"processo {regras.formatar_cnj(conv.valor)} não está no tribunal nem no hub",
            )
    except RegraViolada as erro:
        evento.anotar("descarte", erro.codigo, erro.texto)

    try:
        conv_valor = regras.converter_valor(bruto.get("valor"))
        evento.valor = conv_valor.valor
        if conv_valor.corrigido:
            evento.anotar("correcao", "valor_em_texto", conv_valor.nota)
        if conv_valor.valor < 0:
            evento.anotar(
                "duvida",
                "valor_negativo",
                f"valor negativo ({conv_valor.valor}) com tipo pagamento: estorno, erro de sinal "
                "ou outro lançamento?",
            )
        elif conv_valor.valor == 0:
            evento.anotar("duvida", "valor_zero", "pagamento de valor zero")
    except RegraViolada as erro:
        evento.anotar("descarte", erro.codigo, erro.texto)

    referencia = evento.atualizado_em.date() if evento.atualizado_em else None
    try:
        conv_data = regras.converter_data_pagamento(bruto.get("data_pagamento"), referencia)
        evento.data_pagamento = conv_data.valor
        if conv_data.duvida:
            evento.anotar("duvida", "data_ambigua", conv_data.nota)
        elif conv_data.corrigido:
            evento.anotar("correcao", "data_fora_do_padrao", conv_data.nota)
    except RegraViolada as erro:
        evento.anotar("descarte", erro.codigo, erro.texto)

    tipo = bruto.get("tipo")
    evento.tipo = tipo if isinstance(tipo, str) else None
    if tipo == "pagamento":
        pass
    elif tipo == "estorno":
        evento.anotar(
            "duvida",
            "tipo_estorno",
            "tipo estorno não está na documentação; não se sabe se abate um pagamento",
        )
    else:
        evento.anotar("descarte", "tipo_desconhecido", f"tipo desconhecido: {tipo!r}")


def processar(registros: Iterable[Registro], processos_conhecidos: set[str]) -> list[Evento]:
    """Aplica as regras e devolve todos os eventos, na ordem do arquivo."""
    eventos = [Evento(registro=r) for r in registros]
    for ev in eventos:
        _identificar(ev)
    for ev in _deduplicar(eventos):
        _validar(ev, processos_conhecidos)
    return eventos
