"""Cruzamento dos precatórios entre tribunal.csv, hub.csv e apresentacoes.json.

A chave é sempre o número do processo reduzido aos 20 dígitos, nunca o texto
como veio. Nenhum precatório é descartado: o que diverge entre as fontes
fica em dúvida, com as duas versões lado a lado, para a operação decidir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from . import regras
from .fontes import Fonte
from .pagamentos import CORRIGIDO, EM_DUVIDA, VALIDO, Motivo
from .regras import RegraViolada


@dataclass
class Precatorio:
    numero_processo: str
    fontes: list[str] = field(default_factory=list)
    linhas: dict[str, int | None] = field(default_factory=dict)
    ente_tribunal: str | None = None
    ente_hub: str | None = None
    face_tribunal: Decimal | None = None
    face_hub: Decimal | None = None
    apresentado_em_original: str | None = None
    apresentado_em_hub: str | None = None
    data_apresentacao: date | None = None
    prazo_hub: str | None = None
    ente_devedor: str | None = None
    valor_face: Decimal | None = None
    prazo_pagamento: date | None = None
    motivos: list[Motivo] = field(default_factory=list)

    @property
    def numero_cnj(self) -> str:
        return regras.formatar_cnj(self.numero_processo)

    @property
    def status(self) -> str:
        categorias = {m.categoria for m in self.motivos}
        if "duvida" in categorias:
            return EM_DUVIDA
        if "correcao" in categorias:
            return CORRIGIDO
        return VALIDO

    def anotar(self, categoria: str, codigo: str, texto: str) -> None:
        self.motivos.append(Motivo(categoria, codigo, texto))

    def vencido(self, referencia: date) -> bool | None:
        return None if self.prazo_pagamento is None else self.prazo_pagamento < referencia


@dataclass
class Rejeicao:
    """Linha de uma fonte de precatórios que não pôde ser associada a um processo."""

    fonte: str
    linha: int | None
    codigo: str
    texto: str
    dados: dict


def _processo(dados: dict, campo: str, fonte: str, linha: int | None,
              rejeicoes: list[Rejeicao]) -> tuple[str | None, str]:
    try:
        conv = regras.normalizar_processo(dados.get(campo))
    except RegraViolada as erro:
        rejeicoes.append(Rejeicao(fonte, linha, erro.codigo, erro.texto, dados))
        return None, ""
    return conv.valor, conv.nota if conv.corrigido else ""


def _face(bruto: str | None, fonte: str, linha: int | None, avisos: list[str]) -> Decimal | None:
    try:
        conv = regras.converter_valor(bruto)
    except RegraViolada as erro:
        avisos.append(f"{fonte}, linha {linha}: valor_face não aproveitado ({erro.texto})")
        return None
    return conv.valor


def cruzar(tribunal: Fonte, hub: Fonte, apresentacoes: Fonte) -> tuple[dict[str, Precatorio], list[Rejeicao]]:
    precatorios: dict[str, Precatorio] = {}
    rejeicoes: list[Rejeicao] = []

    def obter(numero: str) -> Precatorio:
        return precatorios.setdefault(numero, Precatorio(numero_processo=numero))

    # tribunal.csv: valor de face com vírgula decimal é desvio do arquivo, não do registro.
    faces_com_virgula = 0
    for reg in tribunal.registros:
        numero, nota = _processo(reg.dados, "numero_processo", tribunal.nome, reg.linha, rejeicoes)
        if numero is None:
            continue
        p = obter(numero)
        p.fontes.append("tribunal")
        p.linhas["tribunal"] = reg.linha
        if nota:
            p.anotar("correcao", "processo_sem_mascara", f"{tribunal.nome}, linha {reg.linha}: {nota}")
        p.ente_tribunal = (reg.dados.get("ente_devedor") or "").strip() or None
        bruto_face = reg.dados.get("valor_face")
        if isinstance(bruto_face, str) and "," in bruto_face:
            faces_com_virgula += 1
        p.face_tribunal = _face(bruto_face, tribunal.nome, reg.linha, tribunal.avisos)
    if faces_com_virgula:
        tribunal.avisos.append(
            f"{tribunal.nome}: {faces_com_virgula} valores de face com vírgula decimal e ponto de "
            "milhar (ex.: 45.000,00), mas a documentação pede ponto decimal; convertidos"
        )

    for reg in hub.registros:
        numero, nota = _processo(reg.dados, "processo", hub.nome, reg.linha, rejeicoes)
        if numero is None:
            continue
        p = obter(numero)
        p.fontes.append("hub")
        p.linhas["hub"] = reg.linha
        if nota:
            p.anotar("correcao", "processo_sem_mascara", f"{hub.nome}, linha {reg.linha}: {nota}")
        p.ente_hub = (reg.dados.get("ente") or "").strip() or None
        p.face_hub = _face(reg.dados.get("valor_face"), hub.nome, reg.linha, hub.avisos)
        p.apresentado_em_hub = (reg.dados.get("apresentado_em") or "").strip() or None
        p.prazo_hub = (reg.dados.get("prazo_pagamento") or "").strip() or None

    for reg in apresentacoes.registros:
        numero, nota = _processo(reg.dados, "processo", apresentacoes.nome, reg.linha, rejeicoes)
        if numero is None:
            continue
        p = obter(numero)
        p.fontes.append("apresentacoes")
        p.linhas["apresentacoes"] = reg.linha
        bruto = reg.dados.get("apresentado_em")
        p.apresentado_em_original = bruto if isinstance(bruto, str) else None

    for p in precatorios.values():
        _resolver(p)
    return dict(sorted(precatorios.items())), rejeicoes


def _resolver(p: Precatorio) -> None:
    no_tribunal = "tribunal" in p.fontes
    no_hub = "hub" in p.fontes

    # Presença nas fontes.
    if no_tribunal and not no_hub:
        p.anotar("duvida", "so_no_tribunal", "está na lista do tribunal, mas não no hub")
    if no_hub and not no_tribunal:
        p.anotar("duvida", "so_no_hub", "está no hub, mas não na lista do tribunal")

    # Ente devedor: compara pela chave sem acento e sem caixa.
    entes = [e for e in (p.ente_tribunal, p.ente_hub) if e]
    if len(entes) == 2:
        if regras.chave_ente(entes[0]) == regras.chave_ente(entes[1]):
            p.ente_devedor = p.ente_tribunal
            if entes[0] != entes[1]:
                p.anotar(
                    "correcao",
                    "ente_grafia",
                    f"ente escrito de outra forma no hub ({p.ente_hub!r}); mesmo ente, "
                    f"mantida a grafia do tribunal",
                )
        else:
            p.anotar(
                "duvida",
                "ente_divergente",
                f"ente diferente: tribunal {p.ente_tribunal!r}, hub {p.ente_hub!r}",
            )
    elif entes:
        p.ente_devedor = entes[0]

    # Valor de face.
    faces = [f for f in (p.face_tribunal, p.face_hub) if f is not None]
    if len(faces) == 2 and faces[0] != faces[1]:
        p.anotar(
            "duvida",
            "valor_face_divergente",
            f"valor de face diferente: tribunal {p.face_tribunal}, hub {p.face_hub}",
        )
    elif faces:
        p.valor_face = faces[0]

    # Data de apresentação e prazo.
    original = p.apresentado_em_original or p.apresentado_em_hub
    if original is None:
        p.anotar("duvida", "sem_apresentacao", "sem data de apresentação; prazo não calculado")
        return
    if (p.apresentado_em_original and p.apresentado_em_hub
            and p.apresentado_em_original != p.apresentado_em_hub):
        p.anotar(
            "duvida",
            "apresentacao_divergente",
            f"data de apresentação diferente: apresentacoes.json {p.apresentado_em_original!r}, "
            f"hub {p.apresentado_em_hub!r}",
        )
    try:
        conv = regras.data_civil_brasilia(original)
    except RegraViolada as erro:
        p.anotar("duvida", erro.codigo, erro.texto)
        return
    p.data_apresentacao = conv.valor
    p.prazo_pagamento = regras.calcular_prazo(conv.valor)

    if conv.corrigido:
        # O fuso mudou o dia. Se o prazo também muda, a resposta depende do fuso adotado.
        dia_escrito = date.fromisoformat(original.strip()[:10])
        prazo_dia_escrito = regras.calcular_prazo(dia_escrito)
        if prazo_dia_escrito != p.prazo_pagamento:
            p.anotar(
                "duvida",
                "prazo_depende_do_fuso",
                f"{conv.nota}; pelo horário de Brasília o prazo é {p.prazo_pagamento.isoformat()}, "
                f"pela data escrita seria {prazo_dia_escrito.isoformat()}",
            )
        else:
            p.anotar("correcao", "apresentacao_outro_fuso", conv.nota)

    if p.prazo_hub and p.prazo_hub != p.prazo_pagamento.isoformat():
        p.anotar(
            "correcao",
            "prazo_recalculado",
            f"prazo do hub {p.prazo_hub} recalculado para {p.prazo_pagamento.isoformat()} "
            f"(apresentado em {p.data_apresentacao.isoformat()}, regra de 2 de abril)",
        )
