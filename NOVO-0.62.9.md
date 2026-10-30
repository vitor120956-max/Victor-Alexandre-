# JARVIS 0.62.9 — "se você não tem acesso, como a gente vai mudar o sistema?"

A pergunta está certa, e é a que eu devia ter respondido antes de escrever
qualquer ferramenta. Vou responder sem rodeio.

## Trocar o sistema operacional **também** passa pela porta USB

Não existe atalho:

| caminho | precisa de quê | está |
| --- | --- | --- |
| Odin / Heimdall (download mode) | dados na porta micro-USB | **morto** |
| TWRP (flashar recovery) | dados na porta micro-USB | **morto** |
| `adb sideload` da ROM | dados na porta (ou TWRP já instalado) | **morto** |
| recovery de fábrica + cartão SD | — | **não instala ROM** |

O último é o que engana: o recovery de fábrica da Samsung aceita "apply update
from external storage", mas **só pacote assinado pela Samsung**. LineageOS,
postmarketOS, qualquer ROM de terceiro — não entra. E essa assinatura não se
fabrica em casa.

Wi-Fi também não: `adb` sem fio exige Depuração USB **já ligada**, e ela se liga
por toque. Flash de sistema por rede não existe.

## A boa notícia: **uma** solda reabre tudo

O conector micro-USB é o gargalo e também a chave. Consertando ele:

- voltam os **dados** na porta → **Odin** funciona → dá para instalar TWRP e ROM;
- volta o **`scrcpy`** → **teclado e mouse pelo cabo** → **a tela quebrada deixa
  de ser bloqueio**;
- logo, o **digitalizador vira opcional**.

Ou seja: o item mais barato dos dois consertos destrava o mais caro — e destrava
o que você quer, que é trocar o sistema.

## A ordem, depois da solda

1. plugar no PC e rodar `sonda-otg.bat` → tem de aparecer `VID_04E8`
   (se aparecer, o conector voltou **de verdade**; se não, o problema é o
   controlador USB na placa e o conserto é outro);
2. `teclado-pelo-pc.bat` → mouse e teclado do PC operam o celular, com o vidro morto;
3. nas Configurações (com o mouse do PC): Opções do desenvolvedor → **Desbloqueio OEM** → Depuração USB;
4. **Odin** + TWRP (download mode: Volume Baixo + Home + Power, depois Volume Cima);
5. no TWRP **sem toque**: instalar a ROM por **`adb sideload`** pelo cabo;
6. **LineageOS 18.1 (Android 11)** tem build para `on7xelte` / G610F. postmarketOS existe para o modelo, mas em *testing* — não é para uso diário;
7. depois da ROM: `celular.espelhar` deixa a tela numa janela do Windows — o uso vira o de um computador pequeno.

## O que não existe, e eu não vou fingir que existe

- **DeX**: começa no Galaxy S8 e exige USB-C com vídeo. O J7 Prime é de 2016.
- **MHL (micro-USB → HDMI)**: a Samsung responde oficialmente que o J7 Prime
  **não suporta**. Adaptador não resolve — falta o hardware de saída de vídeo.
- **"Modo PC" no Android** (Termux com área de trabalho, Sentio, Taskbar):
  precisa de **entrada** — mouse, teclado ou toque. As três estão fora do ar
  hoje; com a porta consertada, a entrada volta **pelo PC**.

## `acesso-celular.bat` — o mapa, para você não andar em círculo

```
acesso-celular.bat
```

Ele imprime as quatro vias, o estado de cada uma, a conclusão e — o mais útil —
**o que dizer ao técnico**:

> "quero trocar o conector de carga micro-USB do Galaxy J7 Prime, SM-G610 /
> on7xelte, com solda em bancada. Ele CARREGA mas não passa dados — não aceito
> teste só com carregador. Teste com um PC e veja se aparece no Gerenciador de
> Dispositivos."

Detalhe que evita ser enganado: **carga são dois pinos; dados são outros dois.**
"Está carregando, então está bom" é resposta de quem não vai consertar o que você
precisa.

## O que eu errei até aqui

Construí `sonda-otg`, `teste-cabo`, `vigiar-cabo`, `resgatar-cartao`,
`formatar-celular` — todas corretas, todas apontando para o mesmo lugar: **não há
software que atravesse um conector quebrado**. O próximo passo desta história não
é código, é uma solda. O código já está pronto para o dia em que ela acontecer.

## Testes

- `pytest server/tests` → **2.898 passed** (`test_acesso_celular.py`: 18).
- Skill nova `celular.acesso` (293 → **294 skills**), sem efeito colateral.
- Os testes travam: a conclusão de que trocar o sistema passa pela porta, que o
  cartão não instala ROM e por quê, que Wi-Fi não serve, a ordem exata depois do
  conserto (`sonda-otg` → `teclado-pelo-pc` → Desbloqueio OEM → Odin →
  `adb sideload` → LineageOS), que se ainda não enumerar é o controlador USB, e
  as duas frases que impedem ilusão: DeX não existe neste modelo e MHL foi
  negado pela Samsung.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
