#!/usr/bin/env node
/**
 * Copia a interface compilada de `dist/` para `web-dist/`.
 *
 * `dist/` está no .gitignore; `web-dist/` é versionado de propósito, para que a
 * API possa servir a interface sem Node instalado — o caminho de quem roda o
 * JARVIS de um pendrive e não quer (ou não consegue) rodar `npm install`.
 *
 * Uso:
 *   npm run build            # gera dist/ com Vite
 *   npm run build:embutido   # build + cópia para web-dist/
 */
import { cpSync, existsSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const RAIZ = fileURLToPath(new URL('..', import.meta.url));
const ORIGEM = join(RAIZ, 'dist');
const DESTINO = join(RAIZ, 'web-dist');

if (!existsSync(join(ORIGEM, 'index.html'))) {
  console.error('dist/index.html não existe. Rode `npm run build` antes.');
  process.exit(1);
}

rmSync(DESTINO, { recursive: true, force: true });
cpSync(ORIGEM, DESTINO, { recursive: true });

function medir(pasta) {
  const arquivos = [];
  const visitar = (caminho) => {
    for (const entrada of readdirSync(caminho, { withFileTypes: true })) {
      const completo = join(caminho, entrada.name);
      if (entrada.isDirectory()) visitar(completo);
      else arquivos.push({ caminho: completo, bytes: statSync(completo).size });
    }
  };
  visitar(pasta);
  return arquivos;
}

const arquivos = medir(DESTINO);
const total = arquivos.reduce((soma, item) => soma + item.bytes, 0);
const maiores = [...arquivos].sort((a, b) => b.bytes - a.bytes).slice(0, 5);
const mb = (bytes) => `${(bytes / 1024 / 1024).toFixed(2)} MB`;

writeFileSync(
  join(DESTINO, 'LEIA-ME.txt'),
  [
    'Interface compilada, versionada de propósito.',
    '',
    'Motivo: a API Python serve esta pasta quando `dist/` não existe, então dá',
    'para usar o JARVIS sem Node e sem `npm install` — o caso de quem roda de',
    'um pendrive lento.',
    '',
    'Para regerar: npm run build:embutido',
    'Não edite estes arquivos à mão: eles vêm do `npm run build`.',
    '',
  ].join('\n'),
  'utf-8',
);

console.log(`web-dist atualizado: ${arquivos.length} arquivos, ${mb(total)}.`);
for (const item of maiores) {
  console.log(`  ${mb(item.bytes).padStart(9)}  ${item.caminho.slice(DESTINO.length + 1)}`);
}
