# 0.50.0 — habilidades de fora e GitHub, sem token

## A resposta curta

**Puxar e guardar: sim, e já está funcionando.** Eu testei aqui com as suas:
`design de front-end` (9.074 caracteres), `vercel-react-best-practices` (6.805),
`diretrizes-de-design-web` (914) e `grelha-com-documentos` — todas baixaram do
GitHub e ficaram guardadas.

**“Usar numa pergunta”: com um limite honesto.** O JARVIS não tem modelo (decisão
sua: sem chave). Então a habilidade não vira raciocínio dele — vira **roteiro**:
quando você pede, ele devolve a habilidade inteira com a sua pergunta em cima.
Quem segue o roteiro é você (ou um modelo, se um dia houver um configurado).

**Copilot: não.** É serviço de modelo pago, exige assinatura e token. Não entra.

## Os comandos (copiar e colar no chat)

```text
importa a habilidade https://github.com/anthropics/skills/tree/main/skills/frontend-design
quais habilidades você importou
usa a habilidade frontend-design para revisar a tela de login
esquece a habilidade frontend-design
```

Link aceito: do arquivo (`.../blob/main/.../SKILL.md`), da pasta
(`.../tree/main/skills/nome`), do repositório inteiro (`github.com/dono/repo`),
do botão **Raw**, ou de uma página de catálogo (skills.sh / clawhub — ele caça o
GitHub dentro da página).

## O que acontece com cada item da sua lista

| Item da lista | O que dá para fazer |
|---|---|
| design de front-end (anthropics) | **testado**: importa e guarda. O roteiro serve de checklist; a checagem objetiva (contraste, tokens, clichê) já existe em `studio.*` |
| vercel-react-melhores-práticas | **testado**: importa (6.805 caracteres) e volta como roteiro |
| diretrizes-de-design-web | **testado**: importa (914 caracteres) |
| grelha-com-documentos (grill-with-docs) | **testado**: importa — mas o texto tem só 64 caracteres: é um atalho, não um guia |
| grelhe-me (grill-me) | o repo `mattpocock/skills` tem **38 habilidades**; importe a pasta do grill-me |
| encontrar-habilidades | já está embutido: `busca repositório no github: claude skills` e depois importe |
| agente-navegador (vercel-labs) | importa o texto; **agir** no navegador continua nas skills `navegador.*` (planejamento), não em código importado |
| melhores práticas de remoção (remotion) | importa como checklist |
| geração de imagens por IA / nano-banana-pro | **não funciona sem chave**: o guia é guardado, mas gerar imagem exige serviço pago. O JARVIS não finge |

## GitHub sem Git e sem token (novo)

```text
ficha do repositório vercel-labs/agent-skills
lista os arquivos de vercel-labs/agent-skills em skills
lê o SKILL.md de vercel-labs/agent-skills em skills/web-design-guidelines/SKILL.md
busca repositório de agent skills
```

API pública do GitHub: estrelas, linguagem, licença, árvore e texto de arquivo.
Sem `clone`, sem `push`, sem repositório privado. **60 pedidos por hora** — é o
limite do GitHub sem token, e ele avisa quando estoura.

## O que o JARVIS NÃO faz com isso

1. Não executa o código de uma habilidade (ela é texto).
2. Não instala pacote nenhum.
3. Não “pensa” com a habilidade — sem modelo, não há raciocínio.
4. Não usa Copilot, nem qualquer serviço que cobre assinatura.

## Números

- **245 skills** (8 novas: `habilidades.*` e `github.*`).
- **2.331 testes** na suíte Python, **110** na interface — todos passando.
- **Zero dependência nova.**
- Teste real feito aqui: 4 habilidades baixadas do GitHub e guardadas.

## Atualizar no seu PC

1. Feche o JARVIS (Ctrl+C no CMD).
2. Baixe:
   `https://codeload.github.com/vitor120956-max/Victor-Alexandre-/zip/refs/heads/arena/f26cfa7a-victor-alexandre`
3. Extraia **por cima** de `D:\JARVIS` (substituir arquivos). Não precisa `pip install`.
4. Suba:

```bat
cd /d D:\JARVIS
set JARVIS_HOST_REDE=1
.venv\Scripts\python iniciar.py
```

5. Confira `http://127.0.0.1:8000/api/health`: `"version": "0.50.0"` e `"skills": 245`.
6. Teste com:

```text
importa a habilidade https://github.com/anthropics/skills/tree/main/skills/frontend-design
sim, pode
quais habilidades você importou
usa a habilidade frontend-design para revisar a tela de login
```

O que ficou guardado está em `D:\JARVIS\storage\habilidades.json` — JSON legível,
dá para abrir no Bloco de Notas. Detalhes em `docs/HABILIDADES.md`.
