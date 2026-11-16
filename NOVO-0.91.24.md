# JARVIS 0.91.24 — o manual da página, e um jeito de medir sem gastar chave

Você tem razão numa coisa e ela muda o jogo: **eu não consigo testar no seu
PC**. Cada rodada custa você atualizar, abrir o site, quase criar uma chave e
me mandar um print. Então esta versão faz duas coisas.

## 1. O manual da página, passo a passo

`docs/CHAVE-OPENROUTER.md` — escrito da documentação oficial do OpenRouter e
dos seus prints. É o que você pediu: onde é o nome, onde é que clica, em que
ordem.

O painel, de cima para baixo:

| # | na tela | o que o JARVIS faz |
|---|---|---|
| 1 | **Name \*** (caixa, com `e.g. "ChatbotKey"`) | digita `jarvis-AAAA-MM-DD` |
| 2 | **Expiration \*** (começa em `Select expiration`) | escolhe **No expiration** |
| 3 | **Credit limit \*** (começa em `Choose a credit limit`) | escolhe **No limit** |
| 4 | **Reset limit every** (começa em `N/A`) | não mexe — com “No limit” o `N/A` é o certo |
| 5 | **Create** | clica só quando ele acende |

As opções de expiração são `1 day`, `7 days`, `30 days`, `90 days`, `180 days`,
`1 year`, `No expiration`. O **Create fica apagado** até os três campos
obrigatórios estarem preenchidos — é por isso que clicar nele antes não fazia
nada. Depois do Create, a chave aparece **uma única vez**, com o botão **Copy**:
o OpenRouter não mostra de novo, e chave existente não tem como ser lida.

## 2. Um comando que mede sem criar nada

Duplo clique em **`diagnostico-chave.bat`**.

Ele **não cria chave e não clica em nada**. Ele mede o que cada leitura do
Windows consegue enxergar da janela do Chrome e escreve `chave-leitura.txt` na
pasta do JARVIS:

    uia_raw     :  31 elementos — painel: SIM — nome, expiração, limite, criar
    uia         :   3 elementos — painel: não — nenhum campo do painel
    msaa        :   3 elementos — painel: não — nenhum campo do painel

**Faça assim:** abra o site, clique em **New key** para o painel aparecer na
tela, e só então rode o `diagnostico-chave.bat`. Aí o arquivo responde a
pergunta que ainda falta: **qual leitura enxerga o painel que está na minha
frente?** — e você não gasta chave nenhuma para descobrir.

Me mande o `chave-leitura.txt`. Com ele eu sei exatamente onde está o buraco,
sem chutar de novo.

## O que mais mudou

- O `chave-leitura.txt` ganhou a linha `painel: SIM — nome, expiração, limite,
  criar` em cada leitura. É o que separa “a página não tem o painel” de “esta
  leitura não vê o painel”.
- O `pegar-chave.bat`, quando falha, agora lembra do `diagnostico-chave.bat`.

## O que continua igual

- nada é criado sem `--autorizar`;
- **No expiration**, **No limit**, nome `jarvis-AAAA-MM-DD`;
- botão apagado não é clicado;
- cursor volta para o dono;
- sem chave, o `.env` não é tocado.

Suíte inteira: **3.781 testes passando** (7 pulados: dependem do Windows real).
