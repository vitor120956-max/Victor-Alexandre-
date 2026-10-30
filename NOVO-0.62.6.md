# JARVIS 0.62.6 — o código 3 era bug meu, e falta o teste do conector

Duas coisas na sua mensagem:

1. **o teste respondeu código 3** ("falha de leitura") — isso é **bug meu**, não o
   seu PC;
2. **"todos os cabos, dois passam dados no A34, mas no J7 só carrega"** — essa é
   a informação mais decisiva que apareceu até agora.

## Bug 1: código 3 falso

A versão 0.62.5 fazia **uma** consulta WMI. Numa máquina de 4 GB com Win10 1607
essa consulta às vezes volta vazia sem erro — e o meu código tratava lista vazia
como "não consegui ler", abortando um teste que estava funcionando.

Agora:

- **3 tentativas** com 700 ms entre elas;
- **plano B**: `Get-CimInstance` (outra API para os mesmos dados);
- **plano C**: `Get-PnpDevice -PresentOnly`;
- **piso de sanidade**: menos de 5 dispositivos é leitura quebrada, nunca
  máquina vazia;
- falha numa tentativa **repete aquela tentativa**, não aborta o teste todo;
- código 3 só quando os três caminhos falham.

## Bug 2: consulta a cada 2 s perde aparelho que aparece por meio segundo

O ponto importante: **conector com solda fria faz o celular enumerar por frações
de segundo**. Minha espera consultava a lista a cada 2 s — e essa consulta leva
segundos nesta máquina. Ou seja, um aparelho que aparece por 300 ms passava
batido, e o teste concluía "nunca apareceu": **falso negativo que manda você
desistir de um conector que ainda funciona em certo ângulo.**

Agora a espera é por **evento** (`Register-WmiEvent` sobre `__InstanceCreationEvent`
do `Win32_PnPEntity`): o Windows avisa na hora, sem intervalo para passar batido.
Cada aparelho que entra é impresso com **hora**, VID, id e driver.

## `vigiar-cabo.bat` — o teste de pressão

Novo arquivo, 60 segundos:

```
vigiar-cabo.bat
```

Com o cabo plugado, você:

- pressiona o plugue para dentro, com cuidado, sem forçar;
- inclina de leve para cima, para baixo, para os lados;
- gira o plugue devagar;
- encosta uma cunha fina (papel dobrado) entre cabo e aparelho.

| resultado | significa |
| --- | --- |
| apareceu `VID_04E8` em algum ângulo | **solda fria** — dá para calçar e trabalhar |
| apareceu outra coisa | colar no chat |
| nada em 60 s | **pino quebrado** — só solda/assistência |

O primeiro caso é o que muda o jogo: se ele aparecer com o conector pressionado,
você descobre o ângulo, prende com papel dobrado e faz o trabalho inteiro
(`sonda-otg.bat` → `teclado-pelo-pc.bat`) enquanto o contato segura.

## Sobre "os cabos passam dados no A34"

Um detalhe que pode estar comendo o teste: **o A34 é USB-C e o J7 é micro-USB**.
Cabo que passa dados no A34 não entra no J7 — então ele não testou o J7. O que
vale para o J7 é um cabo **micro-USB** que já tenha passado dados em algum
aparelho.

Se você já testou cabos micro-USB que comprovadamente passam dados, então a
evidência aponta para o conector do J7 — e o teste de pressão diz se ele está
morto ou só com mau contato.

## O que a evidência está dizendo

| fato | o que descarta |
| --- | --- |
| Windows tem 11 nós USB, nenhum `04E8` | driver: não há o que instalar |
| "dispositivo portátil" era o pen drive (`WUDFWpdFs`) | MTP do celular ativo |
| o celular **carrega** ao plugar | cabo/porta totalmente mortos |
| a foto antiga mostrava o aviso de MTP na tela do J7 | o aparelho já falou com um PC |

Carga funcionando + dados não = os pinos do meio (D+/D-) do micro-USB estão
comprometidos, ou a solda deles na placa. É o dano clássico de queda — a mesma
que trincou o vidro e matou o digitalizador.

## Ordem honesta, do grátis ao caro

1. **Limpar o conector** — palito, sem metal, sem líquido. Pelusa nos pinos do
   meio é o caso clássico de "carrega mas o PC não vê".
2. **`vigiar-cabo.bat`** — solda fria ou pino quebrado.
3. **Cabo micro-USB** que comprovadamente passe dados.
4. **Porta de trás do PC**, direto na placa, sem hub.
5. **Solda do conector** em assistência. Por software eu não conserto pino
   quebrado, e não vou dizer que conserto.

## Testes

- `pytest server/tests` → **2.842 passed** (`test_teste_cabo.py`: 21).
- Novos: três tentativas + dois planos B, piso de sanidade, leitura falhada
  nunca virando "aparelho ausente", tentativa com falha sendo repetida, vigia
  por evento (`__InstanceCreationEvent`) em vez de consulta, hora registrada em
  cada entrada, queda para consulta se o Windows recusar a assinatura, modo
  `-Vigiar` com o passo a passo da pressão, e o aviso de que cabo USB-C do A34
  não testa o J7.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
