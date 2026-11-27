"""Regras dos eventos: deduplicação, versões, quarentena e casos em dúvida."""

from decimal import Decimal

from limpeza.fontes import Registro
from limpeza.pagamentos import CORRIGIDO, DESCARTADO, EM_DUVIDA, VALIDO, processar
from limpeza.saida import totais_por_processo

PROC = "0012345-10.2019.8.26.0053"
DIGITOS = "00123451020198260053"


def evento(evento_id="ev-1", processo=PROC, valor=100.0, data="2025-03-10",
           tipo="pagamento", atualizado_em="2025-03-10T10:00:00-03:00"):
    return {
        "evento_id": evento_id, "processo": processo, "valor": valor,
        "data_pagamento": data, "tipo": tipo, "atualizado_em": atualizado_em,
    }


def rodar(*dados, conhecidos=(DIGITOS,)):
    registros = [Registro(dados=d, linha=i * 10 + 1, posicao=i) for i, d in enumerate(dados)]
    return processar(registros, set(conhecidos))


def test_evento_dentro_do_leiaute_e_valido():
    [ev] = rodar(evento())
    assert ev.status == VALIDO
    assert ev.valor == Decimal("100.00")


def test_versao_mais_recente_substitui_e_nao_soma():
    # ev-001: 15.000 e, no dia seguinte, 15.500. O total é 15.500, não 30.500.
    antiga = evento("ev-001", valor=15000.0, atualizado_em="2025-03-10T10:00:00-03:00")
    nova = evento("ev-001", valor=15500.0, atualizado_em="2025-03-11T09:00:00-03:00")
    eventos = rodar(antiga, nova)
    assert [ev.status for ev in eventos] == [DESCARTADO, CORRIGIDO]
    assert eventos[0].motivos[0].codigo == "versao_substituida"
    assert totais_por_processo(eventos)[DIGITOS].confirmado == Decimal("15500.00")


def test_versao_mais_recente_vence_mesmo_vindo_antes_no_arquivo():
    nova = evento("ev-001", valor=15500.0, atualizado_em="2025-03-11T09:00:00-03:00")
    antiga = evento("ev-001", valor=15000.0, atualizado_em="2025-03-10T10:00:00-03:00")
    eventos = rodar(nova, antiga)
    assert totais_por_processo(eventos)[DIGITOS].confirmado == Decimal("15500.00")


def test_atualizado_em_compara_o_instante_e_nao_o_texto():
    # Como texto, "12:00Z" parece mais tarde que "10:00-03:00". Como instante, 10h em
    # Brasília são 13h UTC: a versão de Brasília é a mais recente.
    utc = evento("ev-1", valor=1.0, atualizado_em="2025-03-10T12:00:00Z")
    brasilia = evento("ev-1", valor=2.0, atualizado_em="2025-03-10T10:00:00-03:00")
    eventos = rodar(utc, brasilia)
    assert totais_por_processo(eventos)[DIGITOS].confirmado == Decimal("2.00")


def test_copia_identica_conta_uma_vez():
    # ev-002 aparece duas vezes, igual.
    eventos = rodar(evento("ev-002", valor="2.500,50"), evento("ev-002", valor="2.500,50"))
    assert eventos[1].status == DESCARTADO
    assert eventos[1].motivos[0].codigo == "duplicata_identica"
    assert totais_por_processo(eventos)[DIGITOS].confirmado == Decimal("2500.50")


def test_versoes_diferentes_com_mesmo_atualizado_em_ficam_em_duvida():
    a = evento("ev-1", valor=100.0)
    b = evento("ev-1", valor=200.0)
    eventos = rodar(a, b)
    assert {ev.status for ev in eventos} == {EM_DUVIDA}
    assert totais_por_processo(eventos)[DIGITOS].confirmado == Decimal("0.00")


def test_estorno_fica_em_duvida_e_fora_do_total_confirmado():
    # ev-006 / ev-007.
    eventos = rodar(
        evento("ev-006", valor=5000),
        evento("ev-007", valor=5000, tipo="estorno", atualizado_em="2025-03-11T10:00:00-03:00"),
    )
    assert [ev.status for ev in eventos] == [VALIDO, EM_DUVIDA]
    totais = totais_por_processo(eventos)[DIGITOS]
    assert totais.confirmado == Decimal("5000.00")
    assert totais.em_duvida == Decimal("-5000.00")  # se confirmado, o estorno abate
    assert totais.com_duvidas == Decimal("0.00")


def test_valor_negativo_fica_em_duvida():
    # ev-009.
    [ev] = rodar(evento(valor=-200))
    assert ev.status == EM_DUVIDA
    assert ev.motivos[0].codigo == "valor_negativo"


def test_valor_nulo_vai_para_quarentena():
    # ev-004.
    [ev] = rodar(evento(valor=None))
    assert ev.status == DESCARTADO
    assert [m.codigo for m in ev.motivos] == ["valor_nulo"]


def test_processo_vazio_vai_para_quarentena():
    # ev-010.
    [ev] = rodar(evento(processo=""))
    assert ev.status == DESCARTADO
    assert ev.motivos[0].codigo == "processo_vazio"


def test_processo_que_nao_existe_em_nenhuma_fonte_vai_para_quarentena():
    [ev] = rodar(evento(processo="9999999-99.2020.8.26.0053"))
    assert ev.status == DESCARTADO
    assert ev.motivos[0].codigo == "precatorio_inexistente"


def test_processo_sem_mascara_e_somado_ao_mesmo_precatorio():
    # ev-005 entra no mesmo total do processo com máscara.
    eventos = rodar(evento("ev-a", valor=8000), evento("ev-b", processo=DIGITOS, valor=1200))
    assert eventos[1].status == CORRIGIDO
    assert totais_por_processo(eventos)[DIGITOS].confirmado == Decimal("9200.00")


def test_tipo_desconhecido_vai_para_quarentena():
    [ev] = rodar(evento(tipo="ajuste"))
    assert ev.status == DESCARTADO


def test_sem_evento_id_ou_sem_atualizado_em_vai_para_quarentena():
    eventos = rodar(evento(evento_id=""), evento(evento_id="ev-2", atualizado_em=None))
    assert [ev.status for ev in eventos] == [DESCARTADO, DESCARTADO]


def test_todos_os_motivos_sao_registrados_juntos():
    # Um evento com dois defeitos mostra os dois, não só o primeiro.
    [ev] = rodar(evento(processo="", valor=None))
    assert {m.codigo for m in ev.motivos} == {"processo_vazio", "valor_nulo"}
