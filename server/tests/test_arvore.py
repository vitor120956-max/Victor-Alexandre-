"""A árvore de acessibilidade: ler sem tocar (0.82.0).

O que estes testes prendem, em uma frase cada:

- o módulo **não tem** como clicar, digitar ou mover o mouse — a etapa 1 é só leitura;
- `ref` só vai para o que é acionável, e muda a cada leitura (nunca “vale por acaso”);
- o corte é dito: `completo: false` com o motivo, em vez de árvore pela metade fingida;
- a janela é escolhida por título **ou** processo, e o erro lista o que está aberto;
- o papel desconhecido não ganha nome inventado;
- fora do Windows, a leitura recusa com frase clara (não finge que leu).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from server import arvore

RAIZ = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Dublês: uma janela pequena e uma grande
# ---------------------------------------------------------------------------

def _no(papel: int, nome: str, acao: str = "", filhos: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"papel": papel, "nome": nome}
    if acao:
        item["acao"] = acao
    if filhos:
        item["filhos"] = filhos
    return item


JANELA_CADASTRO = {
    "janela": {"handle": 111, "titulo": "Cadastro de cliente", "classe": "Chrome_WidgetWin_1", "processo": "chrome.exe"},
    "fonte": "msaa",
    "raiz": _no(
        9,  # janela
        "Cadastro de cliente",
        filhos=[
            _no(16, "", filhos=[  # painel
                _no(43, "Salvar", "Clicar"),
                _no(43, "Cancelar", "Clicar"),
                _no(42, "Nome completo"),
                _no(44, "Aceito os termos", "Marcar"),
            ]),
            _no(22, "Barra de ferramentas", filhos=[_no(12, "Arquivo", "Abrir")]),
        ],
    ),
}


class LeitorFalso:
    def __init__(self, janelas: list[dict[str, Any]], resposta: dict[str, Any] | None = None) -> None:
        self._janelas = janelas
        self._resposta = resposta or JANELA_CADASTRO
        self.pedidos: list[tuple[int, int, int]] = []

    def janelas(self) -> list[dict[str, Any]]:
        return self._janelas

    def janela_em_foco(self) -> dict[str, Any] | None:
        return self._janelas[0] if self._janelas else None

    def ler_janela(self, handle: int, profundidade: int, limite: int) -> dict[str, Any]:
        self.pedidos.append((handle, profundidade, limite))
        resposta = json.loads(json.dumps(self._resposta))
        # A sonda de verdade devolve a janela que leu; o dublê faz o mesmo.
        for item in self._janelas:
            if item["handle"] == handle:
                resposta["janela"] = dict(item)
                break
        return resposta


JANELAS = [
    {"handle": 111, "titulo": "Cadastro de cliente", "processo": "chrome.exe"},
    {"handle": 222, "titulo": "Bloco de notas", "processo": "notepad.exe"},
]


# ---------------------------------------------------------------------------
# Somente leitura, por construção
# ---------------------------------------------------------------------------

def test_o_modulo_nao_tem_como_clicar_digitar_ou_mover():
    """Etapa 1 é leitura. Se alguém acrescentar ação sem querer, este teste cai."""
    proibidos = ("clicar", "digitar", "mover", "teclar", "executar", "enviar")
    publicos = [nome for nome in dir(arvore) if not nome.startswith("_")]
    for nome in publicos:
        assert not any(palavra in nome for palavra in proibidos), nome


def test_o_modulo_nao_importa_rede_nem_executa_comando_do_usuario():
    texto = (RAIZ / "server" / "arvore.py").read_text(encoding="utf-8")
    assert "shell=True" not in texto
    assert "os.system" not in texto


# ---------------------------------------------------------------------------
# Normalização
# ---------------------------------------------------------------------------

def test_le_a_janela_em_foco_e_conta_o_que_importa():
    leitor = LeitorFalso(JANELAS)
    resultado = arvore.ler(leitor=leitor)
    assert resultado["alvo"].startswith("chrome.exe")
    assert resultado["total"] == 8
    assert resultado["acionaveis"] == 4  # Salvar, Cancelar, termos, Arquivo
    assert resultado["completo"] is True
    assert leitor.pedidos == [(111, arvore.PROFUNDIDADE_PADRAO, arvore.LIMITE_PADRAO)]


def test_ref_so_vai_para_o_que_da_para_acionar():
    resultado = arvore.ler(leitor=LeitorFalso(JANELAS))
    todos = arvore.achatar(resultado["arvore"])
    acionaveis = [no for no in todos if no["acionavel"]]
    assert all(no["ref"].startswith("@") for no in acionaveis)
    assert all(no["ref"] == "" for no in todos if not no["acionavel"])
    # todo ref é único
    refs = [no["ref"] for no in todos if no["ref"]]
    assert len(refs) == len(set(refs))


def test_o_id_do_snapshot_muda_quando_a_arvore_muda():
    um = arvore.ler(leitor=LeitorFalso(JANELAS))["id"]
    outra = json.loads(json.dumps(JANELA_CADASTRO))
    outra["raiz"]["filhos"][0]["filhos"].append(_no(43, "Excluir", "Clicar"))
    dois = arvore.ler(leitor=LeitorFalso(JANELAS, outra))["id"]
    assert um != dois


def test_a_mesma_arvore_da_o_mesmo_id():
    a = arvore.ler(leitor=LeitorFalso(JANELAS))["id"]
    b = arvore.ler(leitor=LeitorFalso(JANELAS))["id"]
    assert a == b


def test_nome_com_quebra_de_linha_vira_espaco_e_e_limitado():
    janela = json.loads(json.dumps(JANELA_CADASTRO))
    janela["raiz"]["filhos"][0]["filhos"][2]["nome"] = "Nome   completo\n do cliente" + "x" * 400
    resultado = arvore.ler(leitor=LeitorFalso(JANELAS, janela))
    nome = arvore.achatar(resultado["arvore"])[3]["nome"]
    assert "\n" not in nome and "  " not in nome
    assert len(nome) <= 200


def test_papel_desconhecido_nao_ganha_nome_inventado():
    janela = json.loads(json.dumps(JANELA_CADASTRO))
    janela["raiz"]["papel"] = 999
    resultado = arvore.ler(leitor=LeitorFalso(JANELAS, janela))
    assert resultado["arvore"]["papel"] == "elemento 999"


def test_papel_conhecido_vem_em_portugues():
    resultado = arvore.ler(leitor=LeitorFalso(JANELAS))
    papeis = {no["papel"] for no in arvore.achatar(resultado["arvore"])}
    assert {"janela", "painel", "botão", "texto", "caixa de seleção", "barra de ferramentas", "item de menu"} <= papeis


# ---------------------------------------------------------------------------
# Cortes, com honestidade
# ---------------------------------------------------------------------------

def test_profundidade_um_le_a_raiz_e_os_filhos_diretos():
    resultado = arvore.ler(leitor=LeitorFalso(JANELAS), profundidade=1)
    assert resultado["total"] == 3  # a janela e os dois filhos diretos dele
    assert all("filhos" not in filho for filho in resultado["arvore"].get("filhos") or [])


def test_limite_de_elementos_avisa_que_cortou():
    resultado = arvore.ler(leitor=LeitorFalso(JANELAS), limite=3)
    assert resultado["completo"] is False
    assert resultado["total"] == 3
    assert "parei em 3" in resultado["aviso"]


def test_limite_e_profundidade_sao_limitados_por_dentro():
    leitor = LeitorFalso(JANELAS)
    arvore.ler(leitor=leitor, profundidade=99, limite=99999)
    _, profundidade, limite = leitor.pedidos[0]
    assert profundidade == arvore.PROFUNDIDADE_MAX
    assert limite == arvore.LIMITE_MAX


def test_janela_sem_arvore_explica_em_vez_de_devolver_vazio():
    vazia = {"janela": JANELAS[0], "fonte": "msaa", "raiz": None}
    resultado = arvore.ler(leitor=LeitorFalso(JANELAS, vazia))
    assert resultado["arvore"] is None
    assert "não publicou árvore" in resultado["aviso"]
    assert resultado["total"] == 0


# ---------------------------------------------------------------------------
# Escolher a janela
# ---------------------------------------------------------------------------

def test_escolhe_pelo_titulo():
    leitor = LeitorFalso(JANELAS)
    resultado = arvore.ler("notepad", leitor=leitor)
    assert leitor.pedidos[0][0] == 222
    assert "notepad.exe" in resultado["alvo"]


def test_escolhe_pelo_processo():
    leitor = LeitorFalso(JANELAS)
    arvore.ler("chrome", leitor=leitor)
    assert leitor.pedidos[0][0] == 111


def test_janela_inexistente_lista_as_abertas():
    with pytest.raises(arvore.ArvoreError) as erro:
        arvore.ler("editor de video", leitor=LeitorFalso(JANELAS))
    texto = str(erro.value)
    assert "Cadastro de cliente" in texto and "Bloco de notas" in texto


def test_sem_janela_em_foco_explica():
    with pytest.raises(arvore.ArvoreError, match="janela em foco"):
        arvore.ler(leitor=LeitorFalso([]))


# ---------------------------------------------------------------------------
# Consultas para o chat
# ---------------------------------------------------------------------------

def test_lista_de_acionaveis_traz_nome_e_ref():
    resultado = arvore.ler(leitor=LeitorFalso(JANELAS))
    itens = arvore.acionaveis(resultado)
    nomes = [item["nome"] for item in itens]
    assert "Salvar" in nomes and "Cancelar" in nomes
    assert all(item["ref"] for item in itens)


def test_procurar_por_nome_ignora_maiusculas():
    resultado = arvore.ler(leitor=LeitorFalso(JANELAS))
    assert [no["nome"] for no in arvore.procurar(resultado, "salvar")] == ["Salvar"]
    assert arvore.procurar(resultado, "") == []


def test_o_desenho_mostra_indentacao_e_ref():
    resultado = arvore.ler(leitor=LeitorFalso(JANELAS))
    desenho = arvore.desenhar(resultado["arvore"])
    linhas = desenho.splitlines()
    assert linhas[0].startswith("janela")
    assert any(linha.startswith("  ") for linha in linhas)
    assert "@" in desenho


def test_o_resumo_diz_quantos_e_de_onde():
    resultado = arvore.ler(leitor=LeitorFalso(JANELAS))
    texto = arvore.resumo(resultado)
    assert "8 elemento" in texto
    assert "4 acionável" in texto
    assert "msaa" in texto


# ---------------------------------------------------------------------------
# Fora do Windows / sonda
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform == "win32", reason="o teste simula outro sistema")
def test_fora_do_windows_recusa_com_frase_clara():
    with pytest.raises(arvore.ArvoreError, match="só existe no Windows"):
        arvore.ler()


@pytest.mark.skipif(sys.platform == "win32", reason="o teste simula outro sistema")
def test_a_sonda_fora_do_windows_devolve_erro_em_json_e_codigo_1(capsys):
    import importlib.util

    caminho = RAIZ / "arvore_sonda.py"
    spec = importlib.util.spec_from_file_location("arvore_sonda", caminho)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    assert modulo.principal(["--json"]) == 1
    resposta = json.loads(capsys.readouterr().out)
    assert "Windows" in resposta["erro"]


def test_a_sonda_existe_e_e_ascii_no_essencial():
    caminho = RAIZ / "arvore_sonda.py"
    assert caminho.is_file()
    texto = caminho.read_text(encoding="utf-8")
    assert "só leitura" in texto or "Só leitura" in texto


# ---------------------------------------------------------------------------
# 0.82.1 — o que a primeira medição no PC ensinou
# ---------------------------------------------------------------------------
# O usuário rodou `arvore_sonda.py` dentro de um `cmd.exe` e recebeu:
#
#     cmd.exe — ...: 1 elemento(s), 0 acionável(is) — fonte: msaa
#     área do cliente “C:\Windows\system32\cmd.exe - ...”
#
# Duas coisas erradas ali: a sonda leu **a si mesma** (o terminal é a janela em
# foco) e o console não publica botões pela MSAA. Os testes abaixo prendem as
# duas correções.

CONSOLE = {
    "janela": {"handle": 900, "titulo": "cmd.exe - python arvore_sonda.py", "processo": "cmd.exe"},
    "raiz": _no(10, "C:\\Windows\\system32\\cmd.exe", filhos=[_no(41, "")]),
    "fonte": "msaa",
}

BLOCO_DE_NOTAS = {
    "janela": {"handle": 901, "titulo": "Sem título - Bloco de Notas", "processo": "notepad.exe"},
    "raiz": _no(9, "Bloco de Notas", filhos=[_no(42, "menu", "clicar"), _no(16, "", filhos=[_no(42, "texto")])]),
    "fonte": "uia",
}


def test_uma_arvore_pobre_pede_a_segunda_fonte():
    """1 elemento é moldura, não conteúdo — vale tentar a UIAutomation."""
    assert arvore.precisa_segunda_fonte(CONSOLE) is True
    assert arvore.precisa_segunda_fonte({"raiz": None}) is True


def test_uma_arvore_com_conteudo_dispensa_a_segunda_leitura():
    """9 é o piso: abaixo disso a janela não “falou” o suficiente para confiar."""
    rica = {"raiz": _no(9, "janela", filhos=[_no(43, f"botão {n}", "clicar") for n in range(10)])}
    assert arvore.precisa_segunda_fonte(rica) is False


def test_arvore_rica_nao_paga_a_segunda_leitura():
    """Janela com muita coisa não é lida duas vezes: o usuário espera."""
    grande = {"raiz": _no(9, "janela", filhos=[_no(43, f"botão {n}") for n in range(12)])}
    assert arvore.precisa_segunda_fonte(grande) is False


def test_quem_mostrou_mais_vence_e_diz_que_venceu():
    """“auto” não é chute: fica com a leitura maior e explica a escolha."""
    escolhida = arvore.escolher_fonte(CONSOLE, BLOCO_DE_NOTAS)
    assert escolhida["fonte"] == "uia"
    assert escolhida["janela"]["handle"] == 901
    assert "UIAutomation" in escolhida["nota"]


def test_msaa_vence_quando_da_mais_e_a_nota_diz_isso():
    """Não é “UIA sempre”: é a leitura maior. E o motivo fica escrito."""
    rica = {
        "janela": {"handle": 700, "titulo": "painel", "processo": "app.exe"},
        "raiz": _no(9, "janela", filhos=[_no(43, f"botão {n}", "clicar") for n in range(8)]),
        "fonte": "msaa",
    }
    escolhida = arvore.escolher_fonte(rica, CONSOLE)
    assert escolhida["fonte"] == "msaa"
    assert escolhida["janela"]["handle"] == 700
    assert "MSAA mostrou mais" in escolhida["nota"]


def test_nenhuma_das_duas_trouxe_arvore_explica_o_motivo():
    """Vazio sem explicação foi o que deixou o usuário sem saber o que fazer."""
    escolhida = arvore.escolher_fonte({"janela": {"titulo": "jogo"}, "raiz": None}, {"raiz": None})
    assert escolhida["raiz"] is None
    assert "nenhuma das duas fontes" in escolhida["aviso"]


def test_dica_avisa_quando_o_lido_foi_o_proprio_terminal():
    """O usuário leu o próprio `cmd` e não sabia — a frase tem de dizer isso."""
    resultado = arvore.montar(CONSOLE, 6, 600)
    assert "próprio terminal" in resultado["dica"]
    assert "--alvo" in resultado["dica"]


def test_dica_nao_aparece_quando_a_leitura_e_util():
    resultado = arvore.montar(JANELA_CADASTRO, 6, 600)
    assert "dica" not in resultado


def test_o_resumo_carrega_a_dica():
    """Quem só lê a primeira linha (o chat) também precisa do aviso."""
    texto = arvore.resumo(arvore.montar(CONSOLE, 6, 600))
    assert "próprio terminal" in texto


def test_o_nome_do_papel_da_uia_tem_preferencia():
    """A UIA já manda “editar”/“botão” traduzido; a nossa tabela é o reserva."""
    bruto = {
        "janela": {"handle": 1, "titulo": "x", "processo": "y.exe"},
        "raiz": {"papel": 42, "papel_nome": "editar", "nome": "Nome", "acao": "escrever"},
        "fonte": "uia",
    }
    no = arvore.montar(bruto, 2, 10)["arvore"]
    assert no["papel"] == "editar"
    assert no["ref"]


def test_elemento_desativado_nao_ganha_ref():
    """Botão cinza não é alvo de clique — dar `ref` a ele seria prometer o impossível."""
    bruto = {
        "janela": {"handle": 2, "titulo": "x", "processo": "y.exe"},
        "raiz": {"papel": 43, "nome": "Salvar", "desativado": True},
        "fonte": "uia",
    }
    resultado = arvore.montar(bruto, 2, 10)
    assert resultado["arvore"]["acionavel"] is False
    assert resultado["arvore"]["ref"] == ""
    assert resultado["acionaveis"] == 0


def test_a_sonda_troca_o_terminal_pela_janela_de_tras():
    """O caso do usuário: rodou no `cmd` e queria ver o programa aberto atrás."""
    import importlib.util

    caminho = RAIZ / "arvore_sonda.py"
    spec = importlib.util.spec_from_file_location("arvore_sonda_troca", caminho)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)

    class LeitorComTerminal:
        def janela_em_foco(self):
            return {"handle": 900, "titulo": "cmd.exe", "processo": "cmd.exe"}

        def janelas(self):
            return [
                {"handle": 900, "titulo": "cmd.exe", "processo": "cmd.exe"},
                {"handle": 901, "titulo": "Sem título - Bloco de Notas", "processo": "notepad.exe"},
            ]

    janela, troca = modulo._escolher(LeitorComTerminal(), "foco")
    assert janela["handle"] == 901
    assert "terminal" in troca
    assert "Bloco de Notas" in troca


def test_a_sonda_respeita_alvo_explicito_em_vez_de_trocar():
    """Se o usuário pediu `--alvo`, ele manda — nada de troca silenciosa."""
    import importlib.util

    caminho = RAIZ / "arvore_sonda.py"
    spec = importlib.util.spec_from_file_location("arvore_sonda_alvo", caminho)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)

    class Leitor:
        def janela_em_foco(self):
            return {"handle": 900, "titulo": "cmd.exe", "processo": "cmd.exe"}

        def janelas(self):
            return [
                {"handle": 900, "titulo": "cmd.exe", "processo": "cmd.exe"},
                {"handle": 901, "titulo": "Bloco de Notas", "processo": "notepad.exe"},
            ]

    janela, troca = modulo._escolher(Leitor(), "cmd")
    assert janela["handle"] == 900
    assert troca == ""


def test_a_sonda_oferece_as_duas_fontes():
    """`--fonte` é o que permite comparar as duas no PC do usuário."""
    texto = (RAIZ / "arvore_sonda.py").read_text(encoding="utf-8")
    assert '"--fonte"' in texto
    assert '"msaa", "uia"' in texto


def test_a_sonda_manda_a_fonte_para_o_leitor():
    """Sem repassar `fonte`, escolher a fonte não adiantaria nada."""
    fonte = Path("server/arvore.py").read_text(encoding="utf-8")
    assert '"--fonte",' in fonte


# ---------------------------------------------------------------------------
# 0.82.2 — a segunda medição: o Chrome repetindo a moldura
# ---------------------------------------------------------------------------
# No PC do usuário (Windows 10 14393) o Chrome devolveu 600 elementos, 596
# “acionáveis”, todos `IME → IME → IME` e `Minimizar dentro de Minimizar`. Era
# a moldura da janela exposta dentro dela mesma. Estes testes prendem as duas
# guardas e o alarme.

def _botao(nome: str, x: int = 0) -> dict[str, Any]:
    return {"papel": 43, "nome": nome, "caixa": [x, 0, 20, 20]}


def test_moldura_nunca_desce():
    """Minimizar/Fechar/IME são folha: descer neles foi o que explodiu."""
    for nome in ("IME", "Minimizar", "Maximizar", "Fechar", "Ajuda de contexto", "Sistema"):
        pode, _ = arvore.pode_descer(_botao(nome), ())
        assert pode is False, nome


def test_botao_repetido_dentro_de_si_mesmo_para():
    """O padrão exato do Chrome: “Atualizar” dentro de “Atualizar”."""
    no = {"papel": 43, "nome": "Atualizar", "caixa": [10, 10, 30, 30]}
    pode, caminho = arvore.pode_descer(no, ())
    assert pode is True
    pode_de_novo, _ = arvore.pode_descer({"papel": 43, "nome": "Atualizar", "caixa": [11, 11, 30, 30]}, caminho)
    assert pode_de_novo is False


def test_dois_botoes_irmaos_com_o_mesmo_nome_nao_sao_ciclo():
    """“Excluir” e “Excluir” lado a lado são dois botões — a guarda não os corta.

    A guarda olha a **linhagem** (pai -> filho), não os irmãos: cada irmão entra
    com o mesmo caminho de ancestrais, então os dois passam.
    """
    primeiro = {"papel": 43, "nome": "Excluir", "caixa": [0, 0, 20, 20]}
    segundo = {"papel": 43, "nome": "Excluir", "caixa": [40, 0, 20, 20]}
    tabela = arvore.chave({"papel": 24, "nome": "tabela", "caixa": [0, 0, 400, 300]})
    caminho_do_pai: tuple = (tabela,)
    assert arvore.pode_descer(primeiro, caminho_do_pai)[0] is True
    assert arvore.pode_descer(segundo, caminho_do_pai)[0] is True


def test_filho_com_o_mesmo_nome_do_pai_para():
    """Isso sim é ciclo: “Excluir” dentro de “Excluir”."""
    pai = {"papel": 43, "nome": "Excluir", "caixa": [0, 0, 20, 20]}
    _, caminho = arvore.pode_descer(pai, ())
    filho = {"papel": 43, "nome": "Excluir", "caixa": [40, 0, 20, 20]}
    assert arvore.pode_descer(filho, caminho)[0] is False


def test_painel_vazio_empilhado_com_posicoes_diferentes_desce():
    """“painel” dentro de “painel” é comum e legítimo — não pode ser cortado."""
    de_fora = {"papel": 16, "nome": "", "caixa": [0, 0, 800, 600]}
    de_dentro = {"papel": 16, "nome": "", "caixa": [10, 40, 780, 520]}
    _, caminho = arvore.pode_descer(de_fora, ())
    pode, _ = arvore.pode_descer(de_dentro, caminho)
    assert pode is True


def test_painel_vazio_na_mesma_posicao_para():
    """Mesmo papel, mesmo nome, mesma posição: é o mesmo nó, não um filho."""
    painel = {"papel": 16, "nome": "", "caixa": [0, 0, 800, 600]}
    _, caminho = arvore.pode_descer(painel, ())
    pode, _ = arvore.pode_descer(dict(painel), caminho)
    assert pode is False


def test_a_arvore_repetida_do_chrome_e_denunciada():
    """É melhor avisar do que entregar 596 “botões” que não existem."""
    moldura = [_botao("Minimizar" if n % 2 else "IME", x=n) for n in range(30)]
    bruto = {
        "janela": {"handle": 5, "titulo": "Arena - Google Chrome", "processo": "chrome.exe"},
        "raiz": {"papel": 10, "nome": "área do cliente", "filhos": moldura},
        "fonte": "msaa",
    }
    resultado = arvore.montar(bruto, 6, 600)
    assert resultado["acionaveis"] == 30
    assert arvore.repeticao(resultado) == 15
    assert "repetiu os mesmos botões" in resultado["dica"]
    assert "--fonte uia" in resultado["dica"]


def test_arvore_normal_nao_e_denunciada_como_repetida():
    resultado = arvore.montar(JANELA_CADASTRO, 6, 600)
    assert arvore.repeticao(resultado) == 1
    assert not resultado.get("dica")


def test_de_casca_reconhece_o_menu_iniciar():
    """Foi o que a sonda escolheu no PC do usuário: “Iniciar”, do explorer."""
    assert arvore.de_casca({"classe": "Windows.UI.Core.CoreWindow", "titulo": "Iniciar"}) is True
    assert arvore.de_casca({"classe": "Shell_TrayWnd", "titulo": ""}) is True
    assert arvore.de_casca({"classe": "Chrome_WidgetWin_1", "titulo": "Arena"}) is False


def test_a_sonda_prefere_janelas_de_programa_ao_escolher_a_de_tras():
    """Com o filtro, o Chrome — e não o menu Iniciar — é a janela de trás."""
    import importlib.util

    caminho = RAIZ / "arvore_sonda.py"
    spec = importlib.util.spec_from_file_location("arvore_sonda_casca", caminho)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)

    class LeitorComCasca:
        def janela_em_foco(self):
            return {"handle": 900, "titulo": "cmd.exe", "processo": "cmd.exe"}

        def janelas(self):
            return [
                {"handle": 900, "titulo": "cmd.exe", "processo": "cmd.exe", "classe": "ConsoleWindowClass"},
                {"handle": 902, "titulo": "Iniciar", "processo": "explorer.exe", "classe": "Windows.UI.Core.CoreWindow"},
                {"handle": 901, "titulo": "Arena - Google Chrome", "processo": "chrome.exe", "classe": "Chrome_WidgetWin_1"},
            ]

        def janelas_de_programas(self):
            return [
                {"handle": 900, "titulo": "cmd.exe", "processo": "cmd.exe", "classe": "ConsoleWindowClass"},
                {"handle": 901, "titulo": "Arena - Google Chrome", "processo": "chrome.exe", "classe": "Chrome_WidgetWin_1"},
            ]

    janela, troca = modulo._escolher(LeitorComCasca(), "foco")
    assert janela["handle"] == 901
    assert "Chrome" in troca


def test_os_indices_da_uia_nao_voltam_a_ficar_deslocados():
    """Os índices errados eram todos +3 (faltava contar IUnknown). Prende os certos."""
    import ast

    fonte = (Path("server") / "arvore_windows.py").read_text(encoding="utf-8")
    arvore_ast = ast.parse(fonte)
    valores = {}
    for no in arvore_ast.body:
        if isinstance(no, ast.Assign) and len(no.targets) == 1 and isinstance(no.targets[0], ast.Name):
            if isinstance(no.value, ast.Constant) and isinstance(no.value.value, int):
                valores[no.targets[0].id] = no.value.value

    assert valores["UIA_ELEMENT_FROM_HANDLE"] == 6
    assert valores["UIA_CONTROL_VIEW_WALKER"] == 14
    assert valores["UIA_WALKER_FIRST_CHILD"] == 4
    assert valores["UIA_WALKER_NEXT_SIBLING"] == 6
    assert valores["UIA_EL_GET_NAME"] == 23
    assert valores["UIA_EL_GET_PATTERN"] == 16
    # Qualquer índice abaixo de 3 invadiria IUnknown.
    for nome, valor in valores.items():
        if nome.startswith("UIA_") and nome.isupper():
            assert valor >= 3, nome


def test_a_sonda_tem_diagnostico():
    """Falhar em silêncio foi o pior da 0.82.1 — agora existe um passo a passo."""
    texto = (RAIZ / "arvore_sonda.py").read_text(encoding="utf-8")
    assert '"--diagnostico"' in texto
    assert "diagnostico()" in texto
