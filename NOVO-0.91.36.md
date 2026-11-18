# JARVIS 0.91.36 — “vai chover hoje?” não é pergunta para o modelo

Seu print: `testar ia` respondeu *“A IA externa respondeu em 2832 ms (provedor
OpenRouter)”* — **essa** foi a prova, e ela veio marcada `· IA EXTERNA`.

Sua pergunta depois disso é a certa:

> e se eu perguntar como está a previsão de tempo hoje ou se vai chover hoje?

Até agora, **ia para o modelo**. E o modelo não vê o tempo: não tem janela, não
tem relógio, não consulta previsão. Ele só podia fazer uma de duas coisas —
dizer que não tem acesso, ou **inventar** uma temperatura plausível. Numa tela
que acabou de mostrar `· IA EXTERNA`, as duas parecem igualmente confiáveis. É o
mesmo problema da 0.91.34, uma camada abaixo.

## O que muda

Agora “vai chover hoje?” consulta o **Open-Meteo** — serviço público, sem chave,
sem cota, sem passar pelo modelo:

- devolve **agora**, **hoje** e **amanhã**, com a **chance de chuva em número**;
- termina com *“Fonte: Open-Meteo — quem respondeu foi o serviço de previsão, não
  o modelo”* e a **hora da leitura**;
- a mensagem sai marcada `· PREVISÃO (Open-Meteo)` no balão — não é IA externa,
  não é skill Python;
- sem cidade na frase, usa `JARVIS_CIDADE` do `.env`; vazio, **Palhoça**;
- **sem internet, ele não inventa**: diz que não conseguiu e por quê.

O exemplo do que você vai ler:

    Previsão para Palhoça, Santa Catarina — lida agora, 18/11 às 10:01 (fonte: Open-Meteo):

    Agora: 23 °C · sensação 25 °C · encoberto · umidade 88% · vento 9 km/h
    Hoje: 18 °C a 26 °C · chuva fraca · sim, deve chover — 80% de chance · ~6,4 mm
    Amanhã: 17 °C a 24 °C · encoberto · não deve chover — 20% de chance

    Vai chover hoje? sim, deve chover — 80% de chance.

    Fonte: Open-Meteo (open-meteo.com) — previsão, não medição da janela.
    Quem respondeu foi o serviço de previsão, não o modelo.

As frases que ele entende: *vai chover hoje*, *vai chover amanhã*, *como está a
previsão do tempo*, *que tempo faz hoje*, *como está o clima*, *preciso de
guarda-chuva*, *qual a temperatura agora* — e com cidade: *previsão do tempo em
São José*, *vai chover no Rio de Janeiro*. Quem escreve “pesquise a previsão do
tempo” continua indo para a busca na web: aí a pessoa quer a página, não o número.

E o modelo recebeu uma instrução nova: **não estimar** tempo, cotação nem
placar. O que escapar das frases acima ganha um “não tenho esse dado”, não um
número falso.

## O que fazer agora

```bat
cd /d D:\JARVIS
```

Com a janela da API fechada (no X):

```bat
atualizar.bat
```

Depois suba e pergunte — sem chave, sem cota, sem esperar modelo:

```bat
iniciar-jarvis.bat
```

```text
vai chover hoje?
```

Se a cidade estiver errada, diga o nome na frase (`previsão em São José`) ou
grave a sua no `.env`:

```text
JARVIS_CIDADE=Palhoça
```

## Testado

32 testes novos em `server/tests/test_tempo.py` (com um Open-Meteo falso):
cidade → coordenadas, código do tempo → frase em português, chuva com número,
amanhã sem herdar a resposta de hoje, fonte e hora na resposta, cidade
inexistente explicando o próximo passo, URL fora dos dois endereços recusada, e
a rota devolvendo *“Nada foi inventado”* quando a fonte cai.

21 casos novos de frase em `jarvisEngine.test.ts`: “de hoje” e “guarda-chuva”
não viram cidade, “que horas são” e “vai abrir o chrome” não são roubados, e a
busca na web fica com a web.

Contra a 0.91.35, **21 desses casos de frase falham** e a rota `/api/tempo`
devolve 404.

Suíte: **3.925 testes de API** (7 pulados) e **153 testes web**.
