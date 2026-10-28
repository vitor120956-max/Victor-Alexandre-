# JARVIS 0.61.0 — "USB Composite Device" não é o seu celular

O status da 0.60.8 respondeu:

```
Windows na USB: O Windows vê o aparelho (USB Composite Device).
O Windows vê o aparelho, mas o adb não: cabo e porta estão bons, e o que
falta é ligar a Depuração USB.
```

**O problema é a primeira frase, não a segunda.** "USB Composite Device" é o
nome do *driver genérico* do Windows — webcam, hub, teclado e mouse usam
exatamente esse nome. A sonda procurava a palavra "Composite" e aceitava
qualquer coisa. Ou seja: ela pode ter visto a sua webcam e concluído que o cabo
do celular estava perfeito.

Se essa conclusão estiver errada, o conselho estava errado junto: ligar a
Depuração USB de um aparelho que não está nem conectado não muda nada.

## O que mudou

A sonda agora pede ao Windows o **InstanceId**, que carrega o VID/PID direto do
hardware — não depende de nome de driver nenhum.

- **Samsung é VID `04E8`.** É assim que o aparelho se identifica na USB,
  instalado driver ou não.
- Nome com marca/modelo (`SAMSUNG`, `Galaxy`, `SM-`, `MTP`, `ADB`) também vale.
- **"USB Composite Device" sem VID de Samsung não conta como celular.**

A resposta agora lista o que foi visto, marcado:

```
Windows na USB: O Windows vê o celular (USB Composite Device VID_04E8).
• USB Composite Device VID_04E8 [OK, celular]
• USB Composite Device sem VID [OK, não é Samsung]
```

## Quatro diagnósticos, quatro ações diferentes

| O que a sonda acha | O que o JARVIS diz |
|---|---|
| `VID_04E8` + nome com "SAMSUNG" | cabo bom, falta a **Depuração USB** |
| `VID_04E8` + nome genérico | **falta o driver da Samsung** — sem ele o adb não vê nem com a depuração ligada |
| só dispositivos genéricos | **não é o celular**: teste conectar/desconectar |
| nada | cabo, porta, bateria ou placa USB |

O segundo caso é novo e é o que mais engana em Windows 10 1607 limpo: sem o
**Samsung USB Driver for Mobile Phones**, o Windows reconhece a Samsung pelo
VID, chama de "USB Composite Device" e o adb não enxerga — a pessoa liga a
depuração, nada muda, e conclui que o celular morreu.

## O teste que decide (30 segundos)

Com essa versão, `celular.status` faz a pergunta certa. Se ele disser que o que
está na USB **não é o celular**:

1. com o cabo no celular, rode `celular.status`;
2. tire o cabo do celular e rode de novo.

- a lista **mudou** → o aparelho está sendo reconhecido; volte ao que a resposta
  disser (driver ou depuração);
- a lista **não mudou** → aquele dispositivo é do PC, e o celular não está
  chegando ao Windows. Aí é cabo, porta ou a placa USB do aparelho — e nenhum
  ajuste de software resolve.

## Testes

- `pytest server/tests` → **2.715 passed**.
- `test_celular.py` → **78** (3 novos: Samsung com nome genérico pede driver,
  lista da USB marca quem é celular, e o chat mostra o VID).
- Casos cobertos: VID de outra marca não vira celular, nome "MTP" sem VID vira,
  e o plano muda de primeiro passo conforme o que a sonda achou.
