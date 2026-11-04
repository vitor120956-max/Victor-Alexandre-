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

## 0. Se o cartão não aparece — comece por `conferir-versao.bat`

Desde a **0.79.1** existe um duplo clique que responde isso com fato, em vez de
“tenta atualizar de novo”: **`conferir-versao.bat`**. Ele mostra a versão do
disco, a versão da API que está respondendo, qual interface está sendo servida
e **o que fazer**. Não instala, não baixa e não altera nada.

```text
  versão do servidor:       0.79.1
  pasta da interface:       web-dist
  versão da interface:      0.79.1
  versão da API:            0.79.1
```

Se os três primeiros baterem com o último, o problema é só o navegador:
**Ctrl+F5** na página.

Sem o conferidor, a tabela abaixo serve para o diagnóstico no olho:

| o que você vê | causa | solução |
|---|---|---|
| a frase *“Não cole chaves no chat ou nesta tela”* | versão anterior à 0.77.0 | atualize (`atualizar.bat`, ou “atualiza o jarvis” no chat) |
| rodapé dizendo **VERSÃO 0.5.0** | tela de antes da 0.77.1 (o rodapé era texto fixo) | `conferir-versao.bat` e siga o veredito |
| cartão sem título (só “Nenhuma chave guardada”) | 0.77.0, antes do título | atualize para a 0.77.1 |

O caminho mais seguro quando a tela parece velha: feche a janela preta no **X**,
duplo-clique em `atualizar.bat`, espere a linha **Versao instalada nesta pasta
agora** (o `.bat` imprime o número), e abra `iniciar-jarvis.bat`.

### Por que isso não era óbvio

Três coisas diferentes produzem a mesma tela velha, e sem número nenhuma delas
se distingue da outra:

1. **os arquivos** não foram trocados nesta pasta (o `atualizar.bat` de outra
   cópia foi rodado, ou falhou e a janela fechou antes de alguém ler);
2. **o processo** em execução é antigo: o Python carrega o código no start e não
   recarrega sozinho ao trocar arquivo no disco;
3. **o navegador** guardou o `index.html` velho em cache e nem pediu de novo.

A 0.79.1 ataca as três: o `.bat` imprime a versão que ficou; o build carimba
`versao.json` dentro da interface e a API compara com a sua própria versão
(aparece em `/api/health` e num aviso vermelho na tela); e o `index.html` passou
a sair com `no-cache`, enquanto `/assets/*` (nome com hash) pode ficar em cache
para sempre — o que é guardado é o que nunca muda de conteúdo.

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

## 9. Aviso de cota: “está acabando” e “acabou” (0.79.0)

A pergunta foi *“dá para o JARVIS avisar quando estiver acabando ou quando
acabar totalmente as APIs?”*. Dá — desde que o aviso seja **medido**, não
estimado. Quem mede é o processo Python: ele viu o código HTTP e os cabeçalhos
`x-ratelimit-*` de cada tentativa.

### O que fica registrado

| sinal | o que entra no diário |
|---|---|
| resposta 200 | a chave volta a ser boa; `x-ratelimit-remaining-*` diz quanto resta no minuto |
| HTTP 429 | chave **no limite**; `retry-after`, quando vem, diz em quantos segundos tentar |
| HTTP 401/403 | chave **recusada** — não volta sozinha, só com chave nova |
| botão **Testar** | é chamada real: o resultado do teste também alimenta o diário |

O diário guarda **posição** (chave 1, 2, 3), código e horário. A chave em si
nunca entra em resposta HTTP — há teste para isso.

### Onde o aviso aparece

1. **Faixa no topo** (`src/components/CotaBanner.tsx`), logo acima do aviso de
   versão:
   - âmbar — *“As chaves de IA estão acabando”*: alguma caiu, ou o que resta no
     minuto já é ≤ 20% do limite;
   - vermelho — *“As chaves de IA acabaram”*: nenhuma responde. O texto diz que
     a conversa com o modelo parou e que **as skills locais continuam**.
   - botões: **Conferir agora** (testa as chaves de verdade e atualiza) e
     **Chaves de IA** (leva ao cartão).
   - dispensável, mas volta sozinho quando a situação piora: a dispensa vale
     para a assinatura “situação + quantas restam”, não para sempre;
2. **No cartão Chaves de IA** (Configurações), com o detalhe de cada chave;
3. **No chat**, se você perguntar: *“quantas chaves restam?”*, *“as APIs
   acabaram?”*, *“acabou a cota?”* — responde com o diário, sem chamar modelo.

### O que ele **não** promete

- **não** inventa porcentagem: se o provedor não manda o cabeçalho de cota, o
  aviso fala do que aconteceu (429/401) e não de “restam 37%”;
- **não** antecipa a cota diária que o provedor não informa — o que existe é o
  limite por minuto nos cabeçalhos e a recusa real quando ela acontece;
- **não** some com o problema: avisar é o máximo que um aviso faz. Trocar ou
  acrescentar chave continua sendo no cartão.

## 10. “Coloquei 4 chaves e nenhuma respondeu” (0.79.2)

Esse foi um caso real, com print: quatro chaves `gsk_…` coladas de uma vez, o
aviso verde *“4 chaves guardadas”* e, dois segundos depois, o vermelho
*“Nenhuma das 4 respondeu agora”*.

### A causa mais provável: a cota é da conta, não da chave

O Groq — e quase todo provedor — limita **por organização/conta**, não por
chave. Quatro chaves criadas no mesmo login (`console.groq.com` com o mesmo
e-mail) **dividem o mesmo limite**. Elas não somam cota: servem para trocar
quando uma está com problema, não para multiplicar.

Se as quatro vieram do mesmo login e a conta estourou o dia, as quatro dão
`429` juntas — que é exatamente o que o print mostra.

### A alavanca que **funciona**: trocar de modelo

Cada **modelo** tem a sua própria cota, mesmo dentro da mesma conta. O
`llama-3.3-70b-versatile` (padrão) tem cerca de 1.000 pedidos/dia e 100 mil
tokens/dia no plano grátis; o `llama-3.1-8b-instant` tem cerca de 14.400
pedidos/dia. Trocar no cartão **Modelos de IA** costuma devolver a conversa na
hora, sem chave nova e sem conta nova.

### O que o botão Testar passou a fazer

| antes | agora |
|---|---|
| dizia “HTTP 429” | diz **“tente de novo em 12m34s — limite 100000, usado 100000”**, com o número que o provedor mandou |
| “nenhuma das 4 respondeu” | separa as três causas: chave inválida (401), cota da conta (429), nome do modelo que não existe (404) |
| só o código | quando a falha é 429/404, testa **uma vez** com `llama-3.1-8b-instant`. Se responder, a chave está boa e a tela oferece o botão **Usar llama-3.1-8b-instant** |

O segundo teste custa 8 tokens e só acontece quando o primeiro falha. Ele é o
que transforma “não sei o que houve” em “a chave é boa, o modelo é que caiu”.

### Se as quatro derem 401

Aí é chave mesmo: copiada pela metade, revogada, ou apagada no painel. Gere
novas em `console.groq.com/keys`. **E não cole chaves no chat** — quem vê a
conversa vê a chave; o certo é revogar as que passaram por ali.

### Ordem de socorro, do mais barato ao mais caro

1. **Testar** no cartão Chaves de IA — mostra o motivo real e o tempo de espera;
2. **trocar de modelo** no cartão Modelos de IA (cota separada, custo zero);
3. **esperar** o tempo que o próprio provedor disse;
4. **outra conta** (outro e-mail) — é a única forma de somar cota de verdade;
5. **modelo local** (`ia.local`) — sem conta, sem cota, mais lento.


## 11. “O provedor de IA respondeu com HTTP 400” (0.80.3)

Esse foi o print: o chat devolveu **HTTP 400** e parou aí. Verdade e inútil — o
Google usa 400 para **três** problemas diferentes, e só o corpo da resposta diz
qual é. A tela passou a ler o corpo e traduzir:

| o que o provedor escreve | o que a tela passa a dizer |
|---|---|
| `API key not valid. Please pass a valid API key.` | chave inválida ou expirada — gere outra no painel |
| `User location is not supported for the API use.` | o provedor não atende a sua região; troque para o Groq ou OpenRouter |
| `multiturn requests alternate between user and model` | o histórico precisa alternar — comece uma conversa nova (**e o JARVIS já junta as falas seguidas sozinho**) |
| `model … does not exist` | esse nome de modelo não existe; use “Ver modelos da minha chave” |

O terceiro caso era o mais provável aqui: quando uma skill local responde (abrir
o Gmail, por exemplo), o turno do JARVIS **não entra no histórico** — sobram duas
perguntas suas em sequência, e o Gemini recusa isso com 400. A correção é juntar
as falas seguidas do mesmo lado antes de enviar; é inofensivo nos outros
provedores e resolve o Google.

### A segunda tentativa

Se o 400 não for de chave, de região nem de histórico, o JARVIS repete **uma vez**
com o corpo mínimo (`model` + `messages`), sem `temperature` e sem `max_tokens`.
Parâmetro extra é a causa mais comum, e perder a resposta por causa de
`temperature` seria burrice.

### O que fazer no seu PC, agora

1. abra o JARVIS;
2. **Configurações → Chaves de IA → Testar** — a frase agora diz qual dos três é;
3. se for chave, gere outra em `aistudio.google.com/apikey` (ou
   `console.groq.com/keys`) e cole no cartão;
4. se for região, troque o provedor para **Groq** no cartão **Modelos de IA**;
5. se for histórico, mande a pergunta de novo (a conversa nova já nasce alinhada).
