# JARVIS 0.61.9 — a vigia está certa; o ruído é que estava na frente

O log de 09:55 mostra que a mudança da 0.61.8 funcionou: os eventos chegaram
**em menos de um segundo** uns dos outros.

```
09:55:26  ENTROU  Alcor Micro USB 2.0 Card Reader [VID_058F]
09:55:26  ENTROU  Generic USB CF Reader [sem VID]
09:55:27  ENTROU  Generic USB SD Reader [sem VID]
```

(Compare com a 0.61.7, que só conseguia olhar a cada ~5 s.)

Mas a sessão inteira é **o leitor de cartão e seus quatro conectores** — CF, MS,
SD, SM — entrando e saindo. Nenhum `VID_04E8`. O celular não apareceu nesse
período, e a tela não deixou isso claro por dois motivos, ambos corrigidos aqui.

## O que estava ruim

**1. A tela dizia "nada mudou na USB" com 10 eventos na frente.**
Os contadores agora são honestos:

```
ainda vigiando (2 min) - nenhum aparelho; 10 evento(s) de outros dispositivos USB
ainda vigiando (3 min) - 2 evento(s) de aparelho ate agora
ainda vigiando (4 min) - nada mudou na USB
```

A terceira linha só aparece quando é verdade: nenhum evento de nenhum tipo.

**2. O ruído escondia o que se estava esperando.** Um leitor de cartão gera
**cinco linhas** por evento. Cinco linhas de leitor empurram para cima a única
linha que importa — a do celular. Agora o `vigiar-usb-atento.bat` mostra **só o
que é aparelho**:

- `VID_04E8` (Samsung);
- modelo reconhecido (`SM-A346B`, `SM-G610M`);
- `VID_0000` / "desconhecido" (a porta viu e o Windows não identificou);
- nome com Samsung/Android/Galaxy/MTP/SM-.

Todo o resto vira **uma linha discreta** no fim do evento, e continua **completo
no log**:

```
          (5 dispositivo(s) do PC: 5 entrou - Alcor Micro USB 2.0 Card Reader,
           Generic USB CF Reader, Generic USB MS Reader, ... - no log)
```

**3. Resumo no fim da sessão.** Quando os 10 minutos acabam (ou quando você
fecha), ele diz o que viu:

```
  Nesta sessao: 14 evento(s) de USB, 0 de aparelho.
```

Se esse número de aparelho for zero, o teste do cabo não mostrou nada — e isso é
informação, não silêncio.

## Como repetir

```bat
cd /d D:\JARVIS
```

```bat
atualizar.bat
```

```bat
cd /d D:\JARVIS
```

```bat
vigiar-usb-atento.bat
```

Na abertura:

```
  Modo evento: o Windows avisa na hora (nao existe intervalo para passar batido).
  Filtro: so aparelho (VID da Samsung, modelo ou desconhecido). O resto vai para o log.
```

Agora plugue o J7 (com o cabo que você achou) e, com ele plugado, **mexa o
conector devagar por um ou dois minutos**. O que a tela mostrar decide:

| Na tela | Conclusão |
|---|---|
| `ENTROU ... VID_04E8` (mesmo que apareça e suma) | **conector** com mau contato — bancada |
| nada de aparelho, mas "(N dispositivo(s) do PC…)" | o cabo/porta não apresenta o J7: cabo de dados é o próximo teste |
| `ENTROU ... VID_0000` / desconhecido | a porta viu o aparelho e não conseguiu conversar: **cabo de carga ou conector** |

## Testes

- `pytest server/tests` → **2.786 passed**.
- Novos: o `vigiar-usb-atento.bat` usa `-SoAparelhos`; o filtro reconhece
  `04E8`, `0000`, modelo e nome de aparelho; o ruído filtrado continua indo para
  o log (`Registrar`); e as três frases do sinal de vida existem — inclusive a
  que não deixa dizer "nada mudou" quando algo mudou.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
