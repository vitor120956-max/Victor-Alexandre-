# JARVIS 0.60.8 — o status que não olhava o celular

Você rodou `celular.status` e ele respondeu:

```
adb: D:\JARVIS\storage\ferramentas\platform-tools\adb.exe · scrcpy: ...\scrcpy.exe. Tudo pronto.
```

**"Tudo pronto" era mentira.** Aquele "status" só olhava a pasta das ferramentas
— o mesmo que conferir se a chave está na gaveta e concluir que a porta abriu. O
celular podia estar desligado, sem cabo, sem depuração: a resposta seria igual.

## O que mudou

`celular.status` agora **mede o aparelho de verdade**: roda `adb devices -l`
(só leitura) e, quando não vê nada, consulta a USB do Windows. A resposta começa
pelo que importa e termina dizendo o próximo passo:

| Situação | O que a resposta diz |
|---|---|
| `R58M12ABC (SM-G610M): autorizado` | "Pronto. Próximo passo é `celular.espelhar`." |
| `unauthorized` | "Falta o toque em ‘Permitir depuração USB?’ na tela." |
| vazio, Windows vê o aparelho | "Cabo e porta bons; falta ligar a Depuração USB." |
| vazio, Windows vê com ⚠ | "Falta o Samsung USB Driver." |
| vazio, Windows não vê nada | "É cabo, porta, bateria ou a placa USB." |
| adb falhou | mostra o erro real do adb, sem culpar a trava |

A skill mudou de nome junto: **"Ferramentas do celular"** → **"Estado do
celular"**. A descrição antiga dizia, com todas as letras, "só olha o disco — não
fala com o aparelho". Era exatamente o que fazia.

## Também nesta versão

- **Página Skills**: qualquer skill do celular mostrava o aviso genérico
  ("Skill Python operacional. Versão…") em vez do resultado. Agora há formatação
  própria para `celular.status` e `celular.preparar` — e, de bônus, toda skill que
  devolve `resposta` passa a mostrar esse texto em vez do aviso.
- **Tempo limite** do status: 10 s → 90 s. A primeira chamada do adb pode levar
  45 s (o serviço dele sobe e o antivírus escaneia o `.exe`).
- Quando o adb quebra por conflito de versão de servidor, a resposta diz para
  fechar Android Studio/emulador — em vez de sugerir que a camada está desligada.

## Como testar agora

1. **Conecte o J7 Prime** no PC com o cabo micro-USB, direto numa porta (sem hub).
2. Rode `celular.status` de novo.

Pela primeira vez a resposta vai falar do aparelho, não da pasta. Se aparecer
"vazio", rode `celular.plano` logo depois: ele começa pelo passo certo para o que
o Windows viu.

## Testes

- `pytest server/tests` → **2.696 passed**.
- `test_celular.py` → **72** (7 novos: autorizado, sem cabo com Windows cego, com
  driver ruim, com Windows vendo o aparelho, não autorizado, adb falhando, e o
  caso "tudo pronto sem cabo" que era o bug).
- `vitest` → **124** (4 novos em `skillResults.test.ts`).
- `tsc -b` limpo, build embutido ok.
