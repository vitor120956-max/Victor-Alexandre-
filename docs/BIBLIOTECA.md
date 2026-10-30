# Biblioteca e armazenamento — 0.62.6

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
| `.png` `.jpg` `.jpeg` `.webp` `.bmp` `.tif` `.tiff` | OCR da imagem | uma seção com o texto lido |
| PDF escaneado | `pypdf` não acha texto → OCR página por página | seções com **página** |

Um arquivo só entra se estiver em `storage/` (ou subpasta) **ou** na sua pasta
**Downloads**. O original não é movido nem apagado.

PDF com pouco texto por página (menos de 40 caracteres) é tratado como
digitalizado e passa pelo OCR. Para **forçar** o OCR num PDF que tem camada de
texto ruim, apague a camada ou importe a imagem da página — `usar_ocr` existe na
função, não na skill.

```text
biblioteca.importar   caminho=Downloads/contabilidade.pdf
biblioteca.listar
biblioteca.buscar     consulta=critério de rateio
biblioteca.correlacoes termo=rateio
biblioteca.digest     fonte=contabilidade-4f2a1c gravar=true
biblioteca.remover    fonte=contabilidade-4f2a1c
biblioteca.video      url=https://youtu.be/dQw4w9WgXcQ
biblioteca.ocr
biblioteca.sumario    fonte=contabilidade-4f2a1c
biblioteca.exportar   fonte=contabilidade-4f2a1c
```

---

## 2. Como a resposta é montada

1. **busca** — BM25 sobre as seções de todas as fontes;
2. **cobertura** — quantas palavras do seu pedido realmente aparecem no trecho;
3. **corte** — o pedaço do texto em volta do termo, não o começo seco da seção
   (1.200 caracteres no `trecho`, 2.600 no `contexto`, com os títulos da seção
   anterior e da seguinte em `vizinhas`);
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
apelido ensinado → resposta guardada → skill forte → biblioteca → faixa média → receita → web → não sei
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

## 5. Índice e exportação

`biblioteca.sumario fonte=<slug>` devolve o mapa do livro: cada seção com ordem,
página, tamanho, a primeira frase e os cinco termos mais frequentes dela. Nada é
resumido — é o índice real, lido do texto.

`biblioteca.exportar fonte=<slug>` grava `storage/biblioteca/exportadas/<slug>.md`
com a ficha (sumário, termos, números, citações) e o texto completo, cada seção
marcada com `## ordem. título (p. X)`. Serve para abrir no Obsidian, levar para
outro PC ou revisar sem a interface. O `.md` é cortado em 2 MB; a ficha nunca é
cortada.

---

## 6. Ficha (`SKILL.md`)

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

## 7. Onde ficam os dados

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

## 8. Limites, sem enfeite

| Limite | Valor |
|---|---|
| Tamanho por arquivo | 60 MB |
| Caracteres por fonte | 4.000.000 |
| Seções por fonte | 4.000 |
| Trecho devolvido | 1.200 caracteres (contexto: 2.600) |
| Exportação | `.md` com ficha + texto, teto de 2 MB |
| Formatos | PDF, EPUB, DOCX, TXT, MD, RST, VTT, SRT, PNG, JPG, WEBP, BMP, TIF |
| Páginas por OCR | 40 por arquivo |
| Resolução do OCR | 200 dpi |

- **Sem motor de OCR, imagem e PDF escaneado são recusados** com o comando de
  instalação — a camada não inventa texto que não leu.
- **Vídeo sem legenda não é transcrito.** O JARVIS baixa a legenda que o YouTube
  já publica (inclusive a automática); se não houver nenhuma, ele diz isso.
- **Sem tradução, sem resumo abstrativo, sem modelo.**
- Correlação é coocorrência de palavras, não relação de causa.

---

## 9. OCR: papel, foto e PDF escaneado

Três motores, tentados nesta ordem — o primeiro que existir atende:

| Motor | Onde funciona | Precisa de |
|---|---|---|
| **Tesseract** | Windows, Linux e macOS | `tesseract.exe` instalado + `pip install pytesseract pypdfium2` |
| **winocr** | Windows 10 build 15063+ | `pip install winocr` (usa o OCR do próprio Windows) |
| **RapidOCR** | qualquer plataforma | `pip install rapidocr-onnxruntime` (não instala em Python 3.15) |

O Tesseract é o único que o **Windows 10 1607** aceita, e é o recomendado:
instale pelo pacote da UB Mannheim marcando o idioma **Portuguese**, depois

```bat
.venv\Scripts\pip install pytesseract pypdfium2
.venv\Scripts\python -c "from server import ocr; print(ocr.status())"
```

Se o executável ficou fora do PATH e de `Program Files`, aponte no `.env`:

```text
JARVIS_TESSERACT=C:\Program Files\Tesseract-OCR\tesseract.exe
```

O que o OCR faz com o PDF: rasteriza as páginas com `pypdfium2` a 200 dpi, lê
cada uma e devolve `(página, texto)` — no máximo **40 páginas** por arquivo. Não
existe OCR na nuvem aqui: a imagem não sai da máquina.

O que ele **não** faz: endireitar foto torta, separar coluna de tabela, corrigir
palavra errada, traduzir. Texto reconhecido errado entra errado — a ficha
(`biblioteca.digest`) mostra os números citados justamente para você conferir.

---

## 10. Legenda do YouTube, sozinha

`biblioteca.video url=<endereço>` faz o caminho inteiro — e, como qualquer coisa
que sai para a internet aqui, exige a rede liberada na subida
(`JARVIS_HOST_REDE=1`), a mesma trava das skills de sistema: abre a página do vídeo,
lê as faixas de legenda, escolhe **pt-BR**, **pt**, **en** ou **es** nessa ordem
(aceita a automática), baixa o `json3` e importa o texto como fonte do tipo
`video`, guardando o link como origem.

```text
biblioteca.video url=https://www.youtube.com/watch?v=dQw4w9WgXcQ
→ { "slug": "aula-de-rateio-9c31ab", "tipo": "video", "idioma": "pt-BR",
    "secoes": 6, "caracteres": 18422 }
```

Limites, sem enfeite:

- **não transcreve áudio** — vídeo sem legenda publicada não entra;
- **rede desligada recusa antes de tentar** — a mensagem diz qual variável ligar;
- a página do YouTube muda; se as faixas não vierem, o erro diz que não vieram;
- vídeo pedindo consentimento de cookie pode exigir abrir uma vez no navegador;
- legenda automática tem erro de reconhecimento de fala — e ele fica no texto.

---

## 11. Medido

| Verificação | Resultado |
|---|---|
| Testes da biblioteca | **27** (PDF gerado com reportlab, EPUB e DOCX montados no teste) |
| Testes do OCR | **13** (motor falso por monkeypatch: o sandbox não tem Tesseract) |
| Testes da legenda | **19** (HTML do YouTube montado no teste, sem rede) |
| Testes de armazenamento | **7** |
| Testes do Google Drive | **88** (34 em `test_drive_setup.py`, 10 em `test_mover_dados.py`, 17 em `test_dados.py`, 27 em `test_agente_local.py`) |
| Testes do agente local | **191** (21 novos: mesa, fonte, habilidades e correio) |
| Testes das habilidades de fora | **41** (`test_habilidades.py` e `test_github.py`, com baixador e API falsos) |
| Testes do correio | **25** (`test_correio.py`, com `.eml` e `.mbox` montados no teste) |
| Testes do mouse e do teclado | **19** (`test_mesa.py`, backend falso: nada toca o Windows de verdade) |
| Suíte da API | **2.842** |
| Skills no registro | **291** (75 novas: biblioteca.*, armazenamento.*, mesa.*, habilidades.*, github.*, correio.*, catalogo.*, cultura.*, pc.*, instalador.*, agenda.*, backup.* e git.*) |
| Importação real | `mover-dados.py` copiou **150 arquivos / 2,1 MB** e a conferência deu `ok` nas seis áreas |

**O que não foi medido:** o reconhecimento do Tesseract. Ele não existe na máquina
onde este projeto é testado (Linux, sem o executável), então os testes de OCR
usam um motor falso e cobrem detecção, rasterização, limite de páginas e
mensagem de erro. O reconhecimento em si só é exercitado na sua instalação —
`biblioteca.ocr` diz na hora se o motor está lá.
