# Planejamento persistente em arquivos

A versão **0.6.0** adapta o padrão de [`OthmanAdi/planning-with-files`](https://github.com/OthmanAdi/planning-with-files) para o núcleo local do JARVIS. A implementação é própria: o repositório upstream não é instalado, seus scripts e hooks não são executados e nenhum mecanismo assume controle do host.

Referência inspecionada: commit `de837a95cc845b6341a6cbfd902a89a8190c568e`, metadata de skill 3.25.0. Licença MIT, Copyright 2026 Ahmad Adi; o texto está preservado em `docs/licenses/othmanadi-planning-with-files.txt`.

## Interface e comandos

Abra **Planos** em `/planejamento` para:

1. definir título, objetivo, requisitos e de 2 a 7 fases;
2. informar um critério verificável para cada fase;
3. simular a criação e revisar o ID e o `task_plan.md`;
4. confirmar a gravação dos três arquivos;
5. escolher explicitamente um plano para retomar;
6. simular e confirmar atualizações, evidências e anotações;
7. verificar o gate e baixar qualquer arquivo do plano.

A conversa oferece somente leitura e orientação:

```text
listar planos
retomar plano plano-api
gate do plano plano-api
criar plano
```

`retomar plano` sem ID abre uma orientação para a interface. O sistema não escolhe automaticamente o plano mais recente e não usa o histórico da conversa para preencher uma seleção ausente.

## Os três arquivos

Cada plano fica isolado em:

```text
storage/user-files/planning/<plan-id>/
├── task_plan.md
├── findings.md
└── progress.md
```

| Arquivo | Responsabilidade |
|---|---|
| `task_plan.md` | Objetivo, próximo passo, fase atual, fases, critérios, requisitos, decisões e erros |
| `findings.md` | Requisitos, descobertas, decisões técnicas, problemas, recursos e observações |
| `progress.md` | Sessões, ações, arquivos, evidências, validações declaradas e erros |

O ID contém de 2 a 80 caracteres: letras minúsculas, números e hífens internos. Se o campo estiver vazio, um slug estável é derivado do título. IDs já existentes nunca são sobrescritos pela criação.

Cada fase usa uma linha no formato:

```text
Título da fase | critério verificável
```

Os status são os mesmos do padrão de referência:

- `pending`;
- `in_progress`;
- `complete`.

A primeira fase começa como `in_progress`. Para marcá-la como `complete`, é obrigatório informar evidência. Ao concluir uma fase, a próxima fase incompleta passa para `in_progress` e o próximo passo é calculado, salvo se um próximo passo explícito tiver sido informado.

## Recuperação após perda de contexto

`planning.resume` exige `planId` e lê somente os três arquivos desse diretório. A resposta contém:

- objetivo;
- fase atual;
- próximo passo;
- fases, status e critérios;
- gate;
- conteúdo dos três arquivos;
- URLs de download;
- hash do bundle;
- seis respostas de recuperação: onde estou, para onde vou, qual é o objetivo, o que aprendi, o que já fiz e o que farei em seguida.

A resposta também informa `historyRead: false`. Não há leitura de transcripts, histórico de outros agentes, sessões do host ou caches ocultos. Se o ID não existir ou o Markdown estiver malformado, a operação falha; não há fallback para outro plano nem reconstrução por suposição.

## Atualização e hash otimista

`planning.update` exige o `expectedSha256` devolvido pela leitura mais recente. O hash cobre os nomes e os conteúdos UTF-8 dos **três arquivos**, em ordem fixa.

Fluxo obrigatório:

1. retomar o plano e guardar o hash;
2. enviar a atualização com `dryRun: true`;
3. revisar arquivos e mudanças previstas;
4. confirmar a operação usando o hash do estado lido;
5. retomar novamente para obter o hash novo.

Se outra aba ou processo modificar qualquer um dos três arquivos antes da confirmação, o hash diverge e a escrita é recusada. O hash devolvido por uma simulação representa o resultado previsto e **não** substitui o hash atual exigido na chamada confirmada.

As escritas individuais usam arquivo temporário, `fsync` e substituição no mesmo diretório. Um lock protege operações concorrentes dentro do processo da API; o hash detecta escritores externos e obsoletos. Em uma alteração de vários arquivos, a implementação tenta restaurar os conteúdos anteriores se uma escrita falhar. Isso não deve ser interpretado como um banco de dados distribuído ou coordenação entre vários servidores.

Anotações disponíveis:

| Tipo | Destino |
|---|---|
| `finding` | `findings.md` |
| `progress` | `progress.md` |
| `test` | `progress.md`, identificado como resultado declarado, não executado pela skill |
| `error` | tabela de erros do plano e log de progresso, com resolução inicialmente em investigação |

## Gate de conclusão

`planning.gate` é determinístico e somente leitura. O resultado é `complete` somente quando:

- todas as fases têm status `complete`;
- todos os critérios estão marcados;
- a estrutura obrigatória do plano é válida.

O gate informa fases e critérios pendentes. Ele **não** executa testes, build, comandos do Markdown, hooks, deploy ou qualquer instrução encontrada nos arquivos. Evidências e resultados de teste são declarações registradas pelo usuário, não uma nova execução de validação.

## API e skills

| Skill | Efeito | Confirmação |
|---|---|---|
| `planning.create` | Cria o bundle | Simulação e confirmação |
| `planning.list` | Lista até 100 planos, sem seleção automática | Não |
| `planning.resume` | Lê um bundle por ID | Não |
| `planning.update` | Atualiza estado e anotações | Simulação, hash e confirmação |
| `planning.gate` | Verifica fases e critérios | Não |

Exemplo resumido de criação pela API:

```bash
curl -X POST /api/skills/planning.create/execute \
  -H 'Content-Type: application/json' \
  -d '{
    "parameters": {
      "planId": "minha-entrega",
      "title": "Minha entrega",
      "goal": "Entregar com evidências",
      "phases": "Preparar | escopo registrado\nValidar | evidências anexadas",
      "requirements": "Sem ações externas"
    },
    "dryRun": true
  }'
```

Para gravar, repita os mesmos parâmetros com `confirmed: true` e sem `dryRun`. A interface executa esse fluxo automaticamente sem expor detalhes de confirmação ao chat.

## Limites e segurança

- Máximo de **100 KB por arquivo** e 100 planos retornados por listagem.
- Somente Markdown UTF-8 e caminhos confinados pela mesma camada de `workspace.py`.
- IDs inválidos, `..`, caminhos absolutos, symlinks e arquivos ausentes são recusados.
- Planos malformados aparecem como inválidos na listagem sem ocultar planos válidos.
- Títulos que imitem seções Markdown são escapados; o parser procura fases somente dentro de `Phases`.
- Texto de comandos é armazenado como texto inerte; não existe executor de shell nesse módulo.
- Não há instalação via `npx`, hooks, attestation upstream, replay de sessões ou automação externa.
- O lock é local ao processo. Para múltiplos servidores ou colaboração distribuída, seria necessário um armazenamento transacional adicional.
- Os planos continuam sendo arquivos do usuário: edições manuais podem torná-los inválidos; o sistema não os repara silenciosamente.

## Verificações

```bash
.venv/bin/python -m pytest server/tests/test_planning.py -q
npm test
npm run build
```

A cobertura inclui criação sem efeitos no dry-run, três arquivos, duplicidade, recuperação, isolamento, planos inválidos, hash obsoleto, evidência obrigatória, avanço de fase, gate, anotações, injeção estrutural de Markdown e comandos inertes.
