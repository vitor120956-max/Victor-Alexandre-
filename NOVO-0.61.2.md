# JARVIS 0.61.2 — "a lista não mudou" agora é resposta, não tarefa

Você rodou `status do celular` duas vezes e recebeu **a mesma lista**: 10
dispositivos USB, um deles `USB Mass Storage Device VID_058F`, nenhum Samsung.
O JARVIS pediu para você comparar as duas listas no olho. Isso é trabalho que a
máquina faz melhor — e o pior: a comparação era a única coisa que faltava para
saber se o celular chegou a ser visto.

## O que mudou

**O JARVIS guarda a lista e compara sozinho.** Cada `celular.status` grava o que
o Windows viu em `storage/celular/usb-ultima.json` e compara com a checagem
anterior. A resposta passa a trazer:

```
Comparando com a checagem das 21:38: a lista está idêntica — a porta USB não
viu nada novo entre uma vez e outra.
```

ou

```
Comparando com a checagem das 21:38: entrou Dispositivo USB desconhecido.
A porta viu algo, mas o Windows não identificou o que era: isso é cabo (precisa
ser de dados) ou conector, não driver.
```

e, quando for o caso:

```
Comparando com a checagem das 21:38: entrou SAMSUNG Mobile USB Composite
Device VID_04E8. O celular apareceu na USB agora — o próximo passo é
driver/depuração.
```

**A sonda enxerga mais.** Antes ela perguntava só por `Class = USB` e por nomes
com marca. Agora pergunta também por `Portable Devices`/WPD (MTP), `Modem`,
`AndroidUsbDeviceClass` e — o que estava faltando — por **dispositivo que o
Windows não conseguiu identificar** (`Dispositivo USB desconhecido`, `VID_0000`).
Esse último é o diagnóstico que separa "a porta está vazia" de "a porta viu
alguma coisa e não conseguiu conversar". A lista também deixou de ser cortada em
10 itens na leitura (só a exibição no chat é que mostra os primeiros).

**Diagnóstico novo: "A porta viu algo que o Windows não identificou".** É a
assinatura de cabo só de carga, conector com poeira/oxidação ou porta fraca. O
plano começa por aí, e não por driver nem Depuração USB — porque nesse estado
nenhum dos dois mudaria nada.

**Código de problema traduzido.** `CM_PROB_FAILED_START` vira "driver não
iniciou", `CM_PROB_DEVICE_DISABLED` vira "desativado", e assim por diante. O
código cru continua disponível na lista, só não é a única informação.

**Quando nada muda, o plano muda.** Se a comparação mostra a lista idêntica, o
primeiro passo do plano passa a ser **"1. A USB está idêntica à das 21:38"** —
com o teste físico (cabo de dados, porta traseira, conector), em vez de pedir de
novo um teste que já foi feito.

## O que a sua saída mostra

- **10 dispositivos**, entre eles `USB Root Hub`, controladoras
  `Intel N10/ICH7` e um `USB Mass Storage Device VID_058F` (Alcor Micro é
  controlador de pendrive/leitor — muito provavelmente o próprio pendrive do
  JARVIS, que está funcionando).
- Ou seja: **a USB do PC funciona** (o pendrive é enumerado) e o **celular não
  aparece** — nem como dispositivo desconhecido, nem como MTP.
- Isso descarta driver e Depuração USB por enquanto. O problema está antes
  disso: cabo, conector do celular, porta usada ou aparelho desligado.

## Teste físico, na ordem que rende mais

1. **Cabo de dados**, não de carga. Se você tem o cabo original da Samsung, é
   ele. Cabo de carregador de outra marca, com frequência, só tem os dois fios
   de energia.
2. **Porta USB de trás do PC**, direto na placa-mãe, sem hub nem extensão. Nessa
   máquina (ICH7, USB 2.0) as portas da frente costumam ser fracas.
3. **Teste da porta com o pendrive**: tire o pendrive do JARVIS e ponha na porta
   que você está usando para o celular. Se o Windows vê o pendrive ali, a porta
   presta — sobra cabo/conector.
4. **Conector do celular**: com o cabo desconectado, olhe o micro-USB com
   lanterna. Poeira compactada e oxidação (verde) são comuns no J7 Prime e são
   exatamente o que mata a linha de dados, mantendo a carga.
5. **Celular ligado**: desligado (ou com bateria zerada) ele não aparece de jeito
   nenhum — só carrega. Deixe 30 min no carregador de parede e tente de novo.
6. Se o cabo é bom e outra porta também não mostra nada: o conector do aparelho
   provavelmente perdeu a linha de dados. É peça de bancada (troca do conector
   micro-USB), não é software.

Depois de cada tentativa, rode `celular.status` de novo: a comparação diz na
hora se o Windows viu algo entrar.

## Testes

- `pytest server/tests` → **2.739 passed** (`test_celular.py`: 93).
- Novos: leitura do código de problema, lista além de 10 itens, detecção do
  "desconhecido", primeira checagem que guarda a lista, comparação que vê "nada
  mudou", o que entrou/saiu, arquivo corrompido não derruba o status, plano que
  começa pelo físico, e o chat mostrando a comparação.
