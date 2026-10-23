# Engenharia reversa estática

A versão **0.7.0** acrescenta seis skills locais inspiradas em [`morluto/rea`](https://github.com/morluto/rea). O REA é uma plataforma MIT de engenharia reversa com MCP, CLI e provedores nativos. O JARVIS adapta somente o modelo de **evidência estática**: identidade dos bytes, fatos observados, achados, cobertura e limitações declaradas.

A implementação é própria. O pacote `rea-agents`, o servidor MCP, os bridges de Hopper, Ghidra, IDA e JADX, os hooks, o instalador e os scripts do upstream **não são instalados nem executados**. Nenhum alvo é aberto, importado, descompactado em disco ou rodado como processo.

## O que a adaptação faz

| Skill | Pergunta que responde | Limite principal |
|---|---|---|
| `reverse.inspect` | Que artefato é este, qual seu SHA-256 e o que o cabeçalho declara? | Não prova autoria, assinatura ou confiança |
| `reverse.layout` | Quais seções, segmentos, entradas e imports existem? | Interpreta apenas os formatos listados |
| `reverse.strings` | Quais strings imprimíveis existem, com offsets? | ASCII e UTF-16LE; não interpreta outros encodings |
| `reverse.entropy` | Quais regiões parecem comprimidas ou cifradas? | Não identifica algoritmo nem descompacta |
| `reverse.javascript` | Como módulos, imports, IPC, rotas e fronteiras Electron se relacionam? | Regex estática, sem AST, bundler ou execução |
| `reverse.compare` | O que mudou entre dois artefatos? | Diferença estática não é prova de comportamento |

Toda resposta inclui `executed: false`, `readOnly: true`, identidade SHA-256 e uma lista de limitações. Resultados parciais permanecem explícitos: uma lista truncada nunca é apresentada como inventário completo.

## Formatos reconhecidos

- **ELF** 32/64 bits: seções, segmentos, entry point, máquina, dependências `DT_NEEDED`, `SONAME` e `RUNPATH`.
- **PE** PE32/PE32+: seções, entry point, subsistema, características de DLL, ASLR/NX/CFG declarados, diretórios e imports por biblioteca.
- **Mach-O** slim e universal: CPU, tipo, segmentos, dylibs, UUID e aviso de criptografia.
- **ZIP/APK/AAR/JAR**: diretório central sem extração, nomes inseguros, duplicatas, cifra e razões de compressão anômalas.
- **ASAR**: cabeçalho JSON, inventário de membros e marcação de arquivos `unpacked`.
- **WASM**: seções, imports e exports; corpos de função não são decodificados.
- **PDF**: versão, objetos, JavaScript embutido e criptografia declarada; sem renderização.
- **safetensors**, **GGUF**, **PYC**, **Erlang BEAM** e **imagens**: metadados de cabeçalho com limites.
- **Texto/JavaScript/TypeScript/JSON/HTML/CSS** e formatos não reconhecidos: identidade, entropia e strings.

Um formato sem parser estrutural continua analisável como bytes. Isso é declarado em `limitations`; não existe promessa de cobertura universal.

## Análise JavaScript e Electron

A árvore é percorrida com limites de **2.000 arquivos**, **8 MB no total** e **1,5 MB por arquivo**. `node_modules` é excluído por padrão. Symlinks não são seguidos e caminhos resolvidos precisam permanecer dentro da árvore.

A identidade `sha256` de uma árvore cobre apenas o conteúdo analisado (caminho relativo + bytes de cada arquivo), com `digestScope: "analyzed-content"`. Duas cópias idênticas em pastas diferentes têm o mesmo hash; um byte alterado muda o hash.

São extraídos:

- imports ESM, `export ... from`, `require` CommonJS e imports dinâmicos;
- relações resolvidas entre arquivos da árvore;
- especificadores de pacote, builtins Node e URLs remotas, sem baixar nada;
- fatos Electron (`BrowserWindow`, `preload`, `contextBridge`, `ipcMain`, `ipcRenderer`);
- sinais de risco (`nodeIntegration: true`, `contextIsolation: false`, `sandbox: false`, `eval`, `new Function`, `child_process`);
- rotas Express-like e URLs de `fetch` como **candidatos estáticos**;
- referências a `.node`, `process.dlopen`, source maps e entradas prováveis.

**Importante:** as relações são candidatos estáticos. `resolved` significa que o alvo relativo foi encontrado na árvore, não que o caminho executou. Imports dinâmicos, pacotes e URLs permanecem pendências explícitas. O JARVIS não afirma alcance em runtime, registro de IPC ou política efetiva.

O modo inline aceita até **500.000 caracteres** e **1 MB em UTF-8**, sem resolução de caminhos. O código colado é lido como texto e nunca interpretado pelo motor JavaScript do servidor.

## Strings, entropia e comparação

- Strings: mínimo de 4 a 128 bytes, janela opcional por offset e comprimento, filtro textual, limite de 1.000 resultados e offset absoluto em cada item.
- Entropia: blocos de 256 a 65.536 bytes (potência de dois), até 32.768 blocos, janela opcional; o SHA-256 cobre o arquivo inteiro e a entropia cobre a janela.
- Comparação: SHA-256, delta de tamanho, seções, entradas, imports e amostra de strings. Arquivos idênticos recebem uma mensagem explícita; diferenças não são tratadas como causalidade.

## API e armazenamento

Os artefatos ficam em `storage/user-files/reverse`, separados da biblioteca de documentos. A área tem rotas próprias:

```text
GET  /api/reverse/files
POST /api/reverse/upload      # confirmação obrigatória, 25 MB
GET  /api/reverse/download
```

Uploads aceitam somente extensões de artefato, recusam nomes ocultos, arquivos vazios e caminhos com `..`, e nunca sobrescrevem sem autorização explícita. Downloads saem como `application/octet-stream` com `Content-Disposition: attachment`; a interface não renderiza HTML nem executa JavaScript de um artefato.

As skills usam a área reversa como raiz e recusam caminhos absolutos, ocultos, symlinks e destinos fora dela. Um symlink dentro da árvore não é seguido.

## Segurança

- Nenhuma chamada a `subprocess`, shell, socket, navegador, ADB, MCP ou provedor nativo.
- Nenhum `eval`, `exec`, import dinâmico ou carregamento do artefato como biblioteca.
- ZIP, ASAR e APK são inventariados pelo diretório central; **nada é extraído**.
- Parsers validam offsets, tamanhos, contagens e strings antes de ler, falhando de forma fechada em artefatos truncados ou malformados.
- Limites de 25 MB por artefato, 2.000 entradas por contêiner, 512 linhas de layout e 1.000 strings.
- Resultados são locais e nunca são enviados automaticamente à IA externa.

## O que não foi adaptado

Ficaram fora do escopo: MCP, CLI upstream, Hopper, Ghidra, IDA, Kuna, JADX, Apktool, Frida, adb, captura de rede, navegador, captura de processos, firmware, extração de arquivos e descompilação. O REA completo pode fazer muito mais; o JARVIS entrega um recorte estático, determinístico e auditável.

## Atribuição

- Upstream: [`morluto/rea`](https://github.com/morluto/rea), commit de referência `71a024c789a3d4626b85965a0b511a577a027801`.
- Licença MIT, Copyright (c) 2026 morluto, preservada em [`licenses/morluto-rea.txt`](licenses/morluto-rea.txt).
- Nenhum arquivo de código do upstream foi copiado; os parsers e a interface foram escritos para este projeto.

## Limitações conhecidas

- Não há AST JavaScript, resolução de bundler, source map expansion ou análise de bytecode de função.
- Formatos não listados não têm parser estrutural próprio.
- PE imports são contados por thunk; nomes de funções não são resolvidos.
- ELF sem tabela de seções pode não expor dependências dinâmicas.
- Comparações usam amostras; ausência em uma lista limitada não prova ausência no artefato.
- O resultado é evidência estática, não laudo pericial, atestado de malware ou garantia de segurança.
