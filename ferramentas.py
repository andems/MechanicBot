"""Ferramentas de conhecimento automotivo expostas por MCP."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

BASE_CONHECIMENTO = Path(__file__).parent / "conhecimento" / "base_conhecimento.json"
_base: list[dict[str, Any]] | None = None
_STOPWORDS = {
    "a", "ao", "aos", "as", "com", "da", "das", "de", "do", "dos",
    "e", "em", "meu", "minha", "o", "os", "para", "pela", "pelo",
    "por", "qual", "que", "se", "tem", "um", "uma",
}


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.casefold())
    return "".join(c for c in texto if not unicodedata.combining(c))


def _carregar_base() -> list[dict[str, Any]]:
    global _base
    if _base is None:
        with BASE_CONHECIMENTO.open(encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        _base = dados["artigos"]
    return _base


def buscar_conhecimento(consulta: str) -> dict[str, Any]:
    """Busca orientações na base local usando palavras-chave e tópicos."""
    termos = {
        termo for termo in re.findall(r"\w+", _normalizar(consulta))
        if termo not in _STOPWORDS and len(termo) > 2
    }
    resultados = []
    for artigo in _carregar_base():
        texto = _normalizar(
            artigo["titulo"] + " " + " ".join(artigo["topicos"]) + " "
            + artigo["conteudo"]
        )
        topicos = [_normalizar(topico) for topico in artigo["topicos"]]
        pontuacao = sum(2 for termo in termos if any(termo in topico for topico in topicos))
        pontuacao += sum(1 for termo in termos if termo in texto)
        if pontuacao:
            resultados.append((pontuacao, artigo))
    resultados.sort(key=lambda item: (-item[0], item[1]["id"]))
    return {
        "resultados": [
            {
                "id": artigo["id"],
                "titulo": artigo["titulo"],
                "conteudo": artigo["conteudo"],
                "relevancia": pontuacao,
            }
            for pontuacao, artigo in resultados[:4]
        ],
        "aviso": "Conteúdo informativo; confirme no manual e com profissional habilitado.",
    }


def analisar_sintoma(sintoma: str, veiculo: str = "") -> dict[str, Any]:
    """Relaciona um sintoma a causas possíveis e orienta medidas seguras."""
    resultado = buscar_conhecimento(f"{veiculo} {sintoma}".strip())
    artigos = resultado["resultados"]
    sinais_criticos = (
        "pedal afunda", "sem freio", "perda de freio", "luz vermelha de oleo",
        "pressao do oleo", "superaquec", "fumaça intensa", "fumaça abundante",
        "perda de direcao", "direcao falhando", "baixa pressao de ar",
    )
    texto = _normalizar(sintoma)
    urgente = any(sinal in texto for sinal in sinais_criticos) or (
        "pedal" in texto
        and any(termo in texto for termo in ("afund", "esponjos", "sem freio"))
    )
    return {
        "veiculo": veiculo or "não informado",
        "sintoma": sintoma,
        "hipoteses": [
            {"componente": artigo["titulo"], "orientacao": artigo["conteudo"]}
            for artigo in artigos[:3]
        ],
        "urgencia": "pare em local seguro e solicite assistência"
        if urgente
        else "agende uma inspeção; interrompa o uso se o sintoma piorar",
        "limite": "Isto não confirma uma peça defeituosa nem substitui diagnóstico presencial.",
    }


def consultar_manutencao(componente: str, veiculo: str = "") -> dict[str, Any]:
    """Consulta recomendações gerais de manutenção para um componente."""
    resultado = buscar_conhecimento(f"manutenção revisão {componente} {veiculo}")
    return {
        "veiculo": veiculo or "não informado",
        "componente": componente,
        "orientacoes": resultado["resultados"],
        "intervalo": "Consulte o manual do fabricante para intervalo por tempo e quilometragem.",
        "observacao": "Uso severo pode exigir inspeções mais frequentes.",
    }


try:
    from fastmcp import FastMCP
except ImportError as erro:
    FastMCP = None
    _mcp_import_error = erro
else:
    _mcp_import_error = None


if FastMCP is not None:
    mcp = FastMCP("MechanicBot")
    mcp.tool()(buscar_conhecimento)
    mcp.tool()(analisar_sintoma)
    mcp.tool()(consultar_manutencao)
else:
    mcp = None


def executar_servidor() -> None:
    if mcp is None:
        raise RuntimeError(
            "FastMCP não está instalado. Execute: pip install -r requirements.txt"
        ) from _mcp_import_error
    mcp.run(transport="http", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    executar_servidor()
