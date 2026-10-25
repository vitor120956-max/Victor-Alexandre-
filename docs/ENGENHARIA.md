# Workflows de engenharia

## Origem e escopo

A versão 0.5.0 adapta oito capacidades inspiradas em [`addyosmani/agent-skills`](https://github.com/addyosmani/agent-skills), um catálogo MIT de fluxos de engenharia para agentes. A referência foi inspecionada no commit `aeac41d4d005999432bb7312f7ff06383a91d59d`.

O JARVIS não instala o plugin, não clona o catálogo em runtime e não executa seus hooks, scripts, comandos de Git ou agentes. Os workflows abaixo são implementações próprias em `server/engineering.py`, com contratos Pydantic e saídas locais. O aviso de licença MIT está preservado em [`licenses/addyosmani-agent-skills.txt`](licenses/addyosmani-agent-skills.txt).

Oito workflows foram adaptados; os 25 documentos do catálogo upstream não foram importados como um pacote. Na versão 0.5.0, o número **25 skills** correspondia às 17 skills anteriores mais estes oito módulos locais; o catálogo atual tem 208 skills, incluindo as quatro de engenharia enxuta, as seis de governo de agentes, as cinco de estúdio de design, as sete de direção de arte, as sete de diagramas, as sete de carreira, as sete de navegação assistida, as sete de escritório assistido e as sete de estação do agente, as sete da camada editorial de diagramas, as seis de curadoria, as sete de marketing e as sete de ciência; a 0.17.0 acrescentou o executor real da Estação, que não é skill, a 0.18.0 acrescentou a camada editorial, que decide tipo e mede arquivo sem desenhar, a 0.19.0 acrescentou o motor de curadoria de listas, que valida entrada, agrupa catálogo, deriva README, compara estrelas e audita higiene, e a 0.20.0 acrescentou o motor de marketing mensurável, que calcula funil, amostra, UTM, e-mail, SEO e limite de anúncio sem tocar a rede, e a 0.21.0 acrescentou o motor de rigor científico, que calcula poder, confere o relato, audita desenho e reprodutibilidade, valida método analítico e confere o manuscrito contra a diretriz, e a 0.22.0 acrescentou o motor de confiança em skill de terceiro, que lê a ficha, varre o risco, compara permissão declarada com a usada, confere a instalação, audita o índice e caça duplicata sem executar a skill, e a 0.23.0 acrescentou o motor de contexto, que mede tokens, divide a janela, corta por turno, saneia o histórico e contabiliza o uso sem chamar modelo. A 0.24.0 acrescentou o motor de seleção, que ranqueia um catálogo de milhares de skills com BM25, cobra cobertura por dimensão e valida a stack antes da instalação. A 0.25.0 acrescentou o motor de revisão de código, que lê o diff em hunks, classifica o escopo, agrupa lotes de leitura, confere a âncora de cada comentário, compara regra e agente e monta regra por caminho sem executar git nem publicar comentário. A 0.26.0 acrescentou o motor de submissão de artefatos, que lê o front matter por tipo, confere a estrutura do envio, varre nove regras de risco, valida a licença como expressão SPDX, checa link e âncora e decide o rótulo do envio sem instalar nada. A 0.27.0 acrescentou o motor de memória de agente, que roteia a via pela forma da pergunta, extrai entidade e relação sem modelo, mede grafo com ciclo e componente, destila a lição da sessão e recupera com lastro aberto antes de planejar o esquecimento por escopo. A 0.28.0 acrescentou o motor de portabilidade de skill, que audita o bundle, converte para treze ferramentas, mede deriva, caça colisão e monta o lote de marketplace. A 0.29.0 acrescentou o motor de continuidade de plano, que lê fases por dois formatos de status, aplica os guardas do portão de conclusão, reconstrói o estado pós-`/clear`, monta o bloco injetado e valida o livro append-only. A 0.30.0 acrescentou o motor de sistema, a única camada com efeito real: mede disco, enumera pastas sem ler conteúdo, lê drivers e Bluetooth, busca e lê páginas, baixa para quarentena com hash e executa instalador por allowlist — tudo atrás de token de host, rede desligada e trava de instalação. A 0.31.0 fechou o ciclo com verificação de assinatura e integridade — SHA-256 contra o hash publicado, Authenticode, rpm -K, dpkg-sig e gpg — mais o desinstalador simétrico, que reusa o mesmo token de uso único e revalida o hash do arquivo entre o plano e a execução. A 0.32.0 acrescentou o motor de evolução: o único que pode alterar o próprio código, e por isso o único que prova antes de escrever — aplica o diff, confere as dez guardas, roda a suíte numa cópia isolada e só então promove, com backup e token.

## Catálogo adicionado

| ID | Resultado | O que deliberadamente não faz |
|---|---|---|
| `engineering.spec` | Rascunho de especificação com requisitos, aceite, limites e alertas | Não aprova a especificação nem inicia implementação |
| `engineering.plan` | Fatias verticais ordenadas, dependências e checkpoints | Não executa os comandos de teste/build documentados |
| `engineering.tests` | Matriz unitária, negativa, integração e regressão | Não cria nem executa arquivos de teste |
| `engineering.review` | Sinais estáticos com linha, eixo e severidade | Não executa código, não acessa o repositório e não aprova segurança |
| `engineering.threat-model` | Perguntas STRIDE e casos de abuso por fronteira | Não declara a auditoria concluída |
| `engineering.webvitals` | Classificação de LCP, INP e CLS e próximos passos | Não coleta Lighthouse, CrUX ou RUM |
| `engineering.adr` | ADR em Markdown com alternativas e consequências | Não escolhe numeração definitiva nem aprova a decisão |
| `engineering.release` | Gate `BLOCKED` ou `READY_FOR_HUMAN_APPROVAL` | Não testa, publica, faz deploy ou rollback |

Todos são somente leitura: não possuem efeitos colaterais no registry, não exigem gravação e não chamam IA ou rede.

## Especificação e plano

### Especificação

A skill recebe objetivo, usuários, requisitos e critérios de aceite explicitamente. Ela não inventa métricas ausentes. Termos como “rápido”, “fácil” ou “robusto” geram alertas para revisão, e quantidade insuficiente de critérios também é sinalizada.

O resultado é sempre um **rascunho que requer aprovação humana**. Não há transição automática para planejamento ou código.

### Plano vertical

Cada linha de `requirements` representa uma fatia funcional. Dependências são opcionais e usam índices originais:

```text
2:1
3:1,2
```

Isso significa que a fatia 2 depende da 1, e a 3 depende da 1 e da 2. O algoritmo faz ordenação topológica estável e rejeita índices inexistentes, autorreferências e ciclos. Os comandos informados aparecem apenas como sugestões de verificação; `commandsExecuted` é sempre `false`.

## Matriz de testes

Cada critério gera quatro perspectivas:

- comportamento unitário e fronteiras;
- entradas inválidas e falhas;
- integração entre componentes;
- regressão por inversão da condição principal.

A matriz é uma proposta de cobertura, não evidência de execução. `testsExecuted` é sempre `false`, e o usuário deve registrar comandos e resultados reais.

## Revisão estática

A revisão aceita até 50.000 caracteres de Python, JavaScript, TypeScript, JSX ou TSX. Ela percorre o trecho localmente e procura padrões conhecidos, incluindo:

- avaliação/execução dinâmica e shell;
- possíveis segredos literais, sem repetir seus valores no relatório;
- SQL por interpolação e desserialização que exigem revisão;
- HTML direto e possíveis credenciais em `localStorage`;
- loops sem condição aparente de parada;
- logs, `any`, pendências e mudanças grandes.

Os achados são heurísticos e podem ter falsos positivos ou omitir problemas. “Nenhum padrão encontrado” não significa aprovação. O código nunca é executado, e `codeExecuted` é sempre `false`.

## STRIDE

O modelo de ameaças recebe ativos e até oito fronteiras declarados pelo usuário. Para cada fronteira, apresenta seis perguntas: spoofing, tampering, repudiation, information disclosure, denial of service e elevation of privilege.

As respostas e os controles precisam ser verificados no sistema real. `auditCompleted` é sempre `false`.

## Core Web Vitals

A classificação usa os valores fornecidos:

| Métrica | Bom | Precisa melhorar | Ruim |
|---|---:|---:|---:|
| LCP | ≤ 2.500 ms | ≤ 4.000 ms | > 4.000 ms |
| INP | ≤ 200 ms | ≤ 500 ms | > 500 ms |
| CLS | ≤ 0,100 | ≤ 0,250 | > 0,250 |

A origem `lab` gera aviso de que medição sintética não comprova experiência real. Para `field`, o tamanho da amostra é considerado nos avisos; a skill não calcula nem finge conhecer um p75. `measurementTaken` é sempre `false`.

## ADR

O ADR recebe contexto, decisão e consequências. Cada alternativa usa:

```text
Nome | prós | contras | motivo da rejeição
```

Dados incompletos geram pendências. `ADR-XXX` é um placeholder explícito para evitar inventar a numeração do projeto. A data usa o dia UTC do servidor. O status pode ser `Proposed` ou `Accepted`, mas o resultado continua exigindo revisão humana e preservação do histórico.

## Gate de release

São bloqueadores obrigatórios:

- testes e build/tipagem;
- revisão humana;
- verificação de segredos e dependências;
- rollback e monitoramento;
- performance quando a mudança afeta a interface;
- evidências fornecidas.

Documentação desmarcada gera alerta. Mesmo sem bloqueadores, a decisão é `READY_FOR_HUMAN_APPROVAL`, nunca “deploy autorizado” ou “publicado”. `deployExecuted` é sempre `false`, e as evidências são declarações não verificadas pela skill.

## Conversa

```text
revisar código python:
eval(entrada)

revisar código typescript:
const valor: any = entrada

avaliar web vitals LCP 2600 INP 180 CLS 0,05
```

O comando de revisão exige linguagem explícita. Comandos incompletos e atalhos como `criar ADR`, `matriz de testes` e `gate de release` orientam o uso de `/engenharia`, sem cair no fallback de IA.

## Interface

A página `/engenharia` apresenta os oito workflows e usa os formulários gerados dos schemas da API. Os resultados são Markdown copiável e dados estruturados. Não há escrita automática de specs, ADRs, planos ou releases no repositório.
