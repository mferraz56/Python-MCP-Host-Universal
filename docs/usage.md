# Guia De Uso

## Requisitos

- Python 3.11+
- `uv` para sincronizar dependências e instalar o CLI
- Chave de API do OpenRouter para concluir o onboarding e usar o chat

## Instalação

### Rodando A Partir Do Repositório

```bash
uv sync
uv run mcp-host --help
uv run mcp-host
```

### Instalando Como Ferramenta Local

```bash
uv tool install .
mcp-host --help
mcp-host
```

## Flags Principais

- `--config CAMINHO`: usa um `config.json` específico
- `--prompt TEXTO`: executa um prompt único e encerra
- `--version`: mostra a versão do CLI

Exemplos:

```bash
uv run mcp-host --prompt "Liste os serviços MCP disponíveis."
mcp-host --config ./config.json
mcp-host --version
```

## Configuração

O CLI usa o arquivo `config.json`. No primeiro uso, ou quando `openrouter.apiKey` ainda estiver vazio, o onboarding interativo pede:

1. Nome do usuário
2. Chave da API do OpenRouter
3. Tipo de conta/modelos
4. Modelo para tool use e modelo para resposta final
5. Configuração opcional de um serviço MCP

O schema continua compatível com o `config.json` legado.

Resolução do caminho de configuração:

1. `--config`, quando informado
2. `config.json` legado na raiz do repositório, se já existir
3. Caminho do usuário no sistema operacional

Caminhos padrão:

- Windows: `%APPDATA%/mcp-host-universal/config.json`
- macOS: `~/Library/Application Support/mcp-host-universal/config.json`
- Linux: `~/.config/mcp-host-universal/config.json`, ou `XDG_CONFIG_HOME/mcp-host-universal/config.json`

Exemplo mínimo:

```json
{
  "_user": {
    "nome": "Seu nome"
  },
  "openrouter": {
    "apiKey": "sk-...",
    "pago": false,
    "models": {
      "tools": ["openrouter/auto"],
      "final": ["openrouter/auto"]
    }
  },
  "services": []
}
```

## Serviços MCP

O host aceita dois tipos de transporte:

- HTTP
- stdio

Templates embutidos:

| Template | Transporte | Valor padrão | Observação |
|---|---|---|---|
| `n8n` | HTTP | `http://localhost:5678/mcp` | aceita token opcional |
| `openrouter` | HTTP | `https://openrouter.ai/mcp` | template MCP HTTP do OpenRouter |
| `filesystem` | stdio | sem comando padrão | informe `command` e `args` manualmente |
| `custom-stdio` | stdio | vazio | configuração manual |
| `custom-http` | HTTP | vazio | configuração manual |

Para serviços HTTP, use principalmente `url` e `token` quando necessário. Para serviços stdio, informe `command`, `args` e, se precisar, variáveis em `env`.

## Uso Interativo E One-Shot

Modo interativo:

```bash
uv run mcp-host
```

Modo one-shot:

```bash
uv run mcp-host --prompt "Quais ferramentas MCP estão conectadas?"
```

Comandos de sessão:

| Comando | Ação |
|---|---|
| `/` | abre o menu de atalho |
| `/ferramentas` | lista ferramentas por serviço |
| `/servicos` | mostra o status dos serviços |
| `/modelo` | troca o modelo ativo |
| `/mcp` | adiciona um servidor MCP |
| `/mcp-list` | lista ou gerencia servidores MCP configurados |
| `/limpar` | limpa o histórico |
| `/ajuda` | mostra a ajuda |
| `/sair` | encerra a sessão |

Aliases úteis também funcionam, como `/tools`, `/services`, `/model`, `/help` e `/exit`.

## Desenvolvimento

Fluxo mínimo para desenvolvimento local:

```bash
uv sync
uv run mcp-host --help
uv run pytest
```

Se você já instalou o CLI com `uv tool install .`, pode validar a instalação com:

```bash
mcp-host --version
mcp-host --help
```