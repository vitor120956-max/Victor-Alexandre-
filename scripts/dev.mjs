#!/usr/bin/env node
// `npm run dev` com um recado humano antes do erro.
//
// O problema que gerou isto, medido na maquina do usuario:
//
//   D:\JARVIS>npm run dev
//   > jarvis-nucleo-pessoal@0.62.6 dev
//   'concurrently' nao e reconhecido como um comando interno
//   ou externo, um programa operavel ou um arquivo em lotes.
//
// Essa mensagem nao diz o que fazer. Ela aparece quando `node_modules` nao
// existe (a pasta veio do zip e ninguem rodou `npm install`) — e o pior: sugere
// que o JARVIS esta quebrado, quando na verdade ele so precisa de outro caminho.
//
// Aqui o comando vira: checar antes, explicar depois. Duas saidas honestas:
//
//   1. falta dependencia  -> diz o comando exato E lembra que existe um caminho
//                            sem Node nenhum (`iniciar-jarvis.bat`);
//   2. tudo instalado     -> roda o `concurrently` como antes.
//
// Nada e instalado por conta propria: `npm install` baixa 140 MB e quem decide
// isso e o dono da maquina, nao o atalho.
import { spawn } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const raiz = dirname(dirname(fileURLToPath(import.meta.url)));
const noWindows = process.platform === 'win32';
const pastaModulos = join(raiz, 'node_modules');
const binConcurrently = join(pastaModulos, '.bin', noWindows ? 'concurrently.cmd' : 'concurrently');

function versao() {
  try {
    return JSON.parse(readFileSync(join(raiz, 'package.json'), 'utf8')).version ?? '?';
  } catch {
    return '?';
  }
}

function explicaSemNode() {
  const python = noWindows ? '.venv\\Scripts\\python.exe' : '.venv/bin/python';
  console.log('');
  console.log('  O JARVIS nao esta quebrado: falta a pasta node_modules.');
  console.log(`  Ela vem do "npm install" (cerca de 140 MB, uma vez so). Versao desta pasta: ${versao()}.`);
  console.log('');
  console.log('  Opcao 1 - nao instalar nada e usar o JARVIS agora:');
  console.log(`    ${python} iniciar.py`);
  console.log('    (ou clique duas vezes em iniciar-jarvis.bat, se existir aqui)');
  console.log('    A interface compilada esta em web-dist\\ e sobe junto com a API.');
  console.log('');
  console.log('  Opcao 2 - trabalhar no codigo da interface (precisa do Node):');
  console.log('    npm install');
  console.log('    npm run dev');
  console.log('');
}

if (!existsSync(binConcurrently)) {
  explicaSemNode();
  process.exit(1);
}

const argumentos = [
  '--kill-others-on-fail',
  '--names', 'API,WEB',
  '--prefix-colors', 'yellow,green',
  'npm:dev:api',
  'npm:dev:web',
];

const filho = spawn(binConcurrently, argumentos, {
  cwd: raiz,
  stdio: 'inherit',
  shell: noWindows, // no Windows o .cmd precisa do shell para resolver
});

filho.on('error', (erro) => {
  console.error('');
  console.error(`  Nao consegui iniciar o concurrently: ${erro.message}`);
  console.error('  Rode "npm install" de novo. Se persistir, use:');
  console.error(`    ${noWindows ? '.venv\\Scripts\\python.exe' : '.venv/bin/python'} iniciar.py`);
  console.error('');
  process.exit(1);
});

filho.on('exit', (codigo, sinal) => {
  if (sinal) {
    process.kill(process.pid, sinal);
    return;
  }
  process.exit(codigo ?? 0);
});

for (const sinal of ['SIGINT', 'SIGTERM']) {
  process.on(sinal, () => {
    filho.kill(sinal);
  });
}
