# IA local: o cérebro sem chave, dentro do pendrive (0.75.0)

A pergunta foi dupla:

> *“podemos colocar a ia local no pen drive?”*

e, para o caso de não dar:

> *“se não, me passe o link do portal do grok para mim poder pegar a chave”*.

As duas respostas são **sim**, e elas não competem: uma é o cérebro rápido
(alugado, grátis, precisa de internet), a outra é o cérebro que funciona com o
cabo de rede desligado (lento, mas é seu).

---

## 1. O que mudou no código (a parte que faltava)

Antes desta versão, o JARVIS exigia `JARVIS_AI_API_KEY` **mesmo** quando o
endereço era `127.0.0.1`. Na prática, isso impedia exatamente o que você pediu:
rodar tudo do pendrive, sem conta em lugar nenhum. O servidor local não tem
chave para dar, então a checagem reprovava sozinha.

Agora (`server/ai.py`):

| endereço em `JARVIS_AI_BASE_URL` | chave | resultado |
|---|---|---|
| `http://127.0.0.1:8080/v1` | ausente | **configurado** (modelo local) |
| `http://localhost:11434/v1` | ausente | **configurado** |
| `http://[::1]:8080/v1` | ausente | **configurado** |
| `http://192.168.0.10:8080/v1` | ausente | não configurado — é outro PC, e ali a chave continua valendo |
| `https://api.groq.com/openai/v1` | ausente | não configurado (o pedido só tomaria `401`) |
| qualquer um | presente | configurado, com `Authorization` no cabeçalho |

E o cabeçalho só é enviado quando existe chave: antes, ele ia vazio, e alguns
servidores locais recusam `Authorization:` em branco.

A tela mostra `(offline)` ao lado do nome do modelo quando é local — para você
saber que aquela resposta não passou por nuvem nenhuma.

---

## 2. O pendrive: o que cabe e o que não cabe

A parte honesta, porque isso decide a compra do cartão:

| peça | tamanho | vai para o pendrive? |
|---|---|---|
| `llama-server.exe` + DLLs | ~40 MB | **sim**, roda de onde estiver |
| `modelo.gguf` 1–3 B (4 bits) | 0,7–2 GB | **sim**, o seu pendrive tem 58 GB |
| o modelo **carregado** | o mesmo tamanho, em **RAM** | **não existe**: pendrive não é memória |

Ou seja: dá para levar o JARVIS **com** o cérebro para outro PC, que é a real
vantagem do pendrive. Mas, na hora de responder, o arquivo é lido do USB e
carregado na RAM. Um `.gguf` de 1,5 GB num USB 2.0 leva dezenas de segundos só
para carregar; num USB 3.0, poucos segundos. Se o mesmo arquivo couber no disco
interno, ele responde mais rápido de lá.

**Não** existe “rodar o modelo direto do pendrive”. Existe carregar mais devagar.

---

## 3. Quanto de cérebro cabe na sua máquina

Regra de bolso: em 4 bits, o arquivo ocupa ~0,7 GB por bilhão de parâmetros, e o
programa precisa de ~1 GB a mais para trabalhar.

| RAM do PC | modelo que dá para tentar | arquivo | resposta |
|---|---|---|---|
| 4 GB | 0,5–1 B (Qwen2.5-0.5B / Llama-3.2-1B) | 0,4–0,8 GB | 1–4 palavras/s |
| 8 GB | 1,5–3 B | 1–2 GB | 3–8 palavras/s |
| 16 GB | 7–8 B | 4–5 GB | 8–15 palavras/s |

Meça antes de baixar 2 GB:

```bat
powershell -c "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB"
```

Máquina de **2016 com Windows 1607** (o seu caso): o Ollama **não instala** (ele
pede build 19045+). O caminho que funciona é o **llama.cpp**, que vem em zip,
sem instalador. Build `win-x64`; se o PC for ARM, `win-arm64`; e se o
processador for anterior a 2011, a build `noavx` (as outras fecham com
“instrução ilegal”).

---

## 4. Como usar — sem decorar comando

### Pelo chat (o jeito do dono)

| você diz | o que acontece |
|---|---|
| “posso rodar a ia local no pendrive?” | estado: o que existe, o que falta, quanto ocupa |
| “baixa o modelo local” | pede confirmação; sem `url`, explica que precisa do endereço |
| “liga o modelo local” | escreve as três linhas no `.env` (com cópia do antigo) |
| “desliga o modelo local” | devolve o `.env` como estava |

Nada disso pede chave. `liga` e `desliga` pedem confirmação porque mexem em
`.env`; `estado` nunca pede.

### Pelo script (quando quiser barra de progresso)

```bat
cd /d D:\JARVIS
```

```bat
powershell -ExecutionPolicy Bypass -File modelo-local.ps1
```

Baixar (troque a URL por um `.gguf` de 1–3 B em 4 bits):

```bat
powershell -ExecutionPolicy Bypass -File modelo-local.ps1 -Baixar "https://.../modelo-q4_k_m.gguf"
```

Ligar (sobe o `llama-server`, espera a porta responder e aponta o `.env`):

```bat
powershell -ExecutionPolicy Bypass -File modelo-local.ps1 -Ligar
```

Desligar:

```bat
powershell -ExecutionPolicy Bypass -File modelo-local.ps1 -Desligar
```

Onde as peças moram:

```text
D:\JARVIS\ferramentas\llama\llama-server.exe   <- o programa (você descompacta)
D:\JARVIS\storage\modelo-local\*.gguf          <- o modelo (o script baixa)
D:\JARVIS\env.antes-do-modelo-local            <- cópia do .env (caminho de volta)
```

`storage\` fica fora do `manifest.json`, então 2 GB de modelo **não** entram na
atualização delta nem no Git.

---

## 5. O que este recurso **não** faz

- **não** fica no nível do assistente da nuvem em qualidade. Um modelo de 1–3 B
  responde bem a “resuma este texto”, “explique isso”, “traduza”; erra mais em
  raciocínio longo e código;
- **não** baixa sozinho na primeira vez. Alguém escolhe o modelo e o tamanho —
  escolher por você seria baixar 2 GB sem saber se cabe;
- **não** sobe o servidor quando o Windows reinicia. Continuam valendo
  `iniciar-jarvis.bat` e o `-Ligar` do script;
- **não** engana sobre velocidade: se o modelo não couber na RAM, o Windows
  passa a usar arquivo de paginação e a resposta vira minutos por frase;
- **não** substitui a chave do Groq. Ele é o plano B quando não há internet.

---

## 6. A recomendação, sem rodeio

O que deixa o JARVIS **perto** do nível de um assistente de nuvem é um modelo
grande — 70 B não cabe num PC de 4–8 GB. O caminho grátis para isso é alugar
pela API:

1. **Groq** — <https://console.groq.com/keys>. Grátis, sem cartão, chave `gsk_…`.
   Não confundir com **Grok/xAI** (<https://console.x.ai>), que é pago.
2. No JARVIS: `configurar-chave.py` com base
   `https://api.groq.com/openai/v1` e modelo `llama-3.3-70b-versatile`.
3. Teste com `configurar-chave.py --testar` — ele faz uma chamada real de 8
   tokens e responde em português, sem imprimir a chave.

E o modelo local fica como rede de segurança: quando não houver internet, o
JARVIS continua pensando — devagar, mas continua.
