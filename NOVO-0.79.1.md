# JARVIS 0.79.1 — a tela velha agora se denuncia, e o modelo virou uma escolha

Seu print respondeu a dúvida antes de mim: o rodapé dizia **VERSÃO 0.5.0**. Esse
número **não existe** na interface nova — ele é o texto fixo da tela antiga. Ou
seja: o Python já estava novo, a **tela** não. As 0.77.0 → 0.79.0 estão nessa
pasta; o que ficou velho foi o que o navegador estava mostrando.

---

## 1. Três coisas diferentes produzem a mesma tela velha

Antes, para você, eram todas a mesma coisa. Agora não:

| # | o que acontece | como se parece |
|---|---|---|
| 1 | os **arquivos** não foram trocados nesta pasta | `atualizar.bat` de outra cópia, ou falhou e a janela fechou antes de ler |
| 2 | **o processo** é antigo | o Python carrega o código no start e não recarrega ao trocar arquivo no disco |
| 3 | **o navegador** guardou a página | ele nem pede o `index.html` de novo |

## 2. O duplo clique que diz a verdade: `conferir-versao.bat`

Ele lê três coisas e termina com **um veredito**:

```text
  versão do servidor:       0.79.1
  pasta da interface:       web-dist
  versão da interface:      0.79.1

  versão da API:            0.79.1
  interface que ela serve:  web-dist
```

E então, uma linha de cada vez:

- API não respondeu → *“abra o `iniciar-jarvis.bat`”*;
- API de versão diferente do disco → *“feche a janela preta no **X** e abra de novo”*;
- tela mais velha que o servidor → *“rode o `atualizar.bat` nesta mesma pasta”*;
- tudo batendo → *“aperte Ctrl+F5 na página”*.

Não instala, não baixa, não altera nada. **Rode esse primeiro** quando algo na
tela parecer faltando — ele evita a rodada de “atualizei e nada mudou”.

## 3. O que mudou por dentro para isso não voltar a acontecer

- **carimbo de versão na interface**: o build grava `web-dist/versao.json`, e a
  API compara com a própria versão. A escolha entre `dist` e `web-dist` deixou
  de ser “a data mais nova” e passou a ser **a maior versão carimbada** — data
  mente em cópia por pendrive e em backup restaurado; número não;
- **`/api/health`** agora diz `interfaceVersao` e `interfaceVelha`;
- **aviso vermelho na tela** quando o servidor é mais novo que a tela servida,
  com o caminho de saída (`atualizar.bat` / `conferir-versao.bat`);
- **`index.html` sai com `no-cache`**; `/assets/*`, que tem hash no nome, pode
  ficar em cache para sempre. Antes, os dois saíam iguais — e o navegador podia
  guardar justamente o arquivo que aponta para a versão;
- **`atualizar.bat` imprime a versão** que ficou instalada e manda rodar o
  conferidor quando a tela parecer velha. Ele também parou de mandar apagar a
  pasta `dist\` “às cegas”: a regra mudou, e o aviso antigo assustava sem motivo.

## 4. “E sobre os modelos, como funcionam?”

Resposta curta: **a chave abre a porta; o modelo é quem responde.** A mesma
chave do Groq dá acesso a vários modelos, e trocar de modelo não pede chave
nova.

A troca é sempre a mesma:

| | modelo grande (70B, 120B) | modelo pequeno (8B, 20B) |
|---|---|---|
| entende frase torta | melhor | pior |
| velocidade | mais lento | quase instantâneo |
| cota grátis | menor | muito maior |

Não existe “o melhor” — existe o melhor para o seu uso. Por isso virou **cartão
na tela**: **Configurações → Inteligência generativa → `Modelos de IA`**, logo
abaixo de Chaves de IA.

- cada opção vem com uma frase do tipo *“o padrão; cota menor”* ou *“resposta
  quase instantânea; a maior cota grátis”*;
- **Usar este modelo** grava no `.env` e recarrega **na hora** — sem fechar a
  janela;
- **Voltar ao padrão** desfaz em um clique;
- há um campo para o **nome exato**, porque a lista é atalho e não prisão: se o
  provedor lançar um modelo novo, você usa sem esperar o JARVIS ser atualizado;
- com modelo local, o cartão avisa que o “nome” é o arquivo `.gguf` — não
  oferece lista de nuvem que não se aplica.

Guia completo em [`docs/MODELOS.md`](docs/MODELOS.md).

---

## O caminho mais curto para você, agora

1. Feche a janela preta do JARVIS no **X**.
2. Duplo clique em **`atualizar.bat`** — espere a linha **Versao instalada nesta
   pasta agora: 0.79.1**.
3. Duplo clique em **`iniciar-jarvis.bat`**.
4. Na tela, **Ctrl+F5** uma vez.
5. Confira o rodapé de Configurações: tem de dizer **0.79.1**, não 0.5.0.

Se em algum passo a tela continuar velha, rode **`conferir-versao.bat`** e me
mande a tela dele — ela já diz qual dos três casos é o seu.

## Números

- pytest: **3.295 passed, 2 skipped, 0 failed**
- vitest: **134 passed**
- manifesto: **493 arquivos**
- skills: **315** (nenhuma nova)
