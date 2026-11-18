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
| 0.91.28 | `test_chave_no_navegador.py`: a página que responde “ainda carregando” seis vezes **não perde a vez** (o print de 16/11 11:57, aba aberta e cartão branco — a 0.91.27 desistia em 25 s); a tela de entrada é **esperada** e o trabalho segue sozinho quando o dono entra; sem ninguém entrar, o programa diz qual atalho resolve e **não clica em nada**; e a aba que nunca carrega culpa o carregamento (manda F5), não o clique |
| 0.91.29 | `test_openrouter_api.py`: a chave criada por HTTPS sem navegador — o pedido leva o nome e **não** leva limite nem validade quando não foram pedidos, a chave que volta é a gravada, resposta sem `key` é erro (e não `.env` vazio), 401/403/429/5xx e falta de internet viram frases com o próximo passo, a chave comum copiada por engano é **recusada antes de ser guardada**, e o comando do JARVIS: sem chave de gestão ele ensina onde pegar, com ela cria e grava preservando as outras linhas, sem `--autorizar` não cria nada, e a chave de gestão só entra no `.env` depois de conferida. Os dois atalhos: todo `goto` tem rótulo, o `chave-pela-api.bat` não abre `chrome.exe` e o `chrome-cdp.bat` confere a porta **antes** de abrir o Chrome |
| 0.91.30 | `test_openrouter_api.py`: depois de criar, o comando **confere** a chave (`GET /key`, leitura, não gasta crédito) e mostra o crédito que sobrou; a conferência que falha **não apaga** a chave gravada; e conta gratuita com modelo pago no `.env` avisa na hora (`:free`), enquanto conta gratuita com modelo `:free` não avisa nada |
| 0.91.31 | `test_escolha_modelo.py`: com a lista real do dono (17/11), o modelo sugerido é **gratuito** — nunca os três `deepseek` pagos que o `difflib` propunha; embedding e transcrição ficam fora da conversa; modelo de 1.7b perde para um de 70b; a escolha é a mesma toda vez; e o `conferir-ia.py --corrigir`: **testa antes de gravar** (o primeiro que responde vira `.env`), se o primeiro falha o segundo é testado, o `.env` antigo é **copiado** antes, nenhum candidato respondendo **nada é gravado**, e com o modelo certo nada é testado nem mexido |
| 0.91.32 | `test_atualizacao.py`: o aviso de versão nova diz **quando** ela foi publicada (“publicada em 17/11 09:12 UTC”), sem data a frase continua certa, a data estragada vira texto vazio em vez de quebrar, e `verificar()` devolve o campo `publicado`; `test_escolha_modelo.py`: opção desconhecida vira frase com o próximo passo (o `usage:` do argparse não dizia nada — foi o `--corrigir` numa cópia 0.91.29), o cabeçalho mostra a versão, e o modelo **que está na lista mas dá 404** também é consertado pelo `--corrigir` |
| 0.91.33 | `test_escolha_modelo.py`: **HTTP 200 não aprova modelo** — resposta com `content` vazio é reprovada (“respondeu HTTP 200 sem nenhum texto”), o modelo de raciocínio fica atrás de um de conversa, mas não atrás de um de tamanho desconhecido; `test_ai_provider.py`: resposta cortada por pensamento (`finish_reason: length`) é **pedida de novo com mais espaço**, sem texto e sem espaço a resposta é o raciocínio, e texto vazio de verdade continua sendo erro claro |
| 0.91.34 | `test_conversa_origem.py`: a resposta **local** se declara local — a saudação do “oi” termina dizendo “Essa resposta é local, sem IA” e ensina o comando que prova o resto; existe o comando `testar ia` (13 formas: “conferir a ia”, “a ia está funcionando?”, “status da ia”…, sem roubar “status do sistema”), que chama `/api/ai/chat` com “Responda apenas: ok”, **cronometra** (“respondeu em N ms”) e sai marcado como `'ai'` → `· IA EXTERNA`; na falha ele diz o erro **e** o comando que conserta (`conferir-ia.py --corrigir`); sem backend ou sem chave ele explica em vez de fingir; e o balão continua marcando `· IA EXTERNA` / `· SKILL PYTHON` |
| 0.91.35 | `test_ia_muda.py`: o console do dono — *“OK chave 1: HTTP 200”*, *“respondeu com raciocínio em vez de texto”*, *“Pronto: estão coerentes”* — é reproduzido e reprovado: `chaves.testar()` **não aprova 200 sem texto** (nem pelo modelo de socorro), o resumo separa “a chave está válida” de “o modelo não fala” e manda para o `--corrigir`, o `--testar` não diz “coerentes” e diz o comando, `--corrigir` sozinho **testa o modelo que está na lista** (antes ele nem perguntava), pula o mudo e vai além dos três primeiros candidatos; com texto, tudo volta a ser aprovado |
| 0.91.36 | `test_tempo.py`: “vai chover hoje?” vira consulta ao **Open-Meteo** e não ao modelo — cidade → coordenadas (nome acentuado codificado na URL), código WMO traduzido (chuva forte, trovoada, granizo, código desconhecido não vira mentira), chuva respondida com número (`sim, deve chover — 80% de chance` / `não deve chover — 5%` / `talvez` entre 25% e 49%), amanhã não herda a resposta de hoje, a resposta diz a **fonte e a hora da leitura**, cidade inexistente explica o próximo passo, URL fora dos dois hosts é recusada, resposta que não é JSON/HTTP de erro/sem dados vira erro explicado, e a rota `/api/tempo` devolve `TEMPO_INDISPONIVEL` com *“Nada foi inventado”* quando a fonte cai — nunca um número; `jarvisEngine.test.ts`: 21 casos de frase (hoje/amanhã, cidade na frase, “de hoje” e “guarda-chuva” não viram cidade, busca na web não é roubada) e o prompt do modelo proibindo estimar tempo e cotação |
| 0.91.37 | `test_calendario.py`: “que dia é hoje”, “quanto falta para o fim de semana” e os feriados deixam de ir para o modelo — a **Páscoa** é calculada (10 anos conferidos, 2020–2038) e dela saem Carnaval (−47), Sexta-feira Santa (−2) e Corpus Christi (+60); 20/11 é feriado nacional desde a Lei 14.759/2023; Carnaval e Corpus Christi aparecem como **ponto facultativo**, não como feriado; a lista vem em ordem, o feriado de hoje conta como próximo, dezembro já mostra o ano seguinte, “Natal” em 26/12 traz o do ano que vem, nome sem acento acha, feriado inexistente devolve a lista real em vez de uma data aproximada, e o texto diz a fonte e que *“nada aqui foi estimado”*; `calendario.test.ts`: dia da semana, contagem até o sábado (3 na quarta, 1 na sexta, 0 no sábado, 6 no domingo), confirmação e correção de palpite (“hoje é quinta?”) e contagem para qualquer dia; `jarvisEngine.test.ts`: 20 casos de frase, incluindo “de hoje” que não é cidade, pergunta composta que cai nos feriados e a busca na web que não é roubada |
| 0.91.38 | `test_jogo.py`: arrastar o APK para o `analisar-jogo.bat` passa a valer algo — o leitor de **AndroidManifest.xml binário** (AXML) é exercitado contra um molde binário de verdade montado no teste (pool UTF-16, resource map, start elements, namespace), e o caminho fácil de “achar string ASCII no ZIP” está **proibido** pelo teste: a string aparece com um byte nulo entre as letras; pacote, versão, min/target SDK, permissões sem repetição, `debuggable`, `allowBackup` e `usesCleartextTraffic` saem certos do manifesto compilado; manifesto **em texto** também é lido; manifesto truncado não derruba a análise; motor reconhecido por marca real (Unity com versão `2021.3.16f1`, Godot, Unreal, GameMaker) e — o defeito que o teste pegou — **`classes.dex` não identifica motor nenhum**: ele existe em todo APK e fazia qualquer jogo virar “LibGDX”; Cordova ganha de Construct quando os dois usam `assets/www/`; APK de depuração vira achado **crítico**, três ABIs viram conselho de AAB, falta de arm64 vira aviso, só assinatura v1 vira aviso, `targetSdk` antigo vira aviso, permissão sensível é listada **com o rótulo em português**, e o APK limpo não recebe achado inventado; o texto do chat traz `O que é:`, `Por que importa:`, `Como melhorar:` e `Onde:` em cada achado, os maiores arquivos com tamanho, e o rodapé diz que a análise foi **no seu PC**; nome com `..`, extensão errada, arquivo que não é ZIP e jogo inexistente são recusados com o próximo passo; e as rotas `/api/jogo/arquivos`, `/api/jogo/analisar` e `/api/jogo/upload` (sem `confirmed`, extensão errada, e **sem descompactar nada**); `jarvisEngine.test.ts`: “analisar meu jogo”, “analisar o apk do jogo” e “melhorar meu jogo” chegam na análise do APK em vez do modelo, o nome do arquivo dito na frase é pego, sem nome o servidor diz o que tem na pasta, e a busca na web não é roubada |
| 0.91.39 | `test_jogo_web.py`: “quero testar no meu iphone” — e o fato de que **APK não roda no iOS** — vira servidor de export WebGL. O export é guardado por pasta e por `.zip`, o zip do Unity com uma pasta dentro é **achatado** (sem isso o Safari abre em branco), a pasta sem `index.html` é recusada dizendo qual export gerar e **não deixa lixo** na pasta de jogos, `.zip` com `..` ou caminho absoluto é recusado sem extrair nada, nome repetido ganha número, e nome com espaço/acento vira endereço. O servidor sobe de verdade em `127.0.0.1:0` e é exercitado por HTTP: `index.html` na raiz, `.wasm` com `application/wasm`, pasta sem barra no fim vira `301`, arquivo inexistente vira `404` com dica, **`..`, `%2e%2e`, `.env` e `../../` dão 404** (nenhum byte de chave sai), o `.gz` do export sai com `Content-Encoding: gzip` (o pedido `jogo.data.gz` da Unity) e o original ganha do `.gz` quando existe, `Range` devolve `206` com `Content-Range`, `HEAD` responde sem corpo, `POST` é recusado, e COOP/COEP vêm ligados (desligáveis). O servidor do jogo **não conhece nenhuma rota da API** (`/api/health`, `/api/jogo/arquivos`, `/docs` dão 404). O endereço mostrado é escolhido por faixa doméstica (`192.168` na frente, link-local no fim) — o PC com VirtualBox/WSL tem várias placas — e o texto diz `Safari`, “mesma rede”, firewall, `ipconfig` e que `127.0.0.1` é o próprio iPhone; a rota `/api/jogo/web` lista o que está guardado. `jarvisEngine.test.ts`: “quero testar no meu iphone”, “como rodo o jogo no iphone”, “da para jogar no iphone” caem no caminho do iPhone, enquanto “qual o preço do iphone 17”, a busca na web, “testar ia” e “analisar meu jogo” não são roubados |
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
