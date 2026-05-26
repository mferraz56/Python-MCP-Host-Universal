# MCP Universal CLI

<!-- Adicione uma imagem/banner aqui -->
<!-- ![Banner](./assets/banner.png) -->

---

## Visão Geral

**MCP Universal CLI** é um host de linha de comando para servidores MCP (Model Context Protocol), com suporte a múltiplos modelos de linguagem via **OpenRouter**. Permite conectar ferramentas externas (n8n, filesystem, APIs customizadas) diretamente ao seu terminal com uma interface rica e interativa.

---

## Instalação

```bash
npm install -g @henrysssilveira/mcp-host-universal
```

Após instalar, rode com:

```bash
mcp-host
```

---

## Pré-requisitos

- Node.js **18+**
- Uma chave de API do [OpenRouter](https://openrouter.ai/keys)

---

## Primeiro uso

Na primeira execução, o CLI abre um assistente de configuração interativo que solicita:

1. Seu nome
2. Chave da API do OpenRouter
3. Tipo de modelos (pagos ou gratuitos)
4. Modelo principal de tool-use e modelo de resposta final
5. Configuração opcional de um servidor MCP

As configurações são salvas em `config.json` no diretório de instalação.

---

## Modelos suportados

### Pagos
| Modelo | Contexto |
|---|---|
| Claude Sonnet 4.5 | 200k |
| Claude Opus 4 | 200k |
| GPT-4o | 128k |
| Gemini 2.5 Pro | 1M |
| Mistral Large | 128k |
| DeepSeek Chat V3 | 64k |
| e outros... | — |

### Gratuitos
| Modelo | Contexto |
|---|---|
| Auto Router (recomendado) | — |
| Llama 3.3 70B | 128k |
| Gemma 4 31B | 128k |
| Qwen3 Coder 480B | 128k |
| e outros... | — |

---

## Servidores MCP suportados

| Tipo | Descrição |
|---|---|
| **HTTP** | Qualquer servidor MCP via Streamable HTTP (ex: n8n) |
| **stdio** | Servidores locais via processo (ex: `@modelcontextprotocol/server-filesystem`) |

### Templates prontos
- `n8n` — `http://localhost:5678/mcp`
- `OpenRouter MCP` — `https://openrouter.ai/mcp`
- `Filesystem` — `npx @modelcontextprotocol/server-filesystem /tmp`
- Personalizado via HTTP ou stdio

---

## Comandos disponíveis

| Comando | Descrição |
|---|---|
| `/` | Abre o menu interativo com dropdown |
| `/servicos` | Status dos serviços conectados |
| `/ferramentas` | Lista ferramentas por serviço |
| `/modelo` | Troca o modelo ativo |
| `/mcp` | Configura ou adiciona um servidor MCP |
| `/limpar` | Limpa o histórico da conversa |
| `/ajuda` | Exibe a ajuda |
| `/sair` | Encerra o CLI |

---

## Configuração manual

O arquivo `config.json` gerado tem a seguinte estrutura:

```json
{
  "_user": { "nome": "Seu Nome" },
  "openrouter": {
    "apiKey": "sk-...",
    "pago": false,
    "models": {
      "tools": ["openrouter/auto"],
      "final": ["openrouter/auto"]
    }
  },
  "services": [
    {
      "name": "n8n",
      "transport": "http",
      "url": "http://localhost:5678/mcp",
      "token": "",
      "systemPrompt": "Você tem acesso ao n8n para criar e executar workflows.",
      "enabled": true
    }
  ]
}
```

---

## Stack

- [`@modelcontextprotocol/sdk`](https://github.com/modelcontextprotocol/typescript-sdk) — cliente MCP
- [OpenRouter](https://openrouter.ai) — roteamento de modelos
- [`chalk`](https://github.com/chalk/chalk), [`ora`](https://github.com/sindresorhus/ora), [`figlet`](https://github.com/patorjk/figlet.js), [`gradient-string`](https://github.com/bokub/gradient-string), [`cli-table3`](https://github.com/cli-table/cli-table3), [`boxen`](https://github.com/sindresorhus/boxen) — UI de terminal

---

## Licença

MIT © [Henrique Silveira](https://github.com/henrysssilveira)