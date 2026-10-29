# JARVIS 0.61.3 — `vigiar-usb.bat`: a porta ao vivo, com apito

As respostas fecharam o diagnóstico:

- o celular **carrega** quando plugado no PC → energia (VBUS/GND) está OK, no
  cabo, na porta e no conector;
- **liga**, mas a tela está morta/apagada;
- o cabo foi **plugado e desplugado** entre as duas checagens, e a lista de USB
  continuou **idêntica** (14 dispositivos, nenhum Samsung, nenhum desconhecido).

Ou seja: **a linha de dados (D+/D−) não está passando**. Como o celular carrega,
o problema não é "sem energia" — é a conversa USB, e ela acontece num destes três
lugares: cabo (só-carga ou quebrado), conector do aparelho (poeira/oxidação/pino
solto) ou porta do PC. Enquanto isso não for resolvido, driver e Depuração USB
não mudam nada — nem o `scrcpy --otg`, que usa exatamente os mesmos fios.

## O que entra nesta versão

**`vigiar-usb.bat`** (com `vigiar-usb.ps1` ao lado). Duplo clique e a janela
fica aberta, checando a USB a cada 2 segundos:

```
  JARVIS - vigiando a USB do Windows
  Plugue e desplugue o cabo do celular: o que mudar aparece aqui na hora.
  Para parar: feche esta janela no X.

  Agora: 14 dispositivo(s) na USB.
    - USB Mass Storage Device [VID_058F]
    - USB Root Hub [sem VID]
    - Intel(R) N10/ICH7 Family USB Universal Host Controller - 27C8 [sem VID]
    ... e mais 11

  Esperando mudanca...
22:03:41  ENTROU  Dispositivo USB desconhecido [sem VID]
          O Windows viu algo e nao conseguiu identificar: cabo de
          carga ou conector. Troque por um cabo de dados e veja de novo.
22:04:02  SAIU    Dispositivo USB desconhecido [sem VID]
          ainda vigiando (1 min) - nada mudou na USB
```

- **apita** (`[console]::Beep`) no instante em que algo entra ou sai, com hora;
- reconhece o caso que importa: `VID_04E8` avisa em verde que **é a Samsung** — e
  aí o próximo passo é `status do celular`; `VID_0000`/`desconhecido` avisa em
  amarelo que é cabo/conector, não driver;
- mostra **sinal de vida a cada 30 s** com o tempo decorrido — janela parada não
  é travamento;
- só leitura: não instala, não altera nada, não chama o adb, não precisa de
  admin; PowerShell 5.1 puro;
- para parar, **fecha no X** — nenhum atalho de teclado para decorar;
- `vigiar-usb.bat -Minutos 5` fecha sozinho depois de cinco minutos.

Também entraram nos passos do `celular.plano` e nas respostas do chat: quando o
diagnóstico é físico, o passo agora cita a vigia em vez de mandar rodar
`status do celular` de novo a cada tentativa.

## O que testar agora, do mais barato ao mais caro

1. **Outro cabo** — de preferência o original da Samsung ou um que você saiba que
   sincroniza (aquele que já transferiu foto de algum aparelho). Abra a vigia
   antes: se a linha verde aparecer, era o cabo.
2. **Outro PC** com o mesmo cabo (notebook de alguém serve). Se o celular
   aparecer lá, o problema é a porta deste PC; se não aparecer, é cabo ou
   conector do aparelho.
3. **Conector**: com o cabo fora, luz de lanterna no micro-USB. Poeira
   compactada, fio de tecido ou oxidação verde — limpe com álcool isopropílico e
   um palito/cotovelo, aparelho desligado, e deixe secar.
4. **Se nada disso mudar**: conector micro-USB do aparelho (bancada, faixa de
   R$ 50–100). Já que vai abrir, é a hora de considerar a tela (R$ 70–160 a
   compatível): com tela funcionando, ligar a Depuração USB e espelhar deixa de
   depender de adivinhação às cegas.

## Testes

- `pytest server/tests` → **2.749 passed** (`test_vigiar_usb.py`: 12 novos).
- Garantem: os dois arquivos existem lado a lado do `iniciar.py`, o `.ps1` é
  ASCII puro (chcp 65001 embaralha acento), **sintaxe PowerShell válida** pelo
  parser (`tree_sitter_powershell`), nada de `Remove-Item`/`Start-Process`/
  download, apito e aviso de entrada, reconhecimento do `VID_04E8` e do
  "desconhecido", sinal de vida de 30 s, nenhuma menção a `Ctrl+C`, e o `.bat`
  chamando o `.ps1` com `-ExecutionPolicy Bypass`.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
