"""Cache semântico persistente para perguntas e respostas do MechanicBot."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import sys
import unicodedata
from pathlib import Path
from typing import Sequence


class CacheSemantico:
    def __init__(
        self,
        caminho: str | Path | None = None,
        modelo: str | None = None,
        limiar: float | None = None,
    ) -> None:
        self.caminho = Path(
            caminho
            or os.getenv("MECHANICBOT_CACHE_PATH", ".cache/mechanicbot.sqlite3")
        )
        self.modelo = modelo or os.getenv(
            "MECHANICBOT_EMBEDDING_MODEL",
            "paraphrase-multilingual-MiniLM-L12-v2",
        )
        self.limiar = (
            limiar
            if limiar is not None
            else float(os.getenv("MECHANICBOT_CACHE_THRESHOLD", "0.82"))
        )
        if not 0.0 < self.limiar <= 1.0:
            raise ValueError("O limiar do cache deve estar entre 0 e 1.")
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with self._conectar() as conexao:
            conexao.execute(
                """
                CREATE TABLE IF NOT EXISTS respostas (
                    id TEXT PRIMARY KEY,
                    pergunta TEXT NOT NULL,
                    resposta TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        self._modelo_embedding = None
        self._aviso_fallback_emitido = False

    def _conectar(self) -> sqlite3.Connection:
        return sqlite3.connect(self.caminho)

    @staticmethod
    def _normalizar(texto: str) -> str:
        sem_acentos = unicodedata.normalize("NFKD", texto.casefold())
        return " ".join(
            "".join(c for c in sem_acentos if not unicodedata.combining(c)).split()
        )

    def _vetor_fallback(self, texto: str) -> list[float]:
        normalizado = self._normalizar(texto)
        tokens = normalizado.split()
        caracteristicas = set(tokens)
        compactado = f"  {normalizado}  "
        caracteristicas.update(
            compactado[i : i + 3] for i in range(max(0, len(compactado) - 2))
        )
        vetor = [0.0] * 512
        for caracteristica in caracteristicas:
            digest = hashlib.blake2b(
                caracteristica.encode("utf-8"), digest_size=8
            ).digest()
            indice = int.from_bytes(digest, "big") % len(vetor)
            vetor[indice] += 1.0
        norma = math.sqrt(sum(valor * valor for valor in vetor))
        return [valor / norma for valor in vetor] if norma else vetor

    def _embedding(self, texto: str) -> list[float]:
        if self._modelo_embedding is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._modelo_embedding = SentenceTransformer(self.modelo)
            except (ImportError, OSError, RuntimeError) as erro:
                if not self._aviso_fallback_emitido:
                    print(
                        f"Cache semântico: embeddings não disponíveis ({erro}); "
                        "usando similaridade local por n-gramas.",
                        file=sys.stderr,
                    )
                    self._aviso_fallback_emitido = True
                self._modelo_embedding = False
        if self._modelo_embedding is False:
            return self._vetor_fallback(texto)
        vetor = self._modelo_embedding.encode(texto, normalize_embeddings=True)
        return [float(valor) for valor in vetor]

    @staticmethod
    def _similaridade(vetor_a: Sequence[float], vetor_b: Sequence[float]) -> float:
        if len(vetor_a) != len(vetor_b):
            return 0.0
        return sum(a * b for a, b in zip(vetor_a, vetor_b))

    def buscar(self, pergunta: str) -> tuple[str, float] | None:
        if not pergunta.strip():
            return None
        vetor_consulta = self._embedding(pergunta)
        with self._conectar() as conexao:
            registros = conexao.execute(
                "SELECT resposta, embedding FROM respostas"
            ).fetchall()
        melhor: tuple[str, float] | None = None
        for resposta, embedding_json in registros:
            vetor_salvo = json.loads(embedding_json)
            similaridade = self._similaridade(vetor_consulta, vetor_salvo)
            if melhor is None or similaridade > melhor[1]:
                melhor = (resposta, similaridade)
        return melhor if melhor and melhor[1] >= self.limiar else None

    def gravar(self, pergunta: str, resposta: str) -> None:
        if not pergunta.strip() or not resposta.strip():
            raise ValueError("Pergunta e resposta não podem estar vazias.")
        vetor = self._embedding(pergunta)
        identificador = hashlib.sha256(
            self._normalizar(pergunta).encode("utf-8")
        ).hexdigest()
        with self._conectar() as conexao:
            conexao.execute(
                """
                INSERT INTO respostas (id, pergunta, resposta, embedding)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    pergunta = excluded.pergunta,
                    resposta = excluded.resposta,
                    embedding = excluded.embedding
                """,
                (identificador, pergunta.strip(), resposta.strip(), json.dumps(vetor)),
            )
