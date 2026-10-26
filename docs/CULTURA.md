# Cultura — livros completos, de graça e sem pirataria

A pergunta que abriu esta camada: *“ache um site com todos os livros completos
gratuitos para que ele possa acessar, usar as informações, virar skill ou criar
uma persona”*.

A resposta curta: **não existe um site com “todos” os livros** — e qualquer site
que prometa isso está distribuindo obra protegida. O que existe é melhor: acervos
legais, enormes e com texto completo, de obras em **domínio público** (prazo de
direito autoral vencido) e de livros acadêmicos em **acesso aberto**.

## As sete fontes que prestam

| Fonte | O que tem | Licença | Precisa | Baixar |
|---|---|---|---|---|
| **[Project Gutenberg](https://www.gutenberg.org)** | ~79 mil e-books completos, em texto puro, EPUB e HTML | domínio público (EUA: antes de 1929) | nada | `.txt` por obra |
| **[Standard Ebooks](https://standardebooks.org)** | clássicos com edição revisada e tipografia | domínio público + CC0 no trabalho editorial | nada | EPUB |
| **[Open Library](https://openlibrary.org)** | milhões de registros e scans antigos | domínio público nos scans antigos; o resto é empréstimo | conta só para obra emprestada | só domínio público |
| **[Wikisource](https://pt.wikisource.org)** | textos transcritos, capítulo por capítulo | domínio público ou CC BY-SA | nada | texto na página |
| **[Domínio Público (MEC)](http://www.dominiopublico.gov.br)** | acervo em português: literatura, filosofia, ciências | domínio público | nada | PDF |
| **[LibriVox](https://librivox.org)** | audiolivros de domínio público | domínio público | nada | áudio (não texto) |
| **[DOAB](https://www.doabooks.org)** | livros acadêmicos completos | Creative Commons | nada | PDF/EPUB |

O JARVIS automatiza as duas primeiras de verdade (Gutenberg por API, Open Library
para metadados). Wikisource e Domínio Público entram no fluxo por link.

**O que continua de fora:** livro protegido por direito autoral — best-seller
recente, didático em catálogo, tradução nova. Nenhuma camada deste projeto vai
buscar isso: não é limitação técnica, é a linha que separa acervo livre de
pirataria.

## O que dá para pedir no chat

| Você pede | Ele faz |
|---|---|
| `onde acho livros completos de graça` | as sete fontes, com licença e o que cada uma pede |
| `procura o livro Dom Casmurro` | busca no Gutenberg (Gutendex) e mostra id, autores e o link do `.txt` |
| `baixa o livro 59863` | puxa o texto, tira o cabeçalho legal do Gutenberg e guarda na biblioteca |
| `faz uma persona do livro Dom Casmurro` | mede o estilo do texto e monta o cartão de escrita |

Equivalente por API:

```bash
curl -s -X POST http://localhost:8000/api/skills/cultura.fontes/run \
  -H "Content-Type: application/json" -d '{}'

curl -s -X POST http://localhost:8000/api/skills/cultura.buscar/run \
  -H "Content-Type: application/json" -d '{"consulta": "machado", "idioma": "pt"}'

curl -s -X POST http://localhost:8000/api/skills/cultura.baixar/run \
  -H "Content-Type: application/json" -d '{"livro": "59863"}'

curl -s -X POST http://localhost:8000/api/skills/cultura.persona/run \
  -H "Content-Type: application/json" -d '{"livro": "Dom Casmurro"}'
```

## O caminho do livro até a resposta

1. `cultura.buscar` consulta o **Gutendex** (`gutendex.com`, API aberta do
   catálogo do Gutenberg, sem chave) e devolve o `id`.
2. `cultura.baixar` busca `gutenberg.org/ebooks/<id>.txt.utf-8`, remove o
   cabeçalho e o rodapé legal e chama `biblioteca.importar_texto` com
   `tipo="livro"`.
3. A partir daí **toda a biblioteca já funciona**: `biblioteca.buscar` acha o
   trecho por assunto (BM25, com a seção de origem), `biblioteca.resumir` monta o
   resumo extrativo e `biblioteca.listar` mostra a estante.
4. `cultura.persona` lê o texto guardado e mede o estilo.

Não há etapa de modelo em nenhum ponto — é busca, contagem e corte.

## A persona: o que é, e o que não é

`cultura.persona` devolve números medidos no texto, não impressão:

```text
Persona “Dom Casmurro” — estilo medido em 84.512 palavras:
Tom: reflexivo: período longo, subordinadas encaixadas, com bastante diálogo.

• Frase média de 18 palavras (o livro fica entre 2 e 71).
• 21% das frases são curtas (até 8 palavras) e 12% passam de 30 — mantenha essa proporção.
• Vocabulário recorrente: olhos, casa, tempo, capitu, homem, vida, coisa, dia, mão, noite.
• Diálogo ocupa cerca de 23% dos parágrafos; use travessão para fala.
• Pontuação por mil caracteres: 4.1 interrogação, 3.2 exclamação, 5.8 ponto e vírgula, 9.4 travessão.
• Primeira pessoa aparece 12.3× por mil palavras; segunda pessoa, 2.1×.
```

E os três limites, que ficam no próprio cartão:

1. **É estilo medido, não o autor.** Não imita personalidade, opinião ou biografia.
2. **Não inventa citação.** Para trecho literal, use `biblioteca.buscar`, que
   devolve a seção exata de onde saiu.
3. **Não copia trechos longos.** A persona orienta *como* escrever; não reproduz
   o livro.

## Virar skill

Depois de baixar, o livro já é uma fonte da biblioteca — e fonte é o que
`biblioteca.buscar` consulta quando você pergunta sobre um assunto. Para virar
rotina, o caminho é o mesmo das habilidades de fora:

```text
baixa o livro 59863
faz uma persona do livro Dom Casmurro
```

O cartão fica em `storage/personas.json`. Se você quiser uma **skill** de
verdade sobre o livro (por exemplo “conferir citação da obra X”), ela precisa de
código — o que existe aqui é a estante, a busca e o cartão de estilo.

## Onde ficam os arquivos

| Peça | Caminho |
|---|---|
| fontes, busca, download, persona | `server/cultura.py` |
| o texto do livro e as seções | `storage/biblioteca` (ou `JARVIS_BIBLIOTECA`) |
| cartões de persona | `storage/personas.json` |
| skills | `cultura.fontes`, `cultura.buscar`, `cultura.baixar`, `cultura.persona` |
| testes | `server/tests/test_cultura.py` (16, com download e JSON dublês) |

Nenhum teste abre socket: o download e o JSON das duas APIs são substituídos por
funções de teste. O que se verifica é o que pode dar errado de verdade — JSON
inesperado, livro sem número, texto que veio vazio, download acima de 6 MB,
texto curto demais para medir estilo.
