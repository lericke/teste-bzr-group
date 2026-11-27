"""Uso: python -m limpeza [--entrada PASTA] [--saida PASTA] [--data-referencia AAAA-MM-DD]"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import executar
from .pagamentos import CORRIGIDO, DESCARTADO, EM_DUVIDA, VALIDO


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m limpeza",
        description="Lê os arquivos do case sem alterá-los e gera a base limpa e o relatório.",
    )
    parser.add_argument("--entrada", type=Path, default=Path("case-candidato/dados"),
                        help="pasta com os arquivos originais (padrão: case-candidato/dados)")
    parser.add_argument("--saida", type=Path, default=Path("saida"),
                        help="pasta onde gravar a base limpa e o relatório (padrão: saida)")
    parser.add_argument("--data-referencia", type=date.fromisoformat, default=date.today(),
                        help="data usada para marcar prazo vencido (padrão: hoje)")
    args = parser.parse_args(argv)

    try:
        resultado = executar(args.entrada, args.saida, args.data_referencia)
    except (OSError, ValueError) as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 2

    contagem = {s: sum(1 for ev in resultado.eventos if ev.status == s)
                for s in (VALIDO, CORRIGIDO, EM_DUVIDA, DESCARTADO)}
    print(
        f"{len(resultado.eventos)} eventos: {contagem[VALIDO]} válidos, {contagem[CORRIGIDO]} corrigidos, "
        f"{contagem[EM_DUVIDA]} em dúvida, {contagem[DESCARTADO]} descartados."
    )
    print(f"{len(resultado.precatorios)} precatórios. Saída em {args.saida}/ (veja relatorio.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
