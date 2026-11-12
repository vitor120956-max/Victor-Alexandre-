# JARVIS 0.89.5 — o nome estava certo, o lugar estava errado

```
não achei bloco de notas no PATH, em C:\Windows nem no App Paths
([WinError 2] ...: 'bloco de notas')
```

Olhe com atenção: **`'bloco de notas'`** — o nome de gente usado como nome de
arquivo. Não faltava o Bloco de Notas. Faltava combinar quem fala o quê.

## O que estava trocado

O projeto tem duas camadas que abrem programa, e elas falam línguas
diferentes:

| camada | recebe | exemplo |
|---|---|---|
| `pc.abrir_programa` (a da API) | nome de gente | `bloco de notas` |
| `abrir` injetado (a da sonda) | executável | `notepad.exe` |

Na 0.89.4 eu passei cada um para o lado errado. A mensagem acusava o PC de não
ter o programa — quando o problema era o meu argumento. Terceira vez nesta
semana que um erro meu aparece com cara de problema do Windows.

## O que mudou

- Cada camada recebe o que entende.
- `abrir_direto` **tolera** o nome falado: se chegar `bloco de notas`, resolve
  para `notepad.exe` em vez de falhar. Quem chama nem sempre sabe o que tem em
  mãos.
- O diagnóstico passou a responder **duas perguntas de uma vez**.

## O comando — só o diagnóstico primeiro

```
cd /d D:\JARVIS
```

```
atualizar.bat
```

```
.venv\Scripts\python arvore_sonda.py --programa "bloco de notas"
```

Agora ele diz se está aberto **e** se está instalado. Se estiver fechado mas
instalado, a resposta é (mais ou menos assim):

```
O Bloco de notas (notepad.exe) não está aberto.
Instalado em: C:\Windows\System32\notepad.exe
```

Se não estiver instalado:

```
E não achei notepad.exe no PATH, em %SystemRoot% nem no App Paths —
o programa pode não estar instalado neste PC.
```

Uma linha resolve a dúvida: **o programa existe neste PC?** Com essa resposta,
o próximo passo é certeiro em vez de mais uma tentativa.

## Um pedido

Colar no terminal uma linha que **não é comando** (aqui foi o `abri: ...` que eu
tinha escrito como exemplo de saída) faz o cmd reclamar. Culpa minha por
mostrar saída em bloco parecido com comando. Daqui para a frente eu escrevo a
saída esperada em texto normal, nunca em bloco que dá para copiar.
