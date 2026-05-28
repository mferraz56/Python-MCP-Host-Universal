# MCP Host Universal

> Observacao: esta versao ainda nao foi testada manualmente em cenarios reais. Considere o onboarding e os fluxos principais como pendentes de validacao manual.

<!-- ![Banner](./assets/banner.png) -->
[![image-mcp-host.jpg](https://i.postimg.cc/sXKs8822/image-mcp-host.jpg)](https://postimg.cc/bDG7SmkX)

---

## Visão Geral

**MCP Host Universal** é um CLI Python para conectar e usar serviços MCP (Model Context Protocol) no terminal. O runtime atual é **Python-only**, com entrada pelo comando `mcp-host`, suporte a serviços MCP via **HTTP** ou **stdio** e fluxo de chat usando **OpenRouter**.

---

## Requisitos

- Python **3.11+**
- Uma chave de API do [OpenRouter](https://openrouter.ai/keys) para concluir o onboarding e usar o chat
- [`uv`](https://docs.astral.sh/uv/) recomendado para sincronizar dependências e instalar o CLI

## Instalação Rápida

### Rodar localmente a partir do repositório

```bash
uv sync
uv run mcp-host --help
uv run mcp-host
```

### Instalar o CLI como ferramenta local

```bash
uv tool install .
mcp-host --version
mcp-host
```

---

## Primeiro uso

Na primeira execução, o CLI abre um onboarding interativo quando não encontra um `config.json` válido ou quando a chave `openrouter.apiKey` ainda não foi configurada. O assistente solicita:

1. Seu nome
2. Chave da API do OpenRouter
3. Tipo de conta/modelos (pagos ou gratuitos)
4. Modelo para tool use e modelo para resposta final
5. Configuração opcional de um serviço MCP

Resolução padrão do arquivo de configuração:

1. Caminho explícito em `--config`
2. `config.json` legado na raiz do repositório, se ele já existir
3. Caminho de configuração do usuário no sistema operacional

Caminhos padrão por sistema:

- Windows: `%APPDATA%/mcp-host-universal/config.json`
- macOS: `~/Library/Application Support/mcp-host-universal/config.json`
- Linux: `~/.config/mcp-host-universal/config.json` ou `XDG_CONFIG_HOME/mcp-host-universal/config.json`

O CLI mantém compatibilidade com o schema legado de `config.json`.

---

## Flags Principais

- `--config` aponta para um `config.json` específico
- `--prompt` executa um prompt único, sem entrar no modo interativo
- `--version` imprime a versão instalada do CLI

Exemplos:

```bash
uv run mcp-host --prompt "Liste as ferramentas MCP conectadas."
mcp-host --config ./config.json
mcp-host --version
```

---

## Serviços MCP E Templates Embutidos

O host aceita serviços MCP via **HTTP** ou **stdio**.

Templates prontos incluídos:

- `n8n` — `http://localhost:5678/mcp`
- `OpenRouter MCP` — `https://openrouter.ai/mcp`
- `Filesystem` — template stdio com **comando manual obrigatório**
- `Personalizado — stdio`
- `Personalizado — HTTP`

O template de filesystem não injeta mais um comando pronto. Você deve informar manualmente `command` e `args` para o servidor filesystem que deseja usar.

---

## Documentação

- [Guia de uso](docs/usage.md)
- [Guia de migração para o CLI Python](docs/migration-from-node.md)

---

## Licença

MIT © [Henrique Silveira](https://github.com/henrysssilveira)