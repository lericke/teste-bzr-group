"""Leitura dos arquivos de entrada, sempre em modo somente leitura.

Cada leitor recebe os bytes do arquivo como veio e devolve os registros com
a linha de origem, mais os avisos sobre desvios do leiaute documentado
(codificação, separador, quebra de linha). Nada aqui decide se um registro
é válido; isso fica em ``pagamentos`` e ``precatorios``.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ARQUIVOS = {
    "pagamentos": "pagamentos.json",
    "tribunal": "tribunal.csv",
    "hub": "hub.csv",
    "apresentacoes": "apresentacoes.json",
}


@dataclass
class Registro:
    """Um registro de uma fonte, com a linha onde ele começa no arquivo."""

    dados: dict[str, Any]
    linha: int | None
    posicao: int  # índice do registro no arquivo, a partir de 0


@dataclass
class Fonte:
    nome: str
    caminho: Path
    sha256: str
    registros: list[Registro] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def ler_bytes(caminho: Path) -> tuple[bytes, str]:
    """Lê o arquivo em modo binário, só leitura, e devolve o conteúdo e o SHA-256."""
    with open(caminho, "rb") as f:
        conteudo = f.read()
    return conteudo, hashlib.sha256(conteudo).hexdigest()


def _decodificar(conteudo: bytes, nome: str, avisos: list[str]) -> str:
    """UTF-8 é o leiaute. Se falhar, lê como Windows-1252 e avisa."""
    if conteudo.startswith(b"\xef\xbb\xbf"):
        avisos.append(f"{nome}: começa com BOM UTF-8; o BOM foi ignorado")
        conteudo = conteudo[3:]
    try:
        return conteudo.decode("utf-8")
    except UnicodeDecodeError:
        avisos.append(
            f"{nome}: não está em UTF-8, como diz a documentação; "
            "lido como Windows-1252 (ISO-8859-1), padrão do Excel em português"
        )
        return conteudo.decode("cp1252")


def _linhas_com_chave(texto: str, chave: str) -> list[int]:
    """Números de linha (a partir de 1) onde aparece ``"chave"`` num JSON."""
    alvo = f'"{chave}"'
    return [n for n, linha in enumerate(texto.splitlines(), start=1) if alvo in linha]


def _ler_json_lista(conteudo: bytes, nome: str, chave_linha: str, avisos: list[str]) -> list[Registro]:
    texto = _decodificar(conteudo, nome, avisos)
    dados = json.loads(texto)
    if not isinstance(dados, list):
        raise ValueError(f"{nome}: esperava uma lista JSON")
    linhas = _linhas_com_chave(texto, chave_linha)
    if len(linhas) != len(dados):
        avisos.append(f"{nome}: não foi possível mapear cada registro para a linha de origem")
        linhas = [None] * len(dados)
    registros = []
    for i, (item, linha) in enumerate(zip(dados, linhas)):
        if not isinstance(item, dict):
            item = {"_valor_bruto": item}
        registros.append(Registro(dados=item, linha=linha, posicao=i))
    return registros


def _ler_csv(conteudo: bytes, nome: str, separador_documentado: str | None, avisos: list[str]) -> list[Registro]:
    texto = _decodificar(conteudo, nome, avisos)
    if "\r\n" in texto:
        avisos.append(f"{nome}: quebras de linha CRLF (Windows)")
    cabecalho = texto.splitlines()[0] if texto else ""
    separador = ";" if cabecalho.count(";") > cabecalho.count(",") else ","
    if separador_documentado and separador != separador_documentado:
        avisos.append(
            f"{nome}: separador {separador!r}, mas a documentação diz {separador_documentado!r}"
        )
    leitor = csv.DictReader(io.StringIO(texto, newline=""), delimiter=separador)
    registros = []
    for i, linha in enumerate(leitor):
        # Cabeçalho na linha 1; o arquivo não tem campos com quebra de linha.
        registros.append(Registro(dados=dict(linha), linha=i + 2, posicao=i))
    return registros


def carregar(pasta: Path) -> dict[str, Fonte]:
    """Lê os quatro arquivos da pasta de entrada."""
    fontes: dict[str, Fonte] = {}
    for chave, arquivo in ARQUIVOS.items():
        caminho = pasta / arquivo
        conteudo, sha = ler_bytes(caminho)
        fonte = Fonte(nome=arquivo, caminho=caminho, sha256=sha)
        if chave == "pagamentos":
            fonte.registros = _ler_json_lista(conteudo, arquivo, "evento_id", fonte.avisos)
        elif chave == "apresentacoes":
            fonte.registros = _ler_json_lista(conteudo, arquivo, "processo", fonte.avisos)
        elif chave == "tribunal":
            # Leiaute documentado: UTF-8, vírgula como separador.
            fonte.registros = _ler_csv(conteudo, arquivo, ",", fonte.avisos)
        else:
            # hub.csv é exportação do próprio sistema; não há leiaute documentado.
            fonte.registros = _ler_csv(conteudo, arquivo, None, fonte.avisos)
        fontes[chave] = fonte
    return fontes
