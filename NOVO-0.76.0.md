# JARVIS 0.76.0 — três cérebros, e nenhum deles para a conversa

Você mandou três chaves do Groq num arquivo chamado *“cerebro javis 1 e 2 e 3”*.
A leitura certa disso é **três chaves = três cotas**. O JARVIS usava uma só;
quando ela estourava, a resposta virava erro — mesmo com duas intactas no bolso.

Esta versão faz ele usar as três.

---

## 1. O que mudou

| antes | agora |
|---|---|
| uma chave em `JARVIS_AI_API_KEY` | uma **ou várias**, separadas por vírgula |
| `429` na chave | erro na tela, e o dia acabava |
| `401` (chave apagada) | erro na tela, sem tentar outra | 
| contagem de chaves | não existia na tela | `Groq · 3 chaves` |
| `--testar` | testava uma | testa **cada uma** e fecha com `Resumo: 2 de 3` |

E o detalhe que economiza requisição: depois de uma troca, a **próxima**
pergunta já começa na chave que funcionou. Sem isso, toda resposta gastaria uma
tentativa perdida na chave estourada.

---

## 2. Quando troca de chave — e quando não troca

Troca (`server/ai.py` → `_pedir` → `_ChaveRecusada`):

| código | significa | troca? |
|---|---|---|
| `401` | chave inválida/apagada | **sim** |
| `403` | chave sem permissão para o modelo | **sim** |
| `429` | cota/limite estourado | **sim** |
| `404` / `422` | modelo ou base errados | **não** |
| `5xx` / timeout | problema do provedor ou da rede | **não** |

Trocar de chave num `404` só perderia tempo: o nome do modelo está errado para
todas as chaves.

---

## 3. O que a mensagem diz quando as três falham

Nunca o valor da chave, nem pedaço dela. Só o fato e o próximo passo:

```text
as 3 chaves estão no limite agora (HTTP 429). Espere alguns minutos ou acrescente outra chave ao .env.
```

```text
as 3 chaves foram recusadas pelo provedor (HTTP 401). Gere chaves novas em console.groq.com/keys e rode configurar-chave.py.
```

Com uma chave só, a frase é no singular — não é para parecer que existe uma
segunda escondida.

---

## 4. Como configurar (sem digitar na tela)

```bat
cd /d D:\JARVIS
```

```bat
.venv\Scripts\python configurar-chave.py
```

Quando pedir a chave, cole as três de uma vez, separadas por vírgula. O que você
digita **não aparece** e não fica no histórico do prompt.

Para conferir se cada uma responde:

```bat
.venv\Scripts\python configurar-chave.py --testar
```

---

## 5. Segurança — leia esta parte

As três chaves vieram num arquivo de texto. Isso significa que elas **já não são
secretas**: circularam numa conversa. O procedimento certo é:

1. entre em <https://console.groq.com/keys>;
2. **apague** as três que apareceram aqui;
3. crie três novas (nomeie `jarvis-1`, `jarvis-2`, `jarvis-3`);
4. grave as novas com `configurar-chave.py`;
5. teste com `--testar`.

O JARVIS nunca imprime a chave: nem no `--ver` (mostra `gsk_ab…3456`), nem na
tela, nem no erro. Mas isso não protege uma chave que você mesmo colou num
arquivo.

**Onde ela fica:** só no `.env` da sua máquina — fora do `manifest.json`, fora do
Git, e a atualização delta não toca nele.

---

## 6. O que **não** mudou

- a chave continua **opcional**: sem nenhuma, as 315 skills locais e o modelo
  local funcionam;
- o modelo local segue sem chave (`127.0.0.1`), e agora é a rede de segurança
  quando as três cotas acabam;
- nada de campo de chave na interface: o `.env` é o único lugar;
- a troca é **automática e silenciosa**, mas registrada: o cabeçalho mostra
  quantas chaves existem, não qual está em uso (isso apareceria como detalhe
  interno sem utilidade para você).

---

## 7. O que foi testado

| teste | o que prova |
|---|---|
| 7 novos em `test_ai_provider.py` | separação por vírgula/quebra de linha, troca no `429`, começar na chave boa, mensagem com “3 chaves” sem citá-las, todas no limite, `404` **não** troca, `status()` sem chave |
| 4 novos em `test_configurar_chave.py` | máscara de várias, gravação numa linha só, resumo `1 de 3`, e o aviso do modelo local quando nenhuma responde |

**O que não foi medido:** se as suas três chaves específicas funcionam. O
sandbox onde este código é testado não alcança `api.groq.com`. Quem responde isso
é o `--testar`, na sua máquina, em 10 segundos.
