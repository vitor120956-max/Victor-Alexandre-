# JARVIS 0.61.4 — "dá para acessar pelo Wi-Fi?" agora tem resposta medida

A pergunta: *"ele está conectado no Wi-Fi de casa, será que não conseguimos
acessar o celular pela rede? tipo faz o Wi-Fi cair, quando volta a gente entra na
rede e no celular?"*

Três coisas precisam ser ditas, e nenhuma é opinião:

**1. A tela bloqueada não é a causa.** Um Android com a tela travada continua se
apresentando ao Windows como dispositivo USB — o que o desbloqueio muda é o
acesso aos *arquivos* (MTP), não a existência do aparelho na porta. Se fosse
bloqueio de tela, o Windows listaria um `VID_04E8` com aviso de driver. Não
lista nada — nem o `Dispositivo USB desconhecido` que aparece quando a porta vê
algo e não consegue conversar. Isso continua sendo a linha de dados (cabo ou
conector).

**2. Wi-Fi não substitui o cabo — e o motivo é de desenho, não de configuração.**
O Android não abre porta nenhuma por padrão. O `adb` por rede existe em duas
formas, e as duas dependem do cabo ou da tela:

- `adb tcpip 5555` — precisa ser rodado **uma vez pelo cabo**, com a depuração já
  autorizada;
- "Depuração sem fio" do Android 11+ — pede um **código de pareamento na tela** do
  aparelho. Este é um J7 Prime (Android 6/8), então nem existe.

Sem uma dessas duas, não há o que conectar: o celular não escuta nada na rede.

**3. Derrubar o Wi-Fi não dá acesso ao aparelho.** Quando a rede cai e volta, o
celular simplesmente reconecta ao mesmo roteador, como antes. Quem está na rede
consegue, no máximo, ver tráfego — não "entrar" no aparelho. Não existe caminho
de administração remota em Android sem depuração ligada e sem app previamente
instalado e configurado na tela.

## O que a rede **pode** dar (e agora o JARVIS mede)

**`celular.rede`** — nova skill, só leitura:

- descobre o IP deste PC e qual é a rede local;
- toca cada endereço da faixa (um connect TCP sem enviar dado) para popular a
  tabela ARP, e lê `arp -a`;
- mostra cada dispositivo que respondeu: **IP, MAC, nome de rede e portas
  abertas**, marcando o prefixo Samsung quando reconhece;
- destaca o **jackpot**: se algum aparelho tiver a porta **5555** aberta, o adb sem
  fio funciona sem cabo — e ele diz o comando, `adb connect IP:5555`;
- se nenhuma porta estiver aberta, diz isso com todas as letras, incluindo que
  derrubar o Wi-Fi não muda nada.

A utilidade prática imediata: **confirmar que o aparelho está vivo e qual é o IP
dele**. Isso serve para depois (mirror sem fio, uma vez autorizado) e descarta
"o celular está desligado/fora da rede" como hipótese.

## Como perguntar

No chat, do jeito que vier:

```
dá para acessar o celular pelo wifi sem cabo
```

```
quais dispositivos estão na rede local
```

A skill também entra pelo nome: `celular.rede`.

## Testes

- `pytest server/tests` → **2.758 passed** (`test_celular.py`: 102).
- Novos: leitura da tabela ARP do Windows **e** do Linux, prefixo Samsung sem
  afirmar o que não sabe, recusa quando a camada do celular está desligada, olhar
  só a própria faixa (nem outra faixa, nem o próprio PC), ordem numérica dos IPs,
  veredito sem porta aberta (com a explicação do `adb tcpip 5555`), veredito com
  5555 aberta (`adb connect`), rede sem ninguém (Wi-Fi de visitante) e porta com
  nome do serviço.
- Sem rede de verdade nos testes: `tocar` e `rodar` são injetados, e
  `_portas_abertas` é substituído — nenhum pacote sai da máquina.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
- Registro: **289 skills** (era 288).
