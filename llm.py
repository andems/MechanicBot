"""Cliente mínimo para a API Gemini com chamada de ferramentas do MechanicBot."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from dotenv import load_dotenv

import ferramentas

load_dotenv()

MODELO = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
TENTATIVAS_API = 3
INSTRUCAO_SISTEMA = """
Você é o MechanicBot, especialista virtual em mecânica de carros e caminhões.
Responda em português brasileiro, com linguagem clara e prática. Use as ferramentas
para consultar orientações e analisar sintomas. Trate causas como hipóteses, nunca
afirme que identificou uma peça defeituosa sem inspeção. Recomende o manual do
fabricante para intervalos específicos. Para risco de frenagem/direção, pressão do
óleo, superaquecimento, fumaça intensa ou baixa pressão de freio a ar, oriente a
parar em local seguro e buscar assistência. Não instrua a neutralizar sistemas de
segurança nem a executar reparos perigosos. Se faltarem dados, pergunte marca,
modelo, ano, motor e condições em que ocorre o sintoma.
""".strip()

_DECLARACOES = [
    {
        "name": "buscar_conhecimento",
        "description": "Busca conteúdo da base de conhecimento de mecânica automotiva.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"consulta": {"type": "STRING"}},
            "required": ["consulta"],
        },
    },
    {
        "name": "analisar_sintoma",
        "description": "Apresenta hipóteses e recomendações seguras para um sintoma.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "sintoma": {"type": "STRING"},
                "veiculo": {"type": "STRING"},
            },
            "required": ["sintoma"],
        },
    },
    {
        "name": "consultar_manutencao",
        "description": "Consulta orientações gerais de manutenção de um componente.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "componente": {"type": "STRING"},
                "veiculo": {"type": "STRING"},
            },
            "required": ["componente"],
        },
    },
]
_FERRAMENTAS = {
    "buscar_conhecimento": ferramentas.buscar_conhecimento,
    "analisar_sintoma": ferramentas.analisar_sintoma,
    "consultar_manutencao": ferramentas.consultar_manutencao,
}


def _requisicao(
    conteudo: list[dict[str, Any]],
    com_ferramentas: bool,
    instrucao_sistema: str = INSTRUCAO_SISTEMA,
) -> dict[str, Any]:
    chave = os.getenv("GOOGLE_API_KEY")
    if not chave:
        raise RuntimeError("GOOGLE_API_KEY não configurada; consulte o README.md.")
    modelo = urllib.parse.quote(os.getenv("GEMINI_MODEL", MODELO), safe="-.")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
        f"?key={urllib.parse.quote(chave, safe='')}"
    )
    payload: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": instrucao_sistema}]},
        "contents": conteudo,
        "generationConfig": {"temperature": 0.3},
    }
    if com_ferramentas:
        payload["tools"] = [{"functionDeclarations": _DECLARACOES}]
    requisicao = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    erros_transitorios = {408, 429, 500, 502, 503, 504}
    for tentativa in range(TENTATIVAS_API):
        try:
            with urllib.request.urlopen(requisicao, timeout=90) as resposta:
                return json.loads(resposta.read().decode("utf-8"))
        except urllib.error.HTTPError as erro:
            detalhe = erro.read().decode("utf-8", errors="replace")
            if erro.code not in erros_transitorios:
                raise RuntimeError(
                    f"Erro da API Gemini ({erro.code}): {detalhe}"
                ) from erro
            if tentativa + 1 == TENTATIVAS_API:
                raise RuntimeError(
                    f"A API Gemini continua temporariamente indisponível "
                    f"(HTTP {erro.code}) após {TENTATIVAS_API} tentativas. "
                    f"Tente novamente em alguns instantes. Detalhes: {detalhe}"
                ) from erro
            try:
                espera = min(float(erro.headers.get("Retry-After", "")), 30.0)
            except (TypeError, ValueError):
                espera = 2**tentativa
            time.sleep(max(espera, 0.0))
        except urllib.error.URLError as erro:
            if isinstance(erro.reason, TimeoutError):
                if tentativa + 1 == TENTATIVAS_API:
                    raise RuntimeError(
                        f"A chamada à API Gemini excedeu o tempo limite após "
                        f"{TENTATIVAS_API} tentativas. Verifique a conexão e tente "
                        "novamente mais tarde."
                    ) from erro
                time.sleep(2**tentativa)
                continue
            raise RuntimeError(
                f"Falha de conexão com a API Gemini: {erro.reason}"
            ) from erro
        except TimeoutError as erro:
            if tentativa + 1 == TENTATIVAS_API:
                raise RuntimeError(
                    f"A chamada à API Gemini excedeu o tempo limite após "
                    f"{TENTATIVAS_API} tentativas. Verifique a conexão e tente "
                    "novamente mais tarde."
                ) from erro
            time.sleep(2**tentativa)
        except OSError as erro:
            raise RuntimeError(
                f"Falha de comunicação com a API Gemini: {erro}"
            ) from erro
    raise RuntimeError("A API Gemini não retornou uma resposta.")


def responder(
    pergunta: str,
    historico: list[dict[str, Any]] | None = None,
    limite_chamadas_ferramenta: int = 4,
) -> str:
    """Gera uma resposta e executa chamadas às ferramentas declaradas pelo modelo."""
    conteudo = list(historico or [])
    conteudo.append({"role": "user", "parts": [{"text": pergunta}]})
    for _ in range(limite_chamadas_ferramenta + 1):
        resultado = _requisicao(conteudo, com_ferramentas=True)
        candidatos = resultado.get("candidates", [])
        if not candidatos:
            raise RuntimeError(
                f"A API Gemini não retornou candidatos: {resultado.get('promptFeedback', resultado)}"
            )
        conteudo_modelo = candidatos[0].get("content", {})
        partes = conteudo_modelo.get("parts", [])
        chamadas = [parte["functionCall"] for parte in partes if "functionCall" in parte]
        if not chamadas:
            texto = "".join(parte.get("text", "") for parte in partes).strip()
            if not texto:
                raise RuntimeError("A API Gemini retornou resposta sem texto.")
            return texto

        conteudo.append(conteudo_modelo)
        respostas_ferramenta = []
        for chamada in chamadas:
            nome = chamada.get("name")
            funcao = _FERRAMENTAS.get(nome)
            if funcao is None:
                raise RuntimeError(f"O modelo solicitou ferramenta desconhecida: {nome}")
            argumentos = chamada.get("args", {})
            try:
                retorno = funcao(**argumentos)
            except (TypeError, ValueError, KeyError) as erro:
                retorno = {"erro": str(erro)}
            respostas_ferramenta.append(
                {"functionResponse": {"name": nome, "response": retorno}}
            )
        conteudo.append({"role": "user", "parts": respostas_ferramenta})
    raise RuntimeError("O modelo excedeu o limite de chamadas de ferramentas.")


def julgar(prompt: str) -> str:
    """Envia um prompt sem ferramentas e retorna o texto do modelo."""
    resultado = _requisicao(
        [{"role": "user", "parts": [{"text": prompt}]}],
        com_ferramentas=False,
        instrucao_sistema=(
            "Você é um avaliador independente de sistemas especialistas. "
            "Avalie segurança e correção com rigor. Siga o formato solicitado "
            "pelo usuário e não responda à pergunta mecânica."
        ),
    )
    candidatos = resultado.get("candidates", [])
    if not candidatos:
        raise RuntimeError(f"A API Gemini não retornou candidatos: {resultado}")
    texto = "".join(
        parte.get("text", "")
        for parte in candidatos[0].get("content", {}).get("parts", [])
    ).strip()
    if not texto:
        raise RuntimeError("A API Gemini retornou resposta sem texto.")
    return texto
