# JARVIS 0.91.13 — a resposta direta, e um ajuste que faltava

Pergunta: ele abre o site onde estão as chaves, uma por vez, pega e salva no
próprio sistema?

Quase. Duas correções, e um conserto que veio junto.

## Correção 1 — ele não “pega”; ele cria

Não existe pegar a chave que já está no site. O OpenRouter — e quase todos os
outros — mostra o valor uma vez, na criação, e depois só o prefixo mascarado. A
lista que você vê no site não tem a chave inteira; não tem de onde ler.

Então o que ele faz é **criar uma nova**, com o nome `jarvis-AAAA-MM-DD`, e
salvar essa. A antiga continua existindo na sua conta, e você pode apagá-la lá
quando quiser — o JARVIS não mexe nela.

## Correção 2 — é um provedor por vez

Não é uma varredura de todos os sites. É **o provedor que está no seu `.env`**:
OpenRouter abre openrouter.ai/keys; se você trocar para o Groq, ele abre
console.groq.com/keys. Uma chave, um site, um `.env`.

Se você quiser que ele passe por vários provedores numa rodada, dá para fazer —
mas cada um vira uma chave nova naquela conta, e o JARVIS só usa uma por vez.
Melhor decidir isso antes de sair criando.

## O conserto que faltava

Você disse “salva no próprio sistema”. O arquivo `.env` ficava certo, mas o
JARVIS que já estava aberto **não lia**: ele lê o `.env` uma vez, na abertura.
Resultado: a chave nova gravada, a tela mostrando a antiga até fechar e abrir.
De novo o mesmo defeito de tela velha.

Agora existe uma porta para isso: `POST /api/ai/recarregar`, que só aceita
pedido da própria máquina. Depois de gravar, o script chama essa rota. Se deu
certo, ele diz:

> O JARVIS que já está aberto passou a usar esta chave agora.

Se a API estiver fechada, ele não trata como erro — diz que ela vai ler a chave
quando abrir.

## O que foi provado

- A rota: um teste grava o `.env` **por fora** do processo trocando o provedor
  de Groq para OpenAI, confirma que o status ainda diz “Groq” (o processo não
  sabia), chama a rota e confirma que passa a dizer “OpenAI”.
- O aviso do script: que ele chama o endereço certo, e que API desligada
  devolve falha sem derrubar a gravação.
- Tudo o que já estava: 3.688 testes passando.

## O que não foi provado

O caminho inteiro no seu Chrome e no seu Windows — como sempre, isso mede-se aí.
Mas agora, se a chave for gravada, o JARVIS aberto já a usa, sem você precisar
reiniciar nada.
