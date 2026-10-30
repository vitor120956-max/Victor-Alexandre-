# JARVIS 0.62.5 — o celular não está aparecendo na USB (e o Zadig não resolve isso)

A sua tela respondeu a pergunta. Vou ler o que ela disse:

```
O Windows tem 108 dispositivos; 11 sao nos USB.
Dispositivo portatil / MTP que o Windows esta vendo:
    PEN DRIVE
      id:     SWD\WPDBUSENUM\{9B9986EC-...}#0000000000004000
      driver: WUDFWpdFs
VID dos nos USB ligados agora: 058F 1A2C 275D
```

## O que esses números são

| VID | quem é |
| --- | --- |
| `058F` | Alcor — o **leitor de cartão** (é ele que cria o "PEN DRIVE") |
| `1A2C` | China Resource Semico — o **teclado** |
| `275D` | NewSoc/Hama — o **mouse óptico** |

**Nenhum `04E8`.** E o "Dispositivo portátil" que apareceu é o **seu pen drive**,
não o celular — repare no `WUDFWpdFs` (driver de volume WPD) e no id com GUID de
volume em vez de `VID_04E8&PID_xxxx`.

Ou seja: **o J7 não está enumerando na USB.** Nem como MTP, nem como nada.

## Por que isso muda o plano

O Zadig **só lista aparelho que o Windows está vendo**. Se o celular não
aparece, não existe driver a instalar — insistir no Zadig é perder tempo. A
pergunta anterior ("falta driver?") só faz sentido depois de responder "o
Windows vê o aparelho?".

E sim: a foto antiga mostrou a mensagem de MTP na tela do celular. Alguma coisa
mudou desde então — cabo, porta, ou o próprio conector. Não vou adivinhar qual.

## `teste-cabo.bat` — a pergunta, feita N vezes

Ele pede para você despluggar, pluggar de novo (com cabo/porta **diferente** a
cada tentativa), e observa o Windows. Entre tentativas ele **pausa** e espera
`Enter`, para você não correr contra o relógio. Durante a espera imprime
contagem a cada 2 s.

Veredito, baseado no que ele **viu**:

| código | significa | próximo passo |
| --- | --- | --- |
| **0** | apareceu `VID_04E8` | cabo/porta/conector bons — **agora** é driver: `sonda-otg.bat` |
| **1** | apareceu algo, mas não Samsung | colar a tela no chat |
| **2** | nada apareceu em N tentativas | **físico**: conector, cabo ou porta |
| **3** | a leitura do Windows falhou | rodar de novo (não conclui nada) |

O código 3 existe porque o erro caro aqui é dizer "não apareceu" quando na
verdade a consulta ao WMI falhou — e mandar você comprar cabo por causa disso.

## A lista física, do mais barato ao mais caro

Se o veredito for 2:

1. **Limpe o conector do celular.** Desligado, olhe o buraco do micro-USB com
   lanterna. Pelusa encosta nos pinos do meio (os de dados) e deixa a carga
   funcionando — é *o* caso clássico de "carrega mas o PC não vê". Palito de
   dente, sem força. **Nunca metal, nunca líquido.**
2. **Outra porta do PC** — a de trás, direto na placa. Hub aparece como um
   aparelho só e esconde o que está atrás dele.
3. **Outro cabo micro-USB** — o do carregador, o do power bank. Cabo "só carga"
   existe e não tem marca externa; a única forma de saber é trocar.
4. **Confirme que o celular está ligado** — segure o botão de ligar por 10 s.
   Se nem a carga aparece quando pluga, o problema é o conector e não o cabo.
5. Se nada disso mudar nada: **pino do conector quebrado** (mesma queda que
   trincou o vidro). Aí é solda/assistência — o PC não conserta isso por
   software, e eu não vou fingir que conserta.

## Onde o teste entra no fluxo

```
sonda-otg.bat   -> o driver de cada nó USB ligado (e os VID existentes)
teste-cabo.bat  -> o Windows muda quando o celular entra? (cabo x porta x conector)
teclado-pelo-pc.bat -> só depois que o aparelho aparece e a sonda diz OK
```

A `sonda-otg.bat` agora aponta para o `teste-cabo.bat` sempre que não achar
Samsung — e diz por quê: *"o Zadig só lista o que aparece"*.

## Testes

- `pytest server/tests` → **2.831 passed** (novo `test_teste_cabo.py`: 10).
- Os testes travam: pausa entre tentativas, contagem durante a espera, veredito
  de driver **só** no ramo do `04E8`, ordem da lista física (conector → porta →
  cabo), a frase honesta do pino quebrado, e falha de leitura nunca virando
  "aparelho ausente".
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
- Achado de manutenção: o script de bump de versão reescrevia `.bat`/`.ps1` em
  LF (`read_text` traduz quebra de linha). O teste de CRLF pegou os quatro
  arquivos; agora eles são regravados em CRLF.
