import json
import io
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from cache import CacheSemantico
from ferramentas import analisar_sintoma, buscar_conhecimento, consultar_manutencao
from julgamento.julgamento import _json_da_resposta
from llm import _requisicao


class TesteFerramentas(unittest.TestCase):
    def test_busca_encontra_orientacao_de_freio(self):
        resultado = buscar_conhecimento("ruído ao frear")
        self.assertTrue(resultado["resultados"])
        self.assertEqual(resultado["resultados"][0]["id"], "freios-sinais")

    def test_sintoma_critico_recomenda_parada(self):
        resultado = analisar_sintoma("pedal de freio afundando")
        self.assertIn("pare em local seguro", resultado["urgencia"])
        self.assertIn("não confirma", resultado["limite"])

    def test_manutencao_nao_inventa_intervalo(self):
        resultado = consultar_manutencao("óleo", "carro")
        self.assertIn("manual do fabricante", resultado["intervalo"])


class TesteCache(unittest.TestCase):
    def test_persistencia_e_reutilizacao_semantica(self):
        with tempfile.TemporaryDirectory() as diretorio:
            cache = CacheSemantico(
                caminho=Path(diretorio) / "cache.sqlite3",
                limiar=0.99,
            )
            pergunta = "por que meu motor está superaquecendo"
            resposta = "Pare em local seguro e aguarde o motor esfriar."
            cache.gravar(pergunta, resposta)
            encontrado = cache.buscar(pergunta)
            self.assertIsNotNone(encontrado)
            self.assertEqual(encontrado[0], resposta)
            self.assertGreaterEqual(encontrado[1], 0.99)

    def test_nao_grava_resposta_vazia(self):
        with tempfile.TemporaryDirectory() as diretorio:
            cache = CacheSemantico(caminho=Path(diretorio) / "cache.sqlite3")
            with self.assertRaises(ValueError):
                cache.gravar("pergunta", " ")


class TesteJulgador(unittest.TestCase):
    def test_valida_json_do_julgador(self):
        resultado = _json_da_resposta(
            '{"nota": 4, "aprovado": true, "justificativa": "seguro", "criterios": []}'
        )
        self.assertEqual(resultado["nota"], 4)

    def test_rejeita_nota_invalida(self):
        with self.assertRaises(ValueError):
            _json_da_resposta('{"nota": 8}')


class TesteRetentativasGemini(unittest.TestCase):
    @staticmethod
    def erro_http(codigo, mensagem):
        cabecalhos = Message()
        return urllib.error.HTTPError(
            "https://example.test",
            codigo,
            "erro",
            cabecalhos,
            io.BytesIO(mensagem.encode("utf-8")),
        )

    @patch.dict("os.environ", {"GOOGLE_API_KEY": "teste"})
    @patch("llm.time.sleep")
    @patch("llm.urllib.request.urlopen")
    def test_repete_503_e_retorna_sucesso(self, abrir_url, dormir):
        resposta = io.BytesIO(b'{"ok": true}')
        abrir_url.side_effect = [
            self.erro_http(503, "sobrecarga"),
            resposta,
        ]

        resultado = _requisicao([], com_ferramentas=False)

        self.assertEqual(resultado, {"ok": True})
        self.assertEqual(abrir_url.call_count, 2)
        dormir.assert_called_once_with(1)

    @patch.dict("os.environ", {"GOOGLE_API_KEY": "teste"})
    @patch("llm.time.sleep")
    @patch("llm.urllib.request.urlopen")
    def test_nao_repete_erro_404(self, abrir_url, dormir):
        abrir_url.side_effect = self.erro_http(404, "modelo não encontrado")

        with self.assertRaisesRegex(RuntimeError, "Erro da API Gemini \\(404\\)"):
            _requisicao([], com_ferramentas=False)

        abrir_url.assert_called_once()
        dormir.assert_not_called()

    @patch.dict("os.environ", {"GOOGLE_API_KEY": "teste"})
    @patch("llm.time.sleep")
    @patch("llm.urllib.request.urlopen")
    def test_repete_timeout_e_retorna_sucesso(self, abrir_url, dormir):
        abrir_url.side_effect = [
            TimeoutError("The read operation timed out"),
            io.BytesIO(b'{"ok": true}'),
        ]

        resultado = _requisicao([], com_ferramentas=False)

        self.assertEqual(resultado, {"ok": True})
        self.assertEqual(abrir_url.call_count, 2)
        dormir.assert_called_once_with(1)

    @patch.dict("os.environ", {"GOOGLE_API_KEY": "teste"})
    @patch("llm.time.sleep")
    @patch("llm.urllib.request.urlopen")
    def test_informa_quando_timeouts_esgotam_tentativas(self, abrir_url, dormir):
        abrir_url.side_effect = TimeoutError("The read operation timed out")

        with self.assertRaisesRegex(RuntimeError, "excedeu o tempo limite"):
            _requisicao([], com_ferramentas=False)

        self.assertEqual(abrir_url.call_count, 3)
        self.assertEqual([chamada.args[0] for chamada in dormir.call_args_list], [1, 2])


if __name__ == "__main__":
    unittest.main()
