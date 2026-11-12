# JARVIS 0.89.3 — o terminal não é o Bloco de notas (e sim, ele usa o mouse)

Duas coisas nesta versão: o erro que estava travando e a sua pergunta.

## O erro: o diagnóstico apontou o culpado

```
  Bloco de notas (notepad.exe) — 1 janela(s):
    C:\Windows\system32\cmd.exe - .venv\Scripts\python arvore_sonda.py
    --programa "bloco de notas"  —  12 elemento(s), sem campo
```

A “janela do Bloco de notas” era **o próprio terminal**. O título do `cmd` é a
linha de comando — e a linha de comando dizia `"bloco de notas"`. Ele procurava
por título e achava o mensageiro, não o alvo.

Três regras, agora:

1. **processo vence título, sempre**;
2. **terminal nunca casa por título** — o título dele é o comando;
3. **título só casa inteiro** — “Como abrir o Bloco de notas” é artigo de
   site, não programa.

## Sua pergunta: por que não usa o mouse?

**Para chegar na janela, mouse não é necessário.** O Windows tem
`SetForegroundWindow` — é o que o Alt+Tab faz por dentro. Agora, antes de
escrever, ele traz a janela para a frente sozinho. Sem mover o ponteiro.

**Para apertar algo, o mouse existe — como último degrau.** A ordem agora é:

| grau | o que faz | usa mouse? |
|---|---|---|
| 1 | ação padrão do elemento | não |
| 2 | foco no elemento + teclado | não |
| 3 | foco no campo inteiro + teclado | não |
| 4 | escrever no valor do campo | não |
| 5 | **clique físico no centro medido** | **sim** |

O degrau 5 é o que você perguntou. Ele existe desde agora, com um interruptor:

```
.venv\Scripts\python arvore_sonda.py --programa "bloco de notas" --escrever "oi" --executar --mouse
```

Sem `--mouse`, ele não mexe no ponteiro. Com `--mouse`, se tudo o mais falhar,
ele clica no **centro da caixa que a leitura mediu** — coordenada medida, não
chutada. Sem caixa medida, ele não clica: diz que não tem posição.

Por que não é o primeiro caminho:

- mover o ponteiro mexe na máquina de quem está usando;
- sua tela dá **toque fantasma** — o ponteiro pode ser levado embora entre o
  mover e o clicar;
- clique errado numa tela em uso pode apagar trabalho.

## O que eu acho, para o Visão

Você está certo em querer o mouse: **para o que não se anuncia, ele é a única
mão que existe.** Jogo, vídeo, programa desenhado na tela — nada disso publica
campo.

Mas o caminho do elemento é melhor **onde ele funciona**, e não por gosto: é o
único que permite dizer *"escrevi 'oi' no campo X e conferi lendo de volta"*.
Clique não confere nada — ele acha que acertou.

O JARVIS bom é o que soma: **olho que mede** (árvore) + **mão que alcança**
(foco/ação) + **mouse quando nada disso existe** + **conferência sempre**.

## O comando

```
cd /d D:\JARVIS
```

```
atualizar.bat
```

```
.venv\Scripts\python arvore_sonda.py --programa "bloco de notas"
```

Agora esse comando **não deve** mostrar o cmd como se fosse o Bloco de notas.
Se o Bloco de Notas não estiver aberto, ele vai dizer:

```
  O Bloco de notas (notepad.exe) não está aberto.
```

E aí:

```
.venv\Scripts\python arvore_sonda.py --programa "bloco de notas" --escrever "oi, mundo" --executar
```

Se ainda resistir, acrescente `--mouse` no fim — e cole a saída.
