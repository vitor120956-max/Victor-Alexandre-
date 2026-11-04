# JARVIS 0.76.1 — pôr as três chaves sem digitar 56 caracteres no escuro

Esta versão existe por um motivo prático: as três chaves já estão anotadas no
arquivo `cerebro javis 1 e 2 e 3.txt`. Digitar isso três vezes na janela preta,
sem ver o que se digita, é onde se perde uma letra — e aí o JARVIS responde
`401` e parece que a chave é ruim.

Agora o `configurar-chave.py` **lê o arquivo** e aproveita só o que tem cara de
chave.

---

## O passo a passo (uma vez só)

### 1. Abra a janela do JARVIS

```bat
cd /d D:\JARVIS
```

### 2. Confira que as três chaves são reconhecidas — sem gravar nada

```bat
.venv\Scripts\python configurar-chave.py --arquivo "cerebro javis 1 e 2 e 3.txt" --so-mostrar
```

Saída esperada:

```text
Achei 3 chave(s) em cerebro javis 1 e 2 e 3.txt.
```

Se aparecer menos que três, o arquivo está com alguma linha cortada — abra,
confira, e rode de novo. **Este passo não altera nada.**

> Erro comum: o arquivo precisa estar na pasta `D:\JARVIS`. Se estiver em
> `Downloads`, arraste o arquivo para dentro da janela preta em vez de digitar
> o caminho — o Windows escreve o caminho completo por você.

### 3. Grave as três

```bat
.venv\Scripts\python configurar-chave.py --arquivo "cerebro javis 1 e 2 e 3.txt"
```

Ele não pergunta nada quando o arquivo é do Groq: já preenche
`provedor = Groq`, `base = https://api.groq.com/openai/v1` e
`modelo = llama-3.3-70b-versatile`. Saída:

```text
Achei 3 chave(s) em cerebro javis 1 e 2 e 3.txt.
Gravado em D:\JARVIS\.env
  provedor: Groq
  base:     https://api.groq.com/openai/v1
  modelo:   llama-3.3-70b-versatile
  chave:    3 chaves: gsk_a…XXXX (56 caracteres), gsk_C…YYYY (56 caracteres), …
```

Repare no que **não** aparece: nenhuma chave inteira, nem no `.env`, nem na
tela.

### 4. Teste cada uma de verdade

```bat
.venv\Scripts\python configurar-chave.py --testar
```

Saída esperada (uma linha por chave):

```text
Chave 1 de 3:
FUNCIONOU. O modelo respondeu: 'ok'

Chave 2 de 3:
FUNCIONOU. O modelo respondeu: 'ok'

Chave 3 de 3:
cota ou limite de requisições estourado (HTTP 429). Tente mais tarde.

Resumo: 2 de 3 chave(s) respondendo.
```

Duas respondendo já é suficiente: quando a primeira estourar, o JARVIS usa a
outra sozinho. `401` numa delas quer dizer que aquela chave foi apagada no
painel do Groq.

### 5. Reinicie o JARVIS para ele ler o `.env` novo

Feche a janela no **X** e abra `iniciar-jarvis.bat` de novo.

Confira: <http://127.0.0.1:8000/api/ai/status> deve mostrar `"configured": true`
e `"keys": 3`. Na tela, o cabeçalho da conversa passa a dizer `Groq · 3 chaves`.

---

## Se algo der errado

| mensagem | o que fazer |
|---|---|
| `não achei o arquivo …` | o arquivo não está nessa pasta; arraste-o para a janela |
| `O arquivo não tem nenhuma chave reconhecível` | o `.txt` guardou só os nomes; abra e confira se o `gsk_…` está lá |
| `a chave foi recusada (HTTP 401)` | essa chave foi apagada no painel; crie outra em console.groq.com/keys |
| `cota ou limite … (HTTP 429)` | essa chave gastou o dia; as outras continuam valendo |
| tudo `429` | espere a virada do dia ou use o modelo local (`ia.local`) |

---

## O que mudou no código

- `chaves_do_texto()` reconhece `gsk_…` (Groq), `sk-…` (OpenAI), `AIza…`
  (Google) e `sk-or-v1-…` (OpenRouter), sem repetir;
- `ler_arquivo_de_chaves()` lê UTF-8 e, se falhar, `latin-1` — o Bloco de Notas
  antigo do Windows 1607 salva assim;
- `--arquivo CAMINHO` grava; `--so-mostrar` só informa;
- chaves que já estavam no `.env` são mantidas, sem duplicar;
- 8 testes novos, entre eles o formato exato do seu arquivo
  (`api groq 1 gsk_…`) e um arquivo em latin-1.

**O que este script não faz:** não apaga as chaves antigas do painel do Groq.
Como as três passaram por um arquivo e por uma conversa, o certo é entrar em
<https://console.groq.com/keys>, apagar essas e criar três novas — depois rode
os cinco passos de novo com o arquivo atualizado.
