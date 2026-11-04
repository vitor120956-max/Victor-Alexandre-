# JARVIS 0.77.1 — o cartão agora tem nome na tela (e a versão parou de mentir)

Sua pergunta foi direta: *“onde que tá o cartão Chaves de IA?”*. Duas causas, e
as duas eram minhas.

---

## 1. Você está numa versão anterior à 0.77.0

O cartão nasceu na 0.77.0. Na sua tela ainda aparece a frase antiga:

> *“Para ativar, defina `JARVIS_AI_API_KEY`, `JARVIS_AI_MODEL` e o endpoint
> compatível no arquivo `.env` do servidor. Não cole chaves no chat ou nesta tela.”*

Essa frase foi **substituída** pelo cartão na 0.77.0. Enquanto ela estiver ali,
a tela é a velha. Até atualizar, não há botão nenhum para procurar.

## 2. Mesmo na 0.77.0 o cartão não tinha título

O cartão aparecia como uma caixa com o texto “Nenhuma chave guardada” e um botão
**Colar chaves** — **sem o nome “Chaves de IA”**. Quem procurava o título não
achava, mesmo estando na versão certa. Corrigido: agora tem cabeçalho
**CHAVES DE IA** com ícone de chave, acima do estado.

---

## 3. A versão no rodapé era fixa: `0.5.0`

Aquele quadro **VERSÃO 0.5.0** no canto da sua tela não era a sua versão: era um
texto escrito à mão no código desde sempre. Ou seja, era impossível saber em que
versão você estava — e foi por isso que a ausência do cartão virou dúvida em vez
de “ah, é versão velha”.

Agora ele mostra a versão real, a mesma que responde em `/api/health`:

```text
VERSÃO   0.77.1
```

E se a API estiver desligada, mostra `API OFFLINE` em vez de um número inventado.

---

## 4. Um terceiro problema que daria dor de cabeça

A API escolhia a interface para servir nesta ordem: `dist`, depois `web-dist`.
`dist` é o build local (de quem roda `npm run build`); `web-dist` é a interface
que **vem na atualização**. Resultado: quem tinha um `dist` antigo atualizava e
continuava vendo a tela velha, porque o `dist` ganhava por estar na frente.

Agora a API serve a **mais nova** das duas, pela data do `index.html`. Em
empate, `dist` continua ganhando.

---

## 5. Como atualizar (escolha um caminho)

### Caminho A — um duplo-clique (funciona desde qualquer versão)

1. Feche a janela do JARVIS no **X**;
2. dê duplo-clique em **`atualizar.bat`** na pasta `D:\JARVIS`;
3. espere aparecer **atualizado**;
4. abra **`iniciar-jarvis.bat`**.

### Caminho B — pelo chat (se você já está na 0.74.0 ou mais nova)

```text
tem versão nova?
```
```text
atualiza o jarvis
```
```text
aplica a atualização
```

Depois feche no **X** e abra `iniciar-jarvis.bat` de novo — o código novo só vale
depois de reiniciar.

---

## 6. Como saber que deu certo

1. **Configurações** → rodapé → **VERSÃO 0.77.1** (não `0.5.0`);
2. na seção **Inteligência generativa**, o cabeçalho **CHAVES DE IA** com o
   botão **Colar chaves**;
3. cole o bloco das chaves, clique em **Salvar e testar**.

Se ainda aparecer `0.5.0` no rodapé, a atualização não entrou: confira se a
janela foi fechada no **X** antes de abrir `iniciar-jarvis.bat`, e se o
`atualizar.bat` terminou sem erro.

---

## 7. O que foi testado

| teste | o que prova |
|---|---|
| `test_a_tela_de_configuracoes_tem_o_cartao_e_nao_mente_a_versao` | o cartão existe **e tem o nome na tela**; nenhum número de versão fixo voltou ao rodapé |
| `test_prefere_a_interface_mais_nova` | `dist` velho não esconde o `web-dist` novo |
| `test_em_empate_prefere_dist` | a regra antiga continua valendo no empate |

Suíte: **3.214 passed, 7 skipped**. Front: 130 testes, `tsc` limpo, build
embutido ok, `manifest.json` conferido (478 arquivos).
