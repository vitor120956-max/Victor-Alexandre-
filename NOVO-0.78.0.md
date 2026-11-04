# JARVIS 0.78.0 — agora ele se atualiza sozinho

Sua pergunta: *“ué, o JARVIS ainda não se auto atualiza?”*

Não, e era verdade: até a 0.77.1 ele só **percebia** a versão nova e mostrava o
aviso na tela. Aplicar dependia de você clicar em **Aplicar e reiniciar** — ou de
rodar o `atualizar.bat` na mão. Isso acabou.

---

## 1. O que passa a acontecer quando você abre o JARVIS

Você dá dois cliques no `iniciar-jarvis.bat`, como sempre. Só que agora a janela
mostra **quatro** passos, e o terceiro é novo:

```text
[1/4] Criando o ambiente Python em .venv (uma vez so)...
[2/4] Instalando as bibliotecas Python (so na primeira vez)...
[3/4] Procurando versao nova (so o que mudou)...
[4/4] Subindo o JARVIS. O navegador abre sozinho quando a API responder.
      Na proxima vez ele se atualiza sozinho antes de subir.
      Para parar: feche esta janela no X.
```

No `[3/4]` ele:

1. lê o manifesto (uns 57 KB) e compara com o que você tem;
2. baixa **só os arquivos que mudaram** — numa versão típica, 2 a 15 arquivos,
   algumas centenas de KB;
3. confere o hash de cada arquivo baixado;
4. guarda um backup do que vai ser substituído em `storage/atualizacao/backup-<data>/`;
5. aplica.

E aí sobe a API **já com o código novo**. É por isso que o momento importa: nesse
instante ainda não existe processo com módulo carregado na memória, então trocar
arquivo é seguro. Se ele atualizasse no meio do expediente, o processo velho
continuaria rodando código velho até você fechar.

## 2. Se alguma coisa der errado, ele não trava

Essa foi a regra número um: **atualização nunca pode impedir o JARVIS de abrir.**

| situação | o que acontece |
|---|---|
| sem internet / GitHub fora | sobe na versão atual e escreve o motivo na janela |
| um arquivo baixou corrompido | cancela o lote inteiro (nenhum arquivo pela metade) e sobe na atual |
| pasta com `.git` | não mexe: ali quem manda é o `git` |
| já está na última versão | segue direto, sem baixar nada |

Quando algo falha, aparece na janela:

```text
  A atualizacao automatica nao terminou. Sigo com a versao atual.
  Para tentar de novo na mao: feche esta janela e rode atualizar.bat.
```

## 3. Dependência nova = `pip install` automático

Se a versão nova mudou o `requirements.txt`, o Python avisa pelo código de saída
**4** e o `.bat` roda `pip install -r requirements.txt` antes de subir. Sem isso,
o JARVIS subiria com uma biblioteca faltando e quebraria na primeira chamada.

## 4. Como desligar (se você quiser)

Coloque esta linha no `.env`:

```text
JARVIS_AUTO_ATUALIZAR=0
```

O `.env` **manda mais** que o `iniciar-jarvis.bat` — é de propósito, senão a
variável que o `.bat` exporta anularia a sua escolha.

Para uma vez só, sem mexer no `.env`:

```bat
cd /d D:\JARVIS
.venv\Scripts\python.exe iniciar.py --sem-atualizar
```

## 5. E se eu abrir o JARVIS pelo `iniciar.py` direto?

Também atualiza. O `iniciar-jarvis.bat` marca `JARVIS_AUTO_FEITO=1` depois de
fazer a checagem, então o `iniciar.py` **não repete** — o manifesto não é baixado
duas vezes no mesmo start.

## 6. Pergunte a ele

No chat, *“por que o JARVIS não se atualiza sozinho?”* agora responde com o
estado real: se está ligado, quando foi a última checagem, e o motivo de estar
desligado (por exemplo, “pasta com Git: use o atualizar.bat”).

---

## Como pegar esta versão

Como o automático só existe **a partir** da 0.78.0, esta primeira vez ainda é
manual — depois não é mais:

1. feche a janela do JARVIS no **X**;
2. dois cliques em `atualizar.bat`;
3. espere terminar;
4. dois cliques em `iniciar-jarvis.bat`.

Da próxima vez em diante, o passo 2 deixa de existir: o `iniciar-jarvis.bat`
cuida disso.

## O que NÃO mudou

- **Não** atualiza com o JARVIS aberto: continua sendo no start, ou pelo aviso da
  tela com o seu clique.
- **Não** usa `git pull` nem apaga arquivo seu: `.env`, `storage`, `.venv` e
  `node_modules` ficam intocados.
- **Não** aplica nada vindo de fonte diferente do manifesto oficial, e todo
  arquivo passa por conferência de hash.
