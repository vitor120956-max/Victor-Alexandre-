# JARVIS 0.91.29 — o jeito de não esperar página nenhuma

Você perguntou o que qualquer pessoa perguntaria: *“esse Chrome é muito lento,
não tem outro jeito?”*. Tem — e é bem melhor.

O problema nunca foi o Chrome. Foi **precisar de uma página** para criar uma
chave. O OpenRouter tem uma chave especial para isso, a **chave de gestão**
(management / provisioning key): ela não conversa com o modelo, ela **cria
outras chaves**. Com ela, criar a chave do JARVIS é um pedido e uma resposta,
em um segundo:

    POST https://openrouter.ai/api/v1/keys
    → {"key": "sk-or-v1-…"}

Sem janela. Sem carregamento. Sem login. Sem espera.

## O atalho novo

    chave-pela-api.bat        (um duplo clique)

**Na primeira vez**, ele faz só isto:

1. abre a página `openrouter.ai/settings/management-keys` no seu Chrome normal
   — o rápido, aquele em que você já está logado;
2. você clica em **Create New Key**, dá o nome `jarvis-gestao` e clica em
   **COPIAR**;
3. volta para a janela preta e aperta Enter.

O JARVIS lê a chave da área de transferência, **confere** que ela realmente
pode criar outras chaves e guarda no `.env`. Depois disso, criar chave é um
segundo — e nunca mais precisa abrir navegador.

Essa chave de gestão não serve para conversar com o modelo: se alguém pegá-la,
não gasta os seus créditos. Ela só cria e lista chaves.

## E o Chrome ficou menos lento também

Não desisti dele. O `chrome-cdp.bat` agora:

- **não abre outro Chrome** se a janela do JARVIS já estiver aberta — ele
  aproveita a que está lá, sem recarregar a página;
- abre com as opções que tiram trabalho de segundo plano (sincronização de
  conta, extensões, atualização de componente, pedidos automáticos). Num perfil
  novo isso faz diferença;
- espera até **30 s** pela porta, em vez de 20.

## Qual usar?

| situação | atalho |
|---|---|
| quero o caminho mais rápido, e nunca mais esperar página | **`chave-pela-api.bat`** |
| já tenho a chave de gestão guardada | `chave-pela-api.bat` (um segundo) |
| a página abre rápido na minha máquina e eu prefiro assim | `chrome-cdp.bat` |
| já copiei uma chave no site na mão | `pegar-chave.bat` |

## Testado sem gastar a sua vez

Um OpenRouter falso responde tudo o que importa, e cada resposta tem de virar a
frase certa — sem gravar nada quando não deu:

- a chave que volta é a que é gravada;
- resposta sem `key` é erro, não `.env` vazio;
- 401 (chave não aceita), 403 (é chave comum, não de gestão), 429 (espere um
  pouco), servidor fora e falta de internet — com o próximo passo escrito;
- a chave de gestão é **conferida antes** de ser guardada (ela tem o mesmo
  formato de uma chave comum, e guardar a errada só daria erro na vez seguinte);
- e os atalhos: todo `goto` tem rótulo, o `chave-pela-api.bat` não abre
  `chrome.exe`, o `chrome-cdp.bat` confere a porta **antes** de abrir o Chrome;
- a pasta `perfil-cdp` (o perfil do Chrome do JARVIS, com os dados de login)
  fica **fora** do manifesto de atualização e do repositório — senão toda
  atualização tentaria baixar centenas de megabytes por cima do seu perfil.

Suíte: **3.841 testes**, 7 pulados.
