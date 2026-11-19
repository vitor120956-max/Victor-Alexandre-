# O que o JARVIS não faz — de propósito, por limite, e por falta

Levantamento feito em 19/11, na 0.91.46, para responder à pergunta:

> e oq mais o jarvis atualmente ele nao faz?

“Não faz” tem três significados muito diferentes, e misturar os três é como o
projeto já se enganou antes (o README dizia “PDF não tem OCR” três versões
depois de o OCR existir):

1. **não tem como** — limite de plataforma, de lei ou de física;
2. **não faz por decisão** — o módulo lê, mede ou planeja, e não executa;
3. **não faz e dava para fazer** — lacuna de verdade, com custo estimado.

Abaixo, cada linha diz também **como conferir** — porque uma lista de
limitações que ninguém cobra envelhece igual à frase do OCR.

---

## 1. Não faz e não tem como (limite duro)

| o que | por quê | o caminho que existe |
|---|---|---|
| Rodar o APK no iPhone | o iOS não executa APK; `.ipa` exige conta Apple paga (US$ 99/ano) **e** um Mac para assinar | exportar o mesmo jogo em WebGL e abrir no Safari, com ícone na tela de início (`docs/JOGO-NO-IPHONE.md`) |
| Ligar a Depuração USB sem ninguém tocar no celular | o Android exige consentimento local e a chave RSA do computador; nenhum programa no PC contorna isso | `celular.otg` (PC como teclado/mouse), `celular.plano`, TalkBack (`server/celular.py`) |
| Publicar na Play Store ou na App Store | conta, revisão, taxa e assinatura são do dono | o JARVIS analisa o pacote e diz o que a loja vai recusar; publicar é no console |
| Trabalhar 24 h com o PC desligado | as rotinas vivem dentro da API, não num serviço do Windows | manter o app aberto; para algo 24 h seria preciso um serviço/worker à parte |
| Ver a tela por pixels (print/OCR de tela) | decisão do dono (“não quero fotos”): ele lê a **árvore de acessibilidade**, não a imagem | `mesa.arvore` lê nomes, papéis e posições (`docs/ARVORE.md`) |
| Entender imagem ou áudio na conversa | a IA é texto puro: `Mensagem.content` é `str`, sem `image_url`; não há transcrição de áudio | o ditado e a fala são do navegador (`src/hooks/useSpeechInput.ts`); reunião só analisa texto colado |
| Virar root sem uma linha no sudoers | root de verdade é o `/etc/sudoers`; `NOPASSWD` restrito a binários da tabela fechada | `sistema.elevar` + `sistema.elevar_executar` com token (`docs/ROOT.md`) |
| Prometer FPS ou “o jogo ficou mais rápido” | isso se mede no aparelho, com o jogo rodando; o JARVIS não instrumenta build | o que ele mede é o **pacote** (tamanho, ABIs, compressão) — e diz que é isso |

## 2. Não faz por decisão (lê, mede ou planeja — não executa)

Esses módulos têm a mesma regra: **produzem texto e evidência, nunca efeito**.
Onde há efeito, ele é skill separada, com `confirmed`, variável de ambiente e
token de uso único.

| módulo | o que ele **não** faz | onde está escrito |
|---|---|---|
| Escritório (`gws`) | não instala o CLI, não autentica, não lê credencial, não chama o Google | `docs/ESCRITORIO.md` |
| Correio | não envia e-mail: monta o rascunho a partir do `.eml` | `server/correio.py` |
| Navegador | não abre aba, não clica, não preenche, não paga, não baixa | `docs/NAVEGADOR.md` |
| Carreira | não lê LinkedIn, não envia candidatura, não altera currículo | `docs/CARREIRA.md` |
| Portabilidade | não converte arquivo: devolve o plano do `convert.sh` | `docs/PORTABILIDADE.md` |
| Estúdio de design | não compila tokens, não renderiza HTML, não publica | `docs/ESTUDIO.md` |
| Diagramas | não renderiza Mermaid/DOT — exporta como texto | `docs/DIAGRAMAS.md` |
| Governo de agentes | não executa agente, não lê runtime, não altera permissão | `docs/AGENTES.md` |
| Memória | é lexical: sem embedding, sem grafo, sem paráfrase | `README.md` § Limites |
| Reversa | não descompila, não executa, não extrai contêiner | `docs/ENGENHARIA-REVERSA.md` |
| Engenharia enxuta | não roda teste, não vê o histórico do Git | `docs/LEAN.md` |
| Submissão | não publica: a revisão humana continua no rótulo | `docs/SUBMISSAO.md` |
| Debloat | só planeja — exceto `maquina.arrumar`, que executa com ponto de restauração e diário | `README.md` § Limites |
| Análise do jogo | não descompila DEX, não recompila, não assina | `server/jogo.py` (docstring) |

O que **é** efeito real, e por isso tem trava: `sistema.baixar`,
`sistema.executar`, `sistema.elevar_executar`, `maquina.arrumar`,
`maquina.desfazer`, `mesa.agir`, `mesa.ditar`, `mesa.mover`, `evoluir.promover`,
`files.organize`, `document.create`, `pdf.merge`.

## 3. Não faz hoje, mas dá para fazer (lacunas de verdade)

Em ordem de custo × utilidade para o que o dono tem pedido:

| lacuna | o que falta | custo | vale? |
|---|---|---|---|
| **Comparar dois APKs na aba “Meu jogo”** | `jogo.comparar()` já existe e funciona pelo `analisar-jogo.py` com dois arquivos arrastados — mas **não há botão nem rota** (`/api/jogo/comparar` não existe) | baixo | sim: é o teste “antes/depois” que ele já faz com dois APKs |
| **Instalar o APK no celular por ADB** | `server/celular.py` baixa o `adb` e o `scrcpy` (com hash), espelha a tela e puxa arquivos — mas **não instala APK** (`celular.instalar` não existe) nem tem botão na aba do jogo | médio | sim, **se** a depuração USB já estiver ligada; é o passo que falta entre “analisar” e “jogar no aparelho” |
| **Medir FPS/desempenho do jogo** | precisaria do jogo rodando + instrumentação (Perfetto/`dumpsys gfxinfo`) | alto | só depois de instalar |
| **Transcrever áudio/reunião** | não há Whisper nem serviço de transcrição; `meeting.analyze` recebe texto pronto | médio | utilidade alta, mas exige chave paga ou modelo local |
| **IA com imagens (visão)** | provedor multimodal + campo de imagem no chat | médio | útil para print de erro; hoje o caminho é descrever em texto |
| **Resposta em streaming** | a API devolve a resposta inteira de uma vez (`StreamingResponse` não é usado) | médio | só percepção de velocidade |
| **Backup automático na nuvem** | `backup` grava local; não há Drive/Dropbox | médio | o texto do próprio backup já sugere pendrive/Drive |
| **Rotinas sem o app aberto** | exigiria serviço do Windows (Agendador) — hoje é thread da API | alto | muda o desenho do projeto |
| **Login / multiusuário** | dono único, token de host local, sem contas | alto | não é o caso de uso |
| **API exposta na internet** | escuta em `127.0.0.1`; `--host 0.0.0.0` é opcional e rede é desligada por padrão | alto (e risco) | só com TLS, senha e revisão de superfície |

## 4. Já faz — e às vezes se pensa que não

Esta seção existe porque a lista acima só é honesta se a memória não estiver
desatualizada:

- **OCR de PDF escaneado e de foto de página** (Tesseract; se não estiver
  instalado, diz o que instalar em vez de falhar calado) — `server/ocr.py`,
  usado por `biblioteca.py`. O README dizia “PDF não tem OCR” e estava errado
  até a 0.91.46;
- **voz**: ditado pelo navegador e resposta falada (`speechSynthesis`);
- **notificação do Windows** quando um lembrete vence — enquanto o app está
  aberto;
- **leitura da árvore da janela** (com nomes e posições) sem clicar;
- **instalar/desinstalar programa** com token, hash e quarentena;
- **debloat com ponto de restauração e desfazer**;
- **análise de APK até 2 GB, com OBB** (0.91.44/0.91.45);
- **jogo no iPhone sem Mac**, por WebGL + ícone na tela de início;
- **atualização com manifesto e rollback**.

## 5. Como esta lista é cobrada

`server/tests/test_nao_faz.py` verifica, a cada execução da suíte, que as
afirmações acima continuam verdadeiras:

- o documento existe, tem as quatro seções e o README aponta para ele;
- não há skill `jogo.*` nem `celular.instalar` (enquanto forem lacuna);
- a rota `/api/jogo/comparar` **não** existe (enquanto for lacuna);
- o texto da IA é `str` e não há `StreamingResponse` na API;
- o host padrão continua `127.0.0.1`;
- o OCR de PDF **existe** — e o README não pode voltar a dizer que não.

Quando uma lacuna for fechada, o teste quebra de propósito: é o sinal para
mover a linha de seção e atualizar esta página, em vez de deixar a lista
mentindo por omissão.
