import { existsSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { resolve } from 'node:path';

const localPython = process.platform === 'win32'
  ? resolve('.venv/Scripts/python.exe')
  : resolve('.venv/bin/python');
const python = process.env.PYTHON || (existsSync(localPython) ? localPython : 'python3');
const args = process.argv.slice(2);

if (args.length === 0) {
  console.error('Informe o módulo Python que deve ser executado.');
  process.exit(2);
}

const child = spawn(python, args, { stdio: 'inherit', env: process.env });
const forward = (signal) => child.kill(signal);
process.on('SIGINT', () => forward('SIGINT'));
process.on('SIGTERM', () => forward('SIGTERM'));
child.on('error', (error) => {
  console.error(`Não foi possível iniciar ${python}: ${error.message}`);
  console.error('Crie o ambiente com: python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt');
  process.exit(1);
});
child.on('exit', (code, signal) => {
  if (signal) process.exit(0);
  process.exit(code ?? 1);
});
