# JARVIS 0.75.0 — a IA que roda sem chave (e cabe no pendrive)

A pergunta, nas palavras do dono:

> *“podemos colocar a ia local no pen drive? se não, me passe o link do portal do
> grok para mim poder pegar a chave.”*

As duas respostas são **sim**. E a primeira estava travada por um detalhe do
próprio JARVIS, não pela falta de programa para baixar.

---

## 1. O que estava travado (e por que ninguém via)

O backend exigia `JARVIS_AI_API_KEY` para **qualquer** endereço. Inclusive
`127.0.0.1`. Só que servidor local não tem chave para dar — então o JARVIS
reprovava a própria máquina e dizia “IA externa não configurada”. Quem tentava o
caminho do pendrive batia nisso e desistia.

Agora:

| endereço | chave | estado |
|---|---|---|
| `127.0.0.1`, `localhost`, `[::1]`, `0.0.0.0`, `host.docker.internal` | não precisa | **configurado** |
| `192.168.x.x` (outro PC da rede) | precisa | sem chave, não configura |
| `https://api.groq.com/...` e afins | precisa | sem chave, não configura |

O cabeçalho `Authorization` só vai quando há chave: antes ia vazio, e servidor
local que valida cabeçalho recusava.

**Um arquivo, uma regra:** `server/ai.py`, função `e_local()`. Nada de heurística
por nome de provedor nem por modelo.

---

## 2. O que entrou

| peça | arquivo | o que faz |
|---|---|---|
| regra do endereço local | `server/ai.py` | `e_local()`, `configured` sem chave, `status().local` |
| tela | `src/components/ChatPanel.tsx` | mostra `(offline)` quando o cérebro é local |
| estado, download e `.env` | `server/ia_local.py` | `estado`, `baixar`, `ligar`, `desligar` |
| skill | `ia.local` | as quatro ações, com confirmação nas que escrevem |
| script | `modelo-local.ps1` | barra de progresso no download e `llama-server` com espera de porta |
| chat | `server/agente_local.py` | “posso rodar a ia local?”, “baixa o modelo local”, “liga/desliga o modelo local” |
| configurador | `configurar-chave.py --local` | não grava mais a chave de mentira `local` |

Total: **315 skills**.

---

## 3. O pendrive: o que é verdade

| peça | vai para o pendrive? | por quê |
|---|---|---|
| `llama-server.exe` + DLLs (~40 MB) | **sim** | é programa, roda de onde estiver |
| `modelo.gguf` (0,7–2 GB) | **sim** | `storage\modelo-local` fica fora do manifesto |
| o modelo **carregado** | **não existe** | na hora de responder, ele vai para a **RAM** |

Ou seja: dá para levar o JARVIS **com** o cérebro para outro PC — a vantagem real
do pendrive. Mas não existe “rodar o modelo direto do pendrive”: existe carregar
mais devagar. Num USB 2.0, 1,5 GB levam dezenas de segundos por carga.

Também não muda o que já se sabia: **o Ollama não instala** no Windows 1607; o
caminho é o `llama.cpp` em zip.

---

## 4. O que o JARVIS não faz por você — de propósito

- **não escolhe o modelo.** Escolher errado é baixar 2 GB e descobrir que não
  cabe na RAM. O tamanho e a URL vêm de você (ou do chat com confirmação);
- **não sobe o `llama-server` quando o Windows liga.** O `-Ligar` sobe e espera
  a porta; reiniciar o PC continua exigindo o passo;
- **não baixa acima do limite** (8 GB por padrão, `JARVIS_MODELO_MAXIMO`) nem
  começa com menos de 512 MB livres — e apaga o `.parcial` se a conexão cair;
- **não apaga modelo antigo.** Trocar de modelo é decisão sua;
- **não promete qualidade de nuvem.** 1–3 B responde bem a resumir e explicar;
  erra mais em raciocínio longo e código.

---

## 5. O link que você pediu

O portal que você chamou de “grok” tem dois nomes parecidos, e só um é grátis:

| portal | endereço | preço |
|---|---|---|
| **Groq** (o grátis) | <https://console.groq.com/keys> | grátis, sem cartão, chave `gsk_…` |
| **Grok / xAI** | <https://console.x.ai> | pago |

No JARVIS, o Groq entra com base `https://api.groq.com/openai/v1` e modelo
`llama-3.3-70b-versatile`:

```bat
cd /d D:\JARVIS
```

```bat
.venv\Scripts\python configurar-chave.py
```

E o teste que não imprime a chave:

```bat
.venv\Scripts\python configurar-chave.py --testar
```

**A recomendação, sem rodeio:** use o Groq como cérebro — é o único caminho
grátis para um modelo de 70 B, que é o que fica perto do nível de um assistente
de nuvem. O modelo local é a rede de segurança: quando não houver internet, o
JARVIS continua pensando, devagar.

---

## 5.1. Uma correção de arrumação, para não mentir em comentário

O bump de versão deste projeto sempre trocou `0.x` por `0.y` em **todo** texto,
inclusive onde o número conta história (“até a versão X o debloat só
diagnosticava”). Nesta versão isso foi contido: 19 comentários que descrevem
fatos de versões anteriores voltaram ao número que tinham, em vez de virarem
“bug da 0.75.0” sem nunca ter havido bug. Não é cosmético — quem lê o código
depois de um erro precisa que o número no comentário aponte para o passado
certo.

## 6. Como conferir que está tudo de pé

```bat
cd /d D:\JARVIS
```

```bat
powershell -ExecutionPolicy Bypass -File modelo-local.ps1
```

Saídas possíveis e o que significam:

| saída | significa |
|---|---|
| “não há arquivo .gguf” | falta o modelo — `-Baixar` ou a skill `ia.local` |
| “nada está escutando em …” | `.env` pronto, faltou `-Ligar` |
| “Modelo local de pé em …” | funcionando sem chave nenhuma |

E, no chat: *“posso rodar a ia local no pendrive?”* — a resposta sai do estado
real da máquina, não de um texto fixo.
