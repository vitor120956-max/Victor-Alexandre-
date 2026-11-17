#!/usr/bin/env python3
"""Criar a chave de IA pelo navegador, com o JARVIS clicando.

## O que isto faz — e o que não faz

A chave **não está** na página de chaves: o OpenRouter mostra o valor uma única
vez, no instante da criação, e depois só o prefixo mascarado. Não existe ler a
chave que já existe — por isso este script não promete isso.

O que ele faz é o caminho de **criar uma nova**, em passos medidos:

    --auto --autorizar      abre o site, entra se preciso, cria, copia e grava
    --abrir                 abre a página de chaves no seu navegador
    --ver                   LÊ a página e diz quais botões existem (não clica)
    --pegar                 lê a área de transferência e grava no .env
    --criar --autorizar     clica "Create Key", dá um nome, cria e copia

O `--auto` pega o provedor do `.env` (ou de `--provedor`) e abre **o site dele**:
openrouter.ai/keys, console.groq.com/keys, aistudio.google.com/apikey e assim
por diante.

## As três páginas (medido nas telas do dono, 0.91.14)

Abrir `openrouter.ai/keys` sem sessão **não** cai na página de chaves: cai em
“Sign In | OpenRouter”. Clicar no Google abre a escolha de conta; só depois da
conta é que aparece “API keys” com o botão “New key”. São três páginas na mesma
janela, e o JARVIS tem de saber em qual está antes de clicar em qualquer coisa:

    página de login  → clica no Google
    escolha de conta → clica na conta do dono (`--conta` ou `JARVIS_CONTA_GOOGLE`)
    página de chaves → clica em “New key”, nomeia, cria, copia

Se os botões não estiverem na árvore de acessibilidade, ele não termina em erro:
deixa a página aberta, diz o que falta clicar e fica esperando a chave aparecer
na área de transferência.

O `--ver` existe porque a promessa tem de ser medida antes de ser feita: se o
Chrome não publicar o botão na árvore de acessibilidade, o `--criar` não tem
como funcionar, e é melhor saber disso em dois segundos do que em vinte cliques.

`--criar` mexe na sua conta: cria uma credencial de verdade. Ele só roda com
`--autorizar`, diz cada passo antes de dar, e para no primeiro que falhar
dizendo qual foi.

Uso (Windows, na pasta do JARVIS):

    .venv\\Scripts\\python chave-no-navegador.py --abrir
    .venv\\Scripts\\python chave-no-navegador.py --ver
    .venv\\Scripts\\python chave-no-navegador.py --criar --autorizar
    .venv\\Scripts\\python chave-no-navegador.py --pegar

Nada aqui lê tela por imagem, nem guarda a chave em log: ela vai para o `.env`
e aparece só mascarada.
"""
from __future__ import annotations

import argparse
import importlib.util
from datetime import datetime
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# Onde fica lembrado o e-mail da conta do Google usada para entrar no site.
# Sem isso, a tela de escolha de conta (que lista mais de uma) faria o JARVIS
# perguntar em toda execução — ou pior, chutar.
CONTA_GOOGLE = "JARVIS_CONTA_GOOGLE"
# A chave de gestão (management/provisioning) do OpenRouter: ela não conversa
# com modelo nenhum, só cria outras chaves. Fica no `.env` para o JARVIS poder
# criar uma chave nova sem abrir navegador (0.91.29).
GESTAO_OPENROUTER = "JARVIS_OPENROUTER_GESTAO"


class PassoError(RuntimeError):
    """Um passo não deu — com o nome do passo e o que fazer."""


def _configurar_ambiente() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:  # noqa: BLE001 - sem python-dotenv, o ambiente ainda vale
        return
    load_dotenv(RAIZ / ".env")


def _modulo_do_configurador():
    """Reaproveita gravar/ler/mascarar do `configurar-chave.py` — uma verdade só."""
    caminho = RAIZ / "configurar-chave.py"
    spec = importlib.util.spec_from_file_location("configurar_chave_para_web", caminho)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


# A leitura de estreia é rasa de propósito (rápida, 8 níveis). O diálogo de
# criação, porém, é um painel no fim do documento: no PC do dono ele abriu e a
# leitura rasa não o viu. Para achar o painel, a leitura vai fundo.
PROFUNDA, TETO_FUNDO = 14, 3000


def _ler_janela(alvo: str, profundidade: int = 8, limite: int = 1500):
    """A janela do navegador e a árvore montada — com o erro já em português."""
    from server import arvore, arvore_windows

    try:
        janelas = arvore_windows.janelas()
    except Exception as exc:  # noqa: BLE001 - COM de terceiros
        raise PassoError(f"não consegui listar as janelas ({type(exc).__name__}).") from exc
    foco = arvore_windows.janela_em_foco()
    try:
        janela = arvore_windows.escolher_janela(alvo or "chrome", janelas=janelas, foco=foco)
    except Exception as exc:  # noqa: BLE001
        raise PassoError(
            f"não achei a janela do navegador ({type(exc).__name__}). "
            "Abra openrouter.ai/keys no Chrome e rode de novo."
        ) from exc
    bruto = arvore_windows.ler_janela(int(janela["handle"]), profundidade, limite)
    montada = arvore.montar(bruto, profundidade, limite, com_caminho=True)
    return janela, montada


# Abaixo disto a leitura não chegou na página: veio a **moldura** do Chrome
# (“Chrome Legacy Window”, o título da aba, botões da barra). Medido na tela do
# dono: com o painel aberto, a leitura automática escolheu a moldura e trouxe
# 3 nomes — e o script disse que o diálogo não estava lá.
LEITURA_POBRE = 8

# As fontes de leitura, na ordem em que são tentadas quando a automática vem
# pobre. `uia_raw` é a vista **crua** da UIAutomation: medido no PC do dono
# (0.91.23), com o painel “Create API key” aberto na tela, a vista de controle
# devolvia 3 elementos (a moldura) e era por isso que o script desistia com o
# painel à vista. A crua mostra o que o site marcou como escondido para
# tecnologia assistiva — que é exatamente o que um modal faz com a página.
# Ordem medida no PC do dono (16/11): com a acessibilidade ligada, a MSAA
# trouxe 85 elementos e as vistas da UIAutomation 43 a 58 — e foi a **MSAA** a
# única que viu o painel “Create API key” aberto. Então ela vai primeiro.
FONTES_DE_LEITURA = ("msaa", "uia_raw", "uia_content", "uia")
_FONTE_PREFERIDA: dict[int, str] = {}
_ROTACAO_ATUAL: dict[int, int] = {}


def _nomes(montada: dict) -> int:
    """Quantos elementos com nome a leitura trouxe — o tamanho da “cara” da página."""
    from server import chave_web

    return len(chave_web.elementos(montada))


# Nomes que só existem na moldura do navegador, nunca na página.
MARCAS_DE_MOLDURA = (
    "chrome legacy window",
    "chrome_renderwidgethosthwnd",
    "chrome_widgetwin",
    "mozilla windowclass",
    # Print de 16/11 09:12, depois de reabrir o Chrome: 4 elementos, os títulos
    # repetidos e o balão “Restaurar páginas?”. É a moldura de uma janela que
    # acabou de nascer — e o script chamou isso de “a página foi lida inteira”.
    "restaurar paginas",
    "restore pages",
)


def _parece_moldura(montada: dict) -> bool:
    """A leitura veio da moldura do navegador, e não da página?"""
    from server import chave_web

    nomes = [chave_web.normalizar(str(no.get("nome") or "")) for no in chave_web.elementos(montada)[:12]]
    if any(marca in nome for nome in nomes for marca in MARCAS_DE_MOLDURA):
        return True
    # Título repetido é sinal de moldura também: a página não se apresenta duas
    # vezes com o mesmo nome. Foi o que apareceu com o Chrome recém-aberto.
    com_nome = [nome for nome in nomes if nome]
    if len(com_nome) >= 4 and len(set(com_nome)) <= len(com_nome) // 2:
        return True
    return False


def _leitura_boa(montada: dict) -> bool:
    """Esta leitura mostrou a página — ou o painel?

    Contagem sozinha não decide, e cada régua errada custou uma rodada no PC do
    dono:

    - o painel “Create API key” aberto sobre a página tem 6 ou 7 elementos com
      nome — menos que o piso de 8. Ver o painel contava como “leitura pobre”, e
      o script ia procurar outras vistas com o painel à vista;
    - a página logo depois de criar a chave também é pequena (6 nomes). Ela é
      uma leitura **boa** — o que a denuncia como moldura é o nome
      “Chrome Legacy Window”, não o tamanho.
    """
    from server import chave_web

    nomes = _nomes(montada)
    if nomes >= LEITURA_POBRE:
        return True
    if chave_web.e_dialogo_de_criacao(montada):
        return True
    if nomes < 3:
        return False
    return not _parece_moldura(montada)


def _ler_pela_fonte(handle: int, profundidade: int, limite: int, fonte: str = "auto") -> dict:
    """Uma leitura, por uma fonte escolhida. `auto` deixa o Windows decidir.

    A vista **crua** ganha orçamento maior de propósito: ela mostra o documento
    inteiro, e o painel de criação é o **último** nó do documento. Com o teto
    da leitura normal, o painel seria cortado justamente por estar no fim —
    mais uma vez “o painel não existe” com ele na tela.
    """
    from server import arvore, arvore_windows

    if fonte.endswith("raw"):
        profundidade = max(int(profundidade), PROFUNDA + 4)
        limite = max(int(limite), TETO_FUNDO * 2)
    if fonte == "auto":
        bruto = arvore_windows.ler_janela(handle, profundidade, limite)
    else:
        bruto = arvore_windows.ler_janela(handle, profundidade, limite, fonte=fonte)
    return arvore.montar(bruto, profundidade, limite, com_caminho=True)


def _reler(
    janela: dict, profundidade: int = 8, limite: int = 1500, *, curar: bool = True
):
    """Relê **esta** janela (pelo handle), não “a janela do chrome”.

    Três coisas que esta função garante, e cada uma custou uma execução no PC
    do dono:

    1. **o handle é a identidade.** A cada passo o código escolhia de novo a
       janela pelo nome; com duas janelas do Chrome abertas — a sua e a do
       site —, um passo podia ler (e clicar) na errada;
    2. **leitura pobre é lida de novo, por outra vista.** A escolha automática
       pode cair na moldura (3 nomes) e a página some da leitura; aqui as
       fontes são medidas na mão e fica a que mostrou a página;
    3. **o Chrome desliga a página quando para de ser pedida.** Medido em
       16/11: 85 elementos e, segundos depois, 3 — na mesma janela e no mesmo
       processo. Então, quando a leitura vem pobre, esta função **pede a árvore
       de novo** (`WM_GETOBJECT`) e relê. Fica aqui, e não em cada passo, porque
       é por aqui que **toda** leitura passa: preencher o painel, achar o botão
       “Create”, conferir o clique e copiar a chave.
    """
    from server import arvore_windows

    handle = int(janela.get("handle") or 0)
    if not handle or not arvore_windows.janela_muda(handle):
        raise PassoError("a janela do navegador foi fechada no meio do caminho.")

    # A fonte que já mostrou a página nesta janela vai primeiro: repetir a
    # descoberta a cada leitura custaria caro (a vista crua lê centenas de nós).
    preferida = _FONTE_PREFERIDA.get(handle)
    if preferida:
        try:
            boa = _ler_pela_fonte(handle, profundidade, limite, preferida)
        except Exception:  # noqa: BLE001 - COM de terceiros
            boa = None
        if boa is not None and _leitura_boa(boa):
            return janela, boa
        _FONTE_PREFERIDA.pop(handle, None)

    montada = _ler_pela_fonte(handle, profundidade, limite, "auto")
    if _leitura_boa(montada):
        return janela, montada

    # Uma fonte extra por chamada, girando entre elas. Duas razões para girar em
    # vez de tentar todas: cada leitura custa segundos, e quem chama já está em
    # laço — em duas ou três voltas todas as vistas foram medidas.
    montada = _girar_fontes(handle, montada, profundidade, limite)

    if curar and not _leitura_boa(montada):
        # Pedir a árvore é o que reabre a página no Chrome. Duas tentativas
        # porque ele leva de um a dois segundos para ligar o modo completo.
        _acordar_a_acessibilidade(janela, avisar=True)
        for _tentativa in range(2):
            fonte = _FONTE_PREFERIDA.get(handle) or "auto"
            try:
                depois = _ler_pela_fonte(handle, profundidade, limite, fonte)
            except Exception:  # noqa: BLE001 - COM de terceiros
                continue
            if _nomes(depois) > _nomes(montada):
                montada = depois
            if _leitura_boa(montada):
                break
            time.sleep(0.4)
    return janela, montada


def _girar_fontes(handle: int, montada: dict, profundidade: int, limite: int) -> dict:
    """Uma fonte extra por chamada, girando: a leitura que mostrou mais vence."""
    inicio = _ROTACAO_ATUAL.get(handle, 0)
    for deslocamento in range(len(FONTES_DE_LEITURA)):
        fonte = FONTES_DE_LEITURA[(inicio + deslocamento) % len(FONTES_DE_LEITURA)]
        try:
            tentativa = _ler_pela_fonte(handle, profundidade, limite, fonte)
        except Exception:  # noqa: BLE001 - COM de terceiros: uma fonte pode cair
            continue
        if _nomes(tentativa) > _nomes(montada):
            montada = tentativa
            if _leitura_boa(montada):
                _FONTE_PREFERIDA[handle] = fonte
            break
    _ROTACAO_ATUAL[handle] = (inicio + 1) % len(FONTES_DE_LEITURA)
    return montada


def _clicar(
    janela: dict,
    no: dict,
    acao: str = "clicar",
    texto: str = "",
    *,
    mouse: bool = False,
    primeiro_mouse: bool = False,
) -> dict:
    """Clica num nó **da leitura que o encontrou** (ref antigo não serve).

    Antes da 0.91.10 o resultado era descartado: se o clique não saía, o script
    seguia para o passo seguinte e culpava o passo errado. Agora quem não
    executou vira `PassoError` com o motivo que o Windows deu.
    """
    from server import arvore_windows

    nome = str(no.get("nome") or "")[:60]
    try:
        feito = arvore_windows.executar_ref(
            int(janela["handle"]),
            no["caminho"],
            acao,
            texto,
            no.get("caixa"),
            mouse=mouse,
            primeiro_mouse=primeiro_mouse,
        )
    except Exception as exc:  # noqa: BLE001 - COM de terceiros
        raise PassoError(
            f"não consegui clicar em “{nome}” ({type(exc).__name__})."
        ) from exc
    if not feito.get("executou"):
        motivo = str(feito.get("motivo") or "o Windows não disse o motivo.")
        raise PassoError(f"“{nome}” não aceitou o clique: {motivo}")
    return feito


# Os campos do painel “Create API key”, na ordem em que a página os mostra.
# Medidos no PC do dono (print de 16/11) e confirmados na documentação:
# Name → Expiration → Credit limit → (Reset limit every) → Create.
CAMPOS_DO_PAINEL = ("nome", "expiração", "limite", "criar", "copiar")


def _campos_do_painel(montada: dict) -> dict[str, bool]:
    """Quais dos campos do painel esta leitura enxerga.

    Serve para uma pergunta só, e é a pergunta que sobrou depois da 0.91.23:
    **qual vista vê o painel?** Dizer “3 elementos” não responde; dizer “esta
    vista vê o nome e a expiração, aquela não vê nada” responde.
    """
    from server import chave_web

    return {
        "nome": chave_web.campo_do_nome(montada) is not None,
        "expiração": bool(chave_web.procurar(montada, chave_web.PADROES_EXPIRACAO)),
        "limite": bool(chave_web.procurar(montada, chave_web.PADROES_LIMITE)),
        "criar": _botao_de_criar(montada) is not None,
        "copiar": bool(chave_web.procurar(montada, chave_web.PADROES_COPIAR)),
    }


def _descrever_clique(feito: dict) -> str:
    """Como o clique saiu — com o mouse ou pela ação do elemento."""
    como = str(feito.get("como") or "")
    if como.startswith("clique físico"):
        voltou = " o cursor voltou para onde estava." if feito.get("cursor_voltou") else ""
        return f"{como}.{voltou}"
    return como or "feito"


def _esperar_elemento(janela: dict, padroes: tuple[str, ...], segundos: float = 12.0):
    """Relê **esta** janela até o elemento aparecer. Devolve (janela, nó, árvore).

    Recebe a janela (handle) e não o nome: com duas janelas do Chrome abertas,
    procurar pelo nome podia ler a errada — e o botão que está numa não existe
    na outra.
    """
    from server import chave_web

    fim = time.time() + segundos
    ultima = ""
    while True:
        try:
            janela, montada = _reler(janela, PROFUNDA, TETO_FUNDO)
        except PassoError:
            raise
        achados = chave_web.procurar(montada, padroes)
        if achados:
            return janela, achados[0], montada
        ultima = _diagnostico_da_leitura(montada)
        if time.time() >= fim:
            raise PassoError(f"não apareceu “{padroes[0]}” em {int(segundos)}s nesta leitura. {ultima}")
        time.sleep(0.8)


def passo_diagnostico(args) -> int:
    """Diz **qual leitura enxerga a página** — sem clicar em nada.

    Por que existe: o dono não consegue testar de graça. Cada rodada custa
    atualizar, abrir o site, criar (ou quase criar) uma chave e mandar um print.
    Este comando responde a pergunta que sobrou — *qual leitura de
    acessibilidade vê o painel?* — sem criar chave e sem clicar em nada,
    inclusive com o painel já aberto na tela dele.

    Depois do print de 16/11 08:35 (3 elementos em **todas** as vistas), ele
    passou a medir também duas coisas que ninguém estava olhando:

    1. o **modo leitor de tela** do Windows — o Chrome só publica a página para
       quem parece um leitor de tela;
    2. as **janelas filhas** do Chrome — a página pode estar numa delas.
    """
    from server import arvore_windows, chave_web

    leitor = getattr(arvore_windows, "leitor_de_tela", None)
    antes_do_sinal = leitor() if leitor else None
    _tomar_o_sinal(avisar=False)
    janela, _montada = _ler_janela(args.alvo)
    handle = int(janela.get("handle") or 0)
    print(f"  Janela: {janela.get('titulo') or '?'}  (handle {handle})")
    print("  Medindo o que cada leitura do Windows enxerga. Nada será clicado.")
    print()

    estado_leitor = leitor() if leitor else None
    if estado_leitor is None:
        print("  Modo leitor de tela do Windows: não deu para ler.")
    elif antes_do_sinal is False:
        print(
            "  Modo leitor de tela do Windows: estava desligado — liguei para esta "
            "medição (desligo no fim)."
        )
    else:
        print(f"  Modo leitor de tela do Windows: {'LIGADO' if estado_leitor else 'desligado'}")
    filhas = []
    try:
        filhas = arvore_windows.janelas_filhas(handle, 12)
    except Exception:  # noqa: BLE001 - é diagnóstico, não pode derrubar
        filhas = []
    print(f"  Janelas filhas do Chrome: {len(filhas)}")
    for filha in filhas[:8]:
        # A página do navegador mora numa janela filha (`Chrome_RenderWidgetHostHWND`).
        # Medir cada uma separa “a página não está em lugar nenhum” de “está
        # nesta filha e eu estava lendo a janela de cima”.
        contagens = []
        for fonte in ("msaa", "uia_raw"):
            try:
                medida = _ler_pela_fonte(int(filha["handle"]), PROFUNDA, TETO_FUNDO, fonte)
                contagens.append(f"{fonte}={_nomes(medida)}")
            except Exception:  # noqa: BLE001 - uma filha pode nem aceitar leitura
                contagens.append(f"{fonte}=erro")
        print(
            f"     {filha.get('classe') or '?'}  (handle {filha.get('handle')}) — "
            + ", ".join(contagens)
        )
    print()

    def medir(titulo: str) -> list[tuple[str, int, dict[str, bool], bool]]:
        print(titulo)
        medidas: list[tuple[str, int, dict[str, bool], bool]] = []
        for fonte in ("auto", "uia", "uia_raw", "uia_content", "msaa"):
            try:
                montada = _ler_pela_fonte(handle, PROFUNDA, TETO_FUNDO, fonte)
            except Exception as exc:  # noqa: BLE001 - uma vista pode cair inteira
                print(f"  {fonte:11} : não respondeu ({type(exc).__name__}).")
                continue
            campos = _campos_do_painel(montada)
            painel = chave_web.e_dialogo_de_criacao(montada)
            medidas.append((fonte, _nomes(montada), campos, painel))
            vistos = [rotulo for rotulo in CAMPOS_DO_PAINEL if campos[rotulo]]
            print(
                f"  {fonte:11} : {_nomes(montada):4} elementos — "
                f"diálogo: {'SIM' if painel else 'não'} — "
                + ("campos: " + ", ".join(vistos) if vistos else "nenhum campo do painel")
            )
        print()
        return medidas

    medidas = medir("  ANTES de mexer em qualquer coisa:")
    melhor = max(medidas, key=lambda item: (item[1], sum(item[2].values()))) if medidas else None

    if melhor is not None and not _medida_boa(melhor):
        # Nada mostrou a página. O que o Chrome espera é um **pedido** de
        # árvore — e ele leva alguns segundos para ligar o modo completo.
        # Insistir aqui é o mesmo que o `pegar-chave.bat` faz, e é a medição
        # que responde: “insistir resolve, ou o Chrome não publica de jeito
        # nenhum nesta máquina?”.
        print(
            "  Nenhuma leitura viu a página. Insistindo com o pedido de árvore "
            "(3 rodadas, como o JARVIS faz)…"
        )
        print()
        for rodada in range(1, 4):
            _acordar_a_acessibilidade(janela, avisar=False)
            time.sleep(1.0)
            medidas = medir(f"  DEPOIS do pedido de árvore (rodada {rodada}):")
            if any(_medida_boa(medida) for medida in medidas):
                boa = next(medida for medida in medidas if _medida_boa(medida))
                print(
                    f"  Funcionou na rodada {rodada}: a leitura “{boa[0]}” viu "
                    f"{boa[1]} elementos. É essa que o JARVIS usa."
                )
                break
        else:
            print(
                "  Continuou sem ver a página depois de três pedidos. O Chrome desta "
                "máquina não está publicando a árvore — o relatório abaixo tem o que "
                "cada leitura trouxe."
            )

    print()
    if not medidas:
        print("  Nenhuma leitura respondeu. O Chrome está aberto? A janela está minimizada?")
        return 1
    melhor = max(medidas, key=lambda item: (item[1], sum(item[2].values())))
    print(f"  Quem mais viu: “{melhor[0]}” ({melhor[1]} elementos com nome).")
    if any(item[3] for item in medidas):
        print("  O painel “Create API key” está na tela — e alguma leitura o enxerga.")
    elif melhor[1] < LEITURA_POBRE:
        print(
            "  Nenhuma leitura viu a página. Se o painel está aberto na sua tela, mande o\n"
            "  chave-leitura.txt: ele diz o que cada leitura trouxe, e é com isso que eu conserto.\n"
            "\n"
            "  O que ainda dá para tentar, do mais simples ao mais completo:\n"
            "    1. rode de novo com o Chrome na frente e nada por cima dele;\n"
            "    2. no Chrome, abra chrome://accessibility e ligue a acessibilidade\n"
            "       (é uma página do próprio Chrome, com uma caixa de marcar no topo);\n"
            "    3. feche o Chrome e abra de novo com o atalho que eu deixei:\n"
            "       chrome-acessibilidade.bat"
        )
    else:
        print("  O painel não está aberto agora. Abra (New key) e rode de novo para eu medir com ele aberto.")

    relatorio = _gravar_relatorio(janela)
    print()
    print("  Nada foi clicado e nada foi gravado no .env.")
    if relatorio.get("arquivo"):
        print(f"  Relatório: {relatorio['arquivo']}")
        print("  Me mande esse arquivo: é ele que diz qual leitura vê o painel.")
    _desligar_a_acessibilidade()
    return 0


def _medida_boa(medida: tuple[str, int, dict[str, bool], bool]) -> bool:
    """A leitura dessa fonte mostrou a página ou o painel?"""
    _fonte, total, _campos, painel = medida
    return bool(painel) or total >= LEITURA_POBRE


def _nomes_do_diagnostico(linhas: list[tuple[str, int, dict[str, bool], bool]]) -> bool:
    """Alguma leitura chegou perto da página? Serve para o conselho certo."""
    return any(total >= LEITURA_POBRE for _fonte, total, _campos, _painel in linhas)


def passo_ver(args) -> int:
    from server import chave_web

    janela, montada = _ler_janela(args.alvo)
    estado = chave_web.onde_estou(montada, conta=args.conta)
    print(chave_web.texto_do_estado(estado))
    dados = chave_web.diagnostico(montada)
    print(chave_web.texto_do_diagnostico(dados))
    print()
    if dados["pode_clicar_com_mouse"]:
        print("  Dá para clicar com o mouse: SIM — há botão com posição medida na tela.")
    elif dados["pode_criar"] or dados["pode_copiar"]:
        print("  Dá para clicar com o mouse: não — achei o botão, mas sem posição na tela.")
    print("  Nada foi clicado: isto é só leitura.")
    return 0


# ---------------------------------------------------- a área de transferência
#
# Tudo o que acontece depois do clique passa por aqui. Duas regras que parecem
# detalhe e não são:
#
# 1. **Guardar o que já estava lá.** Se o dono copiou uma chave ontem e deixou
#    na área, ler "a primeira chave que aparecer" gravaria a chave errada. Só
#    vale o texto que **mudou** desde que este comando começou.
# 2. **Não confiar no primeiro instante.** Depois do Ctrl+C o Windows leva um
#    pedaço de segundo para entregar; por isso a espera é um laço, não um `sleep`.

def _texto_da_area() -> str:
    """O texto cru da área de transferência — vazio quando não dá para ler."""
    from server import area_transferencia

    try:
        return area_transferencia.ler(tentativas=2, espera=0.05)
    except Exception:  # noqa: BLE001 - qualquer falha aqui é "ainda não deu"
        return ""


def _chave_no_texto(modulo, texto: str) -> str:
    """A chave que está dentro de um texto (a página inteira também serve)."""
    try:
        chaves = modulo.chaves_do_texto(modulo.sem_controle(texto or ""))
    except Exception:  # noqa: BLE001
        return ""
    return chaves[0] if chaves else ""


def _esperar_chave(
    modulo, anterior: str, segundos: float = 90.0, avisar: bool = False
) -> tuple[str, str] | None:
    """Espera aparecer na área uma chave diferente da que já estava lá.

    `avisar` existe porque esperar calado parece travamento: o dono já apertou
    Ctrl+C numa espera de 120 s que não dizia nada. Com `avisar`, a cada 20 s
    uma linha diz que ele continua olhando e por quanto tempo.
    """
    inicio = time.time()
    fim = inicio + segundos
    proximo_aviso = inicio + 20.0
    while True:
        texto = _texto_da_area()
        if texto and texto.strip() != (anterior or "").strip():
            chave = _chave_no_texto(modulo, texto)
            if chave:
                return texto, chave
        agora = time.time()
        if agora >= fim:
            return None
        if avisar and agora >= proximo_aviso:
            print(f"     continuo olhando a área de transferência… ({int(agora - inicio)}s de {int(segundos)}s)")
            proximo_aviso = agora + 20.0
        time.sleep(0.7)


def _copiar_pela_pagina(janela: dict) -> bool:
    """Ctrl+A e Ctrl+C na janela do navegador — o plano B do botão Copiar.

    Por que existe: o botão “Copy” pode não estar na árvore, mas o texto da
    página está sempre lá. Depois de criar, a chave aparece escrita na tela;
    selecionar tudo e copiar traz a página inteira, e a chave sai dela pela
    mesma régua que lê chave de arquivo. Não lê imagem, não adivinha pixel.
    """
    from server import arvore_windows, mesa

    try:
        if not arvore_windows.trazer_para_frente(int(janela["handle"])):
            return False
        if not arvore_windows.teclado_na_janela(int(janela["handle"])):
            return False
        mesa.teclar("ctrl+a")
        time.sleep(0.15)
        mesa.teclar("ctrl+c")
        return True
    except Exception:  # noqa: BLE001
        return False


def passo_pegar(args) -> int:
    """A chave que você copiou no site → `.env`. Sem digitar nada."""
    modulo = _modulo_do_configurador()
    try:
        limpo, chave = modulo.chave_da_area_de_transferencia()
    except RuntimeError as exc:
        print(f"  NÃO DEU: {exc}")
        print("  Copie a chave no site (botão COPIAR) e rode `--pegar` de novo.")
        return 1
    print(modulo.descrever_area(limpo, chave))
    atual = _chave_do_env(modulo)
    if atual and atual == chave:
        # Aconteceu no PC do dono: o `--auto` falhou, ele apertou Ctrl+C, disse
        # “n” no aviso do .bat, o `--pegar` achou a chave **velha** na área de
        # transferência e o .bat anunciou “a chave está no .env”. Estava — a
        # velha. Aqui a frase passa a ser verdadeira.
        print("  Essa chave é a MESMA que já estava no .env — nada mudou.")
        print("  Se você acabou de criar uma, o COPIAR não chegou a copiá-la.")
        print("  Clique em COPIAR no site e rode `--pegar` de novo.")
        return 0
    return _gravar(modulo, chave)


def _chave_do_env(modulo) -> str:
    """A chave que está gravada hoje — para não anunciar como nova a que já era."""
    try:
        if not modulo.ENV.is_file():
            return ""
        texto = modulo.ler_texto(modulo.ENV)
        return (modulo.ler_valor(texto, modulo.CHAVE) or "").strip()
    except Exception:  # noqa: BLE001 - comparar é conveniência, não requisito
        return ""


def _avisar_jarvis_aberto() -> bool:
    """Manda a API que já está rodando reler o `.env` — sem reiniciar.

    O servidor lê o `.env` uma vez, no start. Gravar a chave por fora da tela
    deixava a tela mostrando a chave antiga até fechar e abrir. Se a API não
    estiver no ar, isso não é erro: o próximo start lê o arquivo novo.
    """
    import json
    import urllib.request

    for porta in (8000, 8001):
        pedido = urllib.request.Request(
            f"http://127.0.0.1:{porta}/api/ai/recarregar",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(pedido, timeout=1.5) as resposta:  # noqa: S310 - endereço fixo local
                return bool(json.loads(resposta.read().decode("utf-8")).get("ok"))
        except Exception:  # noqa: BLE001 - API desligada não é falha de gravar
            continue
    return False


def _gravar(modulo, chave: str) -> int:
    """Grava a chave **sem perguntar nada** quando o provedor já está escolhido.

    A 0.91.10 mandava tudo pelo `principal()`, que é o questionário da primeira
    configuração: provedor, base, modelo. Com o `.env` já montado — o caso de
    quem está só trocando a chave —, esse questionário fazia o duplo clique
    parar esperando Enter em três perguntas que já tinham resposta. Aqui:
    provedor já gravado → troca só a chave; primeira vez → aí sim pergunta.
    """
    texto = modulo.ler_texto(modulo.ENV) if modulo.ENV.is_file() else modulo.texto_base()
    provedor = (modulo.ler_valor(texto, "JARVIS_AI_PROVIDER") or "").strip()
    if provedor:
        texto = modulo.definir(texto, modulo.CHAVE, chave)
        destino = modulo.gravar(texto)
        print(f"\n  Gravado em {destino}")
        print(f"  provedor: {provedor}")
        print(f"  chave:    {modulo.mascarar(chave)}")
        print("\n  As outras linhas do .env ficaram como estavam.")
        if _avisar_jarvis_aberto():
            print("  O JARVIS que já está aberto passou a usar esta chave agora.")
        else:
            print("  O JARVIS não está aberto: ele vai ler esta chave quando abrir.")
        return 0
    codigo = modulo.principal(["--chave", chave])
    if codigo != 0:
        print("  A chave foi lida, mas não deu para gravar no .env — veja acima.")
    return codigo


def _provedor_do_env(modulo) -> tuple[str, str]:
    """(provedor, base) que já estão no `.env` — o `--auto` usa os dois."""
    texto = modulo.ler_texto(modulo.ENV) if modulo.ENV.is_file() else modulo.texto_base()
    return (
        (modulo.ler_valor(texto, "JARVIS_AI_PROVIDER") or "").strip(),
        (modulo.ler_valor(texto, "JARVIS_AI_BASE_URL") or "").strip(),
    )


def _janelas_do_alvo(alvo: str) -> list[dict]:
    """Janelas que podem ser a página aberta, da mais provável para a menos.

    Por que não basta a escolha de sempre: quando o Chrome já está aberto, o
    link abre numa aba da **janela que estava em foco** — e a escolha padrão,
    que decide pelo processo, empatava todas as janelas do Chrome e podia ler a
    errada (a do e-mail do dono, por exemplo). Aqui a janela em foco vem
    primeiro, e o resto mantém a ordem da escolha de sempre.
    """
    from server import arvore, arvore_windows

    try:
        janelas = arvore_windows.janelas()
        foco = arvore_windows.janela_em_foco() or {}
    except Exception:  # noqa: BLE001 - COM de terceiros
        return []
    handle_foco = int(foco.get("handle") or 0)
    pontuadas = []
    for item in janelas:
        peso = arvore.peso_da_janela(item, alvo)
        if peso is None:
            continue
        pontuadas.append((peso, 0 if int(item.get("handle") or 0) == handle_foco else 1, item))
    pontuadas.sort(key=lambda tripla: (tripla[0], tripla[1]))
    return [item for _peso, _foco, item in pontuadas]


def _ler_janelas(
    alvo: str, maximo: int = 3, profundidade: int = 8, limite: int = 1500
) -> list[tuple[dict, dict]]:
    """Lê as janelas do navegador (até `maximo`), a que está em foco primeiro."""
    from server import arvore, arvore_windows

    leituras: list[tuple[dict, dict]] = []
    for janela in _janelas_do_alvo(alvo)[:maximo]:
        try:
            bruto = arvore_windows.ler_janela(int(janela["handle"]), profundidade, limite)
        except Exception:  # noqa: BLE001 - janela que fechou no meio
            continue
        leituras.append((janela, arvore.montar(bruto, profundidade, limite, com_caminho=True)))
    return leituras


def _conta_do_env(modulo) -> str:
    texto = modulo.ler_texto(modulo.ENV) if modulo.ENV.is_file() else modulo.texto_base()
    return (modulo.ler_valor(texto, CONTA_GOOGLE) or "").strip()


def _guardar_conta(modulo, email: str) -> bool:
    """Lembra a conta escolhida no `.env` — perguntar uma vez é útil, duas é chatice."""
    if not email:
        return False
    try:
        texto = modulo.ler_texto(modulo.ENV) if modulo.ENV.is_file() else modulo.texto_base()
        modulo.gravar(modulo.definir(texto, CONTA_GOOGLE, email))
        return True
    except Exception:  # noqa: BLE001 - lembrar é conveniência, não requisito
        return False


def _perguntar_conta(contas: list[dict]) -> dict | None:
    """Pergunta qual conta, quando a tela mostra mais de uma e ninguém disse qual.

    Escolher no chute a conta errada é pior do que perguntar: entrar na conta de
    outra pessoa da casa criaria uma chave na conta errada.
    """
    if len(contas) == 1:
        return contas[0]
    if not contas or not sys.stdin or not sys.stdin.isatty():
        return None
    print("  Achei mais de uma conta do Google. Qual é a sua?")
    for numero, conta in enumerate(contas[:6], start=1):
        print(f"    {numero}. {conta['nome']}")
    try:
        escolha = input("  Número (Enter para eu não escolher): ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not escolha.isdigit():
        return None
    indice = int(escolha) - 1
    return contas[indice] if 0 <= indice < len(contas) else None


# Depois de clicar, a página leva alguns segundos para trocar. Sem esta pausa o
# JARVIS clicaria no mesmo botão duas vezes — e no Google isso abre duas janelas
# de login, que é pior do que esperar.
ESPERA_DEPOIS_DO_CLIQUE = 3.0


def _tentar_entrar(args, estados: list[tuple[dict, dict, dict]], tentativas: dict) -> bool:
    """Um passo do login: clicar em “Google” ou na conta. Devolve se agiu."""
    from server import chave_web

    ultimo_em = tentativas.setdefault("ultimo_em", {})
    agora = time.time()

    # 1. escolha de conta do Google
    for janela, montada, estado in estados:
        if estado["estado"] != chave_web.ESTADO_GOOGLE or tentativas["conta"] >= 3:
            continue
        if agora - ultimo_em.get(chave_web.ESTADO_GOOGLE, -1e9) < ESPERA_DEPOIS_DO_CLIQUE:
            return True
        escolhida = estado.get("conta_escolhida")
        if escolhida is None:
            escolhida = _perguntar_conta(estado.get("contas") or [])
            if escolhida:
                _guardar_conta(_modulo_do_configurador(), escolhida["email"])
        if not escolhida:
            tentativas["conta"] += 1
            print("  escolha de conta: não sei qual é a sua — clique nela que eu sigo.")
            return True
        print(f"  escolha de conta: clicando em “{escolhida['nome']}”…")
        try:
            _clicar(
                janela,
                escolhida["no"],
                mouse=not args.sem_mouse,
                primeiro_mouse=not args.sem_mouse,
            )
        except PassoError as exc:
            print(f"    não deu: {exc}")
        tentativas["conta"] += 1
        ultimo_em[chave_web.ESTADO_GOOGLE] = agora
        return True

    # 2. tela de login do provedor → botão do Google
    for janela, montada, estado in estados:
        if estado["estado"] != chave_web.ESTADO_LOGIN or tentativas["google"] >= 3:
            continue
        if agora - ultimo_em.get(chave_web.ESTADO_LOGIN, -1e9) < ESPERA_DEPOIS_DO_CLIQUE:
            return True
        botoes = chave_web.procurar(montada, chave_web.PADROES_GOOGLE)
        if not botoes:
            tentativas["google"] += 1
            print("  tela de login: não achei o botão do Google — clique nele que eu sigo.")
            return True
        print("  tela de login: entrando pelo Google…")
        try:
            _clicar(
                janela,
                botoes[0],
                mouse=not args.sem_mouse,
                primeiro_mouse=not args.sem_mouse,
            )
        except PassoError as exc:
            print(f"    não deu: {exc}")
        tentativas["google"] += 1
        ultimo_em[chave_web.ESTADO_LOGIN] = agora
        return True
    return False


def _levar_ate_as_chaves(args, conta: str | None = None, segundos: float | None = None) -> tuple[dict, dict]:
    """Leva a janela do navegador até a página de chaves, atravessando o login.

    Medido nas telas do dono (0.91.14): abrir `openrouter.ai/keys` sem sessão cai
    em **Sign In**; o Google abre a **escolha de conta**; só depois aparece
    **API keys**. Três páginas na mesma janela — e o JARVIS tem de saber em qual
    está antes de clicar em qualquer coisa.
    """
    from server import chave_web

    # Sem conta dita aqui, vale a que veio na linha de comando (`--conta`).
    if conta is None:
        conta = str(getattr(args, "conta", "") or "")
    limite = time.time() + (args.espera_pagina if segundos is None else segundos)
    tentativas = {"google": 0, "conta": 0, "ultimo_em": {}}
    ultimo: dict | None = None
    while True:
        leituras = _ler_janelas(args.alvo)
        estados = [(janela, montada, chave_web.onde_estou(montada, conta=conta)) for janela, montada in leituras]
        for janela, montada, estado in estados:
            ultimo = estado
            if estado["estado"] == chave_web.ESTADO_CHAVES:
                return janela, montada
        if estados:
            _tentar_entrar(args, estados, tentativas)
        if time.time() >= limite:
            break
        time.sleep(1.0)

    if ultimo is None:
        raise PassoError("o navegador não abriu nenhuma janela a tempo. A página abriu em outro lugar?")
    if ultimo["estado"] == chave_web.ESTADO_LOGIN:
        raise PassoError(
            "a página abriu na tela de login e eu não consegui entrar. "
            "Entre você pelo Google (uma vez só) e rode de novo."
        )
    if ultimo["estado"] == chave_web.ESTADO_GOOGLE:
        raise PassoError(
            "estou parado na escolha de conta do Google. Diga qual é a sua com "
            "`--conta seuemail@gmail.com` que eu lembro para as próximas vezes."
        )
    raise PassoError(
        "não cheguei na página de chaves. O que a janela mostrou: "
        + chave_web.texto_do_estado(ultimo)
    )


def _garantir_na_frente(janela: dict, segundos: float = 2.0) -> bool:
    """Põe a janela na frente e **confirma** que ela está — pelo Windows.

    Por que confirmar: `SetForegroundWindow` pode voltar dizendo “ok” e o
    Windows não trocar nada (ele recusa quando quem pede está em segundo
    plano). Sem confirmar, o clique físico cairia numa janela coberta — e o
    primeiro clique só serviria para ativar a janela, não para apertar o botão.
    Era exatamente isso que fazia o “New key” não abrir o painel.
    """
    from server import arvore_windows

    handle = int(janela.get("handle") or 0)
    if not handle:
        return False
    fim = time.time() + segundos
    while True:
        try:
            arvore_windows.trazer_para_frente(handle)
        except Exception:  # noqa: BLE001 - COM de terceiros
            return False
        time.sleep(0.25)
        try:
            foco = arvore_windows.janela_em_foco() or {}
        except Exception:  # noqa: BLE001 - sem como confirmar, não atrapalha
            return True
        if int(foco.get("handle") or 0) == handle:
            return True
        if time.time() >= fim:
            return False


_ACESSIBILIDADE_AVISADA: set[int] = set()
_MODO_LEITOR_ATIVO = False


def _tomar_o_sinal(avisar: bool = True) -> bool:
    """Liga o modo leitor de tela **no começo** e mantém até o fim do programa.

    Por que no começo e não na primeira falha: medido no PC do dono (16/11),
    a leitura trazia 85 elementos logo depois de reabrir o Chrome e voltava a 3
    poucos segundos depois, no mesmo processo. O Chrome publica a página
    enquanto acredita que existe um leitor de tela ativo. Ligar só quando a
    leitura falha é chegar depois de a página já ter sumido — e cada leitura
    custa segundos que o Chrome usa para desligar de novo.
    """
    global _MODO_LEITOR_ATIVO
    try:
        from server import arvore_windows
    except Exception:  # noqa: BLE001 - fora do Windows (testes)
        return False
    ligar = getattr(arvore_windows, "ligar_leitor_de_tela", None)
    if ligar is None:  # dublê de teste sem a função
        return False
    try:
        _MODO_LEITOR_ATIVO = bool(ligar())
    except Exception:  # noqa: BLE001 - configuração do sistema: melhor esforço
        return False
    if _MODO_LEITOR_ATIVO and avisar:
        print(
            "     (liguei o modo leitor de tela do Windows para o Chrome publicar a "
            "página; desligo no fim)"
        )
    return _MODO_LEITOR_ATIVO


def _acordar_a_acessibilidade(janela: dict, *, avisar: bool = False) -> bool:
    """Pede a árvore ao Chrome de novo — a cada leitura pobre, não uma vez só.

    O Chrome liga a acessibilidade da página quando alguém a pede e a desliga
    quando para de pedir. No print de 16/11 a mesma janela passou de 85
    elementos para 2 sem nada mudar na tela. Então o pedido é **repetido**,
    com pausa: é ele que mantém a página publicada.
    """
    try:
        from server import arvore_windows
    except Exception:  # noqa: BLE001 - fora do Windows (testes) não há o que acordar
        return False

    handle = int(janela.get("handle") or 0)
    if not handle:
        return False
    acordar = getattr(arvore_windows, "acordar_acessibilidade", None)
    if acordar is None:  # dublê de teste sem a função
        return False
    try:
        feito = acordar(handle)
    except Exception:  # noqa: BLE001 - COM de terceiros: melhor esforço
        return False
    if avisar and handle not in _ACESSIBILIDADE_AVISADA:
        _ACESSIBILIDADE_AVISADA.add(handle)
        if feito.get("ligado"):
            print(
                "     o Chrome parou de publicar a página — pedi a leitura de novo "
                "(modo leitor de tela ligado, desligo no fim)."
            )
        else:
            print(
                "     o Chrome não está publicando a página e eu não consegui ligar o "
                "modo leitor de tela do Windows."
            )
    return bool(feito.get("ligado"))


def _desligar_a_acessibilidade() -> None:
    """Devolve a configuração do Windows como estava antes do programa."""
    global _MODO_LEITOR_ATIVO
    _MODO_LEITOR_ATIVO = False
    try:
        from server import arvore_windows

        desligar = getattr(arvore_windows, "desligar_leitor_de_tela", None)
        if desligar is not None:
            desligar()
    except Exception:  # noqa: BLE001 - devolver é cortesia, não requisito
        pass


def _acordar_leitura(janela: dict, montada: dict, *, avisar: bool = False, segundos: float = 1.2):
    """Leitura pobre não é resposta: põe a janela na frente, pede a árvore e relê.

    Três coisas aprendidas em três prints, nesta ordem:

    - **0.91.22**: com o painel aberto a leitura trouxe 3 elementos — a janela
      do Chrome estava atrás do console. Trazer para a frente é o primeiro remédio;
    - **0.91.23**: janela na frente e ainda 3 — o problema podia ser a vista de
      acessibilidade;
    - **0.91.25**: o diagnóstico provou que eram 3 em **todas** as vistas, com o
      painel na tela. O Chrome simplesmente não estava publicando a página.

    Aqui as três coisas são tentadas **na ordem em que custam menos**, e a
    última é a que importa: pedir a árvore de novo (`WM_GETOBJECT`) — é esse
    pedido, repetido, que mantém a página publicada no Chrome.
    """
    if _leitura_boa(montada):
        return janela, montada

    em_foco = False
    try:
        em_foco = _garantir_na_frente(janela, segundos=segundos)
    except Exception:  # noqa: BLE001 - COM de terceiros: não pode derrubar a espera
        em_foco = False

    pediu = _acordar_a_acessibilidade(janela, avisar=avisar)

    if avisar:
        if not em_foco:
            # Ação que o dono precisa tomar: sem foco, nada do resto adianta.
            print(
                "     a leitura caiu (só a moldura do Chrome) e o Windows não deixou eu "
                "pôr a janela na frente — clique uma vez no Chrome para ela subir."
            )
        elif not pediu:
            print(
                "     a leitura tinha caído (só a moldura do Chrome) — trouxe a "
                "janela para a frente; se ela for para trás, eu trago de novo."
            )
    try:
        janela, montada = _reler(janela, PROFUNDA, TETO_FUNDO, curar=False)
    except PassoError:
        pass
    if not _leitura_boa(montada) and not pediu:
        # Segunda tentativa, agora pedindo a árvore: o Chrome leva alguns
        # segundos para publicar, e quem chama está em laço — repetir aqui custa
        # menos do que desistir com a página na tela.
        _acordar_a_acessibilidade(janela, avisar=avisar)
        try:
            janela, montada = _reler(janela, PROFUNDA, TETO_FUNDO, curar=False)
        except PassoError:
            pass
    return janela, montada


def _outra_janela_com_dialogo(args, janela: dict):
    """O painel abriu em **outra** janela do navegador? Devolve (janela, árvore)."""
    from server import chave_web

    handle = int(janela.get("handle") or 0)
    try:
        leituras = _ler_janelas(args.alvo, profundidade=PROFUNDA, limite=TETO_FUNDO)
    except Exception:  # noqa: BLE001 - ler a vizinha é ajuda, não requisito
        return None
    for outra, montada in leituras:
        if int(outra.get("handle") or 0) == handle:
            continue
        if chave_web.e_dialogo_de_criacao(montada):
            return outra, montada
    return None


def _esperar_dialogo(args, janela: dict, segundos: float = 35.0, avisar: bool = True):
    """Espera o painel “Create API key” aparecer, com paciência e sem palpite.

    O que mudou depois do PC do dono (0.91.17): ele desistia em 12 segundos e,
    pior, desistia **por causa de uma leitura ruim** — uma passada em que o
    Chrome devolveu só a moldura. Duas correções:

    1. **35 segundos**, com aviso de progresso: carregar a página, ou o painel
       abrir, pode levar mais do que os 12 de antes — e esperar calado parece
       travamento;
    2. **leitura pobre não é resposta.** Cada tentativa relê pela fonte que
       mostra a página (ver `_reler`); só quando o painel não aparece em
       leitura boa é que ele conclui que não abriu. Quando a leitura traz só a
       moldura, a janela é posta na frente e a página é lida de novo — foi com
       3 elementos que ele desistiu, na 0.91.21, com o painel aberto na tela.

    As outras janelas do navegador são conferidas a cada três tentativas — o
    clique pode abrir o painel na janela vizinha.
    """
    from server import chave_web

    inicio = time.time()
    fim = inicio + segundos
    if avisar:
        print(f"     esperando o painel abrir (até {int(segundos)}s; a página pode estar carregando)…")
    janela, montada = _reler(janela, PROFUNDA, TETO_FUNDO)
    tentativa = 0
    avisou_caida = False
    while True:
        if chave_web.e_dialogo_de_criacao(montada):
            return janela, montada
        if not _leitura_boa(montada):
            # Leitura pobre **não é** “o painel não abriu”: é “eu não estou
            # vendo a página”. Foi assim que ele desistiu com o painel na tela
            # e a janela do Chrome atrás do console (print de 15/11).
            janela, montada = _acordar_leitura(
                janela, montada, avisar=not avisou_caida, segundos=1.2
            )
            avisou_caida = True
            if chave_web.e_dialogo_de_criacao(montada):
                return janela, montada
            # Pobre na janela principal é justamente quando vale olhar a
            # vizinha: o painel pode ter aberto na outra janela do navegador.
            outra = _outra_janela_com_dialogo(args, janela)
            if outra is not None:
                return outra
            if time.time() >= fim:
                break
            time.sleep(0.6)
            continue

        avisou_caida = False
        if time.time() >= fim:
            break
        tentativa += 1
        if tentativa % 3 == 0:
            outra = _outra_janela_com_dialogo(args, janela)
            if outra is not None:
                return outra
        try:
            janela, montada = _reler(janela, PROFUNDA, TETO_FUNDO)
        except PassoError:
            pass
        if tentativa % 4 == 0:
            print(
                f"     ainda procurando… ({int(time.time() - inicio)}s) — "
                f"a leitura trouxe {_nomes(montada)} elementos."
            )
        time.sleep(1.0)
    relatorio = _gravar_relatorio(janela)
    raise PassoError(
        _diagnostico_da_leitura(montada, insistiu=time.time() - inicio) + relatorio["recado"]
    )


def _gravar_relatorio(janela: dict, extra: list[str] | None = None) -> dict:
    """Grava, na pasta do JARVIS, o que cada fonte de leitura mostrou.

    Por que um arquivo: quando a leitura falha, a tela mostra só o veredito. O
    relatório guarda as três leituras — quantos elementos cada uma trouxe, o
    aviso delas e os primeiros nomes — que é o que permite descobrir a causa
    sem adivinhar.
    """
    from server import chave_web

    linhas = [
        "JARVIS — por que a leitura não achou o painel “Create API key”",
        f"quando: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
        f"janela: {str(janela.get('titulo') or '')!r} (handle {janela.get('handle')})",
    ]
    try:
        from server import arvore_windows

        em_foco = arvore_windows.janela_em_foco() or {}
        handle_atual = int(em_foco.get("handle") or 0)
        linhas.append(
            "estado: "
            + ("minimizada; " if janela.get("minimizada") else "não minimizada; ")
            + (
                "com o foco"
                if handle_atual == int(janela.get("handle") or 0)
                else "SEM o foco (o foco está em " + str(
                    em_foco.get("titulo") or em_foco.get("processo") or "?"
                ) + ")"
            )
        )
    except Exception:  # noqa: BLE001 - diagnóstico não pode derrubar
        pass
    linhas.append("")
    if extra:
        # O que cada clique tentou fazer. Quando o painel não abre, a pergunta
        # “o clique saiu?” se responde aqui, e não no chute.
        linhas.append("tentativas de clique:")
        linhas.extend(f"  {linha}" for linha in extra)
        linhas.append("")
    handle = int(janela.get("handle") or 0)
    try:
        from server import arvore_windows

        filhas = arvore_windows.janelas_filhas(handle, 12)
    except Exception:  # noqa: BLE001 - diagnóstico não pode derrubar
        filhas = []
    if filhas:
        linhas.append("janelas filhas do Chrome:")
        for filha in filhas[:12]:
            linhas.append(
                f"  {filha.get('classe') or '?'}  (handle {filha.get('handle')})"
            )
        linhas.append("")
    # Todas as vistas são medidas e escritas: quando o painel está na tela e a
    # leitura não o traz, esta é a única pergunta que importa — **qual** vista
    # enxerga a página. (0.91.23: a de controle devolvia 3 elementos; a crua,
    # a página inteira com o painel.)
    for fonte in ("auto", "uia", "uia_raw", "uia_content", "msaa"):
        try:
            montada = _ler_pela_fonte(handle, PROFUNDA, TETO_FUNDO, fonte)
        except Exception as exc:  # noqa: BLE001 - é diagnóstico, não pode derrubar
            linhas.append(f"{fonte:4}: erro {type(exc).__name__}: {exc}")
            linhas.append("")
            continue
        nos = chave_web.elementos(montada)
        linhas.append(
            f"{fonte:4}: {len(nos)} elemento(s) com nome, {montada.get('total')} nó(s), "
            f"fonte relatada {montada.get('fonte')!r}"
        )
        for chave in ("aviso", "nota", "de_filha", "dica"):
            valor = str(montada.get(chave) or "").strip()
            if valor:
                linhas.append(f"      {chave}: {valor}")
        campos = _campos_do_painel(montada)
        vistos = [rotulo for rotulo in CAMPOS_DO_PAINEL if campos[rotulo]]
        linhas.append(
            "      painel: "
            + ("SIM — " + ", ".join(vistos) if vistos else "não — nenhum campo do painel nesta leitura")
        )
        if nos:
            linhas.append(
                "      primeiros: " + ", ".join(str(n.get("nome") or "")[:40] for n in nos[:40])
            )
        linhas.append("")
    caminho = Path(__file__).resolve().parent / "chave-leitura.txt"
    try:
        caminho.write_text("\n".join(linhas), encoding="utf-8")
    except OSError:
        return {"arquivo": "", "recado": ""}
    return {"arquivo": str(caminho), "recado": f" Detalhes em {caminho.name}."}


def _diagnostico_da_leitura(montada: dict, quantos: int = 12, insistiu: float = 0.0) -> str:
    """O que a leitura viu, em uma frase — para o dono poder mandar de volta.

    “o diálogo não apareceu” não diz nada a quem está olhando a tela com o
    diálogo aberto. Dizer quantos elementos vieram e quais os primeiros nomes
    transforma o mistério em uma linha copiável.
    """
    from server import chave_web

    nomes = [str(no.get("nome") or "")[:28] for no in chave_web.elementos(montada)[:quantos]]
    total = len(chave_web.elementos(montada))
    aviso = str(montada.get("aviso") or "").strip()
    texto = (
        f"a leitura não trouxe o que eu procurava ({total} elementos com nome, "
        f"fonte {montada.get('fonte') or '?'}"
    )
    texto += f"; os primeiros: {', '.join(nomes)})." if nomes else ")."
    if total < LEITURA_POBRE:
        texto += (
            " A leitura veio pobre — isso é a moldura do Chrome, não a página: "
            "pode ser a página ainda carregando ou o painel ainda abrindo."
        )
        if insistiu:
            # Insistir e continuar pobre muda o conselho: não é lentidão, é a
            # janela que não está publicando (atrás, minimizada ou coberta).
            texto += (
                f" Insisti por {int(insistiu)}s, tentei trazer a janela para a frente e a leitura "
                "continuou pobre: deixe o Chrome visível (nada por cima, nada minimizado) "
                "e rode de novo."
            )
    if aviso:
        texto += f" Aviso da leitura: {aviso}"
    return texto


ROTULOS_DO_CRIAR = ("create", "criar", "confirmar", "confirm", "salvar", "save")


def _botao_de_criar(montada: dict) -> dict | None:
    """O botão que cria, e **não** o título do painel.

    “Create API key” também contém “create”. Quando o botão está apagado (o
    caso em que ele é justamente o que interessa), o título passava na frente na
    ordenação — e o script “clicava” no título e dizia que tinha tentado criar.
    Aqui o rótulo tem de ser **exatamente** criar/confirmar/salvar.
    """
    from server import chave_web

    for no in chave_web.procurar(montada, chave_web.PADROES_CONFIRMAR):
        if chave_web.normalizar(str(no.get("nome") or "")) in ROTULOS_DO_CRIAR:
            return no
    return None


def _esperar_botao_criar(janela: dict, segundos: float = 8.0):
    """Relê até o botão de criar aparecer. Devolve (janela, botão, árvore)."""
    fim = time.time() + segundos
    while True:
        janela, montada = _reler(janela, PROFUNDA, TETO_FUNDO)
        botao = _botao_de_criar(montada)
        if botao is not None:
            return janela, botao, montada
        if time.time() >= fim:
            ultima = _diagnostico_da_leitura(montada)
            raise PassoError(f"não achei o botão “Create” nesta leitura. {ultima}")
        time.sleep(0.8)


def _achar_elemento(
    janela: dict,
    padroes: tuple[str, ...],
    alvo: str = "",
    segundos: float = 18.0,
    rotulo: str = "o elemento",
):
    """Procura o elemento **relendo**, e só desiste depois de tentar de verdade.

    Medido no PC do dono (0.91.19), com a página inteira na tela e o botão “New
    key” nela:

        1. NÃO DEI: o botão de criar não está na árvore desta janela.

    A leitura daquele momento não trazia o botão (leitura pobre, moldura), e o
    script parou na **primeira** tentativa, usando a última leitura que tinha em
    mãos — sem reler fundo e sem dizer o que viu. Aqui:

    - a leitura é **funda** (o painel e os botões moram no fim do documento);
    - cada tentativa confere também **as outras janelas do navegador** (o clique
      pode ter aberto a página na vizinha);
    - desistir exige provas: o erro diz quantos elementos vieram e quais os
      primeiros nomes, e o relatório é gravado.

    Devolve `(janela, nó, árvore)` — com a janela certa, que pode ser outra.
    """
    from server import chave_web

    inicio = time.time()
    fim = inicio + segundos
    ultima: dict | None = None
    tentativa = 0
    while True:
        tentativa += 1
        try:
            janela, montada = _reler(janela, PROFUNDA, TETO_FUNDO)
        except PassoError:
            montada = None
        if montada is not None:
            ultima = montada
            achados = chave_web.procurar(montada, padroes)
            if achados:
                return janela, achados[0], montada
        if alvo and tentativa % 2 == 0:
            for outra, montada_outra in _ler_janelas(alvo, profundidade=PROFUNDA, limite=TETO_FUNDO):
                if int(outra.get("handle") or 0) == int(janela.get("handle") or 0):
                    continue
                achados = chave_web.procurar(montada_outra, padroes)
                if achados:
                    return outra, achados[0], montada_outra
        if time.time() >= fim:
            break
        if tentativa == 1:
            print(f"     {rotulo} não veio na primeira leitura — releio por {int(segundos)}s…")
        time.sleep(1.0)
    detalhe = _diagnostico_da_leitura(ultima) if ultima is not None else "a leitura não devolveu árvore."
    _gravar_relatorio(janela, extra=[f"{rotulo}: não encontrado em {int(segundos)}s ({tentativa} leituras)"])
    raise PassoError(f"não achei {rotulo}. {detalhe}")


def _esperar_pagina_pronta(args, janela: dict, montada: dict, segundos: float = 12.0):
    """Espera a página parar de mudar antes de clicar em “New key”.

    Medido no PC do dono (0.91.17): a página abriu ainda carregando, o clique
    caiu num botão que a página trocou em seguida, e o painel nunca abriu —
    “ele tentou antes de a página ficar pronta”, nas palavras do dono.

    O sinal de “pronta” é simples: o botão de criar está na leitura **e** duas
    leituras seguidas trazem praticamente os mesmos elementos. A leitura aqui é
    funda — é a mesma que vai ser usada para clicar, e ela não pode ser mais
    rasa do que o necessário para achar o botão (foi assim que a 0.91.19 parou
    dizendo que o botão não existia).
    """
    from server import chave_web

    fim = time.time() + segundos
    anterior = -1
    avisou = False
    avisou_caida = False
    while True:
        agora = _nomes(montada)
        tem_botao = bool(chave_web.procurar(montada, chave_web.PADROES_CRIAR))
        if tem_botao and agora >= LEITURA_POBRE and abs(agora - anterior) <= 2:
            return janela, montada
        if time.time() >= fim:
            print(f"     a página não sossegou em {int(segundos)}s (a leitura trouxe {agora} elementos).")
            return janela, montada
        if not avisou:
            print("     a página ainda está carregando — espero ela parar antes de clicar.")
            avisou = True
        anterior = agora
        time.sleep(1.0)
        janela, montada = _reler(janela, PROFUNDA, TETO_FUNDO)
        if not _leitura_boa(montada):
            # Página que não aparece pode ser janela atrás, não página lenta.
            janela, montada = _acordar_leitura(janela, montada, avisar=not avisou_caida)
            avisou_caida = True


def _abrir_lista(
    janela: dict, montada, campo, *, mouse: bool, primeiro_mouse: bool, segundos: float = 5.0
):
    """Clica num campo de lista e devolve as opções que apareceram.

    Lista suspensa não muda nome de nada: ela **acrescenta** nós à janela. É
    comparando a leitura de antes com a de depois que se acham as opções — sem
    saber como o site as desenha. A leitura vai fundo: as opções moram no fim
    do documento, como o próprio diálogo.
    """
    from server import chave_web

    try:
        _clicar(janela, campo, mouse=mouse, primeiro_mouse=primeiro_mouse)
    except PassoError as exc:
        raise PassoError(f"não abri a lista “{campo.get('nome')}”: {exc}") from exc

    fim = time.time() + segundos
    while True:
        janela, depois = _reler(janela, PROFUNDA, TETO_FUNDO)
        opcoes = chave_web.nomes_novos(montada, depois)
        if opcoes:
            return janela, depois, opcoes
        if time.time() >= fim:
            return janela, depois, []
        time.sleep(0.6)


def _preencher_uma_lista(
    janela: dict,
    montada: dict,
    padroes: tuple[str, ...],
    regra,
    rotulo: str,
    *,
    mouse: bool,
    primeiro_mouse: bool,
) -> tuple[dict, str]:
    """Abre a lista do diálogo, escolhe pela regra e devolve (leitura nova, escolha).

    Devolve `(montada, "")` quando não achou o campo ou não deu para escolher —
    quem chama diz o que ficou faltando, em vez de fingir que preencheu.
    """
    from server import chave_web

    campos = chave_web.procurar(montada, padroes)
    if not campos:
        print(f"     {rotulo}: não achei o campo nesta tela.")
        return montada, ""
    campo = campos[0]
    print(f"     {rotulo}: abrindo “{str(campo.get('nome') or '')[:40]}”…")
    try:
        janela, aberta, opcoes = _abrir_lista(
            janela, montada, campo, mouse=mouse, primeiro_mouse=primeiro_mouse
        )
    except PassoError as exc:
        print(f"     {rotulo}: {exc}")
        return montada, ""

    nomes = [str(opcao.get("nome") or "") for opcao in opcoes]
    escolha = regra(nomes)
    if not escolha:
        print(f"     {rotulo}: a lista abriu com {len(nomes)} opções e nenhuma serve — deixei como estava.")
        return aberta, ""
    alvo = next((opcao for opcao in opcoes if str(opcao.get("nome") or "") == escolha), None)
    if alvo is None:
        return aberta, ""
    print(f"     {rotulo}: escolhendo “{escolha}”.")
    try:
        _clicar(janela, alvo, mouse=mouse, primeiro_mouse=primeiro_mouse)
    except PassoError as exc:
        print(f"     {rotulo}: não consegui clicar na opção ({exc}).")
        return aberta, ""
    time.sleep(0.5)
    return _reler(janela, PROFUNDA, TETO_FUNDO)[1], escolha


def _digitar_substituindo(janela: dict, texto: str) -> bool:
    """`Ctrl+A` e depois digita — troca o conteúdo do campo em vez de somar.

    Serve para o caso em que a primeira escrita pode ter ido para outro lugar:
    sem o `Ctrl+A`, tentar de novo escreveria “jarvis-testejarvis-teste”.
    """
    from server import arvore_windows, mesa

    handle = int(janela.get("handle") or 0)
    if not handle or not _garantir_na_frente(janela):
        return False
    try:
        if not arvore_windows.teclado_na_janela(handle):
            return False
        mesa.teclar("ctrl+a")
        mesa.digitar(texto)
        return True
    except Exception:  # noqa: BLE001 - último degrau, não requisito
        return False


def _digitar_na_janela(janela: dict, texto: str) -> bool:
    """Digita com o teclado na janela **depois de conferir que ela está na frente**.

    Só serve quando o foco já está no campo certo — que é o caso do diálogo de
    criação, onde o cursor nasce dentro do “Name”. Se o teclado não estiver na
    janela do navegador, não digita às cegas: devolve `False`.
    """
    from server import arvore_windows, mesa

    try:
        handle = int(janela.get("handle") or 0)
        if not arvore_windows.trazer_para_frente(handle):
            return False
        if not arvore_windows.teclado_na_janela(handle):
            return False
        mesa.digitar(texto)
        return True
    except Exception:  # noqa: BLE001 - digitar é o último degrau, não requisito
        return False


def _nome_aparece(montada: dict, texto: str) -> bool:
    """O nome digitado aparece na leitura? (uns Chrome publicam o valor, outros não)"""
    from server import chave_web

    alvo = chave_web.normalizar(texto)
    if not alvo:
        return False
    return any(alvo in chave_web.normalizar(str(no.get("nome") or "")) for no in chave_web.elementos(montada))


def _escrever_no_campo(
    janela: dict, campo: dict, texto: str, *, mouse: bool
) -> tuple[bool, str, bool | None]:
    """Digita num campo e **confere**. Devolve (deu certo, como, conferido).

    Três degraus, e o segundo só existe porque o primeiro pode mentir:

    1. **clique no campo + teclado** — é o que uma pessoa faz;
    2. **foco pela árvore** (`accSelect`/`put_accValue`) — quando o clique cai
       num lugar que não aceita foco;
    3. **teclado com a janela na frente** — último recurso, com o diálogo que
       nasce com o cursor no campo.

    Cada degrau devolve `conferido`: `True` (o campo mostra o texto), `False`
    (o campo publica valor e ele é outro) ou `None` (o campo não publica valor).
    Sem esta conferência, o script dizia “escrevendo…” e seguia com o campo
    vazio — foi o que aconteceu no PC do dono.
    """
    tentativas = [
        ("clique no campo + teclado", {"mouse": mouse, "primeiro_mouse": mouse}),
        ("foco pela árvore", {"mouse": False, "primeiro_mouse": False}),
    ]
    for rotulo, opcoes in tentativas:
        try:
            feito = _clicar(janela, campo, "digitar", texto, **opcoes)
        except PassoError as exc:
            print(f"     ({rotulo} não deu: {exc})")
            continue
        conferido = feito.get("conferido")
        if conferido is True:
            return True, rotulo, True
        print(f"     ({rotulo}: {_descrever_clique(feito)}"
              + ("" if conferido is None else " — mas o campo não mostra o texto") + ")")
        if conferido is None:
            # O campo não publica valor: a leitura é o único juiz que sobrou.
            # Se nem ela mostra o texto, **não se repete**: digitar de novo com o
            # cursor no fim do campo escreveria o nome duas vezes. Fica a prova
            # que existe no fim do painel — o botão “Create” acender.
            try:
                _janela, depois = _reler(janela, PROFUNDA, TETO_FUNDO)
            except PassoError:
                depois = None
            if depois is not None and _nome_aparece(depois, texto):
                return True, rotulo, True
            return True, rotulo, None
    if _digitar_na_janela(janela, texto):
        try:
            _janela, depois = _reler(janela, PROFUNDA, TETO_FUNDO)
        except PassoError:
            depois = None
        if depois is not None and _nome_aparece(depois, texto):
            return True, "teclado com a janela na frente", True
        return True, "teclado com a janela na frente", None
    return False, "", False


def _preencher_dialogo(
    janela: dict, montada: dict, nome: str, *, mouse: bool, primeiro_mouse: bool
) -> tuple[dict, dict[str, str]]:
    """Preenche “Create API key” inteiro: nome, expiração e limite.

    Medido na tela do dono: o botão “Create” fica desabilitado enquanto a
    expiração (que tem asterisco) está vazia. Escrever só o nome e clicar em
    Create não cria nada — e antes da 0.91.15 o script dizia que tinha dado
    certo. Aqui cada campo devolve o que foi **conferido**, não o que foi
    tentado.
    """
    from server import chave_web

    preenchidos: dict[str, str] = {}
    nome_conferido = False

    # 1. nome — na **caixa**, não no rótulo ao lado
    campo = chave_web.campo_do_nome(montada)
    if campo is not None:
        print(f"     nome: escrevendo “{nome}” no campo…")
        deu, como, conferido = _escrever_no_campo(janela, campo, nome, mouse=mouse)
        if deu:
            preenchidos["nome"] = nome
            nome_conferido = bool(conferido)
            if conferido:
                print(f"     nome: digitado e conferido ({como}).")
            else:
                print(f"     nome: digitado ({como}) — o campo não publica o valor, então")
                print("           quem confirma é o botão “Create” acender no fim.")
        else:
            print("     nome: NÃO consegui escrever no campo.")
    else:
        print("     nome: a leitura não trouxe nenhuma caixa de texto no painel.")
        if _digitar_na_janela(janela, nome):
            preenchidos["nome"] = nome
            nome_conferido = _nome_aparece(montada, nome)
            print(f"     nome: digitado pelo teclado (“{nome}”).")
        else:
            print("     nome: o teclado não estava na janela — não digitei às cegas.")

    janela, montada = _reler(janela, PROFUNDA, TETO_FUNDO)

    # 2. expiração — o campo que deixava o Create apagado
    montada, prazo = _preencher_uma_lista(
        janela, montada, chave_web.PADROES_EXPIRACAO, chave_web.melhor_expiracao, "expiração",
        mouse=mouse, primeiro_mouse=primeiro_mouse,
    )
    if prazo:
        preenchidos["expiração"] = prazo

    # 3. limite de crédito — não é para caber mais, é para não travar sozinho.
    #    Sem opção “sem limite”, ele **não para**: escolhe o maior valor da lista
    #    e diz que escolheu — parar aqui é não ter chave nenhuma.
    def _limite_da_lista(nomes_da_lista: list[str]) -> str | None:
        escolhido = chave_web.melhor_limite(nomes_da_lista, aceitar_maior=True)
        if escolhido and not chave_web.melhor_limite(nomes_da_lista):
            print(
                f"     limite: a lista não tem “sem limite” — escolhendo o maior de lá "
                f"(“{escolhido}”), para a chave não ficar sem criar."
            )
        return escolhido

    montada, limite = _preencher_uma_lista(
        janela, montada, chave_web.PADROES_LIMITE, _limite_da_lista, "limite",
        mouse=mouse, primeiro_mouse=primeiro_mouse,
    )
    if limite:
        preenchidos["limite"] = limite

    # 4. a prova final é o botão “Create”: apagado = falta campo. Se o nome foi
    #    escrito sem confirmação (o campo não publica valor), ele é o suspeito
    #    número um — e reescrever do zero é barato.
    if "nome" in preenchidos and not nome_conferido:
        try:
            janela, montada = _reler(janela, PROFUNDA, TETO_FUNDO)
        except PassoError:
            return montada, preenchidos
        botao = _botao_de_criar(montada)
        if botao is not None and not botao.get("acionavel"):
            print("     o botão “Create” continua apagado — reescrevo o nome do zero.")
            if _digitar_substituindo(janela, nome):
                print(f"     nome: reescrito (“{nome}”), apagando o que estivesse no campo.")
                janela, montada = _reler(janela, PROFUNDA, TETO_FUNDO)
    return montada, preenchidos


def _criar_e_copiar(
    args, modulo, janela, montada, dados, *, mouse: bool, primeiro_mouse: bool, anterior: str
) -> str | None:
    """Os quatro cliques e a cópia. Devolve a chave, ou `None` dizendo onde parou."""
    from server import chave_web

    nome = args.nome or chave_web.nome_sugerido()

    # 0. a página pronta — a 0.91.16 clicou num botão que a página ainda ia
    #    trocar, e o painel nunca abriu. Clicar cedo demais é o mesmo que não
    #    clicar: o efeito se perde quando a página termina de montar.
    janela, montada = _esperar_pagina_pronta(args, janela, montada)

    # 1. Create Key — com uma escada, porque no Chrome a “ação do elemento”
    #    mente: `accDoDefaultAction` devolve sucesso e a página não faz nada.
    #    Medido no PC do dono (0.91.17): duas esperas de 35 s depois de duas
    #    “ações” que não abriram nada. O que abre o painel é o clique do mouse,
    #    que só era tentado com `--mouse` — e o `.bat` não passa `--mouse`.
    #
    #    A ordem agora é: clique do mouse → clique do mouse outra vez (o
    #    primeiro pode só ativar a janela) → ação do elemento. Cada degrau é
    #    conferido: se o painel abriu, para ali.
    plano = [
        ("mouse", 20.0, "clique do mouse"),
        ("mouse", 20.0, "clique do mouse, segunda vez"),
        ("acao", 15.0, "ação do elemento"),
    ]
    if not mouse:
        plano = [("acao", 30.0, "ação do elemento")]
    falha = None
    cliques: list[str] = []
    # Quantos nomes a página tinha ao achar o botão: é a régua para saber se uma
    # leitura nova “despencou”. Não é um número absoluto — página pequena vale.
    referencia = _nomes(montada)
    for degrau, (estrategia, espera, rotulo) in enumerate(plano, start=1):
        if degrau > 1:
            try:
                janela, montada = _reler(janela, PROFUNDA, TETO_FUNDO)
            except PassoError:
                montada = None
            if montada is not None and not _leitura_boa(montada):
                # A leitura caiu depois do clique: é o Chrome que parou de
                # publicar (janela atrás), não o painel que não abriu.
                janela, montada = _acordar_leitura(janela, montada, avisar=True)
            if montada is not None and chave_web.e_dialogo_de_criacao(montada):
                break
            if montada is None or not chave_web.procurar(montada, chave_web.PADROES_CRIAR):
                break
            if referencia and _nomes(montada) * 2 < referencia:
                # Leitura que despencou: não se sabe o que há na tela, e repetir
                # poderia abrir um painel em cima do outro.
                print("     a leitura despencou — não repito o clique sem saber o que está na tela.")
                break
        if degrau == 1:
            try:
                janela, botao, montada = _achar_elemento(
                    janela,
                    chave_web.PADROES_CRIAR,
                    alvo=args.alvo,
                    rotulo="o botão “New key”",
                )
            except PassoError as exc:
                print(f"  1. NÃO DEI: {exc}")
                print("     A página pode estar ainda carregando, ou o botão mudou de nome.")
                print("     Se ele está na tela, clique nele e rode `--pegar`.")
                return None
        else:
            achados = chave_web.procurar(montada, chave_web.PADROES_CRIAR) if montada else []
            if not achados:
                print("  1. NÃO DEI: o botão de criar não está na árvore desta janela.")
                return None
            botao = achados[0]
        if estrategia == "mouse" and not _garantir_na_frente(janela):
            print("     não consegui pôr a janela na frente — o clique pode só ativá-la.")
            cliques.append("janela não veio para a frente")
        print(f"  1. clicando em “{botao.get('nome')}” ({rotulo})…")
        try:
            feito = _clicar(
                janela,
                botao,
                mouse=mouse,
                primeiro_mouse=(estrategia == "mouse"),
            )
            print(f"     {_descrever_clique(feito)}")
            cliques.append(f"{rotulo}: {_descrever_clique(feito)}")
        except PassoError as exc:
            # Clique **recusado** é outra coisa de clique que não abriu nada: o
            # Windows disse não (janela coberta, ponto fora). Repetir do mesmo
            # jeito não muda a resposta — para aqui e diz o motivo, como desde
            # a 0.91.10.
            print(f"  1. NÃO DEI: {exc}")
            cliques.append(f"{rotulo}: {exc}")
            _gravar_relatorio(janela, extra=[f"clique {item}" for item in cliques])
            return None
        time.sleep(1.2)

        # 2. o diálogo inteiro: nome, expiração e limite de crédito.
        #    Medido na tela do dono: sem a expiração (que tem asterisco) o botão
        #    “Create” fica desabilitado, e clicar nele não cria nada.
        try:
            janela, montada = _esperar_dialogo(args, janela, segundos=espera, avisar=(degrau == 1))
            break
        except PassoError as exc:
            falha = exc
            continue
    if falha is not None and (montada is None or not chave_web.e_dialogo_de_criacao(montada)):
        # Sem o diálogo não há o que preencher: seguir daqui faria o passo 3
        # achar o botão “New key” da página e clicar nele outra vez, e o
        # relatório diria “criei” sem ter criado nada.
        # O relatório é reescrito com a escada de cliques dentro (o recado do
        # arquivo já vem na mensagem de `falha`).
        _gravar_relatorio(janela, extra=[f"clique {item}" for item in cliques])
        print(f"  2. NÃO DEI: {falha}")
        if montada is None or not _leitura_boa(montada):
            # Honestidade: aqui o problema foi **ver** a página, não clicar.
            print("     Nada foi criado. E o defeito não foi o clique: eu NÃO consegui ver a")
            print("     página do Chrome — a leitura trouxe só a moldura. Deixe a janela do")
            print("     Chrome na frente (não minimizada, nada por cima dela) e rode de novo;")
            print("     se o painel estiver aberto na sua tela, rode `--pegar`.")
            print("     Se repetir, rode diagnostico-chave.bat e me mande o chave-leitura.txt:")
        else:
            print("     Nada foi criado. O clique não abriu o painel — isso não é mais leitura:")
            print("     a página foi lida inteira e o botão estava nela. Feche o que estiver na")
            print("     frente do Chrome (eu coloco a janela na frente, mas o Windows recusa")
            print("     enquanto outro programa tem o foco) e rode de novo.")
        return None
    print("  2. preenchendo o diálogo:")
    montada, preenchidos = _preencher_dialogo(
        janela, montada, nome, mouse=mouse, primeiro_mouse=primeiro_mouse
    )
    antes = _nomes(montada)
    # O nome entra na conta: sem ele o “Create” também fica apagado, e a
    # mensagem tem de dizer **qual** campo faltou.
    faltando = [campo for campo in ("nome", "expiração", "limite") if campo not in preenchidos]
    if "expiração" in faltando:
        print("     AVISO: sem a expiração o botão Create costuma ficar apagado.")
        print("     Se a chave não nascer, escolha a expiração você mesmo e rode `--pegar`.")

    # 3. o botão do diálogo (“Create”, curto) — e a conferência de que fechou
    try:
        janela, criar, montada = _esperar_botao_criar(janela, segundos=8)
        if not criar.get("acionavel"):
            # Botão apagado = os três campos não estão preenchidos. Clicar nele
            # não gera erro e não cria nada; o script já fez isso duas vezes e
            # o dono ficou olhando uma tela parada. Aqui ele para e diz o que
            # falta, em vez de esperar o milagre.
            print("  3. o botão “Create” está APAGADO — clicar nele não criaria nada.")
            if faltando:
                print(f"     campos que eu não consegui preencher: {', '.join(faltando)}.")
            else:
                print("     os três campos parecem preenchidos; o site pode exigir algo a mais.")
            _gravar_relatorio(janela, extra=["o botão Create estava desativado (desativado=True na leitura)"])
            print("     Complete no navegador e rode `--pegar`; não precisa refazer o resto.")
            return None
        print(f"  3. clicando em “{criar.get('nome')}” para criar…")
        print(f"     {_descrever_clique(_clicar(janela, criar, mouse=mouse, primeiro_mouse=primeiro_mouse))}")
        time.sleep(2.0)
    except PassoError as exc:
        print(f"  3. NÃO DEI: {exc}")
        print("  A chave pode ter ficado criada e não copiada. Veja no navegador.")
        return None

    # O clique pode ter caído num botão desabilitado: isso não gera erro, o
    # diálogo simplesmente continua aberto. Conferir é o que separa “criei” de
    # “achei que criei”.
    try:
        _janela, depois = _reler(janela, PROFUNDA, TETO_FUNDO)
    except PassoError:
        depois = None
    # Leitura que despencou não prova nada sobre o painel: se antes vinham 43
    # elementos e agora vêm 3, o que falhou foi a leitura — não o clique. Nesse
    # caso não se conclui nem “criou” nem “não criou”: segue para a cópia, e a
    # cópia é quem diz a verdade (chave na área = criou).
    if depois is not None and _nomes(depois) < LEITURA_POBRE and _nomes(depois) * 2 < antes:
        print("  3. a leitura despencou agora; não dá para conferir pelo painel — vou pela cópia.")
        depois = None
    if depois and chave_web.e_dialogo_de_criacao(depois):
        print("  3. o diálogo CONTINUA aberto — a chave não foi criada.")
        if faltando:
            print(f"     campos que eu não consegui preencher: {', '.join(faltando)}.")
        print("     Complete no navegador e rode `--pegar`; não precisa refazer nada.")
        return None

    # 4. copiar — primeiro o texto da página (não depende de botão nenhum),
    #    depois o botão “Copy”, se ele existir.
    #
    # `anterior` vem de **antes do primeiro clique**: se for lido aqui, o texto
    # que o próprio clique em “Create” pôs na área já seria confundido com “o
    # que estava lá”, e a chave nova seria recusada por ser igual à nova.
    copiou = False
    if _copiar_pela_pagina(janela):
        print("  4. copiando o texto da página (Ctrl+A, Ctrl+C)…")
        copiou = True
    else:
        print("  4. não consegui copiar pela página — tentando o botão “Copy”…")
    if copiou:
        achado = _esperar_chave(modulo, anterior, segundos=6)
        if achado:
            return achado[1]
    try:
        janela, copiar, _ = _esperar_elemento(janela, chave_web.PADROES_COPIAR, segundos=6)
        print(f"     clicando em “{copiar.get('nome')}”…")
        print(f"     {_descrever_clique(_clicar(janela, copiar, mouse=mouse, primeiro_mouse=primeiro_mouse))}")
    except PassoError as exc:
        print(f"  4. NÃO DEI: {exc}")
        return None
    achado = _esperar_chave(modulo, anterior, segundos=10)
    return achado[1] if achado else None


def passo_criar(args) -> int:
    """Cria uma chave nova: clica, nomeia, cria e copia. Gated por --autorizar."""
    from server import chave_web

    _tomar_o_sinal()
    janela, montada = _ler_janela(args.alvo)
    estado = chave_web.onde_estou(montada, conta=getattr(args, "conta", ""))
    print(chave_web.texto_do_estado(estado))
    dados = chave_web.diagnostico(montada)
    print(chave_web.texto_do_diagnostico(dados))
    print()
    if estado["estado"] in (chave_web.ESTADO_LOGIN, chave_web.ESTADO_GOOGLE):
        print("  Estou numa página de login, não na das chaves — `--criar` não entra sozinho.")
        print("  Use `--auto --autorizar`, que atravessa o login e só então cria.")
        return 1
    if not dados["pode_criar"]:
        print("  Parei aqui: sem o botão de criar na árvore, não há o que clicar.")
        print("  Caminho que funciona sempre: crie no navegador e rode `--pegar`.")
        return 1
    if not args.autorizar:
        print("  Isto VAI CRIAR uma chave nova na sua conta (é uma credencial de verdade).")
        print("  Repita com --autorizar para fazer.")
        return 0

    modulo = _modulo_do_configurador()
    mouse = not args.sem_mouse
    if args.mouse and args.sem_mouse:
        print("  Escolha um: --mouse ou --sem-mouse (os dois juntos não dizem nada).")
        return 2
    _explicar_mouse(mouse, dados)
    print()

    chave = _criar_e_copiar(
        args,
        modulo,
        janela,
        montada,
        dados,
        mouse=mouse,
        primeiro_mouse=mouse,
        anterior=_texto_da_area(),
    )
    if not chave:
        print("\n  Não consegui a chave. Se ela está na tela, clique em COPIAR e rode `--pegar`.")
        return 1
    return _gravar(modulo, chave)


def _explicar_mouse(mouse: bool, dados: dict) -> None:
    if mouse:
        print("  Vou clicar com o mouse nos botões medidos; o cursor volta para onde estava.")
        if not dados.get("pode_clicar_com_mouse"):
            print("  (sem posição medida na leitura, o clique será pela ação do elemento.)")
    else:
        print("  --sem-mouse: só a ação do elemento, o ponteiro não se mexe.")


def passo_auto(args) -> int:
    """O caminho inteiro num comando: abrir → criar → copiar → gravar.

    É o que o dono pediu na 0.91.12: “ele deve abrir os sites onde estão as
    chaves para ele poder copiar e colar na própria pasta”.

    Três coisas que fazem este modo ser honesto:

    - se a criação automática não der, ele **não desiste**: deixa a página
      aberta, diz o que falta clicar e fica esperando a área de transferência;
    - nada é criado sem `--autorizar`;
    - o que já estava copiado antes não é confundido com a chave nova.
    """
    from server import chave_web

    if not args.autorizar:
        print("  Isto VAI CRIAR uma chave nova na sua conta e gravar no .env.")
        print("  Repita com --autorizar para fazer.")
        return 0

    modulo = _modulo_do_configurador()
    provedor, base = _provedor_do_env(modulo)
    provedor = args.provedor or provedor
    if not provedor:
        print("  Não sei qual provedor: o .env não tem nenhum e você não passou --provedor.")
        return 1
    guia = modulo.guia_do_provedor(provedor, base)
    if not guia.get("onde"):
        print(f"  Não sei onde ficam as chaves do provedor “{provedor}”.")
        return 1

    _tomar_o_sinal()
    anterior = _texto_da_area()
    print(f"  Provedor: {guia['nome']}")
    print(f"  Página das chaves: {guia['onde']}")
    if _chave_no_texto(modulo, anterior):
        print("  (havia uma chave copiada antes; ela não vai ser confundida com a nova.)")
    print()
    print("  1. abrindo a página no seu navegador…")
    if not modulo.abrir_no_navegador(guia["onde"]):
        print(f"  NÃO DEI: não consegui abrir o navegador. Abra na mão: {guia['onde']}")
        return 1

    conta = (args.conta or _conta_do_env(modulo)).strip()
    if conta:
        print(f"  Conta do Google: {conta}")
    print()

    chave = ""
    try:
        janela, montada = _levar_ate_as_chaves(args, conta=conta)
        if args.conta:
            for item in chave_web.contas_visiveis(montada):
                if chave_web.casar_conta([item], args.conta):
                    _guardar_conta(modulo, item["email"])
                    break
        dados = chave_web.diagnostico(montada)
        if not dados["pode_criar"]:
            # A página pode ter sido lida ainda carregando: o `_levar_ate_as_chaves`
            # devolve a última leitura que fez, e ela pode ser a de uma página em
            # construção. Medido no PC do dono (0.91.20): o botão estava na tela e
            # a leitura não o trouxe. Antes de desistir da criação automática,
            # espera a página sossegar e lê de novo — fundo.
            janela, montada = _esperar_pagina_pronta(args, janela, montada)
            try:
                janela, montada = _reler(janela, PROFUNDA, TETO_FUNDO)
            except PassoError:
                pass
            dados = chave_web.diagnostico(montada)
        if dados["pode_criar"]:
            # A janela é trazida para a frente antes de qualquer clique: o
            # clique físico acerta o que está por cima, e por cima pode estar
            # qualquer coisa do dono.
            from server import arvore_windows

            arvore_windows.trazer_para_frente(int(janela["handle"]))
            print("  2. página aberta. Vou criar a chave sozinho…")
            print()
            mouse = not args.sem_mouse
            _explicar_mouse(mouse, dados)
            chave = _criar_e_copiar(
                args,
                modulo,
                janela,
                montada,
                dados,
                mouse=mouse,
                primeiro_mouse=mouse,
                anterior=anterior,
            ) or ""
        else:
            print("  2. cheguei na página, mas os botões não estão na árvore de acessibilidade.")
            print("     Então eu não clico: eu espero você clicar.")
    except PassoError as exc:
        print(f"  2. NÃO DEI: {exc}")

    if not chave:
        # Plano B, no mesmo comando: o dono clica, o JARVIS lê.
        print()
        print("  No site, com a sua conta:")
        print("     Create Key → dê um nome → Create → clique no botão COPIAR")
        print()
        print(f"  Estou olhando a área de transferência por {int(args.espera_colar)}s…")
        achado = _esperar_chave(modulo, anterior, segundos=args.espera_colar, avisar=True)
        if not achado:
            print("  NÃO DEU: nada novo apareceu na área de transferência.")
            print("  Copie a chave pelo botão e rode `--pegar` — não precisa refazer o resto.")
            return 1
        chave = achado[1]

    print()
    print(f"  Chave na mão: {modulo.mascarar(chave)}")
    return _gravar(modulo, chave)


# ---------------------------------------------------------------------------
# O caminho pelo protocolo do Chrome (0.91.27)
# ---------------------------------------------------------------------------
# Doze versões tentaram ler a página pela árvore de acessibilidade do Windows.
# O diagnóstico de 16/11 mostrou a mesma janela passando de 85 elementos para 3
# em segundos — e nem o sinal de leitor de tela segurou. Aqui não se lê tela:
# pergunta-se à própria página quais são os elementos, pelo DevTools Protocol.
#
# Uma função só, injetada na página. Ela não sabe de OpenRouter: recebe uma
# ordem e devolve o que a página respondeu.
_CDP_AJUDA = r"""
window.__JARVIS = function (op, a, b) {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const visivel = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const estilo = getComputedStyle(el);
    return estilo.visibility !== 'hidden' && estilo.display !== 'none';
  };
  const clicaveis = () => [...document.querySelectorAll(
    'button, a, [role="button"], [role="option"], [role="menuitem"], [role="combobox"]'
  )].filter(visivel);
  const painel = () => document.querySelector('[role="dialog"], [role="alertdialog"]');

  if (op === 'pronta') {
    const texto = norm(document.body.innerText);
    return {
      url: location.href,
      texto: texto.slice(0, 4000),
      tem_painel: !!painel(),
      carregando: document.readyState !== 'complete',
    };
  }
  if (op === 'texto') {
    const alvo = painel() || document.body;
    return (alvo.innerText || '').slice(0, 6000);
  }
  if (op === 'clicar') {
    const alvo = norm(a);
    const lista = clicaveis();
    const achado = lista.find((el) => norm(el.innerText) === alvo)
      || lista.find((el) => norm(el.innerText).startsWith(alvo))
      || lista.find((el) => norm(el.innerText).includes(alvo));
    if (!achado) return false;
    achado.scrollIntoView({ block: 'center' });
    achado.click();
    return true;
  }
  if (op === 'opcoes') {
    return clicaveis()
      .filter((el) => el.getAttribute('role') === 'option' || el.hasAttribute('data-radix-collection-item'))
      .map((el) => (el.innerText || '').replace(/\s+/g, ' ').trim())
      .filter(Boolean);
  }
  if (op === 'select') {
    const alvo = norm(a);
    for (const sel of document.querySelectorAll('select')) {
      if (!visivel(sel)) continue;
      const opcao = [...sel.options].find((o) => norm(o.text) === alvo || norm(o.text).includes(alvo));
      if (!opcao) continue;
      sel.value = opcao.value;
      sel.dispatchEvent(new Event('input', { bubbles: true }));
      sel.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    }
    return false;
  }
  if (op === 'digitar') {
    const onde = painel() || document;
    const campos = [...onde.querySelectorAll('input, textarea')].filter(visivel);
    if (!campos.length) return false;
    const campo = campos.find((el) => /name|nome/i.test(el.name || el.id || '')) || campos[0];
    const prototipo = campo.tagName === 'TEXTAREA'
      ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
    const definir = Object.getOwnPropertyDescriptor(prototipo, 'value').set;
    campo.focus();
    definir.call(campo, '');
    campo.dispatchEvent(new Event('input', { bubbles: true }));
    definir.call(campo, b);
    campo.dispatchEvent(new Event('input', { bubbles: true }));
    campo.dispatchEvent(new Event('change', { bubbles: true }));
    return campo.value === b;
  }
  if (op === 'chave') {
    // A chave pode estar no texto da página, num campo somente-leitura ou num
    // atributo. O padrão exige os 64 hex: chave mascarada (“sk-or-v1-…abc”)
    // não casa, e é bom que não case.
    const padrao = /sk-or-v1-[0-9a-f]{64}/;
    const noTexto = (document.body.innerText || '').match(padrao);
    if (noTexto) return noTexto[0];
    for (const el of document.querySelectorAll('input, textarea, code, span')) {
      const valor = el.value || el.textContent || '';
      const achado = String(valor).match(padrao);
      if (achado) return achado[0];
    }
    const noHtml = (document.body.innerHTML || '').match(padrao);
    return noHtml ? noHtml[0] : '';
  }
  return null;
};
true;
"""


# Quanto esperar, em segundos. Ficam aqui para o teste poder encurtar: com
# espera cheia, a suíte passaria minutos parada esperando uma página que o
# dublê já respondeu.
ESPERA_PAINEL_CDP = 15.0
ESPERA_CHAVE_CDP = 20.0
# 0.91.28 — no PC do dono a página de entrada do OpenRouter demorou para
# carregar (print de 16/11 11:57: aba aberta, cartão branco vazio). Desistir em
# 25 s transformava lentidão em “não deu”. Agora: até 90 s carregando, com
# aviso a cada 10 s, e — se cair na tela de entrada — até 5 minutos esperando o
# dono entrar, em vez de mandar rodar tudo de novo.
ESPERA_CARREGAR_CDP = 90.0
ESPERA_LOGIN_CDP = 300.0
# De quanto em quanto se pergunta à aba “e agora?”. Zero só nos testes.
PASSO_CDP = 0.5


def _cdp_chamar(sessao, op: str, *argumentos):
    """Chama a função injetada com uma ordem e os argumentos em JSON."""
    import json as _json

    partes = [_json.dumps(op)] + [_json.dumps(item) for item in argumentos]
    return sessao.javascript(f"window.__JARVIS({', '.join(partes)})")


def _cdp_abrir_sessao(args, avisar=True):
    """A sessão de controle com a página do provedor. `None` quando não há porta."""
    from server import chrome_cdp

    porta = int(getattr(args, "porta", 0) or chrome_cdp.PORTA_PADRAO)
    if not chrome_cdp.porta_aberta(porta):
        return None, ""
    pagina = chrome_cdp.achar_alvo(porta, "openrouter", segundos=2.0) or chrome_cdp.achar_alvo(
        porta, "", segundos=0.5
    )
    if pagina is None:
        return None, ""
    try:
        sessao = chrome_cdp.Sessao(pagina)
        sessao.javascript(_CDP_AJUDA)
    except Exception as exc:  # noqa: BLE001 - CDP é de terceiros: nunca derrubar
        if avisar:
            print(f"  não consegui falar com o Chrome pelo protocolo ({exc}).")
        return None, ""
    return sessao, str(pagina.get("url") or "")


def _cdp_estado(sessao) -> dict | None:
    """O estado da aba agora — `None` quando a conexão falhou (a aba pode estar navegando)."""
    try:
        estado = _cdp_chamar(sessao, "pronta")
    except Exception:  # noqa: BLE001 - navegação derruba a conexão de vez em quando
        return None
    return estado if isinstance(estado, dict) else {}


def _e_a_pagina_de_chaves(estado: dict) -> bool:
    """A aba está na página das chaves, e não na tela de entrada?"""
    texto = estado.get("texto") or ""
    if "sign in" in texto or "log in" in texto:
        return False
    if "api keys" in texto:
        return True
    endereco = str(estado.get("url") or "")
    return "/settings/keys" in endereco and "new key" in texto


def _e_a_tela_de_entrada(estado: dict) -> bool:
    """A aba está pedindo para entrar (a janela do JARVIS é nova)."""
    texto = estado.get("texto") or ""
    endereco = str(estado.get("url") or "")
    if "/sign-in" in endereco or "/login" in endereco:
        return True
    return "sign in" in texto or "log in" in texto


def _cdp_reconectar(sessao, args) -> bool:
    """Refaz a conexão com a mesma aba. `False` quando não dá."""
    if not hasattr(sessao, "reconectar"):
        return False
    from server import chrome_cdp

    porta = int(getattr(args, "porta", 0) or chrome_cdp.PORTA_PADRAO)
    pagina = chrome_cdp.achar_alvo(porta, "openrouter", segundos=1.0) or chrome_cdp.achar_alvo(
        porta, "", segundos=0.5
    )
    if pagina is None:
        return False
    try:
        sessao.reconectar(pagina)
    except Exception:  # noqa: BLE001 - sem reconexão a gente só continua tentando
        return False
    print("     (a conexão com a aba caiu e foi refeita — continuando)")
    return True


def _esperar_carregar(sessao, args, guia) -> dict | None:
    """Espera a aba sair do “carregando”. Devolve o estado decisivo, ou `None`.

    Devolve assim que a página das chaves **ou** a tela de entrada aparecem.
    `None` quer dizer que a página não terminou de carregar no tempo dado — e
    aí o programa diz o que fazer, em vez de mandar o dono adivinhar.
    """
    limite = float(getattr(args, "espera_carregar", 0) or ESPERA_CARREGAR_CDP)
    inicio = time.time()
    proximo_aviso = inicio + 10.0
    estado: dict | None = None
    falhas = 0
    vazio_desde: float | None = None
    while True:
        novo = _cdp_estado(sessao)
        if novo is None:
            falhas += 1
            if falhas >= 5 and _cdp_reconectar(sessao, args):
                falhas = 0
        else:
            estado, falhas = novo, 0
            if _e_a_pagina_de_chaves(estado) or _e_a_tela_de_entrada(estado):
                return estado
            if estado.get("texto"):
                vazio_desde = None
            elif vazio_desde is None:
                vazio_desde = time.time()
        agora = time.time()
        if agora - inicio >= limite:
            print()
            print(f"  NÃO DEI: a página do OpenRouter não terminou de carregar em {int(limite)} s.")
            if vazio_desde is not None and agora - vazio_desde >= 20:
                print("  A aba está aberta, mas vazia — ela não chegou a desenhar a página.")
                print("  Quase sempre é internet lenta ou a própria página travada.")
            print("  O que fazer: na janela do JARVIS, aperte F5 e rode o chrome-cdp.bat")
            print("  de novo. Ele aproveita a janela que já está aberta — não precisa")
            print("  entrar de novo.")
            print(f"  (endereço da aba: {guia.get('onde') or 'openrouter.ai/settings/keys'})")
            return None
        if agora >= proximo_aviso:
            print(f"     … ainda carregando ({int(agora - inicio)} s de {int(limite)} s).")
            proximo_aviso = agora + 10.0
        time.sleep(PASSO_CDP)


def _esperar_entrada(sessao, args) -> bool:
    """Espera o dono entrar na janela nova. `True` quando a página das chaves vem."""
    limite = float(getattr(args, "espera_login", 0) or ESPERA_LOGIN_CDP)
    print()
    print("  Esta janela é nova e ainda não tem a sua conta — é assim na primeira vez.")
    print("  Clique em “Sign In” aqui mesmo, na janela do JARVIS, e entre com a mesma")
    print("  conta que você usa no OpenRouter. Eu espero e sigo sozinho quando a")
    print("  página das chaves aparecer.")
    print(f"  (espero até {int(limite)} s — não precisa apertar nada nesta janela preta)")
    print()
    inicio = time.time()
    proximo_aviso = inicio + 15.0
    falhas = 0
    while True:
        estado = _cdp_estado(sessao)
        if estado is None:
            falhas += 1
            if falhas >= 5 and _cdp_reconectar(sessao, args):
                falhas = 0
        else:
            falhas = 0
            if _e_a_pagina_de_chaves(estado):
                print("  Entrou — a página das chaves apareceu. Continuando daqui.")
                return True
        agora = time.time()
        if agora - inicio >= limite:
            print()
            print(f"  NÃO DEI: passaram {int(limite)} s e a página das chaves não apareceu.")
            print("  Se você entrou agora (ou vai entrar), é só rodar o chrome-cdp.bat")
            print("  outra vez: a janela é a mesma e o login fica guardado.")
            return False
        if agora >= proximo_aviso:
            print(f"     … esperando o login ({int(agora - inicio)} s de {int(limite)} s).")
            proximo_aviso = agora + 15.0
        time.sleep(PASSO_CDP)


def _cdp_abrir_a_pagina(sessao, args, guia) -> bool:
    """A aba está pronta para trabalhar? Carrega, espera login se preciso."""
    print("  Esperando a página do OpenRouter terminar de abrir…")
    estado = _esperar_carregar(sessao, args, guia)
    if estado is None:
        return False
    if _e_a_pagina_de_chaves(estado):
        return True
    return _esperar_entrada(sessao, args)


def _cdp_esperar(sessao, condicao, segundos: float, passo: float = 0.5):
    """Espera a página satisfazer `condicao(estado)`. Devolve o último estado."""
    fim = time.time() + segundos
    estado = {}
    while True:
        try:
            estado = _cdp_chamar(sessao, "pronta") or {}
        except Exception:  # noqa: BLE001 - a aba pode estar navegando
            estado = {}
        if condicao(estado):
            return estado
        if time.time() >= fim:
            return estado
        time.sleep(passo)


def _cdp_preencher_painel(sessao, nome: str) -> list[str]:
    """Os três campos do painel: nome, expiração e limite. Devolve o que ficou."""
    feitos: list[str] = []

    if _cdp_chamar(sessao, "digitar", "nome", nome):
        feitos.append("nome")
        print(f"     nome: {nome!r} digitado na caixa do painel.")
    else:
        print("     nome: não achei a caixa de texto do painel.")

    # Expiração e limite: cada um tem um campo que abre uma lista.
    for campo, rotulos, escolhida in (
        (
            "expiração",
            ("Select expiration", "Expiration", "Select an expiration"),
            "No expiration",
        ),
        (
            "limite",
            ("Choose a credit limit", "Credit limit", "Choose a limit"),
            "No limit",
        ),
    ):
        # Um <select> de verdade se resolve sem abrir nada.
        if _cdp_chamar(sessao, "select", escolhida):
            feitos.append(campo)
            print(f"     {campo}: “{escolhida}” escolhido direto no campo.")
            continue
        aberto = False
        for texto in rotulos:
            if _cdp_chamar(sessao, "clicar", texto):
                aberto = True
                break
        if not aberto:
            print(f"     {campo}: não achei a lista na tela.")
            continue
        lista: list[str] = []
        fim = time.time() + 5.0
        while time.time() < fim:
            lista = _cdp_chamar(sessao, "opcoes") or []
            if lista:
                break
            time.sleep(0.3)
        if not lista:
            print(f"     {campo}: a lista abriu e não mostrou opção nenhuma.")
            continue
        escolha = _escolha_da_lista(campo, lista)
        if not escolha:
            print(f"     {campo}: nenhuma opção serve ({', '.join(lista[:6])}).")
            continue
        if _cdp_chamar(sessao, "clicar", escolha):
            feitos.append(campo)
            print(f"     {campo}: escolhendo “{escolha}”.")
        else:
            print(f"     {campo}: não consegui clicar em “{escolha}”.")
    return feitos


def _escolha_da_lista(campo: str, lista: list[str]) -> str | None:
    """Qual opção escolher — a mesma regra do painel lido pela árvore."""
    from server import chave_web

    if campo == "expiração":
        return chave_web.melhor_expiracao(lista)
    # Uma lista de limite não tem opção de expiração — mas se a página devolver
    # as duas coisas na mesma lista, escolher “No expiration” como limite
    # deixaria o campo sem valor e o “Create” apagado.
    so_limite = [opcao for opcao in lista if "expir" not in chave_web.normalizar(opcao)]
    return chave_web.melhor_limite(so_limite, aceitar_maior=True)


def passo_cdp(args) -> int:
    """Cria a chave pelo protocolo do Chrome — sem ler a tela, sem adivinhar.

    Exige o Chrome aberto pelo `chrome-cdp.bat` (porta de depuração ligada).
    De verdade aqui: a página, pelos olhos dela mesma (`document`), e a escrita
    do `.env`. Nada de árvore de acessibilidade, nada de área de transferência.
    """
    from server import chrome_cdp

    porta = int(getattr(args, "porta", 0) or chrome_cdp.PORTA_PADRAO)
    if not chrome_cdp.porta_aberta(porta):
        print("  NÃO DEI: o Chrome não está com a porta de controle aberta.")
        print("  Rode o `chrome-cdp.bat` — ele abre o Chrome já preparado e chama")
        print(f"  este comando de novo. (porta {porta}, só no seu computador)")
        return 1
    sessao, endereco = _cdp_abrir_sessao(args)
    if sessao is None:
        print(f"  NÃO DEI: a porta {porta} está aberta, mas não achei uma aba para controlar.")
        print("  Deixe a página do OpenRouter aberta na janela do JARVIS e rode de novo.")
        return 1
    print(f"  Página: {endereco}")
    print("  Lendo pelo protocolo do Chrome (nada de tela, nada de mouse).")
    try:
        return _cdp_fluxo(args, sessao)
    finally:
        sessao.fechar()


def _cdp_fluxo(args, sessao) -> int:
    from server import chave_web

    modulo = _modulo_do_configurador()
    provedor, base = _provedor_do_env(modulo)
    provedor = args.provedor or provedor
    guia = modulo.guia_do_provedor(provedor or "openrouter", base)

    if not _cdp_abrir_a_pagina(sessao, args, guia):
        return 1
    print("  1. página de chaves aberta.")
    if not getattr(args, "autorizar", False):
        print("\n  Sem --autorizar eu só olhei: nada foi clicado, nada foi criado.")
        print("  O `chrome-cdp.bat` já chama este comando com a autorização.")
        return 1

    if not any(_cdp_chamar(sessao, "clicar", texto) for texto in ("New key", "Create key", "Create Key", "Create API key")):
        print("  NÃO DEI: não achei o botão “New key” na página.")
        return 1
    print("  2. cliquei em “New key”.")

    estado = _cdp_esperar(sessao, lambda item: bool(item.get("tem_painel")), ESPERA_PAINEL_CDP)
    if not estado.get("tem_painel"):
        print("  NÃO DEI: o painel “Create API key” não abriu depois do clique.")
        return 1
    print("  3. painel aberto:")
    nome = (args.nome or "").strip() or chave_web.nome_sugerido()
    _cdp_preencher_painel(sessao, nome)

    if not _cdp_chamar(sessao, "clicar", "Create"):
        print("  NÃO DEI: não achei o botão “Create” no painel.")
        return 1
    print("  4. cliquei em “Create”; esperando a chave aparecer na página…")
    chave = ""
    fim = time.time() + ESPERA_CHAVE_CDP
    while True:
        # Olha antes de esperar: com a página já respondida, esperar seria
        # atraso puro — e com espera zero o laço `while time()<fim` nem rodava.
        chave = str(_cdp_chamar(sessao, "chave") or "")
        if chave or time.time() >= fim:
            break
        time.sleep(0.5)
    if not chave:
        print("  NÃO DEI: a chave não apareceu no texto da página.")
        print("  Veja a aba do Chrome: se o botão “Create” estiver apagado, falta campo.")
        return 1
    print(f"  5. chave na mão: {modulo.mascarar(chave)}")
    return _gravar(modulo, chave)


# ---------------------------------------------------------------------------
# Pela porta do OpenRouter: sem navegador nenhum (0.91.29)
# ---------------------------------------------------------------------------
# O Chrome do JARVIS é um perfil novo, sem cache: no PC do dono a página demora.
# Esperar 90 s funciona, mas é ruim. Com a chave de gestão, criar uma chave é um
# `POST` e uma resposta — leva um segundo e não depende de janela nenhuma.


def _texto_do_env(modulo) -> str:
    return modulo.ler_texto(modulo.ENV) if modulo.ENV.is_file() else modulo.texto_base()


def _gestao_do_env(modulo) -> str:
    return (modulo.ler_valor(_texto_do_env(modulo), GESTAO_OPENROUTER) or "").strip()


def passo_api(args) -> int:
    """Cria a chave pelo `POST /api/v1/keys`. Sem Chrome, sem tela, sem espera."""
    from server import chave_web, openrouter_api

    modulo = _modulo_do_configurador()
    gestao = _gestao_do_env(modulo)
    if not gestao:
        print("  NÃO DEI: falta a chave de gestão do OpenRouter no .env.")
        print("  Rode o `chave-pela-api.bat`: ele abre a página certa uma vez e")
        print("  guarda essa chave. Depois disso, criar chave aqui leva 1 segundo.")
        return 1

    nome = (args.nome or "").strip() or chave_web.nome_sugerido()
    if not getattr(args, "autorizar", False):
        print("  Sem --autorizar eu só olho: nada é criado.")
        print(f"  Seria criada uma chave chamada {nome!r}, sem limite e sem validade.")
        return 1

    print(f"  Criando a chave {nome!r} no OpenRouter (direto pela API, sem navegador)…")
    try:
        chave = openrouter_api.criar_chave(gestao, nome)
    except openrouter_api.OpenRouterError as exc:
        print(f"  NÃO DEI: {exc}")
        return 1
    print(f"  Chave criada: {modulo.mascarar(chave)}")
    codigo = _gravar(modulo, chave)
    if codigo == 0:
        _conferir_a_chave(modulo, chave)
    return codigo


def _conferir_a_chave(modulo, chave: str) -> None:
    """Pergunta ao OpenRouter se a chave responde — leitura, não gasta crédito.

    Gravar não é provar. O dono já ficou com “chave gravada” e o JARVIS
    recusando por falta de crédito (ou por modelo que não é `:free`) — e a
    mensagem dele culpava o modelo, longe da causa. Aqui a resposta sai na
    mesma tela em que a chave foi criada.
    """
    from server import openrouter_api

    print("  Conferindo com o OpenRouter se a chave responde…")
    estado = openrouter_api.estado_da_chave(chave)
    if not estado:
        print("  Não deu para conferir agora (sem resposta do site).")
        print("  A chave recém-criada costuma valer na hora; se o JARVIS recusar,")
        print("  rode: .venv\\Scripts\\python conferir-ia.py --testar")
        return
    print("  A chave respondeu — ela é válida.")
    resumo = openrouter_api.resumo_da_chave(estado)
    if resumo:
        print(f"  {resumo}")

    # Conta gratuita com modelo pago no .env é a próxima pedra do caminho:
    # o JARVIS abre, aceita a chave, e erra na primeira resposta.
    modelo = ""
    try:
        texto = _texto_do_env(modulo)
        modelo = (modulo.ler_valor(texto, "JARVIS_AI_MODEL") or "").strip()
    except Exception:  # noqa: BLE001 - ler o .env é um extra
        modelo = ""
    if estado.get("is_free_tier") and modelo and not modelo.endswith(":free"):
        print()
        print(f"  ATENÇÃO: a conta é gratuita e o modelo gravado é “{modelo}”,")
        print("  que é pago. Na sua conta, só os modelos terminados em :free")
        print("  respondem — os outros dão erro de crédito.")
        print("  Troque no cartão Modelos de IA (ou no .env, JARVIS_AI_MODEL).")
        print("  Para ver quais existem hoje: .venv\\Scripts\\python conferir-ia.py")


def passo_gestao(args) -> int:
    """Guarda a chave de gestão copiada no site — uma vez na vida.

    A chave de gestão tem o mesmo formato de uma chave comum. Por isso ela é
    **verificada** antes de ser gravada (lendo a lista de chaves, que só uma
    chave de gestão pode fazer): gravar uma chave comum aqui só daria erro na
    próxima vez, com a mensagem errada.
    """
    from server import openrouter_api

    modulo = _modulo_do_configurador()
    texto = _texto_do_env(modulo)
    atual = (modulo.ler_valor(texto, GESTAO_OPENROUTER) or "").strip()
    if atual:
        print(f"  A chave de gestão já está guardada: {modulo.mascarar(atual)}")
        print("  Se quiser trocar, apague a linha JARVIS_OPENROUTER_GESTAO do .env.")
        return 0

    print("  Cole a chave de gestão na área de transferência (botão COPIAR do site).")
    print("  Eu leio o que mudar nela — não precisa colar aqui na janela.")
    print()
    anterior = _texto_da_area()
    espera = float(getattr(args, "espera_colar", 0) or 120.0)
    resultado = _esperar_chave(modulo, anterior, segundos=espera, avisar=True)
    if resultado is None:
        print("  NÃO DEI: não apareceu chave nova na área de transferência.")
        print("  No site, clique em COPIAR na chave de gestão e rode de novo.")
        return 1
    _, chave = resultado
    print(f"  Chave recebida: {modulo.mascarar(chave)}")
    print("  Conferindo no OpenRouter se ela pode criar chaves…")
    ok, motivo = openrouter_api.chave_de_gestao_vale(chave)
    if not ok:
        print(f"  NÃO DEI: {motivo}")
        print("  Abra openrouter.ai/settings/management-keys e copie a chave de lá")
        print("  (não a chave comum, que fica em /settings/keys).")
        return 1
    texto = modulo.definir(texto, GESTAO_OPENROUTER, chave)
    destino = modulo.gravar(texto)
    print(f"  Guardada em {destino} — só a linha {GESTAO_OPENROUTER} mudou.")
    print("  Agora dá para criar chave sem abrir navegador: chave-pela-api.bat.")
    return 0


def passo_abrir(args) -> int:
    modulo = _modulo_do_configurador()
    guia = modulo.guia_do_provedor("openrouter", "https://openrouter.ai/api/v1")
    if modulo.abrir_no_navegador(guia["onde"]):
        print(f"  Abri {guia['onde']} no seu navegador.")
        print("  Você já está logado: clique em “Create Key”, dê um nome e clique em COPIAR.")
        print("  Depois rode:  .venv\\Scripts\\python chave-no-navegador.py --pegar")
        return 0
    print("  Não consegui abrir o navegador. Abra na mão: openrouter.ai/keys")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Criar/colher a chave de IA pelo navegador.")
    parser.add_argument("--abrir", action="store_true", help="Abre a página de chaves no navegador.")
    parser.add_argument(
        "--diagnostico",
        action="store_true",
        help="Mede o que cada leitura do Windows enxerga. Não clica e não cria nada.",
    )
    parser.add_argument("--ver", action="store_true", help="Lê a página e diz o que existe. Não clica.")
    parser.add_argument("--pegar", action="store_true", help="Grava a chave que está na área de transferência.")
    parser.add_argument("--criar", action="store_true", help="Tenta criar uma chave nova clicando na página.")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="O caminho inteiro: abre a página, cria, copia e grava. Exige --autorizar.",
    )
    parser.add_argument("--provedor", default="", help="Provedor cujo site abrir (padrão: o do .env).")
    parser.add_argument(
        "--conta",
        default="",
        help="Pedaco do e-mail do Google usado para entrar (fica lembrado no .env).",
    )
    parser.add_argument("--espera-pagina", type=float, default=25.0, help="Segundos esperando a página abrir.")
    parser.add_argument("--espera-colar", type=float, default=120.0, help="Segundos esperando você copiar no site.")
    parser.add_argument("--autorizar", action="store_true", help="Sem isto, --criar só mostra o que faria.")
    parser.add_argument("--nome", default="", help="Nome da chave criada (padrão: jarvis-AAAA-MM-DD).")
    parser.add_argument(
        "--sem-mouse",
        action="store_true",
        help="Não usa o mouse: só a ação do elemento. O padrão do --criar é poder clicar.",
    )
    parser.add_argument(
        "--mouse",
        action="store_true",
        help="(já é o padrão no --criar) Autoriza o clique físico nos botões medidos.",
    )
    parser.add_argument("--alvo", default="chrome", help="Pedaço do título da janela (padrão: chrome).")
    parser.add_argument(
        "--cdp",
        action="store_true",
        help="Cria a chave pelo protocolo do Chrome (exige o chrome-cdp.bat). Não lê a tela.",
    )
    parser.add_argument("--porta", type=int, default=9222, help="Porta de controle do Chrome (padrão: 9222).")
    parser.add_argument(
        "--api",
        action="store_true",
        help="Cria a chave direto pela API do OpenRouter (precisa da chave de gestão no .env).",
    )
    parser.add_argument(
        "--gestao",
        action="store_true",
        help="Lê a chave de gestão da área de transferência, confere e guarda no .env.",
    )
    parser.add_argument(
        "--espera-carregar",
        type=float,
        default=90.0,
        help="Segundos esperando a página terminar de carregar (padrão: 90).",
    )
    parser.add_argument(
        "--espera-login",
        type=float,
        default=300.0,
        help="Segundos esperando você entrar na janela nova do Chrome (padrão: 300).",
    )
    args = parser.parse_args(argv)

    if sys.platform != "win32":
        print("  Isto só funciona no Windows: é lá que existe a janela e a área de transferência.")
        return 1

    _configurar_ambiente()
    sys.path.insert(0, str(RAIZ))

    try:
        if args.gestao:
            return passo_gestao(args)
        if args.api:
            return passo_api(args)
        if args.cdp:
            return passo_cdp(args)
        if args.diagnostico:
            return passo_diagnostico(args)
        if args.abrir:
            return passo_abrir(args)
        if args.auto:
            return passo_auto(args)
        if args.pegar:
            from server import chrome_cdp

            # Porta aberta = o Chrome do `chrome-cdp.bat` está de pé. Aí não se
            # lê tela: a página responde pelo protocolo dela (0.91.27).
            if chrome_cdp.porta_aberta(int(args.porta)):
                print("  O Chrome está com a porta de controle aberta: vou por ela,")
                print("  sem ler a tela e sem área de transferência.")
                return passo_cdp(args)
            return passo_pegar(args)
        if args.criar:
            return passo_criar(args)
        return passo_ver(args)
    except PassoError as exc:
        print(f"  NÃO DEU: {exc}")
        return 1
    except KeyboardInterrupt:
        # Ctrl+C é do dono, não é defeito. Sem isto, o Windows mostrava um
        # traceback de 8 linhas e o `.bat` seguia como se tivesse dado certo.
        print("\n  Interrompido com Ctrl+C. Nada foi gravado.")
        return 130
    finally:
        # O modo leitor de tela é emprestado, não tomado: sai como entrou.
        _desligar_a_acessibilidade()


if __name__ == "__main__":
    raise SystemExit(main())
