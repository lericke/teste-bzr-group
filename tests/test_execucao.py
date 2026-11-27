"""O programa inteiro sobre os arquivos reais do case.

Garante três coisas que nenhuma regra isolada garante: os originais não
mudam, rodar de novo dá o mesmo resultado e os números finais são os que
o diagnóstico prevê.
"""

import hashlib
import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from limpeza import executar
from limpeza.__main__ import main
from limpeza.pagamentos import CORRIGIDO, DESCARTADO, EM_DUVIDA, VALIDO

DADOS = Path(__file__).resolve().parent.parent / "case-candidato" / "dados"
REFERENCIA = date(2026, 11, 26)


def _hashes(pasta: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(pasta.iterdir())}


@pytest.fixture
def entrada(tmp_path):
    """Cópia dos dados reais, para que nenhum teste toque nos originais."""
    destino = tmp_path / "dados"
    shutil.copytree(DADOS, destino)
    return destino


@pytest.fixture
def resultado(entrada, tmp_path):
    return executar(entrada, tmp_path / "saida", REFERENCIA)


def test_arquivos_de_entrada_nao_sao_alterados(entrada, tmp_path):
    antes = _hashes(entrada)
    executar(entrada, tmp_path / "saida", REFERENCIA)
    assert _hashes(entrada) == antes


def test_rodar_duas_vezes_gera_exatamente_a_mesma_saida(entrada, tmp_path):
    # Reprocessar não pode inflar nada: é o problema 1 do diagnóstico.
    executar(entrada, tmp_path / "a", REFERENCIA)
    executar(entrada, tmp_path / "b", REFERENCIA)
    executar(entrada, tmp_path / "b", REFERENCIA)  # por cima da saída anterior
    assert _hashes(tmp_path / "a") == _hashes(tmp_path / "b")


def test_saida_dentro_da_entrada_e_recusada(entrada):
    with pytest.raises(ValueError):
        executar(entrada, entrada / "saida", REFERENCIA)


def test_status_de_cada_evento(resultado):
    status = [(ev.evento_id, ev.linha, ev.status) for ev in resultado.eventos]
    assert status == [
        ("ev-001", 3, DESCARTADO),   # versão antiga
        ("ev-002", 11, CORRIGIDO),   # valor em texto e data DD/MM
        ("ev-003", 19, VALIDO),
        ("ev-002", 27, DESCARTADO),  # cópia idêntica
        ("ev-004", 35, DESCARTADO),  # valor nulo
        ("ev-005", 43, CORRIGIDO),   # sem máscara
        ("ev-006", 51, VALIDO),
        ("ev-007", 59, EM_DUVIDA),   # estorno
        ("ev-001", 67, CORRIGIDO),   # versão mais recente
        ("ev-008", 75, VALIDO),
        ("ev-009", 83, EM_DUVIDA),   # negativo
        ("ev-010", 91, DESCARTADO),  # processo vazio
        ("ev-011", 99, VALIDO),
    ]


def test_totais_por_precatorio(resultado):
    totais = {k: (t.confirmado, t.em_duvida) for k, t in resultado.totais.items()}
    assert totais == {
        "00123451020198260053": (Decimal("18000.50"), Decimal("0.00")),  # 15.500 + 2.500,50
        "00234562120208260053": (Decimal("9200.00"), Decimal("0.00")),   # 8.000 + 1.200
        "00345673220188260405": (Decimal("5000.00"), Decimal("-5000.00")),
        "00456784320215020011": (Decimal("3000.00"), Decimal("0.00")),
        "00567895420174036100": (Decimal("0.00"), Decimal("-200.00")),
        "00678906520168260053": (Decimal("4000.00"), Decimal("0.00")),
    }


def test_precatorios_cruzados(resultado):
    p = resultado.precatorios
    assert len(p) == 6

    # Prazo do hub errado: recalculado.
    assert p["00123451020198260053"].prazo_pagamento == date(2026, 12, 31)
    assert p["00123451020198260053"].ente_devedor == "Município de São Paulo"

    # Fuso: a resposta depende de qual fuso vale, então fica em dúvida.
    fuso = p["00567895420174036100"]
    assert fuso.prazo_pagamento == date(2026, 12, 31)
    assert "prazo_depende_do_fuso" in {m.codigo for m in fuso.motivos}

    # Divergências reais ficam em dúvida e sem valor escolhido.
    assert p["00234562120208260053"].valor_face is None
    assert p["00456784320215020011"].ente_devedor is None

    # Só de um lado.
    assert "so_no_hub" in {m.codigo for m in fuso.motivos}
    so_tribunal = p["00678906520168260053"]
    assert "so_no_tribunal" in {m.codigo for m in so_tribunal.motivos}
    assert so_tribunal.vencido(REFERENCIA) is True


def test_le_tribunal_csv_fora_do_leiaute(resultado):
    avisos = " ".join(resultado.fontes["tribunal"].avisos)
    assert "UTF-8" in avisos and "separador" in avisos and "vírgula decimal" in avisos
    assert resultado.precatorios["00456784320215020011"].ente_tribunal == "União"


def test_linha_de_comando(entrada, tmp_path, capsys):
    codigo = main(["--entrada", str(entrada), "--saida", str(tmp_path / "s"),
                   "--data-referencia", "2026-11-26"])
    assert codigo == 0
    assert "13 eventos" in capsys.readouterr().out
    for arquivo in ("precatorios.csv", "pagamentos.csv", "quarentena.csv", "relatorio.md"):
        assert (tmp_path / "s" / arquivo).is_file()
