# JARVIS 0.61.7 — o log da vigia: o cabo novo e o que ele mostrou

O que a janela mostrou, lido com honestidade:

```
09:27:26  SAIU    Alcor Micro USB 2.0 Card Reader [VID_058F]
09:27:39  ENTROU  Alcor Micro USB 2.0 Card Reader [VID_058F]
```

**Nada de Samsung.** As duas únicas mudanças foram o leitor de cartão saindo e
voltando — ou seja, você mexeu no que já estava lá. Com o cabo "novo" o J7
continuou invisível: **nenhum evento USB com ele na porta**.

Isso não é má notícia; é informação: a vigia está funcionando (pegou o leitor
sair e voltar em 13 segundos) e o J7 não chegou a ser apresentado ao Windows
**nunca** naquele período.

## O que o log prova, e o que ele não prova

| Fato | Prova |
|---|---|
| A34 aparece e some na vigia, com modelo | PC, porta, Windows e a janela: **todos bons** |
| J7 não aparece com o cabo novo | não é driver, não é Depuração USB, não é tela bloqueada |
| J7 está no Wi-Fi de casa | o Android dele **está ligado e funcionando** |
| J7 carrega pelo PC | energia (VBUS/GND) passa; só os dados (D+/D−) não |

Falta separar **cabo** de **conector**. Isso só se resolve com um teste físico.

## O que a 0.61.7 acrescenta

**`vigiar-usb-atento.bat`** — olha a USB **5 vezes por segundo** por 10 minutos.
Um conector com solda trincada às vezes apresenta o aparelho por 0,3 s: entre duas
olhadas de 2 s, isso passa batido. No modo atento, não.

**Toda sessão fica gravada.** Cada entrada e saída vai para
`storage\celular\vigia-DATA-HORA.log`. Se a janela fechar, o que passou continua
lá — e dá para colar no chat inteiro.

**A vigia avisa quando a consulta demora.** Numa máquina de 4 GB, uma leitura de
PnP pode passar de 2 s; sem dizer isso, "ainda vigiando" pareceria travamento.
Agora ela imprime o tempo real da consulta quando ele atrapalha o intervalo.

**`celular.eventos`** — skill nova que lê o **log de eventos do Windows** (canal
System, **sem precisar de administrador**) e mostra o que passou de USB/PnP nos
últimos minutos. É a resposta para "e se ele apareceu quando eu não estava
olhando?":

```
celular.eventos
```

Ela responde uma de três coisas:

- **eventos citando Samsung/VID_04E8** → "o aparelho chegou a ser apresentado, mas
  durou menos que o intervalo: conector com mau contato";
- **só eventos do PC** → "nesta janela o aparelho não foi apresentado nenhuma vez,
  nem por um instante — reforça cabo ou conector";
- **nenhum evento** → "o log não registrou nada de USB no período".

## O teste que falta, em uma frase

**Plugue este cabo "novo" em outro aparelho micro-USB e veja a vigia.** Serve
qualquer coisa que converse com PC: celular antigo, Kindle, câmera, controle de
PS4/Xbox, placa Arduino, leitor de cartão com cabo removível.

- **apareceu** → o cabo é de dados; o problema é o **conector do J7**
  (bancada, R$ 50–100);
- **não apareceu** → o cabo "novo" também é só de carga (acontece muito: cabo de
  carregador, caixa de som, power bank). Aí o teste é com um cabo que você sabe
  que já transferiu foto — ou um novo, de dados, R$ 15–25.

Se não tiver nenhum aparelho micro-USB à mão, o teste alternativo é o **modo
atento com o conector**: com o J7 ligado e o cabo plugado, aperte e mexa o
conector devagar, girando levemente, por dois minutos. Uma piscada de `VID_04E8`
na janela já muda o diagnóstico para "conector".

## Testes

- `pytest server/tests` → **2.780 passed** (`test_celular.py`: 126).
- Novos: leitura de linha de evento, recusa fora do Windows, histórico avisando
  quando o aparelho apareceu "mesmo que por pouco tempo", histórico sem aparelho
  reforçando cabo/conector, histórico vazio sem inventar, skill no registro,
  `vigiar-usb-atento.bat` com `-Intervalo 400 -Minutos 10`, a vigia apontando
  para o modo atento e gravando log em `storage\celular`.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
- Registro: **290 skills**.
