"""Chat interativo de orientação mecânica."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from dotenv import load_dotenv

from cache import CacheSemantico
from ferramentas import analisar_sintoma, buscar_conhecimento

load_dotenv()


def responder_demo(pergunta: str) -> str:
    resultado = analisar_sintoma(pergunta)
    hipoteses = resultado["hipoteses"]
    if not hipoteses:
        conhecimento = buscar_conhecimento(pergunta)
        hipoteses = conhecimento["resultados"]
    if not hipoteses:
        return (
            "Não encontrei uma orientação específica na base local. Informe marca, "
            "modelo, ano, motor e quando o sintoma acontece; consulte também o "
            "manual do fabricante ou uma oficina."
        )
    linhas = ["Possíveis orientações (modo de demonstração, sem LLM):"]
    linhas.extend(f"- {item.get('componente', item.get('titulo'))}: "
                  f"{item.get('orientacao', item.get('conteudo'))}" for item in hipoteses)
    linhas.append(f"Urgência: {resultado['urgencia']}")
    linhas.append(resultado["limite"])
    return "\n".join(linhas)


def _historico_para_llm(historico: list[tuple[str, str]]) -> list[dict[str, Any]]:
    return [
        {"role": papel, "parts": [{"text": texto}]}
        for papel, texto in historico
    ]


def executar(demo: bool = False) -> int:
    cache = CacheSemantico()
    historico: list[tuple[str, str]] = []
    print("MechanicBot — especialista virtual em mecânica automotiva")
    print("Digite /sair para encerrar. Orientações não substituem inspeção profissional.")
    if demo:
        print("Modo de demonstração offline ativo; nenhuma resposta é gerada por LLM.")
    while True:
        try:
            pergunta = input("\nVocê: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAté logo.")
            return 0
        if pergunta.casefold() in {"/sair", "sair", "exit", "quit"}:
            print("Até logo.")
            return 0
        if not pergunta:
            continue
        try:
            consulta_cache = f"mechanicbot-v1 {pergunta}"
            resultado_cache = cache.buscar(consulta_cache)
            if resultado_cache:
                resposta, similaridade = resultado_cache
                print(f"\nMechanicBot [cache semântico, {similaridade:.0%}]:\n{resposta}")
                historico.extend([("user", pergunta), ("model", resposta)])
                continue
            if demo:
                resposta = responder_demo(pergunta)
            else:
                from llm import responder

                resposta = responder(
                    pergunta, historico=_historico_para_llm(historico)
                )
            cache.gravar(consulta_cache, resposta)
            print(f"\nMechanicBot:\n{resposta}")
            historico.extend([("user", pergunta), ("model", resposta)])
        except (RuntimeError, ValueError, OSError, json.JSONDecodeError) as erro:
            print(f"\nNão foi possível responder: {erro}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="usa somente a base local; não chama um LLM",
    )
    argumentos = parser.parse_args()
    return executar(demo=argumentos.demo)


if __name__ == "__main__":
    raise SystemExit(main())
