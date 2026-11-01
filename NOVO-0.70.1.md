# JARVIS 0.70.1 — o que você fala no chat chega na skill

A 0.70.0 entregou o modo ousado, mas só na tela e no `.bat`. No chat, a frase
**“arruma o pc no modo ousado”** caía no arrumar normal: o `ousado` era engolido
e você recebia outra coisa sem aviso. Isso é pior que não ter o recurso — é ter o
recurso e ele mentir.

## O que mudou

A frase agora vira parâmetro, do mesmo jeito que o formulário da tela:

| o que você escreve | o que ele faz |
|---|---|
| `arruma o pc` | pede confirmação e executa o plano normal |
| `arruma o pc só o plano` | mostra o plano e **não** pede confirmação — nada é mexido |
| `o que dá para limpar do windows` | idem: só o plano |
| `quanto de espaço dá para liberar` | idem: só o plano |
| `arruma o pc no modo ousado` | inclui o `cuidado` reversível (Xbox, Teams, Search, Superfetch, hibernação) |
| `arruma o pc sem ponto de restauração` | pula o ponto e mantém o instantâneo |
| `arruma o pc ousado e só o plano` | as duas escolhas juntas |
| `limpa as sobras do pc` / `limpa a lixeira` | o mesmo braço, pelo verbo e pelo alvo |
| `desfaz a última limpeza` / `volta tudo como era` | reverte o último diário |
| `me manda o script da limpeza` | continua texto (`maquina.limpar`) — script não é braço |
| `o que dá para tirar do windows` | continua o debloat, que só lê |

O que a frase **não** diz fica no padrão da skill: ponto de restauração ligado,
modo normal, as cinco frentes. E a confirmação do chat continua mostrando o que
vai ser usado — “Vou usar: ousado=True” — antes de qualquer coisa acontecer.

## Onde ficou

- `server/agente_local.py`: `_pedido_direto_de_maquina`, com as escolhas lidas da
  frase (ousado, só o plano, sem ponto) e o desfazer separado;
- `server/tests/test_agente_local.py`: **7 testes novos** — inclusive o negativo
  que impede a limpeza de roubar “script da limpeza”, “limpa o teclado” e “o que
  dá para tirar do Windows”;
- `docs/LIMPEZA.md` §9: a tabela de frases;
- `README.md`: os limites desse atalho (é palavra-chave, não entendimento).

## Testes

- `pytest server/tests` → **3.042 passed, 7 skipped**.
- `vitest` → 124; `tsc -b` limpo; build embutido ok.
- Skills: **306** (nenhuma nova — o atalho conversa com as que já existiam).
