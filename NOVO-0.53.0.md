# 0.53.0 — o tópico `agent-skills`, livros de graça e adaptação do que vem de fora

## 1. “Ele vai conseguir entender e usar tudo?”

**Entender, sim. Usar tudo, não.** A linha é simples e vale a pena saber onde ela
está:

| O que a skill é | O JARVIS faz | Exemplo |
|---|---|---|
| **Texto** (guia, checklist, passos) | puxa, guarda, organiza em passos e transforma em skill local de procedimento | `frontend-design`, `web-design-guidelines`, `vercel-react-best-practices` |
| **Instrução para um modelo** | guarda o texto, mas sem modelo ela não “pensa” — vira roteiro para você seguir | `grill-me`, `humanizer` |
| **Depende de serviço pago** | o texto é guardado; **o efeito não acontece** | `nano-banana-pro` (imagem), Copilot, geração de vídeo |
| **Código/instalação** | não roda. Importar não instala nada, nunca | qualquer `install: npx skills add …` |

Ou seja: 100% do que é **texto** entra. 0% do que exige **modelo pago** roda
sozinho. Nada é executado no seu PC só por ter sido importado.

## 2. O tópico `agent-skills` do GitHub

```text
pega as skills do tópico agent-skills do github
```

**Teste real, agora, sem token:** um pedido de busca + 12 pedidos de árvore
devolveram **270 `SKILL.md`** — `ComposioHQ` 200, `addyosmani` 25, `anthropics`
20, e mais alguns. Tudo somado ao catálogo, com categoria e fornecedor:

```text
Li 12 repositório(s) do tópico “agent-skills” (https://github.com/topics/agent-skills):
270 skill(s) somada(s) ao catálogo — total agora: 270.
Por categoria: ai-agent (232), dev-programming (37), design-media (1)
```

Depois é o fluxo normal:

```text
quais skills de dev tem no catálogo
importa as 10 primeiras do catálogo
```

Limites que eu não escondo:

- **15 repositórios por chamada** (1 pedido de busca + 1 de árvore cada). O
  GitHub público dá **60 pedidos por hora** por IP, sem token;
- repositório que é **lista** (`awesome-*`) ou plugin **não tem `SKILL.md`** e
  volta pelo nome, sem virar skill;
- o tópico tem **37 mil repositórios** — dá para varrer por partes, mudando o
  tópico (`topic:design`, `topic:marketing`) ou rodando de novo depois de uma hora.

## 3. Cultura: livros completos, de graça e legais

A pergunta era “um site com todos os livros completos gratuitos”. Esse site não
existe — e quem promete isso distribui obra protegida. O que existe é melhor:

| Fonte | O que tem | Precisa |
|---|---|---|
| **Project Gutenberg** | ~79 mil obras completas em texto puro | nada |
| **Standard Ebooks** | clássicos revisados (EPUB) | nada |
| **Open Library** | milhões de registros e scans antigos | conta só para emprestado |
| **Wikisource** | textos transcritos, capítulo a capítulo | nada |
| **Domínio Público (MEC)** | acervo em português | nada |
| **LibriVox** | audiolivros de domínio público | nada |
| **DOAB** | livros acadêmicos em acesso aberto | nada |

```text
onde acho livros completos de graça
procura o livro Dom Casmurro
baixa o livro 59863
faz uma persona do livro Dom Casmurro
```

O download tira o cabeçalho legal do Gutenberg e guarda em `storage/biblioteca`.
A partir daí **a biblioteca inteira já funciona**: `biblioteca.buscar` acha trecho
por assunto (BM25, com a seção de origem) e `biblioteca.resumir` monta o resumo.

A persona é medida, não inventada:

```text
Persona “Dom Casmurro” — estilo medido em 84.512 palavras:
Tom: reflexivo: período longo, subordinadas encaixadas, com bastante diálogo.

• Frase média de 18 palavras (o livro fica entre 2 e 71).
• 21% das frases são curtas e 12% passam de 30 — mantenha essa proporção.
• Diálogo ocupa cerca de 23% dos parágrafos; use travessão para fala.
```

E os três limites, que ficam escritos no próprio cartão: **é estilo, não o
autor**; **não inventa citação** (para trecho literal, `biblioteca.buscar`); **não
copia trechos longos**. Livro ainda protegido por direito autoral não entra.

## 4. Adaptar para uso próprio

```text
adapta a habilidade frontend-design para mim
```

O guia importado vira **skill local de procedimento** (`local.proc-frontend-design`),
com os passos numerados, e passa a responder no chat pelo nome. Continua sendo
roteiro — o JARVIS não finge que a habilidade “aprendeu” a desenhar.

## 5. Como atualizar

```bat
cd /d D:\JARVIS
git pull
.venv\Scripts\python -m pytest server\tests -q -o addopts=
npm run build:embutido
.venv\Scripts\python iniciar.py
```

Para o GitHub e o Gutenberg funcionarem, a API precisa subir com rede:

```bat
set JARVIS_HOST_REDE=1
.venv\Scripts\python iniciar.py
```

Conferir: `http://127.0.0.1:8000/api/health` → `"version": "0.53.0"` e
`"skills": 260`.

## 6. Números

- **260 skills** (6 novas: `catalogo.topico`, `habilidades.adaptar`,
  `cultura.fontes`, `cultura.buscar`, `cultura.baixar`, `cultura.persona`).
- **2.428 testes** Python + **110** da interface.
- Testado de verdade: 12 repositórios do tópico → 270 `SKILL.md` no catálogo,
  leitura de fontes de livro e formatação no chat.

Detalhes em `docs/CATALOGO.md`, `docs/CULTURA.md`, `docs/HABILIDADES.md` e
`docs/AGENTE-LOCAL.md`.
