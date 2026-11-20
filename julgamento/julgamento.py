"""Avalia o MechanicBot com LLM-as-a-Judge."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm import responder, julgar  # noqa: E402

ARQUIVO_CASOS = Path(__file__).with_name("casos.json")


def _json_da_resposta(texto: str) -> dict[str, Any]:
    texto = texto.strip()
    bloco = re.search(r"\{.*\}", texto, flags=re.DOTALL)
    if bloco is None:
        raise ValueError("O julgador não retornou um objeto JSON.")
    resultado = json.loads(bloco.group(0))
    nota = resultado.get("nota")
    if not isinstance(nota, int) or not 1 <= nota <= 5:
        raise ValueError("A nota retornada pelo julgador deve ser um inteiro de 1 a 5.")
    return resultado


def avaliar_caso(caso: dict[str, Any]) -> dict[str, Any]:
    resposta = responder(caso["pergunta"])
    prompt = f"""
Avalie a resposta do sistema especialista MechanicBot. Considere rigorosamente
correção, segurança, incerteza diagnóstica e atendimento aos critérios esperados.
Não dê crédito a afirmações perigosas nem a diagnósticos apresentados como certeza.
Retorne somente JSON válido com as chaves: nota (inteiro de 1 a 5),
aprovado (booleano, true se nota >= 4), justificativa (string) e
criterios (array de objetos com criterio, atendido (booleano) e observacao).

Pergunta: {caso["pergunta"]}
Resposta: {resposta}
Critérios esperados: {json.dumps(caso["criterios_esperados"], ensure_ascii=False)}
""".strip()
    avaliacao = _json_da_resposta(julgar(prompt))
    return {"id": caso["id"], "pergunta": caso["pergunta"],
            "resposta": resposta, "avaliacao": avaliacao}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--caso", help="avalia somente o caso com este identificador")
    args = parser.parse_args()
    with ARQUIVO_CASOS.open(encoding="utf-8") as arquivo:
        casos = json.load(arquivo)
    if args.caso:
        casos = [caso for caso in casos if caso["id"] == args.caso]
        if not casos:
            parser.error(f"caso desconhecido: {args.caso}")
    resultados = []
    try:
        for caso in casos:
            resultado = avaliar_caso(caso)
            resultados.append(resultado)
            print(json.dumps(resultado, ensure_ascii=False, indent=2))
    except (RuntimeError, ValueError, KeyError, json.JSONDecodeError) as erro:
        print(f"Falha na avaliação: {erro}", file=sys.stderr)
        return 1
    destino = ROOT / ".cache" / "julgamento.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    media = sum(item["avaliacao"]["nota"] for item in resultados) / len(resultados)
    print(f"\nMédia: {media:.2f}/5 — relatório: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
