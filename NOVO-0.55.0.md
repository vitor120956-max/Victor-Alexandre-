# 0.55.0 — “isso roda no meu PC?” e “puxa aquelas habilidades do skills.sh”

Duas perguntas suas, duas camadas novas. Em nenhuma delas o JARVIS instala,
executa ou promete o que não pode.

## 1. Instalador: onde guardar, se roda, e só então instalar

A pergunta: *“se eu pedir para baixar um programa, ele pergunta onde deixar o
arquivo, me dá as opções, avisa se pode instalar e antes confere se é compatível
com o meu PC?”*

**Sim.** A ordem ficou assim:

```text
destinos  →  analisar  →  baixar  →  sistema.instalar  →  sistema.executar
```

### Onde guardar (`instalador.destinos`)

Quatro opções com o **espaço livre real** de cada pasta: `padrao`, `programas`,
`temporarios`, `por-data`. Nome livre também vale (`jogos` cria a pasta). As
pastas de fora — `Downloads`, Área de Trabalho, cada disco — aparecem marcadas
como **“guardar sim, instalar não”**, porque `sistema.executar` só instala de
dentro da quarentena. Dizer isso agora evita a frustração depois.

### Se roda (`instalador.analisar`)

Lê **só o cabeçalho** do arquivo — não executa:

- `.exe`: 32/64 bits, arquitetura (x86, x64, ARM64, Itanium), **versão mínima de
  Windows declarada no binário**, janela/console, .NET e qual;
- `.msi`: MSI de verdade e arquitetura (`Intel;` / `x64;`);
- `.msix`/`.appx`: build mínimo (MSIX só a partir do 1809);
- `.zip`: o instalador que está dentro, sem extrair;
- `.dmg`/`.deb`/`.rpm`/`.apk`: recusa com o motivo;
- `.bat`/`.cmd`/`.ps1`: script, sem tela de instalação.

Compara com o PC medido (`instalador.maquina`): Windows e build, arquitetura,
RAM, núcleos, espaço livre e .NET instalado. E aceita o que a página do
fabricante pede (`min_os`, `ram_gb`, `disco_gb`).

Resposta: **roda / roda com ressalva / não roda / não dá para saber** — com
**bloqueios** e **ressalvas** do arquivo separados dos **avisos** do seu PC
(“1607 é antigo”, “4 GB de RAM”). Aviso não muda o veredito; bloqueio muda.

### Baixar (`instalador.baixar`)

Reusa `sistema.baixar` (rede ligada + token + quarentena + SHA-256), guarda na
subpasta escolhida e **já analisa** o que chegou. Link sem nome de arquivo ganha
extensão pelo `content-type`.

### Quem instala continua sendo outro

`sistema.instalar` monta o plano e o token; `sistema.executar` exige o token,
`JARVIS_HOST_INSTALAR=1` e revalida o SHA-256. `instalador.*` não executa nada.

Detalhes em [`docs/INSTALADOR.md`](docs/INSTALADOR.md).

## 2. A leva do skills.sh em um pedido

A pergunta: *“e se eu pedir para ele adicionar essas melhorias [print do
skills.sh], ele vai pesquisar, puxar os dados e usar numa pergunta minha?”*

**Vai.** O caminho já existia (`habilidades.importar` + `habilidades.aplicar`);
agora tem a leva pronta:

> **“importa as 8 habilidades do skills.sh”**

`habilidades.pack` puxa o `SKILL.md` de cada uma pela API pública do GitHub:

| Nome | Repositório |
|---|---|
| `frontend-design` | `anthropics/skills` |
| `web-design-guidelines` | `vercel-labs/agent-skills` |
| `react-best-practices` | `vercel-labs/agent-skills` |
| `react-components` | `google-labs-code/stitch-skills` |
| `remotion` | `google-labs-code/stitch-skills` |
| `grill-me` | `RobMitt/grill-me-skill` |
| `grill-with-docs` | `Caph-dev/delegate-grill-with-docs` |
| `nano-banana-pro` | `YouMind-OpenLab/nano-banana-pro-prompts-recommend-skill` |

Testado de verdade: **8 de 8 importadas**, cada uma com categoria e descrição,
guardadas em `storage/habilidades.json`. Uma falha não derruba as outras — o
retorno diz o que entrou e o que falhou, com o motivo.

Para usar numa pergunta: **“usa a habilidade frontend-design para uma landing
page de estúdio de tatuagem”** → `habilidades.aplicar` devolve o texto da
habilidade junto com o seu pedido, mais o lembrete: *isto é roteiro em texto, não
código rodando*.

`find-skills` e `browser-use` ficaram de fora: o primeiro é comando do próprio
skills.sh, o segundo não existe mais em `vercel-labs/agent-skills` (o repositório
tem nove skills, nenhuma com esse nome). Em vez de inventar link, entra só o que
foi conferido.

## 3. As respostas que não mudam

- **Copilot:** não. Serviço de modelo pago, com assinatura e token — o projeto é
  sem chave de IA por decisão sua.
- **Habilidade não é código que roda.** Sem modelo, `frontend-design` é uma lista
  de conferência; `grill-me` é uma sequência de perguntas para você responder.
- **Gerar imagem (nano-banana) não acontece sem serviço de imagem.** O texto dos
  *prompts* é guardado; o efeito, não.
- **GitHub sim, Git não.** A camada `github.*` lê repositório público (60 pedidos
  por hora, sem token). `commit`, `push` e `clone` não estão no registro: o
  projeto lê e evolui o próprio código por `evoluir.*`, sem executar Git.

## 4. Números

- **269 skills** (4 de instalador + `habilidades.pack`).
- **2.511 testes** Python (+59) e **110** da interface.
- `test_instalador.py` — 40 testes com PE/MSI/MSIX montados à mão.
- Nenhum teste abre programa, baixa arquivo ou instala coisa alguma.

Conferir: `http://127.0.0.1:8000/api/health` → `"version": "0.55.0"` e
`"skills": 269`.
