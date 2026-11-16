# Testes de regressão — a regra do projeto

> **Toda vez que um defeito for corrigido, entra um teste que reproduz aquele
> defeito.**

Pedido do dono, 15/11/2026: *“toda vez q corrigir um bug crie um teste de
regressao”*. Este arquivo é a regra, e o teste
`server/tests/test_regras_do_projeto.py` confere que ela está sendo cumprida.

---

## 1. Por que

As versões 0.91.15 a 0.91.20 consertaram, uma atrás da outra, defeitos que só
apareceram no PC do dono — e três delas consertaram o **mesmo sintoma** (“não
criou a chave”) por causas diferentes:

| versão | o que estava errado | como se descobriu |
|---|---|---|
| 0.91.15 | o diálogo tem três campos e o Create fica apagado | print da tela |
| 0.91.16 | a leitura não chegava no painel (8 níveis) | print com o painel aberto |
| 0.91.17 | a leitura voltava só a moldura (3 nomes) | print com “3 elementos” |
| 0.91.18 | a ação do elemento devolve sucesso e não faz nada | print com “ação padrão do elemento” |
| 0.91.19 | o nome ia para o rótulo, não para a caixa | print do campo vazio |
| 0.91.20 | o botão não vinha na primeira leitura e o script desistia | print com o botão na tela |

Sem teste de regressão, cada correção nova podia desfazer a anterior — e foi o
que quase aconteceu (a espera da página passou a usar leitura rasa na 0.91.17 e
o botão “sumiu” na 0.91.20).

## 2. Como o teste é feito

Quatro regras, e nenhuma delas é sobre estilo:

1. **o teste reproduz o defeito, não a correção.** Ele monta a situação que
   quebrou (a página carregando, a leitura com 3 nomes, o rótulo ao lado da
   caixa) e exige o resultado certo. Se o teste passar na versão anterior à
   correção, ele não é de regressão — é decoração;
2. **o nome diz o que aconteceu**, não o nome da função:
   `test_o_botao_aparece_na_terceira_leitura`, não `test_achar_elemento_2`;
3. **o comentário cita a tela ou a frase do dono.** Quem ler daqui a três meses
   precisa entender por que aquele teste existe;
4. **fica no arquivo do assunto.** Diálogo e reconhecimento em
   `test_chave_web.py`; o driver em `test_chave_no_navegador.py`; o caminho
   inteiro em `test_chave_ponta_a_ponta.py`.

## 3. Onde está cada um

| versão | teste(s) |
|---|---|
| 0.91.13 | `test_chave_no_navegador.py`: a API aberta é avisada para reler o `.env` (`POST /api/ai/recarregar`) |
| 0.91.14 | `test_chave_no_navegador.py`: a travessia do login (Sign In → Google → conta) e a conta ambígua que não é escolhida no chute |
| 0.91.15 | `test_chave_no_navegador.py`: diálogo preenchido, Create conferido, maior prazo, “No limit” |
| 0.91.16 | `test_chave_no_navegador.py`: leitura funda acha o painel enterrado; painel na outra janela; diagnóstico com contagem |
| 0.91.17 | `test_chave_no_navegador.py`: leitura pobre repetida pela UIA; duas leituras ruins não fazem desistir; página que carrega é esperada; relatório das três fontes; leitura que despenca não vira veredito |
| 0.91.18 | `test_chave_no_navegador.py`: clique de mouse antes da ação; `--sem-mouse` sem clique físico; primeiro clique engolido → segundo; janela confirmada na frente; Ctrl+C sem traceback; `--pegar` não repete a chave |
| 0.91.19 | `test_chave_web.py`: campo do nome é a caixa; busca da página descartada; caixa sem nome achada pela posição; rótulo não é campo. `test_chave_no_navegador.py`: nome vai para a caixa; sem caixa não finge; `conferido=False` tenta de novo; botão apagado para a criação; “Create” não é o título |
| 0.91.20 | `test_chave_no_navegador.py`: insiste até o botão aparecer; desistir diz o que viu; espera da página usa leitura funda; página que não sossega avisa |
| 0.91.26 | `test_chave_ponta_a_ponta.py`: a página que **some sozinha** no meio do caminho (85 elementos → 3, como no log de 16/11) e o programa que pede a árvore de novo e termina; o sinal de leitor de tela dado **antes** da primeira leitura; o diagnóstico que insiste três vezes e avisa quando nem isso resolve. `test_chave_no_navegador.py`: o pedido de árvore é repetido a cada leitura pobre, mas a explicação aparece uma vez |
| 0.91.27 | `test_chave_no_navegador.py`: os quatro títulos repetidos do print de 16/11 (“Keys | Settings | OpenRouter” duas vezes e “Restaurar páginas?” duas vezes) **não** são a página; o balão de restaurar é moldura pelo nome, mas “Restaurar chave apagada” é texto do site; a página pequena de quatro nomes distintos continua boa; e o caminho pelo protocolo do Chrome — a chave criada, preenchida e gravada, o painel que não abre parando no clique, a janela sem conta pedindo login, o `--autorizar` que impede o clique e a chave que não aparece não virando `.env`; e o `--pegar` escolhendo a porta quando ela está aberta. `test_chrome_cdp.py`: o transporte sem Chrome (aperto de mão, quadro mascarado, resposta casada por `id`, erro do Chrome em português, exceção do JavaScript apontada) e o **JavaScript injetado rodando no `node`** sobre uma página falsa com o OpenRouter e a moldura: o clique acha “New key” com os títulos repetidos na frente, o painel abre, o nome entra, a lista oferece “No expiration”, a chave só sai depois do “Create” e a que o site mostra dentro de um campo também é encontrada |
| 0.91.25 | `test_chave_ponta_a_ponta.py`: o Chrome com a **acessibilidade desligada** (3 elementos em todas as vistas, painel na tela) é acordado pelo sinal de leitor de tela; o sinal é desfeito no fim; o diagnóstico mostra o sinal e as janelas filhas. `test_chave_no_navegador.py`: o sinal é pedido **uma vez** por janela |
| 0.91.24 | `test_chave_no_navegador.py`: o `--diagnostico` mede as vistas, diz quais campos do painel cada uma vê e **não clica em nada**. `test_chave_ponta_a_ponta.py`: rodar o diagnóstico não cria chave nem toca no `.env`. `test_regras_do_projeto.py`: `docs/CHAVE-OPENROUTER.md` existe, cobre os campos da página e está no README |
| 0.91.23 | `test_chave_ponta_a_ponta.py`: o painel que só a vista **crua** da UIAutomation enxerga (a de controle devolvia 3 elementos, a moldura) e a fonte preferida que deixa de pagar as outras leituras. `test_chave_no_navegador.py`: `_leitura_boa` (página pequena não é moldura) e a espera da área de transferência que não fica calada |
| 0.91.22 | `test_chave_ponta_a_ponta.py`: a janela do Chrome que fica atrás do console depois do clique (o painel estava na tela e a leitura trouxe 3 elementos) — e a leitura pobre que não pode ser contada como “o painel não abriu”. `test_chave_no_navegador.py`: `_acordar_leitura` e a linha `estado:` do relatório |
| 0.91.21 | `test_chave_ponta_a_ponta.py`: **19 cenários de ponta a ponta** — um por print do dono (página lenta, moldura no meio, ação que mente, clique engolido, nome no rótulo, botão apagado, chave velha na área, `.env` preservado) — e a espera da página antes de desistir da criação no `--auto`. `test_regras_do_projeto.py`: a própria regra, cobrada por máquina |

## 4. O teste de ponta a ponta

`server/tests/test_chave_ponta_a_ponta.py` roda o `main()` de verdade contra um
Chrome de mentira que **muda de estado quando é clicado**:

- de mentira: as janelas, a árvore de acessibilidade, o clique, a área de
  transferência e o relógio;
- de verdade: `chave-no-navegador.py`, `server/chave_web.py`,
  `server/arvore.py` (montagem da árvore) e `configurar-chave.py` (o `.env` é
  escrito e lido de um arquivo).

Ele é o mais perto do PC do dono que dá para chegar sem o PC do dono. Cobre
página lenta, moldura no meio do caminho, ação do elemento que mente, primeiro
clique engolido, nome no rótulo, botão apagado, chave velha na área e `.env`
preservado.

## 5. Como rodar

```bat
.venv\Scripts\python -m pytest -o addopts="" -q server\tests\test_chave_ponta_a_ponta.py
```

Só o que interessa da chave:

```bat
.venv\Scripts\python -m pytest -o addopts="" -q server\tests\test_chave_no_navegador.py server\tests\test_chave_web.py
```

Suíte inteira (uns 6 minutos):

```bat
.venv\Scripts\python -m pytest -o addopts="" -q
```

O `-o addopts=""` é necessário porque o `pytest.ini` do projeto traz opções que
não existem fora do ambiente de desenvolvimento.

## 6. O que o projeto confere sozinho

`server/tests/test_regras_do_projeto.py` verifica, a cada execução da suíte:

- existe uma linha para cada `NOVO-<versão>.md` a partir da 0.91.13 na tabela
  da seção 3 deste arquivo;
- cada linha cita um arquivo de teste que existe de verdade;
- este arquivo continua existindo (a regra não pode ser apagada sem alguém
  perceber).

É de propósito que ele seja chato: a regra só vale se for cobrada por máquina.
