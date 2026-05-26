#!/usr/bin/env node
// ─────────────────────────────────────────────────────────────────────────────
// MCP Universal CLI v4.0
// ─────────────────────────────────────────────────────────────────────────────
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import readline from 'readline';
import chalk from 'chalk';
import ora from 'ora';
import figlet from 'figlet';
import boxen from 'boxen';
import gradient from 'gradient-string';
import Table from 'cli-table3';
import { readFileSync, writeFileSync, existsSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const CONFIG_PATH = resolve(__dirname, 'config.json');
const OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions';

// ─────────────────────────────────────────────
// MODELOS
// ─────────────────────────────────────────────

const PAID_MODELS = [
  { id: 'anthropic/claude-sonnet-4-5',       label: 'Claude Sonnet 4.5',            ctx: '200k' },
  { id: 'anthropic/claude-opus-4',           label: 'Claude Opus 4',                ctx: '200k' },
  { id: 'openai/gpt-4o',                     label: 'GPT-4o',                       ctx: '128k' },
  { id: 'openai/gpt-4-turbo',                label: 'GPT-4 Turbo',                  ctx: '128k' },
  { id: 'google/gemini-2.5-pro',             label: 'Gemini 2.5 Pro',               ctx: '1M'   },
  { id: 'google/gemini-2.5-flash',           label: 'Gemini 2.5 Flash',             ctx: '1M'   },
  { id: 'meta-llama/llama-3.3-70b-instruct', label: 'Llama 3.3 70B',               ctx: '128k' },
  { id: 'mistralai/mistral-large',           label: 'Mistral Large',                ctx: '128k' },
  { id: 'deepseek/deepseek-chat',            label: 'DeepSeek Chat V3',             ctx: '64k'  },
  { id: 'qwen/qwen-2.5-72b-instruct',        label: 'Qwen 2.5 72B',                ctx: '128k' },
];

const FREE_MODELS = [
  { id: 'openrouter/auto',                              label: '⚡ Auto Router (recomendado)',      ctx: '—'    },
  { id: 'deepseek/deepseek-v4-flash:free',              label: 'DeepSeek V4 Flash (free)',         ctx: '64k'  },
  { id: 'nvidia/nemotron-3-super-120b-a12b:free',       label: 'Nemotron 3 Super 120B (free)',     ctx: '128k' },
  { id: 'meta-llama/llama-3.3-70b-instruct:free',       label: 'Llama 3.3 70B (free)',             ctx: '128k' },
  { id: 'nousresearch/hermes-3-llama-3.1-405b:free',    label: 'Hermes 3 Llama 405B (free)',       ctx: '128k' },
  { id: 'minimax/minimax-m2.5:free',                    label: 'MiniMax M2.5 (free)',               ctx: '1M'   },
  { id: 'google/gemma-4-31b-it:free',                   label: 'Gemma 4 31B (free)',               ctx: '128k' },
  { id: 'openai/gpt-oss-120b:free',                     label: 'GPT OSS 120B (free)',              ctx: '128k' },
  { id: 'qwen/qwen3-coder-480b-a35b-instruct:free',     label: 'Qwen3 Coder 480B (free)',          ctx: '128k' },
];

// ─────────────────────────────────────────────
// PALETA
// ─────────────────────────────────────────────

const c = {
  primary: chalk.hex('#e36b2f'),
  accent:  chalk.hex('#ff9a5c'),
  dim:     chalk.hex('#6e7681'),
  muted:   chalk.hex('#8b949e'),
  bright:  chalk.hex('#f0f6fc'),
  success: chalk.hex('#3fb950'),
  warn:    chalk.hex('#d29922'),
  error:   chalk.hex('#f85149'),
  info:    chalk.hex('#58a6ff'),
  purple:  chalk.hex('#bc8cff'),
  teal:    chalk.hex('#39d353'),
  gold:    chalk.hex('#ffd700'),
};

const SERVICE_COLORS = [
  chalk.hex('#58a6ff'), chalk.hex('#3fb950'),
  chalk.hex('#bc8cff'), chalk.hex('#ffd700'),
  chalk.hex('#ff6b9d'), chalk.hex('#00d2d3'),
];

const grad = {
  fire: gradient(['#ff4500', '#e36b2f', '#ffd700']),
  cool: gradient(['#58a6ff', '#bc8cff']),
  soft: gradient(['#3fb950', '#58a6ff']),
};

function divider(char = '─', width = 70) { return c.dim(char.repeat(width)); }
function badge(text, color = c.primary)  { return color(`[${text}]`); }
function timestamp() {
  const n = new Date();
  return c.dim(`${String(n.getHours()).padStart(2,'0')}:${String(n.getMinutes()).padStart(2,'0')}:${String(n.getSeconds()).padStart(2,'0')}`);
}

// ─────────────────────────────────────────────
// CONFIG I/O
// ─────────────────────────────────────────────

function loadConfig() {
  if (!existsSync(CONFIG_PATH)) return null;
  try {
    return JSON.parse(readFileSync(CONFIG_PATH, 'utf-8'));
  } catch { return null; }
}

function saveConfig(cfg) {
  writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2), 'utf-8');
}

// ─────────────────────────────────────────────
// INPUT PRIMITIVES (raw mode)
// ─────────────────────────────────────────────

function rawQuestion(prompt, opts = {}) {
  return new Promise(resolve => {
    process.stdout.write(prompt);
    const { secret = false } = opts;
    let buf = '';

    const onKey = (chunk) => {
      const char = chunk.toString();
      const code = chunk[0];

      if (code === 13 || code === 10) { // Enter
        if (!secret) process.stdout.write('\n');
        else process.stdout.write('\n');
        cleanup();
        resolve(buf);
      } else if (code === 127 || code === 8) { // Backspace
        if (buf.length > 0) {
          buf = buf.slice(0, -1);
          if (!secret) process.stdout.write('\b \b');
        }
      } else if (code === 3) { // Ctrl+C
        cleanup();
        process.exit(0);
      } else if (char >= ' ') {
        buf += char;
        if (!secret) process.stdout.write(char);
        else process.stdout.write(c.dim('·'));
      }
    };

    const cleanup = () => {
      process.stdin.removeListener('data', onKey);
      if (process.stdin.isTTY) process.stdin.setRawMode(false);
      process.stdin.pause();
    };

    if (process.stdin.isTTY) process.stdin.setRawMode(true);
    process.stdin.resume();
    process.stdin.on('data', onKey);
  });
}

// Seleção por seta de lista com destaque
function selectFromList(items, opts = {}) {
  const { title = '', displayFn = (x) => x } = opts;
  return new Promise(resolve => {
    let selected = 0;
    const render = () => {
      // Move cursor up para re-renderizar
      if (render._lines > 0) {
        process.stdout.write(`\x1b[${render._lines}A\x1b[0J`);
      }
      const lines = [];
      if (title) lines.push(c.muted('  ' + title));
      items.forEach((item, i) => {
        const label = displayFn(item);
        if (i === selected) {
          lines.push(c.accent.bold(`  ❯ ${label}`));
        } else {
          lines.push(c.dim(`    ${label}`));
        }
      });
      process.stdout.write(lines.join('\n') + '\n');
      render._lines = lines.length;
    };
    render._lines = 0;
    render();

    const onKey = (chunk) => {
      const code = chunk[0];
      const seq  = chunk.toString();
      if (seq === '\x1b[A' || seq === '\x1b[D') { selected = (selected - 1 + items.length) % items.length; render(); }
      else if (seq === '\x1b[B' || seq === '\x1b[C') { selected = (selected + 1) % items.length; render(); }
      else if (code === 13 || code === 10) { cleanup(); resolve(items[selected]); }
      else if (code === 3) { cleanup(); process.exit(0); }
    };

    const cleanup = () => {
      process.stdin.removeListener('data', onKey);
      if (process.stdin.isTTY) process.stdin.setRawMode(false);
      process.stdin.pause();
    };

    if (process.stdin.isTTY) process.stdin.setRawMode(true);
    process.stdin.resume();
    process.stdin.on('data', onKey);
  });
}

// Confirmar boolean (Y/n)
async function confirm(prompt, defaultVal = true) {
  const hint = defaultVal ? c.dim('(Y/n)') : c.dim('(y/N)');
  const ans = await rawQuestion(`${prompt} ${hint} `);
  if (!ans.trim()) return defaultVal;
  return ans.trim().toLowerCase().startsWith('y');
}

// ─────────────────────────────────────────────
// ONBOARDING — PRIMEIRO SETUP
// ─────────────────────────────────────────────

async function runOnboarding() {
  console.clear();
  const title = figlet.textSync('MCP Setup', { font: 'ANSI shadow' });
  console.log(grad.cool(title));
  console.log(boxen(
    c.muted('Bem-vindo! Vamos configurar seu ') + c.accent.bold('MCP Universal CLI') +
    c.muted('\nEste assistente só aparece uma vez. Você pode editar ') + c.dim('config.json') + c.muted(' depois.'),
    { padding: 1, borderStyle: 'round', borderColor: '#58a6ff', textAlignment: 'center' }
  ));
  console.log();

  // 1. Nome
  console.log(c.info.bold('  1/3 · Identificação'));
  console.log(c.dim('  Como posso te chamar?\n'));
  const nome = await rawQuestion(c.accent('  › Nome: '));
  console.log();

  // 2. Chave OpenRouter
  console.log(c.info.bold('  2/3 · OpenRouter API Key'));
  console.log(c.dim('  Encontre em: https://openrouter.ai/keys\n'));
  const apiKey = await rawQuestion(c.accent('  › API Key: '), { secret: true });
  console.log();

  // 3. Modelos pagos ou gratuitos
  console.log(c.info.bold('  3/3 · Modelos'));
  console.log(c.dim('  Você tem créditos pagos no OpenRouter?\n'));
  const pago = await confirm(c.accent('  › Usar modelos pagos?'));
  console.log();

  // Seleção do modelo principal
  const lista = pago ? PAID_MODELS : FREE_MODELS;
  const tipoLabel = pago ? c.gold.bold('PAGOS') : c.success.bold('GRATUITOS');
  console.log(`  ${c.info.bold('Modelo principal')} — lista de modelos ${tipoLabel}:`);
  console.log(c.dim('  Use ↑ ↓ para navegar, Enter para confirmar\n'));

  const modeloEscolhido = await selectFromList(lista, {
    title: 'Escolha o modelo para tool-use:',
    displayFn: m => `${m.label.padEnd(36)} ${c.dim('[' + m.ctx + ']')}`,
  });
  console.log(`\n  ${c.success('✔')} Modelo selecionado: ${c.accent.bold(modeloEscolhido.label)}\n`);

  // Modelo de resposta final (pode ser o mesmo ou mais barato)
  console.log(`  ${c.info.bold('Modelo de resposta final')} (pode ser diferente, geralmente mais leve):\n`);
  const modeloFinal = await selectFromList(lista, {
    displayFn: m => `${m.label.padEnd(36)} ${c.dim('[' + m.ctx + ']')}`,
  });
  console.log(`\n  ${c.success('✔')} Modelo final: ${c.accent.bold(modeloFinal.label)}\n`);

  // Construir config base
  const cfg = {
    _user: { nome, setupAt: new Date().toISOString() },
    openrouter: {
      apiKey,
      pago,
      models: {
        tools: [modeloEscolhido.id],
        final: [modeloFinal.id],
      },
    },
    services: [],
  };

  // Adicionar primeiro serviço?
  const adicionarSvc = await confirm(c.accent('  › Deseja configurar um servidor MCP agora?'));
  if (adicionarSvc) {
    const svc = await configurarServico(cfg);
    if (svc) cfg.services.push(svc);
  }

  saveConfig(cfg);

  console.log();
  console.log(boxen(
    `${c.success.bold('✔ Configuração salva!')}  Olá, ${c.accent.bold(nome)}!\n` +
    c.dim(`Arquivo: ${CONFIG_PATH}`),
    { padding: 1, borderStyle: 'round', borderColor: '#3fb950', textAlignment: 'center' }
  ));
  console.log();

  // Pausa breve antes de iniciar
  await new Promise(r => setTimeout(r, 1200));
  return cfg;
}

// ─────────────────────────────────────────────
// CONFIGURADOR DE SERVIÇO MCP
// ─────────────────────────────────────────────

const MCP_TEMPLATES = [
  {
    id: 'n8n',
    label: 'n8n (HTTP — padrão)',
    transport: 'http',
    url: 'http://localhost:5678/mcp',
    token: '',
    name: 'n8n',
    systemPrompt: 'Você tem acesso ao n8n para criar, editar e executar workflows de automação.',
  },
  {
    id: 'openrouter',
    label: 'OpenRouter MCP (HTTP)',
    transport: 'http',
    url: 'https://openrouter.ai/mcp',
    token: '',
    name: 'openrouter',
    systemPrompt: 'Você tem acesso à API do OpenRouter para gerenciar modelos e créditos.',
  },
  {
    id: 'filesystem',
    label: 'Filesystem (stdio — @modelcontextprotocol/server-filesystem)',
    transport: 'stdio',
    command: 'npx',
    args: ['-y', '@modelcontextprotocol/server-filesystem', '/tmp'],
    name: 'filesystem',
    systemPrompt: 'Você tem acesso ao sistema de arquivos local.',
  },
  {
    id: 'custom-stdio',
    label: 'Personalizado — stdio',
    transport: 'stdio',
    command: '',
    args: [],
    name: '',
    systemPrompt: '',
  },
  {
    id: 'custom-http',
    label: 'Personalizado — HTTP',
    transport: 'http',
    url: '',
    token: '',
    name: '',
    systemPrompt: '',
  },
];

async function configurarServico(cfg) {
  console.log();
  console.log(c.info.bold('  ╔═ Configurar Servidor MCP'));
  console.log(c.dim('  Escolha um template ou crie do zero:\n'));

  const template = await selectFromList(MCP_TEMPLATES, {
    displayFn: t => t.label,
  });
  console.log();

  const svc = { ...template };
  delete svc.id;

  // Nome
  const nomeInput = await rawQuestion(c.accent(`  › Nome do serviço [${svc.name || 'meu-servico'}]: `));
  if (nomeInput.trim()) svc.name = nomeInput.trim();
  if (!svc.name) svc.name = 'meu-servico';

  if (svc.transport === 'http') {
    const urlInput = await rawQuestion(c.accent(`  › URL [${svc.url || 'http://localhost:5678/mcp'}]: `));
    if (urlInput.trim()) svc.url = urlInput.trim();
    if (!svc.url) svc.url = 'http://localhost:5678/mcp';

    const tokenInput = await rawQuestion(c.accent('  › Token de autorização (Enter para pular): '));
    if (tokenInput.trim()) svc.token = tokenInput.trim();
    else delete svc.token;

  } else {
    const cmdInput = await rawQuestion(c.accent(`  › Comando [${svc.command || 'node'}]: `));
    if (cmdInput.trim()) svc.command = cmdInput.trim();
    if (!svc.command) svc.command = 'node';

    const argsInput = await rawQuestion(c.accent(`  › Args (separados por espaço) [${(svc.args||[]).join(' ')}]: `));
    if (argsInput.trim()) svc.args = argsInput.trim().split(/\s+/);

    const envInput = await rawQuestion(c.accent('  › Variáveis ENV extras (KEY=VAL,KEY2=VAL2) [Enter pular]: '));
    if (envInput.trim()) {
      svc.env = Object.fromEntries(
        envInput.trim().split(',').map(pair => pair.split('=').map(s => s.trim()))
      );
    }
  }

  // Descrição / systemPrompt — com opção de autocomplete por AI
  console.log();
  console.log(c.dim('  Descrição do sistema (como o AI deve usar este serviço):'));
  console.log(c.dim('  Deixe vazio para gerar automaticamente via AI.\n'));
  const descInput = await rawQuestion(c.accent('  › Descrição: '));

  if (!descInput.trim() && cfg.openrouter?.apiKey) {
    const sp = ora({ text: c.muted('Gerando descrição via AI...'), spinner: 'dots12', color: 'cyan' }).start();
    try {
      const res = await fetch(OPENROUTER_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${cfg.openrouter.apiKey}`,
          'HTTP-Referer': 'http://localhost',
          'X-Title': 'MCP Host CLI Setup',
        },
        body: JSON.stringify({
          model: cfg.openrouter.models?.tools?.[0] || 'meta-llama/llama-3.3-70b-instruct:free',
          max_tokens: 200,
          messages: [{
            role: 'user',
            content: `Gere uma descrição curta (2-3 frases, em Português do Brasil) para um system prompt de assistente AI que usa o seguinte servidor MCP:\n\nNome: ${svc.name}\nTransporte: ${svc.transport}\n${svc.transport==='http' ? 'URL: '+svc.url : 'Comando: '+svc.command+' '+(svc.args||[]).join(' ')}\n\nDescreva o que o assistente pode fazer com este serviço. Responda APENAS com a descrição, sem prefixos.`,
          }],
        }),
      });
      const data = await res.json();
      const generated = data.choices?.[0]?.message?.content?.trim() || '';
      sp.stop();
      if (generated) {
        svc.systemPrompt = generated;
        console.log(c.success('  ✔ Descrição gerada: ') + c.dim(generated));
      }
    } catch {
      sp.stop();
      svc.systemPrompt = `Você tem acesso ao serviço ${svc.name}.`;
    }
  } else {
    svc.systemPrompt = descInput.trim() || `Você tem acesso ao serviço ${svc.name}.`;
  }

  svc.enabled = true;
  console.log(`\n  ${c.success('✔')} Serviço ${c.accent.bold(svc.name)} configurado!\n`);
  return svc;
}

// ─────────────────────────────────────────────
// TELA PRINCIPAL
// ─────────────────────────────────────────────

function printHeader(cfg, connectedCount, totalTools) {
  console.clear();
  const title = figlet.textSync('MCP Universal', { font: 'ANSI shadow' });
  console.log(grad.fire(title));

  const nome = cfg._user?.nome ? c.accent.bold(cfg._user.nome) : c.dim('anônimo');
  const tipo = cfg.openrouter?.pago ? c.gold('●') + c.dim(' PAGO') : c.success('●') + c.dim(' GRATUITO');
  const modelo = cfg.openrouter?.models?.tools?.[0] || '?';

  console.log(boxen(
    `Olá, ${nome}  ${c.dim('·')}  ${tipo}  ${c.dim('·')}  ${c.dim(modelo)}\n` +
    c.dim(`${connectedCount} serviço(s)  ·  ${totalTools} ferramenta(s)  ·  `) + c.purple.bold('OpenRouter'),
    { padding: { top: 0, bottom: 0, left: 2, right: 2 }, borderStyle: 'none', textAlignment: 'center' }
  ));
  console.log(divider('━'));
  console.log();
}

function printServicesStatus(results) {
  for (const [i, { svc, ok, count, error }] of results.entries()) {
    const col      = SERVICE_COLORS[i % SERVICE_COLORS.length];
    const label    = chalk.bold.bgHex('#161b22')(col(` ${svc.name.toUpperCase()} `));
    const type     = (svc.transport || 'http') === 'stdio' ? c.warn('[stdio]') : c.info('[http] ');
    const addr     = svc.transport === 'stdio'
      ? `${svc.command} ${(svc.args||[]).join(' ')}`.substring(0, 50)
      : (svc.url || '');
    if (ok) {
      console.log(`  ${label} ${type}  ${c.success('●')} ${c.muted(addr)}  ${c.dim('·')}  ${col.bold(count)} ferramentas`);
    } else {
      console.log(`  ${label} ${type}  ${c.error('●')} ${c.muted(addr)}  ${c.dim('·')}  ${c.error(error)}`);
    }
  }
  console.log();
}

function printHelp() {
  const commands = [
    ['/',            'Abre menu interativo (comandos, serviços, ferramentas)'],
    ['/servicos',    'Status dos serviços conectados'],
    ['/ferramentas', 'Lista ferramentas por serviço'],
    ['/modelo',      'Trocar modelo ativo'],
    ['/mcp',         'Configurar / adicionar servidor MCP'],
    ['/limpar',      'Limpa histórico da conversa'],
    ['/ajuda',       'Esta ajuda'],
    ['/sair',        'Encerrar'],
  ];
  const lines = commands.map(([cmd, desc]) =>
    `  ${c.accent.bold(cmd.padEnd(16))} ${c.muted(desc)}`
  ).join('\n');
  console.log(boxen(lines, {
    title: c.bright(' Comandos '),
    titleAlignment: 'center',
    padding: { top: 0, bottom: 0, left: 1, right: 1 },
    borderStyle: 'round',
    borderColor: '#6e7681',
    margin: { top: 0, bottom: 1 },
  }));
}

function printToolsByService(serviceMap) {
  for (const [i, [serviceName, tools]] of [...serviceMap.entries()].entries()) {
    const col = SERVICE_COLORS[i % SERVICE_COLORS.length];
    const table = new Table({
      head: [c.dim('#'), col.bold('Ferramenta'), c.muted('Descrição')],
      colWidths: [5, 34, 36],
      wordWrap: true,
      style: { border: ['dim'], 'padding-left': 1, 'padding-right': 1 },
      chars: { 'top':'─','top-mid':'┬','top-left':'╭','top-right':'╮','bottom':'─','bottom-mid':'┴','bottom-left':'╰','bottom-right':'╯','left':'│','left-mid':'├','mid':'─','mid-mid':'┼','right':'│','right-mid':'┤','middle':'│' },
    });
    tools.forEach((t, idx) => {
      table.push([c.dim(String(idx + 1)), col(t.name), c.muted((t.description || '').substring(0, 60))]);
    });
    console.log(col.bold(`  ╔═ ${serviceName.toUpperCase()} `) + col.dim('═'.repeat(Math.max(0, 60 - serviceName.length)) + '╗'));
    table.toString().split('\n').forEach(l => console.log('  ' + l));
    console.log(col.dim('  ╚' + '═'.repeat(68) + '╝'));
    console.log();
  }
}

// ─────────────────────────────────────────────
// MENU "/" — DROPDOWN INTERATIVO
// ─────────────────────────────────────────────

async function openSlashMenu(ctx) {
  const { serviceMap, toolClientMap, cfg, messages, connectionResults, openaiTools } = ctx;

  const TOP_ITEMS = [
    { id: 'ferramentas',  label: '⚒  Ver ferramentas por serviço' },
    { id: 'servicos',     label: '⚡ Status dos serviços' },
    { id: 'modelo',       label: '🤖 Trocar modelo ativo' },
    { id: 'mcp-add',      label: '＋ Adicionar servidor MCP' },
    { id: 'mcp-list',     label: '☰  Gerenciar servidores MCP' },
    { id: 'limpar',       label: '✕  Limpar histórico' },
    { id: 'ajuda',        label: '?  Ajuda' },
    { id: 'sair',         label: '⏻  Sair' },
  ];

  console.log(`\n${c.dim('┌─ Menu /')} ${c.dim('(↑↓ navegar · Enter selecionar · Ctrl+C cancelar)')}\n`);
  const chosen = await selectFromList(TOP_ITEMS, { displayFn: x => x.label });
  console.log();

  switch (chosen.id) {
    case 'ferramentas':
      printToolsByService(serviceMap);
      break;

    case 'servicos':
      printServicesStatus(connectionResults);
      break;

    case 'modelo':
      await trocaModelo(cfg);
      break;

    case 'mcp-add': {
      const svc = await configurarServico(cfg);
      if (svc) {
        cfg.services.push(svc);
        saveConfig(cfg);
        console.log(c.success('✔ Serviço salvo em config.json. Reinicie para conectar.\n'));
      }
      break;
    }

    case 'mcp-list':
      await gerenciarServicos(cfg, serviceMap, toolClientMap);
      break;

    case 'limpar':
      messages.length = 1;
      console.log(c.success('✔ Histórico limpo.\n'));
      break;

    case 'ajuda':
      printHelp();
      break;

    case 'sair':
      return 'exit';
  }

  return null;
}

// ─────────────────────────────────────────────
// TROCAR MODELO
// ─────────────────────────────────────────────

async function trocaModelo(cfg) {
  const pago = cfg.openrouter?.pago;
  const lista = pago ? PAID_MODELS : FREE_MODELS;
  const tipo = pago ? c.gold.bold('PAGOS') : c.success.bold('GRATUITOS');

  console.log(`  ${c.info.bold('Trocar modelo de tool-use')} — modelos ${tipo}:\n`);
  const toolModel = await selectFromList(lista, {
    displayFn: m => `${m.label.padEnd(36)} ${c.dim('[' + m.ctx + ']')}`,
  });
  console.log();

  console.log(`  ${c.info.bold('Modelo de resposta final')}:\n`);
  const finalModel = await selectFromList(lista, {
    displayFn: m => `${m.label.padEnd(36)} ${c.dim('[' + m.ctx + ']')}`,
  });

  cfg.openrouter.models.tools = [toolModel.id];
  cfg.openrouter.models.final = [finalModel.id];
  saveConfig(cfg);

  console.log(`\n  ${c.success('✔')} Modelos atualizados:`);
  console.log(`    Tool-use: ${c.accent.bold(toolModel.label)}`);
  console.log(`    Final:    ${c.accent.bold(finalModel.label)}\n`);
}

// ─────────────────────────────────────────────
// GERENCIAR SERVIÇOS (listar, editar, remover)
// ─────────────────────────────────────────────

async function gerenciarServicos(cfg, serviceMap, toolClientMap) {
  const svcs = cfg.services || [];
  if (svcs.length === 0) {
    console.log(c.warn('  Nenhum serviço configurado.\n'));
    return;
  }

  const opcoes = [
    ...svcs.map((s, i) => ({
      id: 'svc-' + i,
      label: `${s.enabled !== false ? c.success('●') : c.error('●')}  ${s.name}  ${c.dim('[' + (s.transport || 'http') + ']')}`,
      svc: s, idx: i,
    })),
    { id: 'back', label: c.dim('← Voltar') },
  ];

  const escolhido = await selectFromList(opcoes, { displayFn: x => x.label });
  if (escolhido.id === 'back') return;

  const svc = escolhido.svc;
  const ativado = svc.enabled !== false;

  const acoes = [
    { id: 'toggle', label: ativado ? '⊙ Desativar serviço' : '⊙ Ativar serviço' },
    { id: 'remove', label: c.error('✕ Remover serviço') },
    { id: 'back',   label: c.dim('← Cancelar') },
  ];

  console.log(`\n  ${c.accent.bold(svc.name)} — ${c.dim(svc.transport || 'http')}\n`);
  const acao = await selectFromList(acoes, { displayFn: x => x.label });
  console.log();

  if (acao.id === 'toggle') {
    svc.enabled = !ativado;
    saveConfig(cfg);
    console.log(c.success(`✔ Serviço ${svc.name} ${svc.enabled ? 'ativado' : 'desativado'}. Reinicie para aplicar.\n`));
  } else if (acao.id === 'remove') {
    cfg.services.splice(escolhido.idx, 1);
    saveConfig(cfg);
    console.log(c.success(`✔ Serviço ${svc.name} removido.\n`));
  }
}

// ─────────────────────────────────────────────
// AUTOCOMPLETE de "/" na linha de input
// ─────────────────────────────────────────────

function inputWithSlashComplete(promptStr, ctx) {
  return new Promise(resolve => {
    let buf = '';
    let inMenu = false;

    const SLASH_COMMANDS = [
      '/ferramentas', '/servicos', '/modelo', '/mcp', '/limpar', '/ajuda', '/sair'
    ];

    const render = () => {
      process.stdout.write('\r\x1b[2K');
      process.stdout.write(promptStr + buf);
    };

    process.stdout.write(promptStr);

    const onKey = async (chunk) => {
      if (inMenu) return;
      const code = chunk[0];
      const seq  = chunk.toString();

      if (code === 13 || code === 10) {
        process.stdout.write('\n');
        cleanup();
        resolve(buf);
        return;
      } else if (code === 3) {
        cleanup();
        process.exit(0);
      } else if (code === 127 || code === 8) {
        if (buf.length > 0) {
          buf = buf.slice(0, -1);
          render();
        }
      } else if (seq === '\x1b[A' || seq === '\x1b[B') {
        // Ignore arrows during typing
      } else if (code >= 32) {
        buf += seq;
        process.stdout.write(seq);

        // Se digitou "/" no início, abrir dropdown de autocomplete
        if (buf === '/') {
          inMenu = true;
          process.stdout.write('\n');
          cleanup();
          const result = await openSlashMenu(ctx);
          resolve(result === 'exit' ? '/sair' : '__menu__');
        }
      }
    };

    const cleanup = () => {
      process.stdin.removeListener('data', onKey);
      if (process.stdin.isTTY) process.stdin.setRawMode(false);
      process.stdin.pause();
    };

    if (process.stdin.isTTY) process.stdin.setRawMode(true);
    process.stdin.resume();
    process.stdin.on('data', onKey);
  });
}

// ─────────────────────────────────────────────
// MODELO — LÓGICA DE CHAMADA
// ─────────────────────────────────────────────

function extraiCodigoJs(texto) {
  const m = texto.match(/```(?:javascript|js)?\s*([\s\S]+?)```/);
  if (m) return m[1].trim();
  if (texto.includes('export default')) return texto.substring(texto.indexOf('export default')).trim();
  return null;
}

function modeloRetornouTextoDeTool(content) {
  if (!content) return false;
  return ['<tool_call>', '<function=', '```tool_call', '"function":', 'tool_use'].some(s => content.includes(s));
}

async function chamarModelo(cfg, messages, tools, usarTools, listaModelos, spinner) {
  for (const modelo of listaModelos) {
    for (let tentativa = 0; tentativa < 3; tentativa++) {
      try {
        const body = { model: modelo, messages, max_tokens: 8192, temperature: 0.1 };
        if (usarTools && tools) { body.tools = tools; body.tool_choice = 'auto'; }

        const res = await fetch(OPENROUTER_URL, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${cfg.openrouter.apiKey}`,
            'HTTP-Referer': 'http://localhost',
            'X-Title': 'MCP Host CLI',
          },
          body: JSON.stringify(body),
        });

        if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
        const data    = await res.json();
        const msg     = data.choices[0].message;
        const content = msg.content || '';

        if (usarTools && tools && !msg.tool_calls) {
          if (modeloRetornouTextoDeTool(content) || extraiCodigoJs(content)) {
            if (spinner) spinner.warn(c.warn(`Modelo '${chalk.bold(modelo)}' retornou texto — próximo...`));
            break;
          }
        }

        printModel(modelo);
        return data;
      } catch (e) {
        const err = e.toString();
        if (err.includes('429')) {
          const wait = 10 * (tentativa + 1);
          if (spinner) spinner.text = c.warn(`Rate limit '${modelo}', aguardando ${wait}s...`);
          await new Promise(r => setTimeout(r, wait * 1000));
          continue;
        }
        if (spinner) spinner.warn(c.muted(`Modelo '${modelo}' falhou — próximo...`));
        break;
      }
    }
  }
  throw new Error('Todos os modelos falharam. Tente novamente em instantes.');
}

// ─────────────────────────────────────────────
// PRINT HELPERS
// ─────────────────────────────────────────────

function printUserMessage(text) {
  const prefix = chalk.bgHex('#e36b2f').hex('#0d1117').bold(' VOCÊ ');
  console.log(`\n${prefix} ${timestamp()}`);
  console.log(`${c.dim('│')} ${c.bright(text)}`);
  console.log();
}

function printAssistantStart() {
  const prefix = chalk.bgHex('#58a6ff').hex('#0d1117').bold(' ASSISTENTE ');
  console.log(`${prefix} ${timestamp()}`);
}

function printAssistantText(text) {
  for (const line of text.split('\n')) {
    if      (line.startsWith('### ')) console.log(`${c.dim('│')} ${c.accent.bold(line.slice(4))}`);
    else if (line.startsWith('## '))  console.log(`${c.dim('│')}\n${c.dim('│')} ${c.bright.bold(line.slice(3))}`);
    else if (line.startsWith('# '))   console.log(`${c.dim('│')}\n${c.dim('│')} ${grad.cool(line.slice(2))}`);
    else if (/^[-*] /.test(line))     console.log(`${c.dim('│')}  ${c.primary('◆')} ${c.bright(line.replace(/^[-*] /,''))}`);
    else if (/^\d+\. /.test(line)) {
      const m = line.match(/^(\d+)\. (.*)/);
      if (m) console.log(`${c.dim('│')}  ${c.accent.bold(m[1]+'.')} ${c.bright(m[2])}`);
    }
    else if (line.startsWith('```')) console.log(`${c.dim('│')} ${c.dim(line)}`);
    else if (line.trim() === '')     console.log(c.dim('│'));
    else {
      const fmt = line
        .replace(/\*\*(.+?)\*\*/g, (_, m) => c.bright.bold(m))
        .replace(/`(.+?)`/g,       (_, m) => chalk.bgHex('#161b22').hex('#e2b97e')(` ${m} `));
      console.log(`${c.dim('│')} ${fmt}`);
    }
  }
  console.log();
}

function printToolCall(toolName, serviceName, args, serviceIndex) {
  const col = SERVICE_COLORS[serviceIndex % SERVICE_COLORS.length];
  const argsPreview = JSON.stringify(args, null, 0).substring(0, 100);
  console.log(
    `${c.dim('│')} ${badge('TOOL', c.purple)} ${col(`[${serviceName}]`)} ${c.purple.bold(toolName)} ` +
    `${c.dim('→')} ${c.dim(argsPreview)}${argsPreview.length >= 100 ? c.dim('…') : ''}`
  );
}

function printToolResult(text, isError = false) {
  const preview = text.substring(0, 220);
  const icon  = isError ? c.error('✗') : c.teal('✓');
  const color = isError ? c.error : c.dim;
  console.log(`${c.dim('│')} ${icon} ${color(preview)}${text.length > 220 ? c.dim('…') : ''}`);
}

function printSuccess(msg) { console.log(`${c.dim('│')} ${c.success('✔')} ${c.success.bold(msg)}`); }
function printWarning(msg) { console.log(`${c.dim('│')} ${c.warn('⚠')}  ${c.warn(msg)}`); }
function printModel(name)  { console.log(`${c.dim('│')} ${badge('MODEL', c.dim)} ${c.dim(name)}`); }

function printError(msg) {
  console.log(boxen(
    `${c.error('✗')} ${c.bright.bold(msg)}`,
    { padding: { top:0, bottom:0, left:1, right:1 }, borderStyle:'round', borderColor:'#f85149' }
  ));
}

function printPromptStr() {
  return `\n${c.primary.bold('›')} ${c.bright('Você: ')}`;
}

// ─────────────────────────────────────────────
// CICLO COMPLETO DE INFERÊNCIA
// ─────────────────────────────────────────────

async function cicloCompleto(cfg, toolClientMap, messages, openaiTools) {
  const spinner = ora({ text: c.muted('Consultando modelo...'), spinner: 'dots12', color: 'yellow' }).start();
  printAssistantStart();

  const firstClient = toolClientMap.values().next().value?.client;

  while (true) {
    spinner.text = c.muted('Consultando modelo...');
    const response = await chamarModelo(cfg, messages, openaiTools, true, cfg.openrouter.models.tools, spinner);
    const msg      = response.choices[0].message;
    const content  = msg.content || '';
    const msgDict  = { role: 'assistant', content };

    if (msg.tool_calls) {
      msgDict.tool_calls = msg.tool_calls.map(tc => ({
        id: tc.id, type: 'function',
        function: { name: tc.function.name, arguments: tc.function.arguments },
      }));
      messages.push(msgDict);

      for (const toolCall of msg.tool_calls) {
        const toolName = toolCall.function.name;
        let toolArgs;
        try   { toolArgs = JSON.parse(toolCall.function.arguments); }
        catch { printError('JSON inválido nos argumentos da ferramenta.'); continue; }

        const entry = toolClientMap.get(toolName);
        if (!entry) {
          spinner.stop();
          printError(`Ferramenta desconhecida: ${toolName}`);
          messages.push({ role: 'tool', tool_call_id: toolCall.id, content: `Erro: ferramenta '${toolName}' não encontrada.` });
          spinner.start(c.muted('Continuando...'));
          continue;
        }

        spinner.stop();
        printToolCall(toolName, entry.serviceName, toolArgs, entry.serviceIndex);
        spinner.start(c.muted(`Executando ${toolName}...`));

        try {
          const result     = await entry.client.callTool({ name: toolName, arguments: toolArgs });
          const resultText = result.content.filter(b => b.type === 'text').map(b => b.text).join('\n');
          spinner.stop();
          printToolResult(resultText);
          spinner.start(c.muted('Processando resultado...'));
          messages.push({ role: 'tool', tool_call_id: toolCall.id, content: resultText });
        } catch (e) {
          spinner.stop();
          printToolResult(`Erro: ${e.message}`, true);
          spinner.start(c.muted('Continuando...'));
          messages.push({ role: 'tool', tool_call_id: toolCall.id, content: `Erro: ${e.message}` });
        }
      }
      continue;

    } else {
      const codigo = extraiCodigoJs(content);
      if (codigo && firstClient) {
        spinner.stop();
        printWarning('Código detectado como texto — executando automaticamente...');
        spinner.start(c.muted('Executando create_workflow_from_code...'));
        try {
          const result     = await firstClient.callTool({ name: 'create_workflow_from_code', arguments: { workflowCode: codigo } });
          const resultText = result.content.filter(b => b.type === 'text').map(b => b.text).join('\n');
          spinner.stop();
          printSuccess('Workflow criado via extração automática!');
          printToolResult(resultText);
          messages.push({ role: 'assistant', content });
          messages.push({ role: 'tool', tool_call_id: 'auto-extract', content: `Código executado automaticamente.\n${resultText}` });
          spinner.start(c.muted('Gerando resposta final...'));
          const finalResp = await chamarModelo(cfg, messages, null, false, cfg.openrouter.models.final, spinner);
          const finalText = finalResp.choices[0].message.content || '';
          spinner.stop();
          printAssistantText(finalText);
          messages.push({ role: 'assistant', content: finalText });
          return;
        } catch (e) {
          spinner.stop();
          printError(`Erro ao executar código extraído: ${e.message}`);
          messages.push({ role: 'assistant', content });
          return;
        }
      } else {
        spinner.stop();
        printAssistantText(content);
        messages.push({ role: 'assistant', content });
        return;
      }
    }
  }
}

// ─────────────────────────────────────────────
// MAIN
// ─────────────────────────────────────────────

async function main() {
  let cfg = loadConfig();

  // Primeiro setup
  if (!cfg || !cfg.openrouter?.apiKey) {
    cfg = await runOnboarding();
  }

  // Validar e filtrar serviços ativos
  const svcsAtivos = (cfg.services || []).filter(s => s.enabled !== false);

  // ── Conectar serviços ──
  const spinnerConn = ora({ text: c.muted('Conectando aos serviços...'), spinner: 'dots12', color: 'cyan' }).start();

  const connectionResults = [];
  const serviceMap        = new Map();
  const toolClientMap     = new Map();
  const systemPrompts     = [];
  const openaiTools       = [];

  for (const [i, svc] of svcsAtivos.entries()) {
    const transportType = svc.transport || 'http';
    spinnerConn.text = c.muted(`Conectando a ${svc.name} (${transportType})...`);
    try {
      let transport;
      if (transportType === 'stdio') {
        transport = new StdioClientTransport({
          command: svc.command,
          args:    svc.args || [],
          env:     { ...process.env, ...(svc.env || {}) },
        });
      } else {
        const headers = {};
        if (svc.token) headers['Authorization'] = `Bearer ${svc.token}`;
        transport = new StreamableHTTPClientTransport(new URL(svc.url), { requestInit: { headers } });
      }

      const client = new Client({ name: 'mcp-host-cli', version: '4.0.0' }, { capabilities: { tools: {} } });
      await client.connect(transport);
      const { tools } = await client.listTools();

      serviceMap.set(svc.name, tools);
      for (const t of tools) {
        toolClientMap.set(t.name, { client, serviceName: svc.name, serviceIndex: i });
        openaiTools.push({
          type: 'function',
          function: {
            name: t.name,
            description: `[${svc.name}] ${t.description || ''}`,
            parameters: t.inputSchema || { type: 'object' },
          },
        });
      }

      if (svc.systemPrompt) systemPrompts.push(`=== SERVICO: ${svc.name.toUpperCase()} ===\n${svc.systemPrompt}`);
      connectionResults.push({ svc, ok: true, count: tools.length });
    } catch (e) {
      connectionResults.push({ svc, ok: false, count: 0, error: e.message.substring(0, 60) });
    }
  }

  spinnerConn.stop();

  const totalTools    = openaiTools.length;
  const connectedSvcs = connectionResults.filter(r => r.ok).length;

  printHeader(cfg, connectedSvcs, totalTools);

  if (svcsAtivos.length > 0) printServicesStatus(connectionResults);
  if (connectedSvcs === 0 && svcsAtivos.length > 0) {
    console.log(c.warn('  ⚠ Nenhum serviço conectado com sucesso. Chat sem ferramentas MCP.\n'));
  }
  if (svcsAtivos.length === 0) {
    console.log(c.dim('  Nenhum serviço MCP configurado. Use / → Adicionar servidor MCP.\n'));
  }

  printHelp();
  console.log(divider('─'));
  console.log(c.dim('  Dica: Digite / para abrir o menu interativo com dropdown.\n'));
  console.log(divider('─'));
  console.log();

  const basePrompt = [
    `Você é um assistente multi-serviço com acesso a ferramentas MCP.`,
    cfg._user?.nome ? `Você está conversando com ${cfg._user.nome}.` : '',
    `\nREGRAS GERAIS:`,
    `- Use SEMPRE as ferramentas reais — nunca escreva chamadas de ferramenta como texto`,
    `- Cada ferramenta pertence a um serviço específico indicado em seu prefixo [serviço]`,
    `- Responda em Português do Brasil`,
    systemPrompts.length ? `\n${systemPrompts.join('\n\n')}` : '',
  ].filter(Boolean).join('\n');

  const messages = [{ role: 'system', content: basePrompt }];

  // Contexto passado para o menu
  const ctx = { serviceMap, toolClientMap, cfg, messages, connectionResults, openaiTools };

  // ── Loop principal ──
  while (true) {
    const input = await inputWithSlashComplete(printPromptStr(), ctx);

    if (input === '__menu__') continue;

    const trimmed = input.trim();
    if (!trimmed) continue;

    const lower = trimmed.toLowerCase();

    // Comandos diretos sem menu
    if (['/sair', '/exit', '/quit', 'sair', 'exit', 'quit'].includes(lower)) {
      console.log();
      console.log(boxen(
        `${c.primary.bold('Até logo!')}  ${cfg._user?.nome ? c.accent.bold(cfg._user.nome) + '  ' : ''}${c.muted('Sessão encerrada.')}\n` +
        c.dim(`Mensagens: ${Math.floor((messages.length - 1) / 2)}  ·  Serviços: ${connectedSvcs}  ·  Ferramentas: ${totalTools}`),
        { padding: 1, borderStyle: 'round', borderColor: '#e36b2f', textAlignment: 'center' }
      ));
      break;
    }

    if (['/ferramentas', '/tools'].includes(lower)) { printToolsByService(serviceMap); continue; }
    if (['/servicos', '/services', '/status'].includes(lower)) { printServicesStatus(connectionResults); continue; }
    if (['/modelo', '/model'].includes(lower)) { await trocaModelo(cfg); continue; }
    if (['/limpar', '/clear', '/reset'].includes(lower)) { messages.length = 1; console.log(c.success('✔ Histórico limpo.\n')); continue; }
    if (['/ajuda', '/help'].includes(lower)) { printHelp(); continue; }

    if (['/mcp'].includes(lower)) {
      const svc = await configurarServico(cfg);
      if (svc) {
        cfg.services.push(svc);
        saveConfig(cfg);
        console.log(c.success('✔ Serviço salvo. Reinicie para conectar.\n'));
      }
      continue;
    }

    printUserMessage(trimmed);
    messages.push({ role: 'user', content: trimmed });

    try {
      await cicloCompleto(cfg, toolClientMap, messages, openaiTools);
    } catch (e) {
      printError(e.message);
      messages.pop();
    }
  }
}

main().catch(e => {
  console.error(chalk.red(`\n✗ Erro fatal: ${e.message}\n`));
  process.exit(1);
});