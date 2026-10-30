# JARVIS 0.63.0 — Estudo: o laço que faltava

A lista que você mandou tem 20 projetos. Antes de escrever código, li o que cada
um faz de diferente — e a maior parte do que está lá **o seu JARVIS já tem**:

| da lista | o que é | já existia aqui |
| --- | --- | --- |
| `pbakaus/impeccable`, `nutlope/hallmark` | vocabulário de design, anti-“slop” | `taste.*` (29 regras lexicais, júri, tells) e `studio.critique` |
| `obra/superpowers` | metodologia de skills de agente | `habilidades.*`, `engineering.*`, `planning.gate` |
| `anythingllm` | workspaces com RAG | `biblioteca.*`, `curadoria.*` |
| `vinodrajvtr/jarvis-ui` | framework de plugins de UI | o registro de 299 skills já é isso |
| `OpenJarvis`, `Marvell`, `MARK-1`, `JARVIS-OS` | assistente local, voz, HUD | API local, `agente_local` e 299 skills — mas sem **voz** e sem **laço de aprendizado** |
| `hkuds/deeptutor` | tutoria como **laço**: material → pergunta → resposta → retorno | **nada** |

Foi essa última linha que virou trabalho. O resto era vitrine.

## O que entrou: `estudo.*`

Repetição espaçada local, determinística, sem modelo e sem chave. Cinco skills:

| skill | o que faz |
| --- | --- |
| `estudo.baralhos` | lista baralhos, quantos vencem hoje, quantos são novos |
| `estudo.adicionar` | vira material em cartões (ou aceita cartão à mão) |
| `estudo.revisar` | os cartões vencidos, do mais atrasado para o menos |
| `estudo.responder` | registra a nota e agenda o retorno (SM-2) |
| `estudo.progresso` | boletim: retenção, sequência de dias, o que mais erra |

### Material vira cartão por padrão de frase, não por “resumo com IA”

Três padrões explícitos, e **nada** fora deles:

- **definição** — `Direito civil é o ramo que regula…` → *O que é Direito civil?*
- **verbete** — `**Posse**: é o exercício de fato…` ou `Prescrição — perda do direito…`
  → *O que é Posse?* (e o verso perde o “é” repetido)
- **título + primeiro parágrafo** → *Segundo o material, o que se diz sobre X?*

Duas travas que existem porque o contrário é pior que não fazer nada:

1. **termo com mais de 6 palavras não vira pergunta.** Sem isso, “Segundo
   parágrafo que não deve virar cartão nenhum **porque é** longo demais” virava
   *O que é Segundo parágrafo que … porque?* — pergunta sem sentido.
2. **o relatório diz quantas linhas foram ignoradas.** Se 90% do texto é
   descartado, você vê o número em vez de descobrir depois que o baralho tem
   dois cartões.

### SM-2 de verdade

Cada resposta tem nota (`errei`, `difícil`, `bom`, `fácil` ou 0–5). A nota mexe
na **facilidade** do cartão e no **intervalo**:

- errou → volta **amanhã** e a sequência zera;
- acertou 1ª vez → 1 dia; 2ª → 6 dias; depois → `intervalo × facilidade`;
- a facilidade sobe com acerto e cai com erro, com piso em 1,3.

É o algoritmo do SuperMemo 2, escrito aqui em 30 linhas, com teste para cada
regra. Nada de “+1 dia sempre”, que é o que a maioria dos apps de flashcard faz.

### Boletim medido, não elogio

Retenção (`acertos ÷ respostas`), cartões vencidos, novos, dias estudados,
sequência de dias seguidos e os **cartões que mais erram**.

E uma frase que vale mais que o gráfico: cartão que erra sempre quase nunca é
memória ruim — é material ruim. A tela manda reescrever a pergunta.

## A tela

`/estudo` (menu **Estudo**), no mesmo desenho do resto:

- **Sessão de hoje** — a pergunta, o botão *Mostrar resposta*, e as quatro notas
  com o que cada uma significa (“volta amanhã”, “some por semanas”);
- **Material novo** — cole o resumo, escolha o baralho, veja *quantos entraram,
  quantos eram repetidos e quantas linhas foram ignoradas*;
- **Seus baralhos** — vencidos por baralho, e a lista do que mais erra.

Estado offline é dito na cara: sem API, a tela não finge que leu nada.

## O que eu não fiz, e por quê

- **voz** (MARK-1, Marvell): dá para fazer com a Web Speech API, mas isso não
  tem teste automatizado confiável e o navegador muda de comportamento entre
  versões. Fica para quando você pedir — e com o aviso de que é o Chrome/Edge
  que implementa, não o Windows.
- **HUD 3D, globos, temas** (MARK-1, JARVIS-OS): é vitrine. O valor está no que
  o assistente resolve, não no que ele gira na tela.
- **RAG de novo** (anythingllm): `biblioteca.*` já indexa, busca e cita.

## Testes

- `pytest server/tests` → **2.927 passed** (`test_estudo.py`: 29).
- Os testes travam: os três padrões de geração, o filtro de 6 palavras, o verso
  sem “é” repetido, o contador de linhas ignoradas, deduplicação por frente,
  arquivo corrompido virando estudo vazio, cada regra do SM-2 (1 dia, 6 dias,
  `intervalo × facilidade`, erro zerando sequência, piso da facilidade), o laço
  completo (revisar → responder → some da fila), retenção, sequência de dias e
  os cartões fracos.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
- Skills: **294 → 299**.

A referência está no cabeçalho de `server/estudo.py`: DeepTutor (HKUDS) para a
ideia do laço; SM-2 é do SuperMemo 2 (Piotr Woźniak, 1987). Nenhum código de
fora foi copiado ou executado.
