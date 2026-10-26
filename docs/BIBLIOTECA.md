# Biblioteca e armazenamento — 0.42.0

Duas coisas que faltavam para o JARVIS deixar de depender só do que você digita
na hora:

- **biblioteca** — ele lê o livro, a legenda do vídeo e a sua pesquisa, guarda em
  seções pesquisáveis e responde citando fonte, seção e página;
- **armazenamento** — os dados saem do pendrive e passam a morar onde há espaço.

Nenhuma das duas usa modelo de linguagem.

---

## 1. O que entra na biblioteca

| Formato | Como é lido | Vira |
|---|---|---|
| `.pdf` | `pypdf`, página por página | seções com **página** |
| `.epub` | `zipfile` + leitura do spine | seções na ordem do livro |
| `.docx` | `python-docx` | seções por título |
| `.md` `.markdown` `.rst` `.txt` | leitura direta | seções por título |
| `.vtt` `.srt` | legenda com tempo removido | seções por bloco de fala |

Um arquivo só entra se estiver em `storage/` (ou subpasta) **ou** na sua pasta
**Downloads**. O original não é movido nem apagado.

```text
biblioteca.importar   caminho=Downloads/contabilidade.pdf
biblioteca.listar
biblioteca.buscar     consulta=critério de rateio
biblioteca.correlacoes termo=rateio
biblioteca.digest     fonte=contabilidade-4f2a1c gravar=true
biblioteca.remover    fonte=contabilidade-4f2a1c
```

---

## 2. Como a resposta é montada

1. **busca** — BM25 sobre as seções de todas as fontes;
2. **cobertura** — quantas palavras do seu pedido realmente aparecem no trecho;
3. **corte** — o pedaço do texto em volta do termo, não o começo seco da seção;
4. **referência** — título da fonte, seção e página.

Só responde se a cobertura for **≥ 50%** e houver pelo menos dois termos do
pedido presentes (um, se o pedido tiver até duas palavras). Abaixo disso, ele
cala — e aí entra a web.

Exemplo de resposta:

```text
Na biblioteca, “Manual de custo” (seção “Capítulo 2 — Rateio”) fala disso:

O rateio distribui o custo indireto entre os produtos. O critério precisa ser
defensável, estável e documentado…

Também aparece em:
- Nota de vídeo · seção “Parte 1”
```

Repare no que **não** existe: resumo escrito por modelo, opinião, "provavelmente".
É o trecho real, recortado.

---

## 3. No chat, sem comando nenhum

A ordem de resolução do agente local agora é:

```text
apelido ensinado → resposta guardada → skill → receita → biblioteca → web → não sei
```

Então basta perguntar:

```text
como funciona o rateio de custo indireto
```

Se o assunto estiver num livro importado, a resposta vem de lá (e a web nem é
consultada). Se não estiver, ele segue para a web.

---

## 4. Correlações

`biblioteca.correlacoes` devolve termos que aparecem em **duas ou mais fontes** e,
para um termo dado, os **vizinhos** que andam junto dentro das seções. É medida de
coocorrência, não inferência: se aparecer "rateio ↔ custo" é porque as duas
palavras estão na mesma seção, em mais de uma fonte.

---

## 5. Ficha (`SKILL.md`)

`biblioteca.digest` monta um `SKILL.md` determinístico:

- front matter com `name` e `description`;
- **sumário** com as seções e páginas;
- **termos mais frequentes** com a contagem;
- **números e regras citados** (frases que contêm dígitos);
- **passagens para conferir** (citações com referência).

Com `gravar=true`, o arquivo vai para
`storage/biblioteca/fichas/<slug>/SKILL.md` — no padrão Agent Skills, do mesmo
tipo que o `book-to-skill` gera, só que por regra e sem modelo.

---

## 6. Onde ficam os dados

Por padrão, em `<projeto>/storage`. Para usar outro disco:

```bat
cd /d D:\JARVIS
.venv\Scripts\python mover-dados.py --ver
.venv\Scripts\python mover-dados.py --destino C:\JARVIS-DADOS
```

O script mostra o tamanho por área, copia com progresso, **confere arquivo por
arquivo**, grava `JARVIS_DADOS=C:\JARVIS-DADOS` no `.env` (em CRLF) e manda
reiniciar. Ele **não apaga** a pasta antiga: quem apaga é você, depois de ver a
API subir e `armazenamento.status` mostrar a raiz nova.

Sem o script, a mesma coisa à mão: copiar a pasta e colocar no `.env`

```ini
JARVIS_DADOS=C:\JARVIS-DADOS
```

```text
armazenamento.status
armazenamento.planejar destino=C:/JARVIS-DADOS
```

`armazenamento.planejar` devolve os cinco passos com o `robocopy` exato — ele não
copia nada.

---

## 7. Limites, sem enfeite

| Limite | Valor |
|---|---|
| Tamanho por arquivo | 60 MB |
| Caracteres por fonte | 4.000.000 |
| Seções por fonte | 4.000 |
| Trecho devolvido | 1.200 caracteres |
| Formatos | PDF, EPUB, DOCX, TXT, MD, RST, VTT, SRT |

- **PDF digitalizado (imagem) não funciona** — sem OCR não sai texto; a camada
  diz isso em vez de fingir.
- **Não há legendas automáticas do YouTube** — baixe o `.vtt` e importe.
- **Sem tradução, sem resumo abstrativo, sem modelo.**
- Correlação é coocorrência de palavras, não relação de causa.

---

## 8. Medido

| Verificação | Resultado |
|---|---|
| Testes da biblioteca | **22** (PDF gerado com reportlab, EPUB e DOCX montados no teste) |
| Testes de armazenamento | **7** |
| Testes do agente local | **127** |
| Suíte da API | **2.108** |
| Skills no registro | **223** (8 novas: biblioteca.* e armazenamento.*) |
| Importação real | `mover-dados.py` copiou **150 arquivos / 2,1 MB** e a conferência deu `ok` nas seis áreas |
