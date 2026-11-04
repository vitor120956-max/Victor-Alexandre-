# As chaves de IA, pela tela (0.77.0)

O pedido: *“não é melhor botar um botão dentro do JARVIS onde eu só coloco as
chaves?”* — Sim, e o motivo apareceu na prática: a instrução anterior mandava
rodar um comando no `cmd`, e o que aconteceu foi colar as anotações
(`api grok 1 gsk_…`) no prompt, recebendo três vezes

```text
'api' não é reconhecido como um comando interno ou externo,
um programa operável ou um arquivo em lotes.
```

Nada foi gravado naquela vez — o `cmd` só reclamou. A chave continua sendo um
texto, não um comando.

---

## 1. O caminho novo: três cliques

1. **Configurações** (na barra lateral).
2. Seção **Inteligência generativa** → cartão **Chaves de IA** → botão
   **Colar chaves**.
3. Cole o bloco inteiro — com ou sem os rótulos — e clique em
   **Salvar e testar**.

O JARVIS varre o texto e aproveita **só o que tem cara de chave**:

| formato | de onde é |
|---|---|
| `gsk_…` | Groq |
| `sk-…` | OpenAI e compatíveis |
| `sk-or-v1-…` | OpenRouter |
| `AIza…` | Google AI Studio |

Rótulo, número e palavra são descartados. Então o bloco que falhou no `cmd`
funciona colado na tela:

```text
api grok 1 gsk_AAAA…
api groq 2 gsk_BBBB…
api cerebro 3 gsk_CCCC…
api cerebro 4 gsk_DDDD…
```

→ **4 chaves guardadas**, e o JARVIS passa a usar `Groq` +
`llama-3.3-70b-versatile` sozinho (quando todas são `gsk_` e o endereço ainda
não é do Groq).

---

## 2. O que cada botão faz

| botão | o que acontece |
|---|---|
| **Colar chaves** | abre o campo; o texto aparece oculto, com o olho para revelar |
| **Salvar e testar** | grava no `.env`, aplica na hora e faz uma chamada real de 8 tokens em cada chave |
| **Só salvar** | grava e aplica, sem gastar requisição |
| **Testar** (fora do modal) | testa de novo as chaves guardadas, sem salvar nada |
| **Apagar todas** | limpa a lista; provedor, endereço e modelo continuam |
| **Manter as que já estão** | acrescenta em vez de trocar (o caso de comprar mais cota) |

O resultado do teste aparece chave por chave, **sem o valor**:

```text
As 4 chaves responderam.
  ✓ chave 1: respondeu
  ✓ chave 2: respondeu
  × chave 3: cota ou limite de requisições estourado (HTTP 429)
```

---

## 3. Por que ainda existe um campo e não um “login”

Porque não há conta do JARVIS: a chave é do **seu** Groq. O que a tela garante é
que ela não precise passar pelo terminal, pelo chat ou pelo Bloco de Notas.

O que a tela **não** faz, de propósito:

- **não** mostra a chave depois de salva — só a máscara (`gsk_a…BkXV`);
- **não** guarda a chave no navegador: nada de `localStorage`, nada de
  `sessionStorage`, nada em cookie. O campo é limpo assim que você salva;
- **não** manda a chave para lugar nenhum além de `127.0.0.1` — a API é a sua;
- **não** deixa outro aparelho gravar: quem abre a tela pelo celular na rede
  local **vê** o estado, mas o botão fica desligado (`podeEditar: false`);
- **não** escreve a chave em log, diário de erro ou resposta HTTP. Há teste
  varrendo as respostas para garantir isso.

---

## 4. O que muda no disco

Uma linha, no `.env` da pasta do JARVIS:

```text
JARVIS_AI_API_KEY=gsk_primeira…,gsk_segunda…,gsk_terceira…,gsk_quarta…
```

- o arquivo continua em **CRLF e sem BOM** (o Bloco de Notas do Windows 1607
  depende disso);
- comentários, ordem e as outras variáveis ficam como estavam;
- o `.env` não entra no `manifest.json`, não vai para o Git e a atualização
  delta não toca nele.

Quando as chaves têm cara de Groq e o endereço ainda não é dele, três linhas
mudam junto: `JARVIS_AI_PROVIDER=Groq`,
`JARVIS_AI_BASE_URL=https://api.groq.com/openai/v1` e
`JARVIS_AI_MODEL=llama-3.3-70b-versatile`. Quem já apontava para outro provedor
(OpenRouter, por exemplo) **não** é trocado.

---

## 5. Aplicar sem reiniciar

Antes, o `.env` só era lido ao subir a API: salvar chave exigia fechar a janela
e abrir de novo. Agora o servidor relê o ambiente na hora
(`OpenAICompatibleProvider.recarregar`), e o cabeçalho da conversa passa a
mostrar `Groq · 4 chaves` no segundo seguinte.

Se algo der errado no meio, o `.env` já está gravado — o próximo `iniciar-jarvis.bat`
começa com as chaves certas de qualquer forma.

---

## 6. Segurança, dito sem rodeio

As chaves que você colou num arquivo e nesta conversa **já não são secretas**.
Depois de funcionar na tela:

1. abra <https://console.groq.com/keys>;
2. apague as chaves antigas (todas as que saíram de um `.txt` ou de um print);
3. crie novas — nomeie `jarvis-1`, `jarvis-2`, …;
4. volte em **Configurações → Colar chaves**, cole as novas e use
   **Manter as que já estão** desligado (trocar, não acrescentar);
5. clique em **Testar**.

Enquanto isso, o teste com `429` não é problema: 429 quer dizer “essa está
gastando cota agora”, e o JARVIS usa a próxima.

---

## 7. O caminho antigo continua valendo

Para quem prefere terminal, ou quando a tela não abre:

```bat
cd /d D:\JARVIS
```

```bat
.venv\Scripts\python configurar-chave.py --arquivo "cerebro javis 1 e 2 e 3.txt"
```

Os dois caminhos gravam o mesmo `.env`, com a mesma regra de extração — há um
teste que compara os dois no bloco exato que você colou no `cmd`.

---

## 8. Limites conhecidos

- o campo **não é** `<input type="password">`: é um `textarea`, porque chave em
  várias linhas não cabe num campo de uma linha. A ocultação usa
  `-webkit-text-security`, que funciona no Chrome/Edge/Safari (o navegador da
  tela) e degrada para texto visível em navegador antigo;
- **imprimir a tela** com o campo aberto mostra a chave. Não há como evitar
  isso sem leitor de digital;
- o teste de chave gasta **8 tokens por chave** da sua cota. Testar 4 chaves
  custa quase nada, mas não é zero;
- se o provedor estiver fora do ar, o teste devolve `falhou na conexão` — isso
  não quer dizer que a chave está errada.
