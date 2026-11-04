# JARVIS 0.77.0 — um botão para colar as chaves (e o `cmd` sai do caminho)

Sua pergunta: *“não é melhor botar um botão dentro do JARVIS onde eu só coloco
as chaves?”*. É. E o print que você mandou explica por quê:

```text
D:\JARVIS>api grok 1 gsk_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
'api' não é reconhecido como um comando interno ou externo,
um programa operável ou um arquivo em lotes.
```

Aquele bloco é **anotação**, não comando. O `cmd` leu `api` como programa,
procurou um `api.exe` que não existe e desistiu — quatro vezes. **Nada foi
gravado** e nenhuma chave foi usada: foi só uma tentativa que não achou o
caminho. O caminho agora é na tela.

---

## 1. Onde fica

**Configurações** → seção **Inteligência generativa** → cartão **Chaves de IA**
→ botão **Colar chaves**.

Cole o bloco inteiro, do jeito que você tem no arquivo. O JARVIS varre o texto e
aproveita **só o que tem cara de chave**:

```text
api grok 1 gsk_AAAA…
api groq 2 gsk_BBBB…
api cerebro 3 gsk_CCCC…
api cerebro 4 gsk_DDDD…
```

→ **4 chaves guardadas** · `Groq · llama-3.3-70b-versatile` · e já respondendo.

Nada de escolher provedor, endereço ou modelo: quando as chaves começam com
`gsk_`, ele preenche os três.

---

## 2. O que a tela faz

| botão | o que acontece |
|---|---|
| **Colar chaves** | abre o campo com o texto oculto (o olho revela) |
| **Salvar e testar** | grava no `.env`, aplica na hora e faz uma chamada real de 8 tokens por chave |
| **Só salvar** | grava sem gastar requisição |
| **Testar** | testa as chaves guardadas, uma a uma, **sem** salvar nada |
| **Apagar todas** | limpa a lista e mantém provedor/endereço/modelo |
| **Manter as que já estão** | acrescenta em vez de trocar |

Resultado do teste, sem mostrar nenhum valor:

```text
2 de 4 responderam — as outras ficam de reserva para quando faltar cota.
  ✓ chave 1: respondeu
  × chave 2: cota ou limite de requisições estourado (HTTP 429)
```

---

## 3. O que mudou no servidor

| antes | agora |
|---|---|
| `.env` editado à mão | `GET/POST/DELETE /api/ai/chaves` e `POST /api/ai/chaves/testar` |
| salvar chave exigia reiniciar | `provider.recarregar()` relê o ambiente na hora |
| texto colado com rótulo seria chave inválida | a varredura extrai `gsk_…`, `sk-…`, `sk-or-v1-…`, `AIza…` |
| nada impedia gravar de fora | só a própria máquina grava (`403` para o resto) |
| `/api/health` dizia `0.75.0` fixo | a versão agora vem de `atualizacao.VERSAO` |

Essa última linha era um defeito de verdade: o `health` ficou preso em `0.75.0`
durante dois lançamentos porque o número estava escrito à mão em dois lugares.
Agora há um teste comparando `atualizacao.VERSAO`, `package.json` e
`manifest.json`.

---

## 4. O que este botão **não** faz

- **não** mostra a chave depois de salva — só `gsk_a…BkXV (56 caracteres)`;
- **não** guarda a chave no navegador: sem `localStorage`, sem cookie, sem
  `sessionStorage`; o campo é limpo ao salvar (há teste para isso);
- **não** manda a chave para fora de `127.0.0.1`;
- **não** deixa o celular na rede local gravar (ele vê o estado; o botão fica
  desligado);
- **não** registra a chave em log, diário de erro ou resposta HTTP — há teste
  varrendo todas as respostas;
- **não** testa sem internet: chave boa com provedor fora do ar responde
  `falhou na conexão`, que é diferente de chave inválida.

---

## 5. Segurança, sem rodeio

As chaves que passaram por arquivo e por conversa **não são mais secretas**.
Procedimento, na ordem:

1. <https://console.groq.com/keys> → **apague** as antigas;
2. crie novas (`jarvis-1` … `jarvis-4`);
3. tela → **Colar chaves** → cole as novas → **Salvar e testar**
   (com “manter as que já estão” **desligado**, para trocar).

Enquanto isso, se o teste disser `429`, não é erro seu: é aquela chave gastando
a cota do dia. O JARVIS usa a próxima automaticamente.

---

## 6. O que foi testado

| onde | quantos | cobre |
|---|---|---|
| `server/tests/test_chaves.py` | 29 | extração do bloco real que falhou no `cmd`, máscara, gravação em CRLF sem BOM, resto do `.env` intacto, não trocar provedor alheio, `429`/`401`/rede no teste, API 400/403, origem de fora, e uma varredura provando que nenhuma resposta contém chave |
| `src/lib/confirmacao.test.ts` | 2 | a máscara da tela não serve para autenticar, e nada vai para `localStorage` |
| `server/tests/test_atualizacao.py` | 1 | versão única (health = package.json = manifest) |

Suíte: **3.211 passed, 7 skipped**. Front: **130 testes**, `tsc` limpo, build
embutido ok, `manifest.json` conferido.

**O que não foi medido:** se as suas quatro chaves respondem. O sandbox onde
este código roda não alcança `api.groq.com`. Quem responde é o botão
**Testar**, na sua máquina, em segundos.
