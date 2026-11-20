# MechanicBot

Chatbot especialista em manutenção e diagnóstico inicial de carros e caminhões. O sistema combina um LLM (Google Gemini), ferramentas MCP para consulta de conhecimento e triagem de sintomas, cache semântico persistente e um avaliador LLM-as-a-Judge.

> O MechanicBot oferece orientação educativa e triagem, não substitui inspeção profissional, manual do fabricante nem diagnóstico presencial. Em sinais de risco, priorize a segurança e não continue dirigindo.

## Requisitos

- Python 3.10 ou superior
- Chave da API Gemini para usar o chat com LLM e executar o julgador
- A primeira execução do cache tenta baixar o modelo multilíngue `paraphrase-multilingual-MiniLM-L12-v2`. Se o modelo não estiver disponível, o cache avisa e usa similaridade local por n-gramas.
- Erros temporários da API Gemini (como HTTP 503/429 e timeouts) são tentados novamente até três vezes, com espera progressiva.

## Instalação e configuração

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                   # Windows: copy .env.example .env
# Edite .env e informe GOOGLE_API_KEY
```

Obtenha uma chave em <https://aistudio.google.com/apikey>. Nunca publique o arquivo `.env`.

## Executar

```bash
# Terminal interativo com LLM e acesso às ferramentas
python chat.py

# Demonstração offline: regras e base local; não usa LLM
python chat.py --demo

# Servidor de ferramentas MCP independente (HTTP em http://127.0.0.1:8000/mcp)
python ferramentas.py

# Avaliação LLM-as-a-Judge; requer GOOGLE_API_KEY
python julgamento/julgamento.py
python julgamento/julgamento.py --caso freios-pedal-baixo

# Testes determinísticos, sem rede e sem chave
python -m unittest discover -s testes -v
```

No chat, digite `/sair` para encerrar. A primeira resposta pode demorar enquanto o modelo de embeddings é carregado. Use perguntas com contexto do veículo (marca, modelo, ano e motor) para obter uma orientação mais útil.

## Arquitetura

| Arquivo | Responsabilidade |
|---|---|
| `chat.py` | Interface de chat, histórico e fluxo cache → LLM |
| `llm.py` | Integração Gemini, chamadas de ferramentas e geração de respostas |
| `cache.py` | Cache semântico SQLite com embeddings locais e limiar de similaridade |
| `ferramentas.py` | Ferramentas MCP `buscar_conhecimento`, `analisar_sintoma` e `consultar_manutencao` |
| `conhecimento/base_conhecimento.json` | Conhecimento automotivo de referência, causas possíveis, cuidados e sinais de risco |
| `julgamento/` | Casos e avaliação por critérios com LLM-as-a-Judge |
| `testes/` | Testes automatizados das regras, ferramentas e persistência do cache |

O chat usa as mesmas funções de ferramenta que são publicadas pelo servidor MCP. O cache armazena somente perguntas e respostas não vazias e reutiliza uma resposta quando a similaridade ultrapassa o limiar configurado. Evite incluir dados pessoais nas perguntas.

## Segurança e limitações

- As causas apresentadas são hipóteses, não confirmações de falha.
- O cronograma de manutenção varia por veículo, uso e mercado. O manual do fabricante prevalece sobre recomendações gerais.
- Pare o veículo e procure assistência quando houver perda de frenagem/direção, luz vermelha de pressão do óleo, superaquecimento ou fumaça intensa.
- O modo `--demo` demonstra busca e triagem local; ele não representa inferência por LLM.
# MechanicBot
