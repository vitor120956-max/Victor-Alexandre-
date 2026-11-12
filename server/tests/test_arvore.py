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
    # O diagnóstico precisa saber QUAL janela examinar — já mediu o terminal
    # por engano quando usava sempre a janela em foco.
    assert "diagnostico(args.alvo, handle=janela_diagnostico[" in texto


# ---------------------------------------------------------------------------
# 0.82.3 — `--alvo chrome` leu o terminal
# ---------------------------------------------------------------------------
# Medição no PC do usuário:
#
#     D:\JARVIS>.venv\Scripts\python arvore_sonda.py --alvo chrome
#     cmd.exe — ... --alvo chrome: 12 elemento(s) — fonte: uia
#
# O Chrome nunca foi tocado: o título do `cmd` é a linha de comando, e a linha
# de comando contém “chrome”. A janela que roda a sonda é a única que sempre
# carrega o pedido escrito nela.

JANELAS_CHROME = [
    {"handle": 1, "titulo": "cmd.exe - .venv\\Scripts\\python arvore_sonda.py --alvo chrome", "processo": "cmd.exe"},
    {"handle": 2, "titulo": "Arena | Benchmark - Google Chrome", "processo": "chrome.exe"},
]


def test_alvo_por_processo_nao_pega_o_terminal():
    """O caso exato do usuário: `chrome` tem de ser o chrome.exe."""
    escolhida = arvore.escolher_janela("chrome", janelas=JANELAS_CHROME, foco=JANELAS_CHROME[0])
    assert escolhida["handle"] == 2


def test_processo_vence_titulo_mesmo_vindo_depois_na_lista():
    """Ordem na lista não decide: quem decide é a nota."""
    invertidas = list(reversed(JANELAS_CHROME))
    escolhida = arvore.escolher_janela("chrome", janelas=invertidas, foco=None)
    assert escolhida["processo"] == "chrome.exe"


def test_a_janela_da_sonda_nunca_e_candidata():
    """Sem esta regra, o pedido casa com o próprio comando que o contém."""
    assert arvore.da_sonda({"titulo": "cmd.exe - python arvore_sonda.py --alvo chrome"}) is True
    assert arvore.da_sonda({"titulo": "Arena - Google Chrome"}) is False


def test_titulo_ainda_serve_quando_nao_ha_processo_com_o_nome():
    """“Arena” não é nome de processo — aí o título é a única pista."""
    janelas = [
        {"handle": 1, "titulo": "cmd.exe - arvore_sonda.py", "processo": "cmd.exe"},
        {"handle": 3, "titulo": "Arena | Benchmark", "processo": "firefox.exe"},
    ]
    assert arvore.escolher_janela("arena", janelas=janelas, foco=None)["handle"] == 3


def test_sem_alvo_que_casa_a_mensagem_nao_lista_o_proprio_terminal():
    with pytest.raises(arvore.ArvoreError) as erro:
        arvore.escolher_janela("calculadora", janelas=JANELAS_CHROME, foco=None)
    texto = str(erro.value)
    assert "Arena | Benchmark" in texto
    assert "arvore_sonda" not in texto


def test_terminal_e_reconhecido_para_a_troca_de_foco():
    assert arvore.e_terminal({"processo": "cmd.exe"}) is True
    assert arvore.e_terminal({"processo": "PowerShell.exe"}) is True
    assert arvore.e_terminal({"processo": "chrome.exe"}) is False
    assert arvore.e_terminal(None) is False


def test_peso_da_janela_ordena_do_melhor_para_o_pior():
    """0 processo igual, 1 processo parecido, 2 título começa, 3 título contém."""
    assert arvore.peso_da_janela({"processo": "chrome.exe", "titulo": ""}, "chrome") == 0
    assert arvore.peso_da_janela({"processo": "chrome_proxy.exe", "titulo": ""}, "chrome") == 1
    assert arvore.peso_da_janela({"processo": "x.exe", "titulo": "Chrome - perfil"}, "chrome") == 2
    assert arvore.peso_da_janela({"processo": "x.exe", "titulo": "Abrir no Chrome"}, "chrome") == 3
    assert arvore.peso_da_janela({"processo": "x.exe", "titulo": "outra"}, "chrome") is None


# ---------------------------------------------------------------------------
# 0.82.4 — a causa raiz de TODA a repetição
# ---------------------------------------------------------------------------
# Medição no PC do usuário (`--alvo chrome`, 600 elementos):
#
#     barra de rolagem “Vertical”
#       botão “Uma linha acima”
#         botão “Uma linha acima”
#           botão “Uma página acima”
#             botão “Uma linha acima” ...
#
# A guarda de moldura não pegava porque a repetição não era a moldura da
# janela: era a **barra de rolagem** repetindo a si mesma. A causa estava em
# `arvore_windows._no`: filho “simples” da MSAA (VT_I4) não tem ponteiro
# próprio, e o código reusava o ponteiro do pai para pedir os filhos — o pai
# devolvia os próprios filhos, para sempre.
#
# A guarda na montagem é a segunda linha de defesa: mesmo que a sonda devolva
# árvore repetida, o `montar` corta.

def _rolagem(profundidade: int) -> dict[str, Any]:
    """Uma barra de rolagem que repete a si mesma, como a sonda antiga fazia."""
    no = {"papel": 3, "nome": "Vertical", "filhos": []}
    atual = no
    for _ in range(profundidade):
        filho = {"papel": 43, "nome": "Uma linha acima", "acao": "Pressionar", "filhos": []}
        atual["filhos"].append(filho)
        atual = filho
    return no


def test_montagem_corta_barra_de_rolagem_que_repete():
    """Era isto que enchia os 600 elementos: o mesmo botão, 200 vezes."""
    bruto = {
        "janela": {"handle": 77, "titulo": "Chrome", "processo": "chrome.exe"},
        "raiz": {"papel": 10, "nome": "área do cliente", "filhos": [_rolagem(40)]},
        "fonte": "msaa",
    }
    resultado = arvore.montar(bruto, 14, 3000)
    assert resultado["total"] < 10, resultado["total"]
    nomes = [no["nome"] for no in arvore.achatar(resultado["arvore"])]
    assert nomes.count("Uma linha acima") == 1


def test_montagem_preserva_barra_de_rolagem_normal():
    """A guarda não pode comer uma barra legítima: 5 botões diferentes."""
    rolagem = {
        "papel": 3,
        "nome": "Vertical",
        "filhos": [
            {"papel": 43, "nome": "Uma linha acima", "acao": "Pressionar"},
            {"papel": 43, "nome": "Uma página acima", "acao": "Pressionar"},
            {"papel": 51, "nome": "Posição"},
            {"papel": 43, "nome": "Uma página abaixo", "acao": "Pressionar"},
            {"papel": 43, "nome": "Uma linha abaixo", "acao": "Pressionar"},
        ],
    }
    bruto = {
        "janela": {"handle": 78, "titulo": "Chrome", "processo": "chrome.exe"},
        "raiz": {"papel": 10, "nome": "área do cliente", "filhos": [rolagem]},
        "fonte": "msaa",
    }
    resultado = arvore.montar(bruto, 14, 3000)
    assert resultado["total"] == 7
    # quatro botões + o elevador (controle deslizante também é acionável)
    assert resultado["acionaveis"] == 5
    assert not resultado.get("dica")


def test_a_leitura_nao_reusa_o_ponteiro_do_pai_em_filho_simples():
    """O defeito exato: `ponteiro_filho or ponteiro` pedia ao pai os filhos dele.

    Sem Windows não dá para chamar o COM, mas dá para prender a regra no
    código — foi uma linha só, e ela custou três versões.
    """
    fonte = (Path("server") / "arvore_windows.py").read_text(encoding="utf-8")
    assert "ponteiro_filho or ponteiro" not in fonte
    assert "if not ponteiro_filho:" in fonte


def test_filho_simples_entra_na_arvore_sem_descer():
    """Elemento simples tem nome e papel — só não tem o que descer.

    O que se prende aqui: no ramo do filho simples **não existe chamada
    recursiva**. Era ela (com o ponteiro do pai) que repetia tudo.
    """
    fonte = (Path("server") / "arvore_windows.py").read_text(encoding="utf-8")
    inicio = fonte.index("if not ponteiro_filho:", fonte.index("def _no("))
    trecho = fonte[inicio : fonte.index("continue", inicio) + len("continue")]
    assert "_papel(ponteiro, id_filho)" in trecho
    assert "_nome(ponteiro, id_filho)" in trecho
    assert "_no(" not in trecho
    assert "continue" in trecho


def test_navegador_sempre_pede_a_segunda_leitura():
    """O Chrome no Windows 10 do usuário: MSAA devolve moldura, página mora na UIA."""
    for processo in ("chrome.exe", "msedge.exe", "firefox.exe", "code.exe"):
        bruto = {"janela": {"processo": processo}, "raiz": _no(9, "janela", filhos=[_no(43, str(n)) for n in range(30)])}
        assert arvore.quer_segunda_fonte(bruto) is True, processo
        assert arvore.precisa_segunda_fonte(bruto) is False, processo


def test_programa_comum_com_arvore_rica_nao_pede_segunda_leitura():
    bruto = {"janela": {"processo": "notepad.exe"}, "raiz": _no(9, "janela", filhos=[_no(43, str(n)) for n in range(30)])}
    assert arvore.quer_segunda_fonte(bruto) is False


# ---------------------------------------------------------------------------
# 0.82.5 — moldura != conteúdo, e a página mora na janela filha
# ---------------------------------------------------------------------------
# Medição no PC do usuário, depois de consertar a repetição:
#
#     chrome.exe — Arena | Benchmark...: 47 elemento(s), 26 acionável(is) — fonte: msaa.
#     a UIAutomation mostrou 4; a MSAA mostrou mais (47).
#
# Os 47 eram todos moldura. A regra "quem mostrou mais" premiava justamente a
# leitura sem conteúdo. E a página do Chrome não é um elemento da janela de
# topo: é uma janela filha (Chrome_RenderWidgetHostHWND).

MOLDURA_DO_CHROME = {
    "janela": {"handle": 10, "titulo": "Arena - Google Chrome", "processo": "chrome.exe"},
    "raiz": _no(
        10,
        "área do cliente",
        filhos=[
            _no(43, "IME", "Pressionar"),
            _no(43, "Minimizar", "Pressionar"),
            _no(3, "Vertical", filhos=[_no(43, "Uma linha acima", "Pressionar"), _no(43, "Uma página abaixo", "Pressionar")]),
            _no(4, "alça"),
        ],
    ),
    "fonte": "msaa",
}

PAGINA_DO_CHROME = {
    "janela": {"handle": 11, "titulo": "Arena - Google Chrome", "processo": "chrome.exe", "de_filha": "Chrome_RenderWidgetHostHWND"},
    "raiz": _no(
        15,
        "Arena | Benchmark",
        filhos=[
            _no(30, "Entrar", "Clicar"),
            _no(41, "Compare the best AI models"),
        ],
    ),
    "fonte": "uia",
}


def test_moldura_nao_conta_como_conteudo():
    assert arvore.tem_conteudo(MOLDURA_DO_CHROME) is False
    assert arvore.tem_conteudo(PAGINA_DO_CHROME) is True


def test_conteudo_vence_moldura_mesmo_com_menos_elementos():
    """47 elementos de moldura perdem para 3 de conteúdo — é o caso do usuário."""
    escolhida = arvore.escolher_fonte(MOLDURA_DO_CHROME, PAGINA_DO_CHROME)
    assert escolhida["fonte"] == "uia"
    assert "conteúdo" in escolhida["nota"]


def test_navegador_prefere_uia_mesmo_com_empate_de_moldura():
    moldura_uia = {
        "janela": {"handle": 10, "processo": "chrome.exe"},
        "raiz": _no(43, "Minimizar"),
        "fonte": "uia",
    }
    escolhida = arvore.escolher_fonte(MOLDURA_DO_CHROME, moldura_uia)
    assert escolhida["fonte"] == "uia"
    assert "navegador" in escolhida.get("nota", "")


def test_programa_comum_sem_conteudo_mantem_quem_tem_mais():
    """A regra nova não pode quebrar o caso simples: janela de app Win32."""
    maior = {
        "janela": {"handle": 20, "processo": "app.exe"},
        "raiz": _no(9, "app", filhos=[_no(43, f"botão {n}") for n in range(6)]),
        "fonte": "msaa",
    }
    menor = {"janela": {"handle": 20, "processo": "app.exe"}, "raiz": _no(9, "app"), "fonte": "uia"}
    assert arvore.escolher_fonte(maior, menor)["fonte"] == "msaa"


def test_o_resumo_diz_quando_a_leitura_veio_de_uma_janela_filha():
    """“De onde veio” importa: a página não é a janela, é a filha dela."""
    resultado = arvore.montar(PAGINA_DO_CHROME, 6, 600)
    assert resultado["de_filha"] == "Chrome_RenderWidgetHostHWND"
    assert "lido de dentro" in arvore.resumo(resultado)


def test_a_sonda_conhece_as_janelas_filhas_e_a_varredura():
    fonte = (Path("server") / "arvore_windows.py").read_text(encoding="utf-8")
    assert "EnumChildWindows" in fonte
    assert "Chrome_RenderWidgetHostHWND".lower() in fonte.lower()
    assert "def janelas_filhas" in fonte
    assert "def varrer_uia" in fonte
    assert '"varredura"' in fonte


def test_o_diagnostico_respeita_o_alvo():
    """`--alvo chrome --diagnostico` mediu o terminal e respondeu “nenhum”.

    O diagnóstico usava sempre `janela_em_foco()`, ignorando o alvo. A tabela
    que devia decidir a etapa 2 estava medindo a janela errada.
    """
    fonte = (Path("server") / "arvore_windows.py").read_text(encoding="utf-8")
    inicio = fonte.index("def diagnostico(")
    trecho = fonte[inicio : inicio + 4000]
    assert 'alvo: str = "foco"' in trecho
    assert "handle: int | None = None" in trecho
    assert "arvore.escolher_janela(alvo" in trecho
    # A janela em foco só entra como candidata — não como decisão.
    assert "foco=janela_em_foco()" in trecho


def test_a_tabela_do_diagnostico_mostra_o_processo():
    """Classe “ConsoleWindowClass” não diz nada a quem lê; `cmd.exe` diz."""
    fonte = (Path("server") / "arvore_windows.py").read_text(encoding="utf-8")
    inicio = fonte.index("varredura: list[dict[str, Any]] = []")
    trecho = fonte[inicio : inicio + 400]
    assert '"processo"' in trecho
    assert '"classe"' in trecho


def test_a_sonda_diz_qual_janela_esta_medindo():
    """A tabela do diagnóstico já mediu o terminal sem avisar ninguém."""
    texto = (RAIZ / "arvore_sonda.py").read_text(encoding="utf-8")
    assert "medindo: " in texto
    assert "classe:  " in texto
    # E fecha com um veredito, em vez de deixar a tabela para o usuário interpretar.
    assert "VEREDITO" in texto


def test_o_diagnostico_mede_do_jeito_que_a_leitura_le():
    """O veredito é a leitura de verdade — não uma segunda implementação dela.

    A 0.82.6 montava o veredito à mão (`varrer_msaa` + `_ler_uia` +
    `escolher_fonte`) logo depois de a tabela ter tocado na UIA. Duas
    implementações da mesma pergunta divergem; uma só, não.
    """
    fonte = (Path("server") / "arvore_windows.py").read_text(encoding="utf-8")
    inicio = fonte.index("def diagnostico(")
    trecho = fonte[inicio : fonte.index("def estado(", inicio)]
    assert '"veredito"' in trecho
    assert "escolhida = ler_janela(" in trecho


def test_o_diagnostico_mede_a_msaa_antes_de_abrir_a_uia():
    """No Chrome a MSAA deu 47 numa medição e 4 na outra. A diferença era a ordem.

    Abrir a UIA na mesma janela antes de medir a MSAA mudava o número. O
    diagnóstico não pode medir de um jeito que a leitura nunca usa.
    """
    fonte = (Path("server") / "arvore_windows.py").read_text(encoding="utf-8")
    inicio = fonte.index("def diagnostico(")
    trecho = fonte[inicio : fonte.index("def estado(", inicio)]
    # A primeira passada da tabela é a MSAA...
    assert trecho.index("_ler_msaa(") < trecho.index("_ler_uia_da_janela(")
    # ...e o CoCreateInstance só aparece depois dela.
    assert trecho.index("_ler_msaa(") < trecho.index("CoCreateInstance(IUIAutomation)")


def test_a_varredura_msaa_desce_as_janelas_filhas():
    """MSAA só na janela de topo nunca alcança a página do navegador."""
    fonte = (Path("server") / "arvore_windows.py").read_text(encoding="utf-8")
    inicio = fonte.index("def varrer_msaa(")
    trecho = fonte[inicio : fonte.index("def _ler_msaa(")]
    assert "janelas_filhas(" in trecho
    assert "FILHAS_MAXIMAS" in trecho
    assert "de_filha" in trecho
    # Janela já rica não paga 24 leituras: rende o que já tem.
    assert "melhor_conteudo and melhor_total >= 9" in trecho
    # Achou conteúdo numa filha, para: não paga as outras 23.
    assert "if conteudo:\n            break" in trecho


# ---------------------------------------------------------------------------
# 0.83.0 — onde o JARVIS consegue trabalhar
# ---------------------------------------------------------------------------

def test_montar_diz_se_a_arvore_tem_conteudo():
    """A conta da prontidão precisa do papel **cru**, e ele se perde na montagem."""
    from server import arvore as mod

    moldura = {
        "janela": {"handle": 1, "titulo": "Chrome", "processo": "chrome.exe"},
        "fonte": "msaa",
        "raiz": _no(9, "Chrome", filhos=[_no(22, "barra de título", filhos=[_no(43, "Fechar", "Clicar")])]),
    }
    pagina = {
        "janela": {"handle": 2, "titulo": "Texto", "processo": "notepad.exe"},
        "fonte": "uia",
        "raiz": _no(9, "Bloco de notas", filhos=[_no(42, "texto do documento")]),
    }
    assert mod.montar(moldura)["conteudo"] is False
    assert mod.montar(pagina)["conteudo"] is True


def test_prontidao_recusa_moldura_mesmo_com_muitos_botoes():
    """Os 47 elementos do Chrome eram 47 botões de janela. Não servem."""
    from server import arvore as mod

    filhos = [_no(43, nome, "Clicar") for nome in ("Fechar", "Minimizar", "Maximizar", "IME")]
    montada = mod.montar(
        {
            "janela": {"handle": 3, "titulo": "Chrome", "processo": "chrome.exe"},
            "fonte": "msaa",
            "raiz": _no(9, "Chrome", filhos=[_no(22, "barra de título", filhos=filhos)]),
        }
    )
    lido = mod.prontidao(montada)
    assert lido["pronto"] is False
    assert lido["conteudo"] is False
    assert "moldura" in lido["motivo"]


def test_prontidao_aceita_campo_de_texto_sem_nome():
    """No Bloco de Notas o campo onde se escreve não tem nome — e serve.

    Exigir nome em todo acionável recusaria justamente o programa mais
    simples de todos, e a etapa 2 nunca começaria.
    """
    from server import arvore as mod

    montada = mod.montar(
        {
            "janela": {"handle": 4, "titulo": "Sem título - Bloco de notas", "processo": "notepad.exe"},
            "fonte": "uia",
            "raiz": _no(9, "Sem título - Bloco de notas", filhos=[_no(42, "", "escrever")]),
        }
    )
    lido = mod.prontidao(montada)
    assert lido["pronto"] is True
    assert lido["editaveis"] == 1


def test_prontidao_de_janela_sem_arvore_diz_o_motivo():
    from server import arvore as mod

    montada = mod.montar({"janela": {"handle": 5, "titulo": "Jogo"}, "raiz": None})
    lido = mod.prontidao(montada)
    assert lido["pronto"] is False
    assert lido["total"] == 0
    assert lido["motivo"]


def test_a_sonda_tem_o_comando_que_mede_todas_as_janelas():
    """Uma rodada por programa custou seis mensagens no Chrome. Agora é uma."""
    texto = (RAIZ / "arvore_sonda.py").read_text(encoding="utf-8")
    assert '"--provados"' in texto
    assert "def _provados(" in texto
    # Mede com a leitura de verdade e com a mesma conta da prontidão.
    assert "leitor.ler_janela(" in texto
    assert "arvore.prontidao(" in texto
    # Não mede a si mesma (o terminal onde o comando foi digitado).
    assert "arvore.da_sonda(" in texto


def test_a_sonda_diz_se_a_janela_serve_para_agir():
    """O número sozinho enganou: 47 elementos eram 47 botões de janela."""
    texto = (RAIZ / "arvore_sonda.py").read_text(encoding="utf-8")
    assert "SERVE para agir" in texto
    assert "NAO SERVE para agir" in texto
    assert "arvore.prontidao(montada)" in texto


def test_o_mesa_arvore_entrega_a_prontidao():
    """O JARVIS tem de saber que a janela não serve — não descobrir depois."""
    texto = (Path("server") / "skill_registry.py").read_text(encoding="utf-8")
    inicio = texto.index("def mesa_arvore_handler(")
    trecho = texto[inicio : inicio + 1400]
    assert 'lida["pronto"] = arvore.prontidao(lida)' in trecho


# ---------------------------------------------------------------------------
# 0.83.1 — saber ONDE a peça está ≠ saber O QUE ela é
# ---------------------------------------------------------------------------

def test_desenhar_mostra_onde_fica_cada_elemento():
    """A posição era medida e nunca impressa — daí a pergunta “ele sabe onde?”."""
    montada = {
        "arvore": {
            "papel": "janela",
            "nome": "Chrome",
            "caixa": [0, 0, 1200, 800],
            "filhos": [
                {"papel": "botão", "nome": "Fechar", "acao": "Clicar", "caixa": [1180, 5, 30, 20]},
                {"papel": "texto", "nome": "", "acionavel": False},
            ],
        }
    }
    desenho = arvore.desenhar(montada["arvore"])
    assert "em 0,0 (1200x800)" in desenho
    assert "em 1180,5 (30x20)" in desenho
    # Elemento sem caixa continua aparecendo, sem inventar coordenada.
    assert desenho.count("em ") == 2


def test_a_prontidao_diz_que_a_posicao_e_conhecida_quando_o_conteudo_nao_e():
    """Os 4 elementos do Chrome: posição medida, conteúdo nenhum.

    Dizer só “não serve” faz parecer que nada foi reconhecido. A posição foi —
    e o motivo tem de separar as duas coisas.
    """
    montada = {
        "conteudo": False,
        "total": 4,
        "arvore": {
            "papel": "janela",
            "nome": "Chrome",
            "caixa": [0, 0, 1200, 800],
            "filhos": [
                {"papel": "botão", "nome": "Fechar", "acionavel": True, "caixa": [1180, 5, 30, 20]},
                {"papel": "botão", "nome": "Minimizar", "acionavel": True, "caixa": [1140, 5, 30, 20]},
            ],
        },
    }
    lido = arvore.prontidao(montada)
    assert lido["pronto"] is False
    assert lido["com_posicao"] == 3
    assert "posição dela eu sei" in lido["motivo"]
    assert "3 de 3" in lido["motivo"]


def test_a_varredura_geral_mostra_a_coluna_de_posicoes():
    """`--provados` responde “onde ele enxerga?” coluna por coluna."""
    texto = (RAIZ / "arvore_sonda.py").read_text(encoding="utf-8")
    assert "posicoes  conteudo" in texto
    assert "com_posicao" in texto
    # E diz, em uma linha, a diferença que gerou a dúvida.
    assert "Saber onde" in texto


# ---------------------------------------------------------------------------
# 0.84.0 — a janela acorda na segunda leitura
# ---------------------------------------------------------------------------

def test_ler_janela_tenta_uma_segunda_vez_quando_so_vem_moldura():
    """Medido no PC: a 1ª leitura do Chrome deu 3 elementos; a 2ª, 104.

    O Chrome liga a árvore da página quando percebe alguém lendo, e não
    instantaneamente. Ler uma vez e concluir “não tem nada” era mentira — e foi
    essa mentira que me fez encerrar o Chrome antes da hora.
    """
    fonte = (Path("server") / "arvore_windows.py").read_text(encoding="utf-8")
    inicio = fonte.index("def ler_janela(")
    trecho = fonte[inicio : fonte.index("def _ler_auto(", inicio)]
    assert "PAUSA_DE_DESPERTO" in trecho
    assert "segunda = _ler_auto(" in trecho
    assert 'segunda["acordou"]' in trecho
    # E só relê quando não veio conteúdo: janela boa não paga o segundo passe.
    assert "or arvore.tem_conteudo(resultado)" in trecho


def test_a_pausa_do_desperto_e_curta_de_proposito():
    """0,4 s é janela ligando acessibilidade — não programa carregando.

    Uma pausa longa viraria espera em toda janela morta, e `--provados` mede
    até 12 de uma vez.
    """
    import re

    fonte = (Path("server") / "arvore_windows.py").read_text(encoding="utf-8")
    casa = re.search(r"PAUSA_DE_DESPERTO = ([0-9.]+)", fonte)
    assert casa, "a pausa precisa de nome e valor"
    assert float(casa.group(1)) <= 0.5


def test_o_resumo_avisa_quando_a_janela_acordou_na_segunda_leitura():
    montada = arvore.montar(
        {
            "janela": {"handle": 77, "titulo": "Arena - Google Chrome", "processo": "chrome.exe"},
            "fonte": "uia",
            "acordou": "esta janela só publicou o conteúdo na segunda leitura.",
            "raiz": _no(9, "Arena", filhos=[_no(30, "Benchmark", "Clicar")]),
        }
    )
    assert "segunda leitura" in arvore.resumo(montada)


def test_a_varredura_geral_diz_quais_acordaram():
    """Para o usuário não achar que precisa rodar duas vezes."""
    texto = (RAIZ / "arvore_sonda.py").read_text(encoding="utf-8")
    assert "Acordaram na segunda leitura" in texto
    assert '"acordou": item.get("acordou", False)' in texto


# ---------------------------------------------------------------------------
# 0.85.0 — os 26 “acionáveis” do Bloco de Notas eram todos moldura
# ---------------------------------------------------------------------------

NOTEPAD_CRU = {
    "janela": {
        "handle": 1,
        "titulo": "Sem título - Bloco de notas",
        "classe": "Notepad",
        "processo": "notepad.exe",
    },
    "fonte": "msaa",
    "raiz": _no(
        10,
        "Sem título - Bloco de notas",
        filhos=[
            _no(
                9,
                "",
                filhos=[
                    _no(1, "", filhos=[  # barra de título
                        _no(43, "IME", "Pressionar"),
                        _no(43, "Minimizar", "Pressionar"),
                        _no(43, "Maximizar", "Pressionar"),
                        _no(43, "Fechar", "Pressionar"),
                    ]),
                    _no(42, "", "digitar"),  # o campo onde se escreve
                    _no(3, "Vertical", filhos=[
                        _no(43, "Uma linha acima", "Pressionar"),
                        _no(43, "Uma página abaixo", "Pressionar"),
                    ]),
                ],
            )
        ],
    ),
}


def _com_caixa(no: dict[str, Any], caixa: list[int]) -> dict[str, Any]:
    no = dict(no)
    no["caixa"] = caixa
    return no


def _bloco_com_posicoes() -> dict[str, Any]:
    bruto = json.loads(json.dumps(NOTEPAD_CRU))
    raiz = bruto["raiz"]
    raiz["caixa"] = [225, 557, 991, 144]
    janela = raiz["filhos"][0]
    janela["caixa"] = [225, 557, 991, 144]
    titulo, texto, rolagem = janela["filhos"]
    titulo["filhos"][0]["caixa"] = [300, 560, 30, 20]
    titulo["filhos"][3]["caixa"] = [1180, 560, 30, 20]
    texto["caixa"] = [227, 559, 970, 140]
    rolagem["caixa"] = [1197, 559, 17, 140]
    return bruto


def test_o_campo_do_bloco_de_notas_ganha_ref():
    """Sem `ref` no campo, o JARVIS não tem onde digitar — só botão de janela.

    A leitura real do Bloco de Notas deu 26 acionáveis: IME, Minimizar,
    Maximizar, Fechar e os botões de rolagem. O `texto` onde se escreve vinha
    sem `ref`, porque a MSAA não dá ação padrão a ele.
    """
    montada = arvore.montar(_bloco_com_posicoes())
    achados = [no for no in arvore.achatar(montada["arvore"]) if no.get("papel") == "texto"]
    assert achados, "o campo de texto precisa estar na árvore"
    assert achados[0]["ref"], "o campo de texto precisa de ref"
    assert achados[0]["acao"] == "digitar"


def test_a_prontidao_aponta_onde_escrever():
    montada = arvore.montar(_bloco_com_posicoes())
    lido = montada["pronto"]
    assert lido["pronto"] is True
    assert lido["editaveis"] == 1
    assert lido["onde_escrever"]["caixa"] == [227, 559, 970, 140]
    assert lido["onde_escrever"]["ref"].startswith("@")
    # E não conta os botões de moldura como “dá para agir”.
    assert lido["com_nome_acionavel"] == 0


def test_a_prontidao_recusa_janela_so_de_moldura_sem_campo():
    """Era o furo: 26 botões de moldura passavam como “dá para agir”."""
    bruto = json.loads(json.dumps(NOTEPAD_CRU))
    # Tira o campo de escrita: sobra só moldura.
    del bruto["raiz"]["filhos"][0]["filhos"][1]
    montada = arvore.montar(bruto)
    lido = montada["pronto"]
    assert lido["pronto"] is False
    assert "moldura" in lido["motivo"]
    assert lido["onde_escrever"] is None


def test_e_moldura_reconhece_botao_de_janela_e_nao_um_link():
    assert arvore.e_moldura({"papel": "botão", "codigo": 43, "nome": "Fechar"}) is True
    assert arvore.e_moldura({"papel": "barra de rolagem", "codigo": 3}) is True
    assert arvore.e_moldura({"papel": "botão", "codigo": 43, "nome": "Salvar"}) is False
    assert arvore.e_moldura({"papel": "link", "codigo": 30, "nome": "Benchmark"}) is False


def test_o_desenho_marca_onde_se_escreve():
    montada = arvore.montar(_bloco_com_posicoes())
    desenho = arvore.desenhar(montada["arvore"])
    assert "(escreve aqui)" in desenho
    assert "em 227,559 (970x140)" in desenho


def test_o_resumo_avisa_quando_todos_os_acionaveis_sao_moldura():
    montada = arvore.montar(_bloco_com_posicoes())
    texto = arvore.resumo(montada)
    assert "Todos os acionáveis são moldura" in texto
    assert "o lugar de escrever é @" in texto


def test_a_msaa_deriva_digitar_do_papel_de_texto_e_respeita_somente_leitura():
    """Papel de texto nem sempre é lugar de escrever: log também é texto."""
    fonte = (Path("server") / "arvore_windows.py").read_text(encoding="utf-8")
    assert "PAPEIS_DE_ESCRITA = {15, 42}" in fonte
    assert "STATE_SYSTEM_READONLY" in fonte
    assert "GET_ACC_STATE = 14" in fonte
    inicio = fonte.index("def _acao_de_escrita(")
    trecho = fonte[inicio : inicio + 500]
    assert "_somente_leitura(" in trecho
    assert '"digitar"' in trecho


def test_a_uia_escreve_no_documento_e_no_campo_de_edicao():
    """O documento (50030) não se clica, mas é onde a digitação entra."""
    fonte = (Path("server") / "arvore_windows.py").read_text(encoding="utf-8")
    inicio = fonte.index("def _uia_acao(")
    trecho = fonte[inicio : inicio + 700]
    assert "50004, 50030" in trecho
    assert "PADRAO_VALOR" in trecho


# ---------------------------------------------------------------------------
# 0.86.0 — agir por `ref`: o braço, com freio
# ---------------------------------------------------------------------------

def _notepad_bruto() -> dict[str, Any]:
    return {
        "janela": {
            "handle": 4242,
            "titulo": "Sem título - Bloco de notas",
            "processo": "notepad.exe",
        },
        "fonte": "msaa",
        "raiz": _no(
            9,
            "",
            filhos=[
                _no(1, "", filhos=[_no(43, "Fechar", "Pressionar")]),
                _com_caixa(_no(42, "", "digitar"), [227, 559, 970, 140]),
            ],
        ),
    }


def _notepad_montado():
    bruto = _notepad_bruto()
    montada = arvore.montar(bruto, com_caminho=True)
    refs = {
        "campo": [n["ref"] for n in arvore.achatar(montada["arvore"]) if n.get("acao") == "digitar"][0],
        "fechar": [n["ref"] for n in arvore.achatar(montada["arvore"]) if n.get("nome") == "Fechar"][0],
    }
    return montada, refs


class LeitorDeAcao:
    """Dublê de `arvore_windows` para a etapa 2."""

    def __init__(self, bruto: dict[str, Any], falha: str = "") -> None:
        self._bruto = bruto
        self._falha = falha
        self.pedidos: list[tuple] = []

    def janelas(self):
        return [self._bruto["janela"]]

    def janela_em_foco(self):
        return self._bruto["janela"]

    def ler_janela(self, handle, profundidade, limite, fonte="auto"):
        return json.loads(json.dumps(self._bruto))

    def executar_ref(self, handle, caminho, acao, texto="", caixa=None, acrescentar=False, mouse=False):
        self.pedidos.append((handle, list(caminho), acao, texto))
        if self._falha:
            raise RuntimeError(self._falha)
        return {"executou": True, "como": "ação padrão do elemento"}


def test_o_montar_guarda_o_caminho_ate_o_elemento():
    """`ref` identifica; o caminho é o que localiza na árvore viva."""
    montada, refs = _notepad_montado()
    campo = [n for n in arvore.achatar(montada["arvore"]) if n["ref"] == refs["campo"]][0]
    assert campo["caminho"] == [1]


def test_sem_executar_nao_toca_em_nada():
    """O plano aparece; o leitor não recebe um único pedido de ação."""
    from server import mesa_agir

    _montada, refs = _notepad_montado()
    leitor = LeitorDeAcao(json.loads(json.dumps(_notepad_bruto())))
    # A montagem perde `com_caminho`; o `agir` remonta com caminho a partir do bruto.
    resposta = mesa_agir.agir(
        ref=refs["campo"], acao="digitar", texto="olá", executar=False, leitor=leitor
    )
    assert resposta["executou"] is False
    assert plano_ok(resposta)
    assert leitor.pedidos == []


def plano_ok(resposta: dict[str, Any]) -> bool:
    plano = resposta["plano"]
    return bool(plano["ref"] and plano["acao"] == "digitar" and plano["texto"] == "olá")


def test_com_executar_a_digitacao_chega_ao_elemento_certo():
    from server import mesa_agir

    _montada, refs = _notepad_montado()
    leitor = LeitorDeAcao(json.loads(json.dumps(_notepad_bruto())))
    resposta = mesa_agir.agir(
        ref=refs["campo"], acao="digitar", texto="olá", executar=True, leitor=leitor
    )
    assert resposta["executou"] is True
    assert leitor.pedidos == [(4242, [1], "digitar", "olá")]


def test_ref_de_leitura_anterior_e_recusado():
    """A tela muda. `ref` antigo não vira alvo por acaso."""
    from server import mesa_agir

    bruto = {
        "janela": {"handle": 1, "titulo": "x", "processo": "notepad.exe"},
        "fonte": "msaa",
        "raiz": _no(9, "", filhos=[_no(43, "Salvar", "Clicar")]),
    }
    with pytest.raises(mesa_agir.AgirError) as erro:
        mesa_agir.planejar(arvore.montar(bruto, com_caminho=True), "@antigo:e99", "clicar")
    assert "não existe nesta leitura" in str(erro.value)
    assert "Refs válidos agora" in str(erro.value)


def test_moldura_e_recusada_como_alvo():
    from server import mesa_agir

    montada, refs = _notepad_montado()
    with pytest.raises(mesa_agir.AgirError) as erro:
        mesa_agir.planejar(montada, refs["fechar"], "clicar")
    assert "moldura" in str(erro.value)


def test_digitar_sem_texto_e_recusado():
    from server import mesa_agir

    montada, refs = _notepad_montado()
    with pytest.raises(mesa_agir.AgirError) as erro:
        mesa_agir.planejar(montada, refs["campo"], "digitar", "   ")
    assert "informe o texto" in str(erro.value)


def test_a_sonda_tem_o_comando_de_agir():
    texto = (RAIZ / "arvore_sonda.py").read_text(encoding="utf-8")
    assert '"--ref"' in texto
    assert '"--executar"' in texto
    assert "mesa_agir.agir(" in texto
    # Sem `--executar`, o comando diz como autorizar — não age calado.
    assert "como_autorizar" in texto or "--executar" in texto


def test_o_executor_nao_move_o_mouse():
    """Você não tem mouse USB e a tela dá toque fantasma.

    A ação tem de vir do elemento (ação padrão / foco), nunca de coordenada.
    Se um dia alguém puser um clique por posição aqui, este teste avisa.
    """
    fonte = (Path("server") / "arvore_windows.py").read_text(encoding="utf-8")
    inicio = fonte.index("def executar_ref(")
    trecho = fonte[inicio : inicio + 3000]
    assert "ACC_DO_DEFAULT_ACTION" in trecho
    assert "_focar(" in trecho
    assert "mesa.clicar(" not in trecho
    assert "mesa.mover(" not in trecho


# ---------------------------------------------------------------------------
# 0.87.0 — escrever sem pedir ref para ninguém
# ---------------------------------------------------------------------------

def test_escrever_acha_o_campo_sozinho():
    """O usuário colou o marcador `@SEU_REF_AQUI` — a culpa foi do comando.

    Copiar código de uma saída para a linha seguinte é trabalho que não devia
    existir: o JARVIS já sabe apontar onde se escreve.
    """
    from server import mesa_agir

    leitor = LeitorDeAcao(json.loads(json.dumps(_notepad_bruto())))
    resposta = mesa_agir.escrever_na_janela(texto="oi, mundo", executar=False, leitor=leitor)
    plano = resposta["plano"]
    assert plano["acao"] == "digitar"
    assert plano["texto"] == "oi, mundo"
    assert plano["caixa"] == [227, 559, 970, 140]
    assert leitor.pedidos == [], "sem executar, nada é tocado"


def test_escrever_com_executar_digita_no_campo_certo():
    from server import mesa_agir

    leitor = LeitorDeAcao(json.loads(json.dumps(_notepad_bruto())))
    resposta = mesa_agir.escrever_na_janela(texto="oi", executar=True, leitor=leitor)
    assert resposta["executou"] is True
    assert leitor.pedidos == [(4242, [1], "digitar", "oi")]


def test_escrever_em_janela_sem_campo_explica_em_vez_de_falhar_mudo():
    from server import mesa_agir

    bruto = {
        "janela": {"handle": 3, "titulo": "Chrome", "processo": "chrome.exe"},
        "fonte": "msaa",
        "raiz": _no(9, "Chrome", filhos=[_no(1, "", filhos=[_no(43, "Fechar", "Pressionar")])]),
    }
    leitor = LeitorDeAcao(json.loads(json.dumps(bruto)))
    with pytest.raises(mesa_agir.AgirError) as erro:
        mesa_agir.escrever_na_janela(texto="oi", leitor=leitor)
    assert "não achei lugar para escrever" in str(erro.value)
    assert "provados" in str(erro.value)


def test_a_sonda_tem_o_atalho_de_escrever():
    texto = (RAIZ / "arvore_sonda.py").read_text(encoding="utf-8")
    assert '"--escrever"' in texto
    assert "mesa_agir.escrever_na_janela(" in texto


def test_erro_na_sonda_sai_legivel_quando_nao_e_json(capsys):
    """`{"erro": ...}` numa linha só é formato de máquina, não de gente."""
    import importlib.util

    caminho = RAIZ / "arvore_sonda.py"
    spec = importlib.util.spec_from_file_location("arvore_sonda_2", caminho)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    assert modulo.principal(["--ref", "@x"]) == 1
    saida = capsys.readouterr().out
    assert saida.strip().startswith("NÃO DEU:")
    assert not saida.strip().startswith("{")


def test_a_skill_mesa_agir_aceita_ref_em_branco():
    texto = (Path("server") / "skill_registry.py").read_text(encoding="utf-8")
    inicio = texto.index("class MesaAgirInput")
    trecho = texto[inicio : inicio + 900]
    assert 'ref: str = Field(default=""' in trecho
    inicio = texto.index("def mesa_agir_handler(")
    trecho = texto[inicio : inicio + 2000]
    assert "escrever_na_janela(" in trecho


# ---------------------------------------------------------------------------
# 0.87.1 — o índice da vtable estava errado, e o JARVIS culpou o Bloco de Notas
# ---------------------------------------------------------------------------

def _fonte_windows() -> str:
    return (Path("server") / "arvore_windows.py").read_text(encoding="utf-8")


def test_os_indices_da_msaa_sao_os_da_oleacc():
    """A 0.86.0 chamava `accNavigate` achando que era `accSelect`.

    Ordem real (oleacc.h): get_accDefaultAction 20, accSelect 21,
    accLocation 22, accNavigate 23, accDoDefaultAction 25, put_accValue 27.
    Um índice trocado vira "o elemento recusou o foco" na tela do usuário —
    mentira com cara de diagnóstico.
    """
    fonte = _fonte_windows()
    assert "ACC_SELECT = 21" in fonte
    assert "ACC_DO_DEFAULT_ACTION = 25" in fonte
    assert "PUT_ACC_VALUE = 27" in fonte
    assert "ACC_SELECT = 23" not in fonte
    assert "ACC_DO_DEFAULT_ACTION = 21" not in fonte
    # accLocation continua 22 — esse sempre esteve certo.
    assert "ACC_LOCATION = 22" in fonte


def test_digitar_tem_tres_degraus_e_nao_digita_as_cegas():
    fonte = _fonte_windows()
    inicio = fonte.index("def _digitar_em(")
    fim = fonte.index("def executar_ref(")
    trecho = fonte[inicio:fim]
    # na ordem: elemento → campo inteiro → valor
    um = trecho.index("_selecionar(alvo, filho)")
    dois = trecho.index("_selecionar(alvo, CHILDID_SELF)")
    tres = trecho.index("_por_valor(alvo, filho, final)")
    assert um < dois < tres
    # teclado só depois de confirmar que o foco é da janela alvo
    assert trecho.count("_teclado_esta_na_janela(handle)") >= 2
    for posicao in [i for i in range(len(trecho)) if trecho.startswith("mesa.digitar(", i)]:
        assert trecho.rfind("_teclado_esta_na_janela", 0, posicao) != -1
    # e não sobrescreve campo com texto sem permissão explícita
    assert "não sobrescrevo o que não escrevi" in trecho
    assert "if atual.strip() and not acrescentar:" in trecho


def test_o_plano_mostra_o_nome_da_janela():
    """Saía `janela: —` na tela: `montar` devolve `alvo`, não `janela`."""
    from server import mesa_agir

    montada, refs = _notepad_montado()
    assert "janela" not in montada
    plano = mesa_agir.planejar(montada, refs["campo"], "digitar", "oi")
    assert plano["janela"], "a janela aparecia como — na tela"
    assert plano["janela"] in montada["alvo"], "o título tem de vir do alvo lido"
    assert "notepad.exe" in plano["processo"]


def test_a_resposta_nao_diz_feito_sem_ter_visto_o_texto():
    """"Mandei as teclas" não é "o texto entrou"."""
    from server import mesa_agir

    class LeitorCego(LeitorDeAcao):
        def __init__(self, bruto, conferido):
            super().__init__(bruto)
            self.conferido = conferido

        def executar_ref(self, handle, caminho, acao, texto="", caixa=None, acrescentar=False, mouse=False):
            self.pedidos.append((handle, list(caminho), acao, texto))
            return {"executou": True, "como": "foco + teclado", "conferido": self.conferido}

    for conferido, esperado in [(True, "conferi"), (False, "não mostrou o texto"), (None, "Feito")]:
        leitor = LeitorCego(json.loads(json.dumps(_notepad_bruto())), conferido)
        resposta = mesa_agir.escrever_na_janela(texto="oi", executar=True, leitor=leitor)
        assert esperado in resposta["resumo"]


# ---------------------------------------------------------------------------
# 0.88.0 — na segunda vez o campo já tem texto
# ---------------------------------------------------------------------------

def test_o_terceiro_degrau_preserva_o_que_ja_estava_no_campo():
    """`put_accValue` **substitui**. Escrever por cima apaga o trabalho da pessoa."""
    # Não se importa `arvore_windows` aqui: ele é Windows puro, e a regra mora
    # no texto do arquivo — que é o que se pode conferir fora do Windows.
    fonte = _fonte_windows()
    inicio = fonte.index("def _digitar_em(")
    trecho = fonte[inicio : fonte.index("def executar_ref(")]
    assert "final = (atual + texto) if atual.strip() else texto" in trecho
    assert "_por_valor(alvo, filho, final)" in trecho
    assert "acrescentou" in trecho
    # o executor precisa aceitar a opção, senão o caminho morre em TypeError
    assert "def executar_ref(" in fonte
    assert "acrescentar: bool = False" in fonte


def test_acrescentar_pede_licenca_antes_de_mexer_em_campo_com_texto():
    from server import mesa_agir

    class LeitorDeCampoCheio(LeitorDeAcao):
        """Simula o Bloco de Notas com “oi, mundo” já escrito."""

        def __init__(self, bruto):
            super().__init__(bruto)
            self.recebido: dict = {}

        def executar_ref(self, handle, caminho, acao, texto="", caixa=None, acrescentar=False, mouse=False):
            self.pedidos.append((handle, list(caminho), acao, texto))
            self.recebido = {"texto": texto, "acrescentar": acrescentar}
            return {"executou": True, "como": "valor do campo", "conferido": True}

    leitor = LeitorDeCampoCheio(json.loads(json.dumps(_notepad_bruto())))
    mesa_agir.escrever_na_janela(texto=" de novo", executar=True, leitor=leitor, acrescentar=True)
    assert leitor.recebido == {"texto": " de novo", "acrescentar": True}


def test_a_sonda_tem_a_opcao_de_acrescentar():
    texto = (RAIZ / "arvore_sonda.py").read_text(encoding="utf-8")
    assert '"--acrescentar"' in texto
    assert "acrescentar=args.acrescentar" in texto


def test_a_skill_mesa_agir_tem_acrescentar():
    texto = (Path("server") / "skill_registry.py").read_text(encoding="utf-8")
    inicio = texto.index("class MesaAgirInput")
    assert "acrescentar: bool" in texto[inicio : inicio + 1200]
    inicio = texto.index("def mesa_agir_handler(")
    assert "acrescentar=bool(data.acrescentar)" in texto[inicio : inicio + 2000]


def test_o_nome_da_janela_nao_sai_duplicado():
    """Na tela saiu `notepad.exe — notepad.exe — Sem título - Bloco de notas`."""
    from server import mesa_agir

    montada, refs = _notepad_montado()
    plano = mesa_agir.planejar(montada, refs["campo"], "digitar", "oi")
    assert plano["processo"] == "notepad.exe"
    assert not plano["janela"].startswith("notepad.exe")
    assert plano["janela"] == "Sem título - Bloco de notas"
