# JARVIS 0.82.3 — a UIAutomation funcionou; a busca da janela não

Duas notícias, uma boa e uma minha.

## A boa: a segunda fonte está de pé

Os índices corrigidos na 0.82.2 fizeram o que deviam:

```
--alvo chrome --diagnostico
  [ok  ] CoCreateInstance(IUIAutomation)    0x00000000  objeto criado
  [ok  ] get_ControlViewWalker (índice 14)  0x00000000
  [ok  ] ElementFromHandle (índice 6)       0x00000000
  [ok  ] get_CurrentControlType             0x00000000  tipo=50032
```

E onde a MSAA devolvia 1 elemento (a moldura), a UIA devolveu **12 com
conteúdo**:

```
barra de rolagem “Vertical”
  botão “Uma linha acima”     @93d11915:e3
  botão “Uma página acima”    @93d11915:e4
  elevador “Posição”
  botão “Uma página abaixo”   @93d11915:e6
  botão “Uma linha abaixo”    @93d11915:e7
```

Isso é a primeira leitura **com nome de verdade** vinda do seu PC. A etapa 2
(clicar por `ref`) deixou de ser hipótese.

## A minha: `--alvo chrome` leu o terminal

Olhe o título da janela que ele leu:

```
cmd.exe — C:\Windows\system32\cmd.exe - .venv\Scripts\python arvore_sonda.py --alvo chrome
```

A palavra “chrome” está **ali**, no meio do comando. A busca procurava primeiro
no título — e o título do terminal é a linha de comando. A janela que roda a
sonda é a única que sempre tem o pedido escrito dentro dela, e era justamente
onde a busca começava.

Corrigido em três regras:

| regra | por quê |
|---|---|
| a janela da sonda **nunca** é candidata | é a que sempre carrega o pedido |
| **processo vence título** | `chrome` → `chrome.exe` (nota 0) antes de qualquer título (nota 3) |
| erro lista só janelas de programa | sem menu Iniciar, sem barra, sem o próprio terminal |

Agora `--alvo chrome` acha o Chrome — e `--alvo calculadora` diz o que está
aberto em vez de ler o `cmd`.

## O teste de agora

Com o **Chrome** aberto e na frente:

```
cd /d D:\JARVIS
```

```
atualizar.bat
```

```
.venv\Scripts\python arvore_sonda.py --alvo chrome
```

O que eu preciso saber, em uma linha: **quantos elementos**, **quantos
acionáveis**, e se aparece **nome de conteúdo** (título, link, botão da página)
ou só moldura.

Se vier pouco, o segundo comando é:

```
.venv\Scripts\python arvore_sonda.py --alvo chrome --fonte uia
```

## O que o Windows 10 do seu PC muda

O build 14393 é de 2016. A UIAutomation dele é antiga, mas **funciona** — você
acabou de ver. O que pode acontecer: o Chrome publicar só a moldura dele pela
UIA e deixar o conteúdo da página para a árvore interna do próprio Chrome (que a
UIA expõe como “documento”). Se for isso, eu vejo no número e trato na próxima.

## O que continua fora

- **Clicar por `ref`** (etapa 2): agora é a próxima de verdade, mas ainda depende
  de ver a árvore do Chrome com conteúdo.
- **Gmail/Drive/Agenda por OAuth**, **WhatsApp**: como antes.
