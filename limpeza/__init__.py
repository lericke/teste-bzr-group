"""Limpeza dos arquivos do case: lê os originais sem alterá-los e gera uma base confiável."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import fontes as _fontes
from . import pagamentos as _pagamentos
from . import precatorios as _precatorios
from . import saida as _saida


@dataclass
class Resultado:
    fontes: dict[str, _fontes.Fonte]
    eventos: list[_pagamentos.Evento]
    precatorios: dict[str, _precatorios.Precatorio]
    rejeicoes: list[_precatorios.Rejeicao]
    totais: dict[str, _saida.Totais]


def executar(entrada: Path, saida: Path, referencia: date) -> Resultado:
    """Lê a pasta de entrada, aplica as regras e escreve a base limpa e o relatório."""
    entrada = entrada.resolve()
    saida = saida.resolve()
    if saida == entrada or entrada in saida.parents:
        raise ValueError("a pasta de saída não pode ficar dentro da pasta de entrada")

    fontes = _fontes.carregar(entrada)
    precatorios, rejeicoes = _precatorios.cruzar(
        fontes["tribunal"], fontes["hub"], fontes["apresentacoes"]
    )
    conhecidos = {
        numero for numero, p in precatorios.items() if {"tribunal", "hub"} & set(p.fontes)
    }
    eventos = _pagamentos.processar(fontes["pagamentos"].registros, conhecidos)
    totais = _saida.escrever(saida, fontes, eventos, precatorios, rejeicoes, referencia)
    return Resultado(fontes, eventos, precatorios, rejeicoes, totais)
