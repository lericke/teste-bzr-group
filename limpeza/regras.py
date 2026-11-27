"""Regras de normalização e de cálculo, sem leitura de arquivo.

Cada função recebe um valor como veio da fonte e devolve uma ``Conversao``
(o valor normalizado e se foi preciso corrigir ou se ficou em dúvida),
ou levanta ``RegraViolada`` com um código de motivo. As funções ficam
isoladas aqui para serem testadas uma a uma.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from decimal import Decimal, InvalidOperation
from typing import Any, Generic, TypeVar

T = TypeVar("T")


def _fuso_brasilia() -> tzinfo:
    """America/Sao_Paulo, ou UTC-3 fixo se a base de fusos não estiver instalada.

    O Windows não traz a base IANA; sem o pacote ``tzdata`` o ``zoneinfo``
    falha. Brasília não tem horário de verão desde 2019, então o UTC-3 fixo
    é exato para as datas do case (2023 a 2025). Para datas anteriores a 2019,
    instalar ``tzdata``.
    """
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("America/Sao_Paulo")
    except Exception:  # ZoneInfoNotFoundError ou módulo ausente
        return timezone(timedelta(hours=-3), "UTC-03:00")


BRASILIA = _fuso_brasilia()


class RegraViolada(ValueError):
    """O valor não pode ser aproveitado. ``codigo`` identifica o motivo."""

    def __init__(self, codigo: str, texto: str) -> None:
        super().__init__(texto)
        self.codigo = codigo
        self.texto = texto


@dataclass(frozen=True)
class Conversao(Generic[T]):
    """Resultado de uma conversão.

    ``corrigido``: o valor veio fora do leiaute e foi convertido com segurança.
    ``duvida``: o valor foi convertido, mas a interpretação precisa ser confirmada.
    ``nota``: explicação para o relatório (vazia quando nada foi feito).
    """

    valor: T
    corrigido: bool = False
    duvida: bool = False
    nota: str = ""


# --- Número do processo ------------------------------------------------------

_CNJ_COM_MASCARA = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
_CNJ_SO_DIGITOS = re.compile(r"\d{20}")


def normalizar_processo(bruto: Any) -> Conversao[str]:
    """Reduz o número CNJ aos 20 dígitos.

    Aceita o formato da documentação (``NNNNNNN-DD.AAAA.J.TR.OOOO``) e os
    20 dígitos sem máscara (marcado como corrigido). Qualquer outra coisa
    é recusada: não dá para adivinhar dígitos que faltam.
    """
    if bruto is None or (isinstance(bruto, str) and not bruto.strip()):
        raise RegraViolada("processo_vazio", "número do processo vazio")
    if not isinstance(bruto, str):
        raise RegraViolada("processo_invalido", f"número do processo não é texto: {bruto!r}")

    texto = bruto.strip()
    if _CNJ_COM_MASCARA.fullmatch(texto):
        return Conversao(re.sub(r"\D", "", texto))
    if _CNJ_SO_DIGITOS.fullmatch(texto):
        return Conversao(
            texto,
            corrigido=True,
            nota=f"processo sem máscara CNJ ({texto}); normalizado pelos dígitos",
        )
    raise RegraViolada("processo_invalido", f"número do processo fora do formato CNJ: {texto!r}")


def formatar_cnj(digitos: str) -> str:
    """20 dígitos para ``NNNNNNN-DD.AAAA.J.TR.OOOO``."""
    d = digitos
    return f"{d[0:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:20]}"


# --- Valores em reais --------------------------------------------------------

# "2.500,50", "2500,50", "-200,00": formato brasileiro, vírgula decimal.
_VALOR_BR = re.compile(r"-?(\d{1,3}(\.\d{3})+|\d+),\d{1,2}")
# "2500.50", "2500": número escrito como texto, ponto decimal.
_VALOR_TEXTO_PONTO = re.compile(r"-?\d+(\.\d{1,2})?")


def converter_valor(bruto: Any) -> Conversao[Decimal]:
    """Converte o valor para ``Decimal`` com duas casas.

    Número JSON: aceito como está. Texto: aceito no formato brasileiro
    (``"2.500,50"``) ou com ponto decimal, e marcado como corrigido.
    ``"2.500"`` é recusado: pode ser dois mil e quinhentos ou dois e meio.
    O sinal é preservado; quem decide o que fazer com negativo é quem chama.
    """
    if bruto is None:
        raise RegraViolada("valor_nulo", "valor nulo")
    if isinstance(bruto, bool):
        raise RegraViolada("valor_invalido", f"valor booleano: {bruto!r}")

    corrigido = False
    nota = ""
    if isinstance(bruto, (int, float)):
        texto = str(bruto)
    elif isinstance(bruto, str):
        texto = bruto.strip()
        if _VALOR_BR.fullmatch(texto):
            texto = texto.replace(".", "").replace(",", ".")
        elif not _VALOR_TEXTO_PONTO.fullmatch(texto):
            raise RegraViolada("valor_invalido", f"valor em formato não reconhecido: {bruto!r}")
        corrigido = True
        nota = f"valor veio como texto ({bruto!r}); convertido para {texto}"
    else:
        raise RegraViolada("valor_invalido", f"valor de tipo inesperado: {bruto!r}")

    try:
        valor = Decimal(texto)
    except InvalidOperation:
        raise RegraViolada("valor_invalido", f"valor não numérico: {bruto!r}") from None
    if not valor.is_finite():
        raise RegraViolada("valor_invalido", f"valor não finito: {bruto!r}")
    if valor != valor.quantize(Decimal("0.01")):
        raise RegraViolada("valor_invalido", f"valor com mais de duas casas decimais: {bruto!r}")
    return Conversao(valor.quantize(Decimal("0.01")), corrigido=corrigido, nota=nota)


# --- Datas -------------------------------------------------------------------

_DATA_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATA_BR = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def converter_data_pagamento(bruto: Any, referencia: date | None = None) -> Conversao[date]:
    """Converte ``data_pagamento`` para ``date``.

    ``AAAA-MM-DD`` é o leiaute. ``DD/MM/AAAA`` é lida como dia/mês. Se a
    leitura confere com ``referencia`` (a data do ``atualizado_em``), é
    corrigida; se não confere e a leitura mês/dia também seria possível,
    fica em dúvida.
    """
    if not isinstance(bruto, str) or not bruto.strip():
        raise RegraViolada("data_invalida", f"data de pagamento ausente: {bruto!r}")
    texto = bruto.strip()

    if _DATA_ISO.fullmatch(texto):
        try:
            return Conversao(date.fromisoformat(texto))
        except ValueError:
            raise RegraViolada("data_invalida", f"data inexistente: {texto!r}") from None

    m = _DATA_BR.fullmatch(texto)
    if not m:
        raise RegraViolada("data_invalida", f"data em formato não reconhecido: {texto!r}")
    dia, mes, ano = (int(g) for g in m.groups())
    try:
        lida = date(ano, mes, dia)
    except ValueError:
        raise RegraViolada("data_invalida", f"data inexistente: {texto!r}") from None

    if referencia is not None and lida == referencia:
        return Conversao(
            lida,
            corrigido=True,
            nota=f"data {texto!r} lida como DD/MM/AAAA ({lida.isoformat()}); confere com atualizado_em",
        )
    ambigua = dia <= 12 and dia != mes
    return Conversao(
        lida,
        corrigido=True,
        duvida=ambigua,
        nota=(
            f"data {texto!r} lida como DD/MM/AAAA ({lida.isoformat()})"
            + ("; também poderia ser MM/DD, confirmar" if ambigua else "")
        ),
    )


def ler_data_hora(texto: str) -> datetime:
    """``datetime.fromisoformat`` que aceita ``Z`` também no Python 3.10."""
    t = texto.strip()
    if t.endswith(("Z", "z")):
        t = t[:-1] + "+00:00"
    return datetime.fromisoformat(t)


def converter_atualizado_em(bruto: Any) -> datetime:
    """``atualizado_em`` precisa de data, hora e fuso para ordenar versões."""
    if not isinstance(bruto, str) or not bruto.strip():
        raise RegraViolada("atualizado_em_invalido", f"atualizado_em ausente: {bruto!r}")
    try:
        momento = ler_data_hora(bruto)
    except ValueError:
        raise RegraViolada("atualizado_em_invalido", f"atualizado_em inválido: {bruto!r}") from None
    if momento.tzinfo is None:
        raise RegraViolada("atualizado_em_invalido", f"atualizado_em sem fuso: {bruto!r}")
    return momento


def data_civil_brasilia(bruto: Any) -> Conversao[date]:
    """Data de apresentação como data civil no horário de Brasília.

    Só data: é a data local, como está. Data e hora com fuso: convertida para
    Brasília. Data e hora sem fuso: tratada como horário de Brasília. Se a
    conversão mudar o dia em relação ao que está escrito, a nota registra.
    """
    if not isinstance(bruto, str) or not bruto.strip():
        raise RegraViolada("data_invalida", f"data de apresentação ausente: {bruto!r}")
    texto = bruto.strip()

    if _DATA_ISO.fullmatch(texto):
        try:
            return Conversao(date.fromisoformat(texto))
        except ValueError:
            raise RegraViolada("data_invalida", f"data inexistente: {texto!r}") from None

    try:
        momento = ler_data_hora(texto)
    except ValueError:
        raise RegraViolada("data_invalida", f"data de apresentação inválida: {texto!r}") from None

    if momento.tzinfo is None:
        local = momento.date()
        return Conversao(local, nota=f"{texto!r} sem fuso; tratada como horário de Brasília")

    local = momento.astimezone(BRASILIA).date()
    escrita = momento.date()
    if local != escrita:
        return Conversao(
            local,
            corrigido=True,
            nota=(
                f"{texto!r} está em outro fuso; no horário de Brasília é "
                f"{local.isoformat()}, não {escrita.isoformat()}"
            ),
        )
    return Conversao(local)


# --- Prazo -------------------------------------------------------------------


def calcular_prazo(apresentacao: date) -> date:
    """Prazo constitucional de pagamento.

    Apresentado até 2 de abril (inclusive): 31 de dezembro do ano seguinte.
    Depois de 2 de abril: 31 de dezembro do ano subsequente ao seguinte.
    """
    limite = date(apresentacao.year, 4, 2)
    anos = 1 if apresentacao <= limite else 2
    return date(apresentacao.year + anos, 12, 31)


# --- Ente devedor ------------------------------------------------------------


def chave_ente(nome: str) -> str:
    """Chave de comparação: maiúsculas, sem acento, espaços simples.

    ``"Município de São Paulo"`` e ``"MUNICIPIO DE SAO PAULO"`` dão a mesma
    chave. Não resolve sinônimos ("Prefeitura de São Paulo"): isso exige
    um cadastro de entes, proposto na seção de Prevenção.
    """
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", nome) if not unicodedata.combining(c)
    )
    return " ".join(sem_acento.upper().split())
