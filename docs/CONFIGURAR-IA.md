# Configurar a IA externa

A camada generativa é opcional. As skills locais e Python não dependem dela.

## 0. De onde vem a IA: chave grátis ou modelo local

**Não existe chave grátis da OpenAI.** A OpenAI não tem mais camada gratuita de API desde 2024. Todo site que oferece "chave OpenAI grátis" está revendendo chave vazada ou compartilhada: ela para de funcionar em horas e todo mundo que a usa lê o que você escreve. Não use.

O JARVIS fala o formato **OpenAI Chat Completions**, então serve qualquer provedor compatível. Estes três têm camada gratuita de verdade e **não pedem cartão**:

| Provedor | O que é grátis | Base para o `JARVIS_AI_BASE_URL` | Onde pegar a chave |
|---|---|---|---|
| **Groq** | 30 req/min e cerca de **1.000 requisições por dia** nos modelos abertos | `https://api.groq.com/openai/v1` | <https://console.groq.com/keys> |
| **Google AI Studio** (Gemini) | cota diária por modelo, mostrada no próprio painel | `https://generativelanguage.googleapis.com/v1beta/openai` | <https://aistudio.google.com/apikey> |
| **OpenRouter** | **50 req/dia** em modelos com `:free` no nome (1.000/dia depois de comprar US$ 10 em créditos, uma vez só) | `https://openrouter.ai/api/v1` | <https://openrouter.ai/keys> |

Números conferidos em **25/10/2026**. Limite de camada gratuita muda sem aviso; o painel do provedor manda mais que esta tabela.

### Privacidade de cada um

| Provedor | Usa suas conversas para treinar? |
|---|---|
| Groq | **não** por padrão |
| OpenRouter | depende do modelo de origem; os `:free` variam |
| Google AI Studio | **sim** na camada gratuita, fora da União Europeia, Reino Unido e Suíça — o Brasil entra nessa |

Se a conversa tiver dado sensível, prefira o Groq ou simplesmente não configure IA externa: as 229 skills locais continuam funcionando sem chave nenhuma.

### Passo a passo — Groq (o mais rápido, ~3 minutos)

1. Abra <https://console.groq.com/keys>.
2. Crie a conta com e-mail ou com a conta do Google. **Não pede cartão.**
3. Clique em **Create API Key**, dê um nome qualquer (ex.: `jarvis`) e confirme.
4. **Copie a chave agora** — ela aparece uma vez só, começando com `gsk_`. Se perder, crie outra.
5. Anote também o **nome do modelo** que aparece em *Models* no menu. Use o identificador exato, sem inventar.

Depois, no `cmd`:

```bat
cd /d D:\JARVIS
.venv\Scripts\python configurar-chave.py
```

Responda:

```text
Provedor [OpenAI]: Groq
Base da API [https://api.openai.com/v1]: https://api.groq.com/openai/v1
Modelo [gpt-4o-mini]: nome-que-voce-copiou-do-painel
Chave (não aparece ao digitar): gsk_...
```

### Passo a passo — Google AI Studio

1. Abra <https://aistudio.google.com/apikey> com a sua conta Google.
2. **Create API key** num projeto novo. **Não pede cartão.**
3. Copie a chave (começa com `AIza`).
4. No `configurar-chave.py`, use provedor `Gemini`, base `https://generativelanguage.googleapis.com/v1beta/openai` e o modelo no formato `gemini-...` que o painel mostrar.

Não acrescente `/chat/completions` na base: o servidor põe esse caminho sozinho. Barra sobrando no fim é removida pelo script.

### Passo a passo — OpenRouter

1. Abra <https://openrouter.ai/keys> e entre com e-mail ou GitHub.
2. **Create Key**, copie (começa com `sk-or-v1-`).
3. Provedor `OpenRouter`, base `https://openrouter.ai/api/v1`.
4. O modelo **precisa** terminar em `:free`, por exemplo `nvidia/nemotron-3-super:free`. **Não esqueça o `:free`, ou a chamada vira cobrança.**

### Confira antes de reiniciar o servidor

```bat
.venv\Scripts\python configurar-chave.py --testar
```

Ele faz uma chamada real de 8 tokens e responde em português:

| Saída | Significa |
|---|---|
| `FUNCIONOU. O modelo respondeu: ...` | chave, base e modelo estão certos |
| `a chave foi recusada (HTTP 401)` | copiou a chave pela metade ou ela foi apagada |
| `base ou modelo não encontrado (HTTP 404)` | nome do modelo errado — copie de novo do painel |
| `cota ou limite de requisições estourado (HTTP 429)` | acabou a cota do dia; espere ou troque de provedor |
| `Falhou na conexão` | internet, proxy ou firewall bloqueando |

O teste não imprime a chave. Você pode rodá-lo quantas vezes quiser.

### Modelo local: sem chave, sem limite e sem internet

**Você não é obrigado a ter chave.** A camada de IA é opcional: sem chave nenhuma, as **229 skills** locais, a legislação, os documentos, a memória e as tarefas continuam funcionando. O que fica de fora é só o chat aberto (`IA EXTERNA`) e o `distilar.persona`.

Se você quer o chat também, sem chave e sem limite de requisições, dá para rodar o modelo **na sua máquina**. O custo não é dinheiro, é RAM e paciência: a resposta sai bem mais devagar que num provedor de nuvem.

**O Ollama — o caminho mais fácil — não roda no seu Windows.** A documentação dele pede **Windows 10 22H2 (build 19045) ou mais novo**; o seu é o build **14393 (1607)**, de 2016. Não é limitação do JARVIS, é do instalador.

| Programa | Como vem | Roda no Windows 1607? | Endereço padrão |
|---|---|---|---|
| **llama.cpp** (`llama-server.exe`) | zip, sem instalador | provavelmente sim (binário `x64` genérico, sem AVX2) | `http://127.0.0.1:8080/v1` |
| **KoboldCpp** | um `.exe` só | provavelmente sim | `http://127.0.0.1:5001/v1` |
| LM Studio | instalador grande | incerto, costuma pedir Windows mais novo | `http://127.0.0.1:1234/v1` |
| Ollama | instalador | **não** | `http://127.0.0.1:11434/v1` |

"Provavelmente" é o máximo que se pode dizer sem testar na sua máquina. **Meça antes de baixar 2 GB.**

### Meça a máquina primeiro

```bat
powershell -c "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB; (Get-CimInstance Win32_Processor).Name; (Get-CimInstance Win32_Processor).NumberOfCores"
```

```bat
wmic logicaldisk get caption,freespace
```

A primeira linha é a RAM em GB, a segunda o processador, a terceira quantos núcleos. A quarta mostra o espaço livre de cada disco, em bytes (`10737418240` = 10 GB).

| RAM | Modelo que cabe (quantizado em 4 bits) | Como fica |
|---|---|---|
| 4 GB | 1–2 bilhões de parâmetros (~1 GB de arquivo) | responde, mas devagar e simples |
| 8 GB | 3–4 bilhões | usável para conversa curta |
| 16 GB | 7–8 bilhões | confortável |
| 32 GB | 13–14 bilhões | bom |

Regra de bolso: o arquivo do modelo ocupa mais ou menos **0,7 GB por bilhão de parâmetros** em 4 bits, e o programa precisa de mais ~1 GB para trabalhar.

### Máquina antiga e pouca RAM: o que esperar

Se a sua máquina tem **4 GB de RAM e um processador anterior a 2011**, o modelo local funciona, mas devagar — e vale saber os números antes de baixar 2 GB.

| RAM total | Modelo que dá para tentar | Arquivo (4 bits) | Velocidade esperada |
|---|---|---|---|
| 4 GB | 0,5 bilhão de parâmetros | ~0,4 GB | 1 a 4 palavras por segundo |
| 4 GB | 1 bilhão | ~0,7 GB | 1 a 2 palavras por segundo |
| 8 GB | 1 a 3 bilhões | 0,7 a 2 GB | 3 a 8 palavras por segundo |
| 16 GB | 7 a 8 bilhões | 4 a 5 GB | 8 a 15 palavras por segundo |

São estimativas de CPU, não medições: dependem do modelo e de quanta memória o Windows já está usando. Some a isso o navegador aberto, que sozinho come 1 GB.

**Processador sem AVX (Intel Core 2, Pentium, Athlon antigos):** os binários `avx2` e `avx` fecham com *"instrução ilegal"*. Baixe o pacote **`noavx`** do llama.cpp (`llama-bXXXX-bin-win-noavx-x64.zip`); ele é lento de propósito, mas não usa instrução que a máquina não tem. Core 2 Quad é de 2007–2008: **não tem AVX**, então é essa a versão.

**Onde guardar o arquivo:** no disco com mais espaço livre, não necessariamente o do projeto. O `.gguf` é lido do disco local o tempo todo, então pendrive e rede deixam tudo mais lento.

### Google Drive não resolve falta de RAM

Vale dizer porque é uma confusão comum: o Drive é **armazenamento**, não memória nem processador. O modelo precisa ser carregado inteiro na RAM a cada resposta; deixar o arquivo no Drive só faz você baixá-lo de novo antes de rodar. Não existe "rodar o modelo direto do Drive".

Onde o Drive ajuda de verdade neste projeto:

| Uso | Como |
|---|---|
| **Backup** das suas memórias, tarefas e documentos | copiar a pasta `storage/` para o Drive de vez em quando |
| **Fonte de arquivos** para a skill `files.import` | instalar o *Drive para desktop*, que cria uma unidade local; o JARVIS lê como qualquer pasta |

O *Drive para desktop* pede Windows 10 64 bits e, desde a versão 117, o **WebView2** — que em Windows 10 muito antigo (1607, 1709) pode não instalar. Se não instalar, o caminho é baixar os arquivos pelo navegador e importar da pasta Downloads, que é o que a skill já faz.

### Apontar o JARVIS para o servidor local

Suba o `llama-server` (ou o KoboldCpp) e, noutra janela:

```bat
cd /d D:\JARVIS
.venv\Scripts\python configurar-chave.py --local
```

Ele já preenche a base com `http://127.0.0.1:8080/v1` e grava a chave `local`; só pergunta o nome do modelo. Se o seu servidor estiver noutra porta, informe:

```bat
.venv\Scripts\python configurar-chave.py --local http://127.0.0.1:5001/v1 --modelo nome-do-modelo
```

> **Por que uma "chave" se não existe chave?** O JARVIS só considera a IA configurada quando os quatro campos têm valor. Servidores locais ignoram o cabeçalho `Authorization`, então o valor `local` é só um marcador. Sem ele, o painel fica em NÃO CONFIGURADA mesmo com o servidor no ar.

Confira com `--testar`, como nos provedores de nuvem: ele faz uma chamada de verdade e responde `FUNCIONOU` ou o motivo.

Nesse modo, **nada sai da sua máquina**: nem a pergunta, nem as conversas, nem o contexto. É o único caminho em que o "local-first" do projeto vale também para o chat.

## 1. Escolha um provedor compatível

O backend chama `POST {JARVIS_AI_BASE_URL}/chat/completions` com o formato OpenAI Chat Completions. Consulte a documentação do provedor escolhido para obter:

- a base da API compatível;
- o nome exato do modelo;
- uma chave com o menor escopo e limite de gasto adequado.

Não use uma chave de administrador e não compartilhe a credencial no chat.

## 2. Crie o arquivo de ambiente no servidor

O caminho mais seguro é o script do projeto: ele pergunta os campos, pede a chave **sem ecoar** (nada de chave no histórico do terminal) e grava o `.env` com a quebra de linha do Windows.

```bash
.venv/bin/python configurar-chave.py
```

```bat
.venv\Scripts\python configurar-chave.py
```

`--ver` mostra a configuração atual com a chave mascarada; `--limpar` apaga só a chave, mantendo o resto do arquivo.

Na mão:

```bash
cp .env.example .env
```

Edite `.env`:

```dotenv
JARVIS_AI_PROVIDER=Nome exibido na interface
JARVIS_AI_BASE_URL=https://api.exemplo.com/v1
JARVIS_AI_MODEL=modelo-disponivel-na-sua-conta
JARVIS_AI_API_KEY=valor-da-chave
```

Não inclua `/chat/completions` na base: o backend acrescenta esse caminho. O `.env` já está no `.gitignore`.

## 3. Reinicie e verifique

O `.env` só é lido na inicialização: pare o processo e suba de novo.

```bash
npm run dev
```

Abra **Configurações → Inteligência generativa**. O painel deve mostrar `CONFIGURADA`, o provedor e o modelo. Também é possível verificar o status público, que nunca inclui a chave:

```bash
curl http://127.0.0.1:8000/api/ai/status
```

## 4. Teste uma pergunta aberta

Na conversa, envie uma pergunta que não seja um comando local. A resposta deverá exibir a marca `IA EXTERNA`. Comandos como `calcular 8 * 7` continuam locais, e `analisar texto ...` continua usando Python. Consultas como `artigo 49 do CDC` e `pesquisar na legislação sobre privacidade` usam o corpus local e não são enviadas ao provedor.

## Privacidade

Por padrão, a IA recebe a pergunta e até 12 mensagens recentes, mas não recebe sua lista de tarefas ou notas. Para permitir esse contexto, ative **Compartilhar tarefas e notas como contexto**. Desative essa opção se a conversa tratar de dados sensíveis.

## Diagnóstico

- **NÃO CONFIGURADA:** revise os nomes das variáveis e reinicie o processo.
- **HTTP 401/403:** confira a chave e as permissões no provedor.
- **HTTP 404:** revise a base e o nome do modelo.
- **HTTP 429:** aguarde ou revise cota e limites de gasto.
- **Timeout/conexão:** verifique se o ambiente do servidor tem rota de saída para o provedor.

Os erros de resposta do provedor não são copiados integralmente para a interface, para reduzir risco de vazamento de dados.
