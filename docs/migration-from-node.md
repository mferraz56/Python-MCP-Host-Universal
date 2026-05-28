# Migração Do CLI Npm Para O CLI Python

O runtime atual do MCP Host Universal é Python-only. Referências a Node.js, npm, npx, `package.json` e `index.js` pertencem apenas ao contexto histórico da migração.

## O Que Mudou

| Antes | Agora |
|---|---|
| Runtime baseado em Node.js | Runtime baseado em Python 3.11+ |
| Execução via npm ou npx | Execução via `mcp-host` |
| Metadados em artefatos JavaScript | Metadados em `pyproject.toml` |
| Entrada de execução em JavaScript | Entrada em `mcp_host_universal.cli:main` |
| Configuração local no repositório | Compatibilidade com `config.json` legado, mas com fallback para diretório de usuário |
| Template filesystem com comando pronto | Template filesystem exige `command` e `args` definidos manualmente |

## Como Migrar

1. Pare de depender de npm ou npx para instalar ou executar o host.
2. Passe a validar o projeto com `uv sync` e `uv run mcp-host --help`.
3. Se quiser instalar o CLI localmente, use `uv tool install .`.
4. Reaproveite seu `config.json` existente. Se houver um arquivo legado na raiz do projeto, o CLI Python o usa primeiro.
5. Revise serviços stdio, principalmente o template `filesystem`, e preencha `command` e `args` manualmente.

## Instalação Equivalente

Rodando do repositório:

```bash
uv sync
uv run mcp-host --help
uv run mcp-host
```

Instalando o comando localmente:

```bash
uv tool install .
mcp-host --version
mcp-host
```

## Configuração E Compatibilidade

O arquivo de configuração continua sendo `config.json`, com compatibilidade para o schema legado. Isso inclui a estrutura principal de `_user`, `openrouter` e `services`.

Ordem de resolução do arquivo:

1. Caminho informado em `--config`
2. `config.json` legado na raiz do projeto, se já existir
3. Caminho do usuário no sistema operacional

Caminhos padrão do usuário:

- Windows: `%APPDATA%/mcp-host-universal/config.json`
- macOS: `~/Library/Application Support/mcp-host-universal/config.json`
- Linux: `~/.config/mcp-host-universal/config.json`, ou `XDG_CONFIG_HOME/mcp-host-universal/config.json`

Se o arquivo existir, o CLI não força migração automática para outro lugar. Ele apenas reutiliza o caminho resolvido.

## OpenRouter E Serviços MCP

O onboarding continua pedindo uma chave da API do OpenRouter no primeiro uso, ou sempre que `openrouter.apiKey` estiver vazio. Os serviços MCP continuam podendo ser configurados em dois transportes:

- HTTP
- stdio

Templates embutidos disponíveis no runtime Python:

- `n8n` HTTP
- `OpenRouter MCP` HTTP
- `filesystem` stdio com comando manual
- `custom-stdio`
- `custom-http`

## Checklist Rápido Pós-Migração

1. `uv run mcp-host --help` responde sem erro.
2. Seu `config.json` legado continua sendo encontrado, ou você aponta o caminho com `--config`.
3. A chave `openrouter.apiKey` está presente.
4. Serviços HTTP têm `url` correta e token quando necessário.
5. Serviços stdio têm `command` e `args` válidos, especialmente no caso de `filesystem`.