# JARVIS 0.61.6 — o A34 provou a porta; o J7 não apareceu

O teste com o Galaxy A34, tela desbloqueada, deu o resultado que faltava:

```
09:06:14  ENTROU  USB Composite Device [VID_04E8]
          E a Samsung: o celular esta na porta agora.
09:06:14  ENTROU  Remote NDIS based Internet Sharing Device [VID_04E8]
09:06:35  SAIU    USB Composite Device [VID_04E8]
```

Isso prova, em uma tacada: **a porta USB do PC funciona**, o **Windows 10 1607
reconhece Samsung** (VID_04E8 é lido do hardware) e a **janela de vigia detecta
na hora**. O que sobrou para o J7 é o cabo micro-USB ou o conector do aparelho —
e nada mais.

## "Será a tela de bloqueio?"

Não. O aparelho **aparece na USB mesmo travado**: o Android enumera o
dispositivo quando recebe energia, independentemente da tela. O desbloqueio muda
o **acesso a arquivo** (MTP/pedido de permissão), não a existência dele na porta.
Se a tela bloqueada fosse a causa, o J7 apareceria como `USB Composite Device
VID_04E8` e falharia só ao abrir as pastas.

E você pode provar isso com o A34 em 30 segundos: **bloqueie a tela do A34** e
plugue. Se ele continuar aparecendo na vigia como `VID_04E8`, está provado que o
bloqueio não esconde aparelho nenhum — e o J7, que não aparece nem travado, tem
problema de fio, não de tela.

## O que muda no JARVIS

**O modelo do aparelho agora aparece.** A sonda lê
`DEVPKEY_Device_BusReportedDeviceDesc` — o modelo que o próprio aparelho informa
no protocolo USB — e mostra `SM-A346B` (A34) ou `SM-G610M` (J7 Prime). Sem isso,
todo Galaxy é "USB Composite Device" e não havia como saber qual dos dois estava
na porta:

```
• USB Composite Device SM-A346B VID_04E8 [OK, celular]
```

**O JARVIS guarda quem já passou por esta máquina** (`storage/celular/aparelhos-vistos.json`).
Quando o Windows não vê nada e já viu um Samsung antes, a resposta não manda
repetir teste nenhum — ela diz o que o teste já provou:

> Esta porta já viu um Samsung (SM-A346B, em 29/10 09:06): o PC, a porta e a
> instalação do Windows estão provados bons. O que não aparece agora é o aparelho
> que você plugou — cabo de dados ou o conector dele.

**A vigia mostra o modelo** na entrada (`E a Samsung SM-A346B: o aparelho esta na
porta agora`) e na lista inicial.

**Mensagem do driver, corrigida.** Antes ela afirmava que "sem o driver da Samsung
o adb não enxerga o aparelho". O A34 mostrou o caso real: VID reconhecido, nome
genérico, e o MTP funcionando. Agora a mensagem é condicional e correta — MTP
funciona com o driver genérico; o que pode faltar é a **interface ADB**, e o passo
de instalar o Samsung USB Driver entra **se o adb continuar sem ver** depois de
ligar a Depuração USB.

## O próximo teste, agora que o PC está provado

1. **O cabo micro-USB em outro aparelho de entrada igual.** Qualquer coisa com
   micro-USB: outro celular antigo, Kindle, câmera, controle, Arduino. Abra o
   `vigiar-usb.bat` e plugue. **Se nada aparecer, o cabo é só de carga** — e o
   problema custa R$ 15–25. Esse é o teste decisivo, e ele não depende do J7.
2. Se o cabo estiver bom em outro aparelho, o suspeito é o **conector do J7**:
   abra a vigia e aperte/balançe o conector devagar — um conector com solda
   trincada às vezes enumera por um instante.
3. Lanterna no micro-USB do J7, aparelho desligado: poeira compactada e oxidação
   verde matam só a linha de dados, mantendo a carga (que é exatamente o sintoma).

## Testes

- `pytest server/tests` → **2.771 passed** (`test_celular.py`: 115).
- Novos: leitura do modelo, modelo de outra marca recusado, caminho interno do
  Windows (`\Device\USBPDO-3`) recusado, modelo na linha do chat, memória de quem
  já apareceu (só Samsung), a memória aparecendo nos dois diagnósticos de "nada
  na porta", a frase sobre tela bloqueada presente nos textos, e o plano mandando
  testar o mesmo cabo em outro aparelho.
- `vitest` → 124, `tsc -b` limpo, build embutido ok.
