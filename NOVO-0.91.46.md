# JARVIS 0.91.46 — o que ele não faz (lista honesta, cobrada por teste)

Sua pergunta, em 19/11:

> e oq mais o jarvis atualmente ele nao faz?

“Não faz” tem três significados diferentes, e misturar os três é como o projeto
já se enganou antes. Então a resposta virou um documento —
[`docs/NAO-FAZ.md`](docs/NAO-FAZ.md) — separado assim:

1. **não tem como** (limite de plataforma, de lei ou de física);
2. **não faz por decisão** (lê, mede ou planeja — não executa);
3. **não faz e dava para fazer** (lacuna de verdade, com custo).

## 1. Não tem como

| o que | por quê | o caminho que existe |
|---|---|---|
| rodar o APK no iPhone | o iOS não executa APK; `.ipa` exige Apple paga **e** Mac | jogo em WebGL + ícone na tela de início |
| ligar a Depuração USB sem ninguém tocar no celular | o Android exige consentimento local e a chave RSA do PC | `celular.otg` (PC como teclado/mouse), TalkBack |
| publicar na Play/App Store por você | conta, revisão e taxa são suas | ele analisa o pacote e diz o que a loja recusa |
| rodar 24 h com o PC desligado | as rotinas vivem dentro da API | manter o app aberto |
| ver a tela por pixels (print/OCR de tela) | decisão sua (“não quero fotos”) | ele lê a **árvore de acessibilidade**, não a imagem |
| entender imagem/áudio na conversa | a IA é texto puro; não há transcrição | ditado e fala são do navegador |
| virar root sem uma linha no sudoers | root de verdade é o `/etc/sudoers` | `sistema.elevar` com token e tabela fechada |
| prometer FPS | isso se mede no aparelho, com o jogo rodando | ele mede o **pacote** e diz que é isso |

## 2. Não faz por decisão

Escritório não chama o Google, correio não envia e-mail, navegador não abre aba,
carreira não envia candidatura, portabilidade não converte arquivo, estúdio não
renderiza, diagramas não desenham Mermaid, agência não executa agente, memória é
lexical (sem embedding), Reversa não descompila, enxuto não roda teste,
submissão não publica. **Debloat só planeja** — exceto `maquina.arrumar`, que
executa com ponto de restauração e diário.

O que é efeito real tem trava própria (`sistema.baixar`, `sistema.executar`,
`mesa.agir`, `maquina.arrumar`…): confirmação, variável de ambiente e token.

## 3. Lacunas de verdade (com custo)

| lacuna | o que falta | custo |
|---|---|---|
| **comparar dois APKs na aba** | `jogo.comparar()` já funciona no `.bat` com dois arquivos — **não há botão nem rota** | baixo |
| **instalar o APK no celular** | o módulo baixa `adb`/`scrcpy` e puxa arquivos; **não instala APK** | médio |
| medir FPS do jogo | precisaria do jogo rodando + instrumentação | alto |
| transcrever áudio/reunião | não há Whisper; reunião recebe texto pronto | médio |
| IA com imagens | provedor multimodal + campo de imagem | médio |
| resposta em streaming | a API devolve tudo de uma vez | médio |
| backup na nuvem | `backup` grava local | médio |
| rotinas sem o app aberto | exigiria serviço do Windows | alto |
| login/multiusuário | dono único, token local | alto |
| API na internet | escuta em `127.0.0.1`; rede desligada por padrão | alto (e risco) |

## 4. O que ele **já** faz (e a memória estava errada)

Achei um defeito de documentação enquanto levantava isso: o README dizia
**“PDF não tem OCR”** — mas o OCR de PDF escaneado e de foto de página existe
desde a versão do `server/ocr.py` (Tesseract, com `pypdfium2` para rasterizar).
A frase foi corrigida. Também já funcionam: voz (ditado e fala), notificação do
Windows com o app aberto, leitura da árvore da janela, instalar/desinstalar com
token, debloat com desfazer, APK até 2 GB com OBB e o jogo no iPhone por WebGL.

## Como isso não envelhece

`server/tests/test_nao_faz.py` (**11 casos**) confere a lista a cada suíte:

- o documento existe, tem as quatro seções e o README aponta para ele;
- **as lacunas continuam lacunas**: `/api/jogo/comparar` não existe, `jogo.*`
  não existe como skill, `celular.instalar` não existe;
- **as decisões continuam decisões**: o conteúdo da IA é `str` (sem visão), não
  há `StreamingResponse`, o host padrão é `127.0.0.1`;
- **o “já faz” continua fazendo**: OCR de PDF, ditado/fala, OBB e o teto de 2 GB;
- e o README não pode voltar a dizer “PDF não tem OCR”.

Quando uma lacuna for fechada, o teste quebra **de propósito** — é o aviso para
mover a linha de seção em vez de deixar a lista mentindo.

## Para quem for mexer

- `docs/NAO-FAZ.md` — a lista.
- `server/tests/test_nao_faz.py` — a cobrança.
- `README.md` § Limites desta etapa — a porta de entrada e a frase do OCR.
