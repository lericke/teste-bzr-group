"""Regras puras: prazo, fuso, conversão de valor e data, normalização do processo e do ente."""

from datetime import date
from decimal import Decimal

import pytest

from limpeza import regras
from limpeza.regras import RegraViolada


# --- Prazo: a regra que define a priorização da carteira ---------------------

@pytest.mark.parametrize(
    "apresentacao, prazo",
    [
        (date(2025, 4, 2), date(2026, 12, 31)),   # 2 de abril é "até 2 de abril" (0012345)
        (date(2025, 4, 3), date(2027, 12, 31)),   # um dia depois muda o ano
        (date(2025, 1, 1), date(2026, 12, 31)),
        (date(2024, 2, 29), date(2025, 12, 31)),  # ano bissexto (0034567)
        (date(2023, 12, 31), date(2025, 12, 31)),  # fim de ano, depois de 2 de abril (0067890)
    ],
)
def test_prazo_respeita_o_limite_de_2_de_abril(apresentacao, prazo):
    assert regras.calcular_prazo(apresentacao) == prazo


# --- Fuso da data de apresentação --------------------------------------------

def test_apresentacao_em_utc_vira_data_de_brasilia():
    # 0056789: 01h UTC de 3 de abril são 22h de 2 de abril em Brasília.
    conv = regras.data_civil_brasilia("2025-04-03T01:00:00Z")
    assert conv.valor == date(2025, 4, 2)
    assert conv.corrigido
    assert regras.calcular_prazo(conv.valor) == date(2026, 12, 31)


def test_apresentacao_com_fuso_de_brasilia_mantem_o_dia():
    # 0045678: 23h30 de 2 de abril em Brasília seria 3 de abril em UTC; continua 2 de abril.
    conv = regras.data_civil_brasilia("2025-04-02T23:30:00-03:00")
    assert conv.valor == date(2025, 4, 2)
    assert not conv.corrigido


def test_apresentacao_so_data_e_data_local():
    assert regras.data_civil_brasilia("2025-04-02").valor == date(2025, 4, 2)


def test_apresentacao_invalida_e_recusada():
    with pytest.raises(RegraViolada) as erro:
        regras.data_civil_brasilia("02/04/2025 10h")
    assert erro.value.codigo == "data_invalida"


# --- Valor -------------------------------------------------------------------

@pytest.mark.parametrize(
    "bruto, esperado, corrigido",
    [
        (15000.0, Decimal("15000.00"), False),
        (8000, Decimal("8000.00"), False),
        (-200, Decimal("-200.00"), False),       # o sinal é preservado; quem decide é a regra do evento
        ("2.500,50", Decimal("2500.50"), True),  # ev-002
        ("45.000,00", Decimal("45000.00"), True),  # tribunal.csv
        ("1.234.567,89", Decimal("1234567.89"), True),
        ("2500,5", Decimal("2500.50"), True),
        ("45000.00", Decimal("45000.00"), True),  # hub.csv: número como texto
    ],
)
def test_converte_valor(bruto, esperado, corrigido):
    conv = regras.converter_valor(bruto)
    assert conv.valor == esperado
    assert conv.corrigido is corrigido


@pytest.mark.parametrize(
    "bruto, codigo",
    [
        (None, "valor_nulo"),          # ev-004
        (True, "valor_invalido"),
        ("2.500", "valor_invalido"),   # dois mil e quinhentos ou dois e meio? não adivinha
        ("R$ 10,00", "valor_invalido"),
        ("", "valor_invalido"),
        (10.005, "valor_invalido"),    # mais de duas casas
        (float("nan"), "valor_invalido"),
    ],
)
def test_recusa_valor_que_nao_da_para_interpretar(bruto, codigo):
    with pytest.raises(RegraViolada) as erro:
        regras.converter_valor(bruto)
    assert erro.value.codigo == codigo


def test_valor_nao_passa_por_float():
    # 0.1 + 0.2 em float não é 0.3; em Decimal a soma de centavos é exata.
    soma = regras.converter_valor("0,10").valor + regras.converter_valor("0,20").valor
    assert soma == Decimal("0.30")


# --- Data de pagamento -------------------------------------------------------

def test_data_iso_nao_e_alterada():
    conv = regras.converter_data_pagamento("2025-03-10")
    assert conv.valor == date(2025, 3, 10)
    assert not conv.corrigido and not conv.duvida


def test_data_brasileira_que_confere_com_atualizado_em_e_corrigida():
    # ev-002: 10/04/2025, atualizado_em 2025-04-10.
    conv = regras.converter_data_pagamento("10/04/2025", referencia=date(2025, 4, 10))
    assert conv.valor == date(2025, 4, 10)
    assert conv.corrigido and not conv.duvida


def test_data_brasileira_ambigua_sem_confirmacao_fica_em_duvida():
    conv = regras.converter_data_pagamento("10/04/2025", referencia=date(2025, 5, 1))
    assert conv.duvida


def test_data_brasileira_sem_ambiguidade_e_corrigida():
    # 25/04 não pode ser mês 25.
    conv = regras.converter_data_pagamento("25/04/2025")
    assert conv.valor == date(2025, 4, 25)
    assert conv.corrigido and not conv.duvida


@pytest.mark.parametrize("bruto", ["2025-02-30", "31/02/2025", "ontem", "", None])
def test_data_invalida_e_recusada(bruto):
    with pytest.raises(RegraViolada):
        regras.converter_data_pagamento(bruto)


def test_atualizado_em_aceita_z_e_exige_fuso():
    assert regras.converter_atualizado_em("2025-04-03T01:00:00Z").utcoffset().total_seconds() == 0
    with pytest.raises(RegraViolada):
        regras.converter_atualizado_em("2025-04-03T01:00:00")


# --- Número do processo ------------------------------------------------------

def test_processo_com_e_sem_mascara_dao_a_mesma_chave():
    # ev-003 e ev-005: o mesmo precatório escrito de dois jeitos.
    com = regras.normalizar_processo("0023456-21.2020.8.26.0053")
    sem = regras.normalizar_processo("00234562120208260053")
    assert com.valor == sem.valor == "00234562120208260053"
    assert not com.corrigido
    assert sem.corrigido


def test_formata_cnj_de_volta():
    assert regras.formatar_cnj("00234562120208260053") == "0023456-21.2020.8.26.0053"


@pytest.mark.parametrize(
    "bruto, codigo",
    [
        ("", "processo_vazio"),  # ev-010
        ("   ", "processo_vazio"),
        (None, "processo_vazio"),
        ("0023456-21.2020.8.26.005", "processo_invalido"),  # falta um dígito
        ("0023456212020826005", "processo_invalido"),
        ("0023456-21.2020.8.26.0053 ", None),  # espaço nas pontas é tolerado
    ],
)
def test_processo_fora_do_formato(bruto, codigo):
    if codigo is None:
        assert regras.normalizar_processo(bruto).valor == "00234562120208260053"
        return
    with pytest.raises(RegraViolada) as erro:
        regras.normalizar_processo(bruto)
    assert erro.value.codigo == codigo


# --- Ente devedor ------------------------------------------------------------

def test_ente_compara_sem_acento_e_sem_caixa():
    assert regras.chave_ente("Município de São Paulo") == regras.chave_ente("MUNICIPIO DE SAO PAULO")
    assert regras.chave_ente("União") != regras.chave_ente("Município de Santos")
