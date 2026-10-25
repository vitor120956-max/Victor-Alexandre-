#!/usr/bin/env node
/**
 * Verifica se esta máquina e esta pasta estão prontas para rodar o JARVIS
 * — inclusive de um pendrive.
 *
 * Roda só com Node: é o único requisito que o script não consegue instalar
 * sozinho. Por isso ele funciona antes de existir `.venv` ou `node_modules`,
 * que é exatamente quando a dúvida aparece.
 *
 * Uso:
 *   node scripts/checar-pendrive.mjs
 *   node scripts/checar-pendrive.mjs --json
 *
 * Código de saída: 0 quando não falta nada obrigatório, 1 quando falta.
 */
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, statfsSync, accessSync, constants as fsConstants, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { createConnection } from 'node:net';
import { platform, release } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// `import.meta.dirname` só existe a partir do Node 20.11; o URL funciona em qualquer versão.
const RAIZ = fileURLToPath(new URL('..', import.meta.url));
const JSON_SAIDA = process.argv.includes('--json');
const VERDE = '\u001b[32m';
const AMARELO = '\u001b[33m';
const VERMELHO = '\u001b[31m';
const CINZA = '\u001b[90m';
const ZERAR = '\u001b[0m';

/** @type {{id: string, titulo: string, estado: 'ok'|'aviso'|'falha', detalhe: string, conserto: string}[]} */
const itens = [];

function registrar(id, titulo, estado, detalhe, conserto = '') {
  itens.push({ id, titulo, estado, detalhe, conserto });
}

function simbolo(estado) {
  if (estado === 'ok') return `${VERDE}OK${ZERAR}`;
  if (estado === 'aviso') return `${AMARELO}ATENÇÃO${ZERAR}`;
  return `${VERMELHO}FALTA${ZERAR}`;
}

function rodar(binario, argumentos, opcoes = {}) {
  return execFileSync(binario, argumentos, { encoding: 'utf-8', timeout: 15_000, stdio: ['ignore', 'pipe', 'pipe'], ...opcoes }).trim();
}

function versaoEmNumeros(texto) {
  const achado = texto.match(/(\d+)\.(\d+)(?:\.(\d+))?/);
  if (!achado) return null;
  return [Number(achado[1]), Number(achado[2]), Number(achado[3] || 0)];
}

function comparar(a, b) {
  for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
    const x = a[i] || 0;
    const y = b[i] || 0;
    if (x !== y) return x - y;
  }
  return 0;
}

// --------------------------------------------------------------------------
// 1. Node
// --------------------------------------------------------------------------
{
  const atual = versaoEmNumeros(process.version);
  const minimo = [22, 0, 0];
  if (atual && comparar(atual, minimo) >= 0) {
    registrar('node', 'Node.js', 'ok', `${process.version} (mínimo v22)`);
  } else {
    registrar('node', 'Node.js', 'falha', `${process.version} — abaixo do mínimo v22`, 'Instale a versão LTS em https://nodejs.org e reabra o terminal.');
  }
}

// --------------------------------------------------------------------------
// 2. Python e dependências
// --------------------------------------------------------------------------
function candidatosPython() {
  const lista = [];
  if (process.env.PYTHON) lista.push({ binario: process.env.PYTHON, argumentos: [] });
  if (platform() === 'win32') {
    lista.push({ binario: join(RAIZ, '.venv', 'Scripts', 'python.exe'), argumentos: [] });
    lista.push({ binario: 'py', argumentos: ['-3'] });
    lista.push({ binario: 'python', argumentos: [] });
  } else {
    lista.push({ binario: join(RAIZ, '.venv', 'bin', 'python'), argumentos: [] });
    lista.push({ binario: 'python3', argumentos: [] });
    lista.push({ binario: 'python', argumentos: [] });
  }
  return lista;
}

let pythonEscolhido = null;
{
  const tentativas = [];
  for (const candidato of candidatosPython()) {
    if (candidato.binario.includes('/') || candidato.binario.includes('\\')) {
      if (!existsSync(candidato.binario)) {
        tentativas.push(`${candidato.binario}: não existe`);
        continue;
      }
    }
    try {
      const saida = rodar(candidato.binario, [...candidato.argumentos, '--version']);
      const numeros = versaoEmNumeros(saida);
      if (!numeros) {
        tentativas.push(`${candidato.binario}: versão ilegível`);
        continue;
      }
      if (comparar(numeros, [3, 11, 0]) < 0) {
        tentativas.push(`${saida} (abaixo de 3.11)`);
        continue;
      }
      pythonEscolhido = { ...candidato, versao: saida, numeros };
      break;
    } catch (erro) {
      tentativas.push(`${candidato.binario}: ${erro.code || 'erro'}`);
    }
  }

  if (pythonEscolhido) {
    const viaVenv = pythonEscolhido.binario.includes('.venv');
    registrar(
      'python',
      'Python',
      'ok',
      `${pythonEscolhido.versao}${viaVenv ? ' (do .venv do projeto)' : ` (${pythonEscolhido.binario} do sistema)`}`,
    );
    if (!viaVenv) {
      registrar('venv', 'Ambiente .venv', 'aviso', 'não existe nesta pasta; o launcher usa o Python do sistema', 'Para isolar: python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt');
    }
  } else {
    registrar(
      'python',
      'Python',
      'falha',
      `não encontrei Python 3.11+: ${tentativas.join(' · ') || 'nenhum candidato'}`,
      'Instale em https://www.python.org/downloads/ (no Windows marque “Add python.exe to PATH”) ou use o gerenciador do sistema.',
    );
  }
}

{
  if (!pythonEscolhido) {
    registrar('deps-python', 'Bibliotecas Python', 'falha', 'não há Python para conferir', 'Resolva o item Python primeiro.');
  } else {
    try {
      const saida = rodar(pythonEscolhido.binario, [
        ...pythonEscolhido.argumentos,
        '-c',
        'import fastapi, pydantic, httpx, dotenv; print(fastapi.__version__, pydantic.VERSION)',
      ]);
      registrar('deps-python', 'Bibliotecas Python', 'ok', `fastapi ${saida.split(' ')[0]} · pydantic ${saida.split(' ')[1]}`);
    } catch {
      registrar(
        'deps-python',
        'Bibliotecas Python',
        'falha',
        'fastapi/pydantic/httpx/python-dotenv não importam',
        'Rode: python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt',
      );
    }
  }
}

// --------------------------------------------------------------------------
// 3. Dependências do Node
// --------------------------------------------------------------------------
{
  const vite = join(RAIZ, 'node_modules', 'vite');
  if (existsSync(vite)) {
    registrar('deps-node', 'Bibliotecas do Node', 'ok', 'node_modules presente (vite instalado)');
  } else {
    registrar('deps-node', 'Bibliotecas do Node', 'falha', 'node_modules ausente ou incompleto', 'Rode: npm install');
  }
}

// --------------------------------------------------------------------------
// 4. .env e chave de IA
// --------------------------------------------------------------------------
{
  const caminhoEnv = join(RAIZ, '.env');
  if (!existsSync(caminhoEnv)) {
    registrar('env', 'Arquivo .env', 'falha', 'não existe', 'Copie o exemplo: cp .env.example .env (Windows: copy .env.example .env)');
  } else {
    registrar('env', 'Arquivo .env', 'ok', 'presente');
    const texto = readFileSync(caminhoEnv, 'utf-8');
    const ler = (chave) => {
      const linha = texto.split(/\r?\n/).find((item) => item.trim().startsWith(`${chave}=`));
      return linha ? linha.slice(linha.indexOf('=') + 1).trim() : '';
    };
    const apiKey = ler('JARVIS_AI_API_KEY');
    const base = ler('JARVIS_AI_BASE_URL');
    const modelo = ler('JARVIS_AI_MODEL');
    if (apiKey) {
      const mascarada = `${apiKey.slice(0, 4)}…${apiKey.slice(-4)}`;
      registrar('chave', 'Chave de IA', 'ok', `preenchida (${mascarada}, ${apiKey.length} caracteres)`);
    } else {
      registrar('chave', 'Chave de IA', 'aviso', 'vazia — as 8 skills de perfil sem modelo funcionam; distilar.persona e o chat externo não', 'Cole o valor em JARVIS_AI_API_KEY e reinicie a API.');
    }
    if (base && modelo) {
      registrar('modelo', 'Endpoint e modelo', 'ok', `${base} · ${modelo}`);
    } else {
      registrar('modelo', 'Endpoint e modelo', 'aviso', 'BASE_URL ou MODEL vazios — valem os padrões do código', 'Confira JARVIS_AI_BASE_URL e JARVIS_AI_MODEL no .env.');
    }
  }
}

// --------------------------------------------------------------------------
// 5. storage: existe, aceita escrita e cabe
// --------------------------------------------------------------------------
{
  const storage = join(RAIZ, 'storage');
  try {
    mkdirSync(storage, { recursive: true });
    const teste = join(storage, '.checagem-escrita');
    writeFileSync(teste, 'ok');
    rmSync(teste);
    accessSync(storage, fsConstants.W_OK);
    registrar('storage', 'Pasta storage', 'ok', storage);
  } catch (erro) {
    registrar('storage', 'Pasta storage', 'falha', `não aceita escrita (${erro.code || erro.message})`, 'Confira permissão e se o drive não está somente leitura (proteção contra gravação ligada).');
  }
}

// --------------------------------------------------------------------------
// 6. Sistema de arquivos e espaço (o detalhe que quebra pendrive)
// --------------------------------------------------------------------------
const TIPOS = new Map([
  [0xef53, { nome: 'ext2/3/4', nota: 'ok' }],
  [0x9123683e, { nome: 'btrfs', nota: 'ok' }],
  [0x58465342, { nome: 'XFS', nota: 'ok' }],
  [0x2fc12fc1, { nome: 'ZFS', nota: 'ok' }],
  [0xf2f52010, { nome: 'F2FS', nota: 'ok' }],
  [0x5346544e, { nome: 'NTFS', nota: 'ok' }],
  [0x2011bab0, { nome: 'exFAT', nota: 'aviso' }],
  [0x4d44, { nome: 'FAT (FAT32)', nota: 'aviso' }],
  [0x01021994, { nome: 'tmpfs', nota: 'aviso' }],
  [0x794c7630, { nome: 'overlayfs (contêiner)', nota: 'aviso' }],
]);

{
  try {
    const info = statfsSync(RAIZ);
    const livre = Number(info.bavail) * Number(info.bsize);
    const total = Number(info.blocks) * Number(info.bsize);
    const gb = (valor) => `${(valor / 1024 ** 3).toFixed(2)} GB`;
    const tipo = TIPOS.get(Number(info.type));
    const obrigatorio = 1024 ** 3; // 1 GB
    if (livre < obrigatorio) {
      registrar('espaco', 'Espaço livre', 'falha', `${gb(livre)} livres de ${gb(total)} — abaixo de 1 GB`, 'Libere espaço ou use outro drive.');
    } else {
      registrar('espaco', 'Espaço livre', 'ok', `${gb(livre)} livres de ${gb(total)}`);
    }
    if (tipo) {
      if (tipo.nota === 'ok') {
        registrar('fs', 'Sistema de arquivos', 'ok', `${tipo.nome} — guarda permissão e link simbólico`);
      } else if (tipo.nome.startsWith('overlay') || tipo.nome === 'tmpfs') {
        registrar('fs', 'Sistema de arquivos', 'aviso', `${tipo.nome} — dados não persistem fora do contêiner`, 'Para uso real, rode numa pasta do seu disco ou do pendrive.');
      } else {
        registrar(
          'fs',
          'Sistema de arquivos',
          'aviso',
          `${tipo.nome} — não guarda permissão POSIX${tipo.nome === 'exFAT' ? '' : ' e limita arquivo a 4 GB'}`,
          tipo.nome === 'exFAT'
            ? 'No Windows, NTFS funciona melhor; no Linux, ext4. exFAT serve para código e documentos, mas `chmod +x` falha.'
            : 'Formate em NTFS (Windows) ou ext4 (Linux). FAT32 não guarda arquivo acima de 4 GB.',
        );
      }
    } else {
      registrar('fs', 'Sistema de arquivos', 'ok', `tipo não identificado (${Number(info.type)}) — assume-se compatível`);
    }
  } catch (erro) {
    registrar('espaco', 'Espaço livre', 'aviso', `não consegui medir (${erro.code || erro.message})`);
  }
}

// --------------------------------------------------------------------------
// 7. Git (só a camada de evolução precisa)
// --------------------------------------------------------------------------
{
  let gitOk = false;
  try {
    const versao = rodar('git', ['--version']);
    gitOk = true;
    const temRepo = existsSync(join(RAIZ, '.git'));
    if (temRepo) {
      registrar('git', 'Git', 'ok', `${versao.split(' ').slice(2).join(' ')} · repositório presente (evoluir.promover disponível)`);
    } else {
      registrar('git', 'Git', 'aviso', `${versao.split(' ').slice(2).join(' ')} · sem .git nesta pasta`, 'A camada `evoluir.*` exige repositório. Clone com git em vez de copiar a pasta.');
    }
  } catch {
    registrar('git', 'Git', 'aviso', 'não encontrado', gitOk ? '' : 'Opcional: só a camada de evolução precisa. Instale em https://git-scm.com');
  }
}

// --------------------------------------------------------------------------
// 8. Portas 8000 e 5173
// --------------------------------------------------------------------------
async function portaOcupada(porta) {
  return new Promise((resolver) => {
    const socket = createConnection({ host: '127.0.0.1', port: porta });
    const fim = (valor) => {
      socket.destroy();
      resolver(valor);
    };
    socket.setTimeout(1_000);
    socket.once('connect', () => fim(true));
    socket.once('timeout', () => fim(false));
    socket.once('error', () => fim(false));
  });
}

{
  const ocupadas = [];
  for (const porta of [8000, 5173]) {
    if (await portaOcupada(porta)) ocupadas.push(porta);
  }
  if (ocupadas.length === 0) {
    registrar('portas', 'Portas 8000 e 5173', 'ok', 'livres');
  } else {
    registrar(
      'portas',
      'Portas 8000 e 5173',
      'aviso',
      `ocupadas: ${ocupadas.join(', ')} — pode ser o JARVIS já rodando`,
      'Se não for o JARVIS, encerre o processo ou mude a porta em `npm run dev`.',
    );
  }
}

// --------------------------------------------------------------------------
// Saída
// --------------------------------------------------------------------------
const falhas = itens.filter((item) => item.estado === 'falha');
const avisos = itens.filter((item) => item.estado === 'aviso');

if (JSON_SAIDA) {
  console.log(JSON.stringify({ raiz: RAIZ, pronto: falhas.length === 0, falhas: falhas.length, avisos: avisos.length, itens }, null, 2));
} else {
  console.log(`\nJARVIS — checagem desta pasta\n${CINZA}${RAIZ}${ZERAR}`);
  console.log(`${CINZA}${platform()} ${release()} · node ${process.version}${ZERAR}\n`);
  const largura = Math.max(...itens.map((item) => item.titulo.length));
  for (const item of itens) {
    console.log(`  ${simbolo(item.estado)}  ${item.titulo.padEnd(largura)}  ${item.detalhe}`);
    if (item.estado !== 'ok' && item.conserto) {
      console.log(`        ${CINZA}→ ${item.conserto}${ZERAR}`);
    }
  }
  console.log('');
  if (falhas.length === 0) {
    console.log(`${VERDE}Pronto para rodar.${ZERAR} ${avisos.length} aviso(s). Suba com: npm run dev`);
    console.log(`${CINZA}Depois confira: curl http://127.0.0.1:8000/api/health${ZERAR}\n`);
  } else {
    console.log(`${VERMELHO}Falta ${falhas.length} item(ns).${ZERAR} Resolva as linhas marcadas FALTA e rode de novo.\n`);
  }
}

process.exit(falhas.length === 0 ? 0 : 1);
