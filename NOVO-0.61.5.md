# JARVIS 0.61.5 — a rede de casa, medida: e o que ela não resolve

A varredura da 0.61.4 respondeu antes de qualquer opinião:

```
Rede local: 192.168.15.0/24 — este PC é 192.168.15.8.
5 dispositivo(s) responderam:
• 192.168.15.1 — nenhuma porta aberta
• 192.168.15.5 — nenhuma porta aberta
• 192.168.15.12 192.168.15.12 — nenhuma porta aberta
• 192.168.15.22 A34 — nenhuma porta aberta
• 192.168.15.255 — nenhuma porta aberta
```

**Nenhuma porta de aparelho aberta.** Isso encerra a hipótese do Wi-Fi com
medição, não com opinião: o Android não escuta nada na rede sem Depuração USB já
autorizada (e `adb tcpip 5555` rodado uma vez pelo cabo) ou sem a Depuração sem
fio do Android 11+ — que este aparelho não tem.

## O que a própria saída mostrou de errado (e foi corrigido)

**`192.168.15.255` não é um dispositivo.** É o endereço de broadcast da faixa: a
tabela ARP guarda essa linha e a 0.61.4 contou como "respondeu". Agora endereço
de rede, broadcast e multicast ficam de fora — contar cinco aparelhos quando são
quatro muda a conclusão de quem lê.

**`192.168.15.12 192.168.15.12`.** O Windows devolve o próprio IP quando não
consegue resolver o nome, e o JARVIS repetia isso como se fosse nome. Nome que é
IP agora sai vazio.

**O MAC entrou na linha.** Quando o nome não ajuda (`A34`, vazio), é o MAC que
identifica o aparelho — e é ele que recebe a marca `[prefixo Samsung]` quando o
prefixo é reconhecido.

```
• 192.168.15.22 A34 · 8c:77:12:dd:ee:ff [prefixo Samsung] — nenhuma porta aberta
```

## A frase que não chegou na skill

`quais dispositivos estão na rede local` ficou em **0,47** — abaixo do 0,50 para
executar — e o agente respondeu "não tenho certeza de qual skill resolve isso".
Agora a skill se chama **"Dispositivos na rede local e no Wi-Fi (celular sem
cabo)"**, e os sinônimos do agente ganharam o vocabulário de casa:
`aparelhos`/`dispositivos` → `celular`/`rede`. Medido:

| pedido | antes | agora |
|---|---|---|
| quais dispositivos estão na rede local | 0,47 (perguntava) | **0,67** (executa) |
| quais aparelhos estão conectados no wifi | 0,33 (perguntava) | **0,73** (executa) |
| dá para acessar o celular pelo wifi sem cabo | 0,83 | **0,83** |
| status do celular | 1,0 | **1,0** (sem mudança) |

## O que sobrou de verdade nessa varredura

- O aparelho está **vivo e na rede**; a rede **não oferece porta** nenhuma. Fim da
  linha do Wi-Fi.
- Apareceu um `A34` na rede. Se for um Galaxy A34 de casa, ele serve como **teste
  de bancada do PC**: com um cabo USB-C **de dados**, plugar o A34 na mesma porta
  que o pendrive já usou. Se o A34 aparecer no `vigiar-usb.bat` como MTP, o lado
  Windows/porta está provado bom — sobra cabo micro-USB ou conector do J7.
  (Cabo USB-C não testa o cabo micro-USB do J7: são plugues diferentes.)

## Testes

- `pytest server/tests` → **2.762 passed** (`test_celular.py`: 106).
- Novos: broadcast/rede/multicast fora da contagem, nome que é o próprio IP vira
  vazio, a varredura de casa (com o ARP real do formato visto) mostrando MAC e
  prefixo Samsung sem repetir IP nem contar `.255`, e as três frases de rede
  chegando na skill com nota ≥ 0,5 — com `status do celular` continuando na sua.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
