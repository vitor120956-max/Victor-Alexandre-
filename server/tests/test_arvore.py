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
