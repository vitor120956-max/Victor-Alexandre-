# Pessoa — perfil com lastro

A 0.34.0 porta a parte determinística de **`titanwings/distilly`** (MIT, ~20 mil estrelas): um projeto que transforma material sobre alguém — mensagens, documentos, entrevistas, fontes públicas — em um *Person Profile* empacotado como skill para agentes.

O que foi portado é o que **não** precisa de modelo de linguagem: as quatro famílias, as dimensões que cada perfil precisa cobrir, o gate de treze checagens, a hierarquia de fonte por peso, a tabela de oito hospedeiros, a regra de slug portátil e o fluxo de correção.

O que **não** foi portado: o gerador de persona. O original escreve o perfil com um modelo; aqui a camada mede, confronta e recusa. O texto do perfil é seu — ou do modelo que você escolher —, e entra nesta camada para ser conferido.

## A regra

**Citação é prova, não enfeite.** Cada linha do perfil precisa apontar a linha de origem no material. Onde não há origem, a seção diz "não há evidência" em vez de preencher.

Isso não é preciosismo. Um perfil de pessoa é uma afirmação sobre alguém — o que essa pessoa decide, como fala, do que desconfia. Sem lastro, o perfil vira a sua memória projetada em outra pessoa, com a autoridade de um documento.

## As oito skills

| Skill | O que faz |
|---|---|
| `distilar.perfil` | Mede o corpus: linhas, palavras, fontes, evidências por dimensão, cobertura e lacunas |
| `distilar.dimensoes` | Publica as quatro famílias e as dimensões de cada uma, com os sinais lexicais usados |
| `distilar.esboco` | Monta o `SKILL.md` e o `manifest.json` propostos, com slug portátil e seção por dimensão |
| `distilar.qualidade` | Aplica as treze checagens na régua padrão ou estrita |
| `distilar.lastro` | Confere cada afirmação do perfil contra o material |
| `distilar.correcao` | Classifica o "ele não faria isso" e diz o que muda, exigindo evidência nova |
| `distilar.hospedeiros` | Mostra o caminho de skill nativo dos oito agentes compatíveis |
| `distilar.regras` | Catálogo: famílias, checagens, hospedeiros, limites e recusas |

Todas são de leitura: nenhuma grava arquivo, instala skill ou chama modelo. `distilar.regras` não pede token; as outras também não — esta camada não toca a máquina. Ela é a única do projeto que analisa texto puro do começo ao fim.

## As quatro famílias

| Família | Domínio | Dimensões |
|---|---|---|
| `colleague` | trabalho | padrões de decisão, padrão técnico, fluxo de trabalho, voz, comportamento no time, limites |
| `relationship` | pessoal | voz, gatilhos emocionais, conflito, reparo, memória afetiva, limites |
| `celebrity` | público | modelos mentais, decisões observáveis, DNA de expressão, genealogia intelectual, tensão interna, o que não sabe |
| `owner` | dono do agente | preferências, contexto de vida, rotina, limites, como quer ser tratado |

Cada dimensão tem uma lista de sinais lexicais — `decidi`, `prefiro`, `desculpa`, `não sei`, `contradiz`. Não é análise semântica: é o que dá para provar sem modelo, e o relatório diz isso nas limitações.

## Como o material é lido

```
>>> conversa-ana.txt
Ana: eu sempre prefiro revisar o PR antes de subir
Ana: desculpa a resposta seca de ontem, foi mal
>>> email-ana.md
```

- `>>> arquivo` abre uma fonte nova e entra no manifesto.
- `Autor: texto` marca uma fala; o resto vira linha de contexto.
- Tudo é contado: linhas, palavras, fontes, evidências por dimensão.

Cobertura por dimensão: **3 ou mais evidências** = coberta; **1 ou 2** = parcial; **zero** = ausente. Ausente não é erro do material — é informação: aquilo que você não tem.

## O gate de qualidade

Portado de `tools/research/quality_check.py` e `tools/research/merge_research.py`. Treze checagens, em duas réguas:

| Régua | O que exige |
|---|---|
| `budget-friendly` | modelos mentais (≥3 bullets), limites, DNA de expressão, fronteiras honestas, tensão interna, lastro (≥2 URLs com conteúdo), segurança de direito |
| `budget-unfriendly` | tudo acima **mais** genealogia intelectual, protocolo de agente, hierarquia de fonte (≥50% primária ou 3 primárias), cadeia de revisão, profundidade de validação, profundidade de pesquisa (≥6 arquivos, ≥8 URLs, ≥6 blocos de fonte, ≥6 trilhas) |

**Segurança de direito** reprova por bloco de código, linha em citação (`>` com mais de 25 palavras), marca de tempo `00:00:00` — qualquer coisa com cara de transcrição colada. O original usa a mesma heurística; aqui ela é `must`, porque reproduzir transcrição inteira é problema jurídico antes de ser problema de qualidade.

Hierarquia de fonte usa a anotação `source weight: 1-7` do original: 1–3 primária, 4–5 média, 6–7 baixa.

## O lastro

`distilar.lastro` pega cada bullet do perfil e procura, no material, a linha mais parecida por similaridade de palavras (Jaccard, limiar **0,18**). O que passa vira "com lastro" e mostra `fonte:linha`. O que não passa entra na lista de afirmações sem apoio.

Três recusas explícitas:

- citação acima de **240 caracteres** → `must`, problema de direito autoral;
- citação entre aspas que **não está** no corpus → `should`, aspas indicam fala literal;
- perfil sem nenhum bullet → `nice`, não há o que conferir.

O limiar foi calibrado à mão e está declarado nas limitações. Frase parafraseada pode ficar sem lastro — e isso é aceitável: o relatório pede revisão, não condena.

## O esqueleto

`distilar.esboco` devolve **proposta**, não arquivo:

- front matter com `name: distilly-<slug>`, descrição, versão;
- uma seção por dimensão, com o comentário `<!-- evidência: N linha(s) — estado -->`;
- onde não há evidência, a seção já vem escrita como *"Não há evidência sobre este ponto no material fornecido"*;
- `manifest.json` com slug, família, fontes, contagem por dimensão e SHA-256 do conteúdo.

O slug segue a regra do original: sem acento, minúsculo, hífen, até **40 caracteres**, e nomes reservados do Windows (`con`, `prn`, `aux`, `nul`, `com1`–`com9`, `lpt1`–`lpt9`) são recusados.

## A correção

O "ele não faria isso" é o evento mais importante da vida de um perfil — é quando o retrato erra na frente do dono. A skill classifica em quatro tipos e diz o que cada um muda:

| Tipo | Marcadores | O que muda |
|---|---|---|
| `fato` | "na verdade", "não foi", "data errada" | reescreve a afirmação e a citação de origem; sem origem, a afirmação sai |
| `voz` | "não fala assim", "soa artificial" | vocabulário, ritmo e exemplos, sem mudar julgamento |
| `julgamento` | "não faria", "não decidiria" | remove a regra atribuída e acrescenta o caso que a contradiz |
| `limite` | "não sabe", "fora da área" | acrescenta o tema em "o que não sabe" e remove a promessa |

Correção **sem evidência nova** é bloqueio (`must`): trocar uma afirmação sem lastro por outra sem lastro não melhora o perfil, só troca o erro.

## Os oito hospedeiros

Do `tools/hosts.json` do original:

| Agente | Pasta nativa | Invocação |
|---|---|---|
| Claude Code | `~/.claude/skills` | `/distilly` |
| OpenClaw | `~/.openclaw/workspace/skills` | `/distilly` ou `/skill distilly` |
| Hermes | `~/.hermes/skills/openclaw-imports` (gerados em `distilly-generated`) | `/distilly` |
| Codex | `~/.agents/skills` | `$distilly` ou `/skills` |
| DeepSeek Harness | `$DSH_HOME/skills` | `/distilly` |
| Pi | `~/.pi/agent/skills` | `/skill:distilly` |
| Grok Build | `~/.grok/skills` | `/distilly` |
| OpenCode | `~/.config/opencode/skills` | nativo, sem comando |

A skill calcula o caminho e **não instala nada**. Grok Bot não importa `SKILL.md` local — o próprio README do original diz isso, e a camada repete.

## O que ela recusa

- Escrever a persona: ela mede e confere, não inventa.
- Chamar modelo de linguagem.
- Baixar fonte: o material é colado.
- Instalar o perfil no agente.
- Copiar transcrição ou bloco longo.
- Afirmar parentesco, doença ou opinião íntima sem linha de origem.
- Aceitar correção sem evidência.

## Como usar, na ordem

1. **`distilar.perfil`** com o material e a família → veja o que está coberto e o que falta.
2. **`distilar.dimensoes`** se precisar conferir o que cada família exige.
3. **`distilar.esboco`** → copie o `SKILL.md` proposto e escreva as seções.
4. **`distilar.qualidade`** no texto final → corrija o que reprovar.
5. **`distilar.lastro`** → tire ou reescreva o que não tem apoio.
6. **`distilar.correcao`** quando alguém disser "ele não faria isso".
7. **`distilar.hospedeiros`** para saber onde instalar o resultado.

## Onde o limite está

1. **Busca lexical não entende ironia.** "Adoro quando quebra" entra como sinal positivo de "adoro".
2. **Cobertura mede ocorrência, não qualidade.** Três frases rasas cobrem uma dimensão.
3. **Passar no gate não prova fidelidade.** Prova que o perfil tem as seções e as fontes exigidas.
4. **O perfil é sempre um recorte.** O próprio projeto original diz: não clona a pessoa atrás do material — e eu repito, porque é a frase mais importante deste documento.
5. **Direito autoral é do material, não do perfil.** Resumir com citação curta e `fonte:linha` é o caminho; colar bloco é bloqueio.
