"""Testes do ditar num programa: abrir se preciso, escrever e conferir (0.89.0).

A 0.88.0 escrevia numa janela que já estava aberta. Aqui a janela pode não
existir ainda — e o teste que importa é o de que **sem `executar` nada é
aberto**: abrir programa por conta própria num plano seria o oposto de pedir
autorização.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from server import arvore, mesa_agir, mesa_ditar, pc

RAIZ = Path(__file__).resolve().parents[2]


def _no(papel: int, nome: str = "", filhos: list | None = None, acao: str = "", caixa: list | None = None) -> dict:
    no: dict[str, Any] = {"papel": papel, "nome": nome}
    if filhos:
        no["filhos"] = filhos
    if acao:
        no["acao"] = acao
    if caixa:
        no["caixa"] = caixa
    return no


def _janela_notepad() -> dict[str, Any]:
    return {"handle": 4242, "titulo": "Sem título - Bloco de notas", "processo": "notepad.exe"}


def _bruto_notepad() -> dict[str, Any]:
    campo = _no(42, "", acao="digitar", caixa=[227, 559, 970, 140])
    return {
        "janela": _janela_notepad(),
        "fonte": "msaa",
        "raiz": _no(9, "Sem título - Bloco de notas", filhos=[_no(1, "", filhos=[campo])]),
    }


class LeitorAberto:
    """A janela já existe: só lê e registra o que seria executado."""

    def __init__(self, bruto: dict[str, Any]) -> None:
        self._bruto = bruto
        self.pedidos: list[tuple] = []

    def janelas(self):
        return [self._bruto["janela"]]

    def janela_em_foco(self):
        return self._bruto["janela"]

    def ler_janela(self, handle, profundidade, limite, fonte="auto"):
        return json.loads(json.dumps(self._bruto))

    def abrir(self, nome) -> None:  # pragma: no cover - não é chamado aqui
        raise AssertionError(f"não devia abrir {nome!r}: já está aberto")

    def executar_ref(self, handle, caminho, acao, texto="", caixa=None, acrescentar=False):
        self.pedidos.append((handle, list(caminho), acao, texto, acrescentar))
        return {"executou": True, "como": "valor do campo", "conferido": True}


class LeitorFechado(LeitorAberto):
    """Nada aberto no começo; abre quando o `abrir` é chamado."""

    def __init__(self, bruto: dict[str, Any], abrir_ao_chamar: bool = True) -> None:
        super().__init__(bruto)
        self._abriu = False
        self._abrir_ao_chamar = abrir_ao_chamar

    def janelas(self):
        return [self._bruto["janela"]] if self._abriu else []

    def abrir(self, nome) -> None:
        if self._abrir_ao_chamar:
            self._abriu = True

    def ler_janela(self, handle, profundidade, limite, fonte="auto"):
        assert self._abriu, "leu a janela sem ela existir"
        return super().ler_janela(handle, profundidade, limite, fonte)


def _sem_espera(*_args, **_kwargs) -> None:
    return None


def test_sem_executar_nada_e_aberto_nem_escrito():
    """Plano é plano: abrir um programa já é agir."""
    leitor = LeitorFechado(_bruto_notepad())
    resposta = mesa_ditar.ditar(
        programa="bloco de notas",
        texto="oi, mundo",
        executar=False,
        leitor=leitor,
        abrir=leitor.abrir,
        dormir=_sem_espera,
    )
    assert resposta["ok"] is True
    assert resposta["executou"] is False
    assert resposta["precisa_abrir"] is True
    assert "nada foi aberto" in resposta["resumo"].lower()
    assert leitor.pedidos == []


def test_ditar_abre_a_janela_quando_ela_nao_existe():
    leitor = LeitorFechado(_bruto_notepad())
    resposta = mesa_ditar.ditar(
        programa="bloco de notas",
        texto="oi, mundo",
        executar=True,
        leitor=leitor,
        abrir=leitor.abrir,
        dormir=_sem_espera,
    )
    assert resposta["abriu"] is True
    assert resposta["executou"] is True
    assert resposta["programa"] == "notepad"
    assert resposta["rotulo"] == "Bloco de notas"
    assert resposta["resumo"].startswith("Abri o Bloco de notas.")
    assert leitor.pedidos and leitor.pedidos[0][2] == "digitar"
    assert leitor.pedidos[0][3] == "oi, mundo"


def test_janela_que_nao_aparece_e_dita_com_saida():
    leitor = LeitorFechado(_bruto_notepad(), abrir_ao_chamar=False)
    with pytest.raises(mesa_ditar.DitarError) as erro:
        mesa_ditar.ditar(
            programa="bloco de notas",
            texto="oi",
            executar=True,
            leitor=leitor,
            abrir=leitor.abrir,
            espera=0,
            dormir=_sem_espera,
        )
    assert "nenhuma janela dele apareceu" in str(erro.value)


def test_programa_fora_da_lista_e_recusado_com_a_lista():
    leitor = LeitorAberto(_bruto_notepad())
    with pytest.raises(mesa_ditar.DitarError) as erro:
        mesa_ditar.ditar(programa="word", texto="oi", leitor=leitor, abrir=leitor.abrir)
    assert "Não abro" in str(erro.value)
    assert "notepad" in str(erro.value)


def test_janela_do_programa_casa_pelo_processo_e_pelo_rotulo():
    janelas = [
        {"handle": 1, "titulo": "Qualquer coisa", "processo": "chrome.exe"},
        {"handle": 2, "titulo": "Sem título - Bloco de notas", "processo": "notepad.exe"},
    ]
    assert mesa_ditar.janela_do_programa(janelas, "notepad.exe", "Bloco de notas")["handle"] == 2
    so_titulo = [{"handle": 3, "titulo": "Bloco de notas", "processo": ""}]
    assert mesa_ditar.janela_do_programa(so_titulo, "notepad.exe", "Bloco de notas")["handle"] == 3
    assert mesa_ditar.janela_do_programa(janelas, "mspaint.exe", "Paint") is None


def test_esperar_janela_termina_quando_o_tempo_acaba():
    leitor = LeitorFechado(_bruto_notepad(), abrir_ao_chamar=False)
    assert mesa_ditar.esperar_janela(leitor, "notepad.exe", "Bloco de notas", segundos=0, dormir=_sem_espera) is None


def test_acrescentar_chega_ate_o_executor():
    leitor = LeitorAberto(_bruto_notepad())
    mesa_ditar.ditar(
        programa="bloco de notas",
        texto=" de novo",
        executar=True,
        acrescentar=True,
        leitor=leitor,
        abrir=leitor.abrir,
    )
    assert leitor.pedidos[0][4] is True, "a opção tem de atravessar até o executor"


def test_o_pc_sabe_resolver_sem_abrir():
    info = pc.resolver("bloco de notas")
    assert info == {"chave": "notepad", "executavel": "notepad.exe", "rotulo": "Bloco de notas"}


def test_a_sonda_tem_o_atalho_do_programa():
    texto = (RAIZ / "arvore_sonda.py").read_text(encoding="utf-8")
    assert '"--programa"' in texto
    assert "mesa_ditar.ditar(" in texto


def test_a_skill_mesa_ditar_existe_e_pede_confirmacao():
    from server import skill_registry

    registro = skill_registry.build_registry(RAIZ / "storage" / "user-files")
    itens = {item["id"]: item for item in registro.list()}
    assert "mesa.ditar" in itens
    ditar = itens["mesa.ditar"]
    assert ditar["requiresConfirmation"] is True
    assert "texto" in (ditar.get("inputSchema") or {}).get("properties", {})
    assert "programa" in (ditar.get("inputSchema") or {}).get("properties", {})
    # a descrição tem de dizer que sem executar nada acontece
    assert "executar" in ditar["description"]


# ---------------------------------------------------------------------------
# 0.89.1 — a janela existe antes do campo: esperar o campo, não a janela
# ---------------------------------------------------------------------------

class LeitorQueDemora:
    """A janela aparece na hora; o campo só nasce depois de N leituras.

    Foi o que aconteceu na medição real da 0.89.0: janela achada, leitura
    devolvendo 12 elementos de moldura, e o comando morrendo com "não achei
    lugar para escrever" — que era verdade por meio segundo e mentira no
    segundo seguinte.
    """

    def __init__(self, bruto: dict[str, Any], leituras_ate_o_campo: int) -> None:
        self._bruto = bruto
        self._restantes = leituras_ate_o_campo
        self.leituras = 0
        self.pedidos: list[tuple] = []

    def janelas(self):
        return [self._bruto["janela"]]

    def janela_em_foco(self):
        return self._bruto["janela"]

    def ler_janela(self, handle, profundidade, limite, fonte="auto"):
        self.leituras += 1
        bruto = json.loads(json.dumps(self._bruto))
        if self._restantes > 0:
            self._restantes -= 1
            # Só a moldura da janela: nada de campo de escrita.
            bruto["raiz"] = _no(9, "Sem título - Bloco de notas", filhos=[_no(1, "", filhos=[_no(43, "Fechar", "Pressionar")])])
        return bruto

    def executar_ref(self, handle, caminho, acao, texto="", caixa=None, acrescentar=False):
        self.pedidos.append((handle, list(caminho), acao, texto, acrescentar))
        return {"executou": True, "como": "valor do campo", "conferido": True}


def test_espera_o_campo_aparecer_em_vez_de_desistir_da_janela():
    leitor = LeitorQueDemora(_bruto_notepad(), leituras_ate_o_campo=3)
    resposta = mesa_ditar.ditar(
        programa="bloco de notas",
        texto="oi, mundo",
        executar=True,
        leitor=leitor,
        abrir=lambda _nome: None,
        dormir=_sem_espera,
    )
    assert resposta["executou"] is True
    assert leitor.leituras >= 4, "tinha de reler até o campo existir"
    assert leitor.pedidos and leitor.pedidos[0][3] == "oi, mundo"


def test_campo_que_nunca_aparece_diz_que_esperou_e_para():
    leitor = LeitorQueDemora(_bruto_notepad(), leituras_ate_o_campo=999)
    with pytest.raises(mesa_ditar.DitarError) as erro:
        mesa_ditar.ditar(
            programa="bloco de notas",
            texto="oi",
            executar=True,
            leitor=leitor,
            abrir=lambda _nome: None,
            espera_campo=0,
            dormir=_sem_espera,
        )
    mensagem = str(erro.value)
    assert "não publicou nenhum lugar de escrever" in mensagem
    assert "--provados" in mensagem
    assert leitor.pedidos == [], "nada pode ser executado sem campo"


def test_sem_executar_espera_o_campo_e_mostra_o_plano():
    leitor = LeitorQueDemora(_bruto_notepad(), leituras_ate_o_campo=2)
    resposta = mesa_ditar.ditar(
        programa="bloco de notas",
        texto="oi",
        executar=False,
        leitor=leitor,
        dormir=_sem_espera,
    )
    assert resposta["executou"] is False
    assert resposta["plano"]["acao"] == "digitar"
    assert leitor.pedidos == []


def test_janela_sem_titulo_nao_e_a_janela_do_programa():
    """Processo nascendo ≠ janela pronta: sem título, é o vazio."""
    janelas = [
        {"handle": 1, "titulo": "", "processo": "notepad.exe"},
        {"handle": 2, "titulo": "Sem título - Bloco de notas", "processo": "notepad.exe"},
    ]
    assert mesa_ditar.janela_do_programa(janelas, "notepad.exe", "Bloco de notas")["handle"] == 2
    assert mesa_ditar.janela_do_programa(janelas[:1], "notepad.exe", "Bloco de notas") is None


def test_com_dois_blocos_de_notas_o_texto_vai_para_a_janela_certa():
    """Escolher duas vezes é escolher errado uma vez.

    Havia dois `notepad.exe`: um aberto e vazio, outro com o texto. O `ditar`
    achava um e a ação escolhia o outro pela mesma regra de novo — e o texto
    caía no primeiro da lista.
    """
    vazio = {
        "janela": {"handle": 100, "titulo": "Sem título - Bloco de notas", "processo": "notepad.exe"},
        "fonte": "msaa",
        "raiz": _no(9, "Sem título - Bloco de notas", filhos=[_no(1, "", filhos=[_no(43, "Fechar", "Pressionar")])]),
    }
    cheio = _bruto_notepad()
    cheio["janela"] = {"handle": 200, "titulo": "notas.txt - Bloco de notas", "processo": "notepad.exe"}

    class DoisBlocos:
        def __init__(self):
            self.pedidos = []

        def janelas(self):
            return [vazio["janela"], cheio["janela"]]

        def janela_em_foco(self):
            return vazio["janela"]

        def ler_janela(self, handle, profundidade, limite, fonte="auto"):
            return json.loads(json.dumps(cheio if int(handle) == 200 else vazio))

        def executar_ref(self, handle, caminho, acao, texto="", caixa=None, acrescentar=False):
            self.pedidos.append((handle, texto))
            return {"executou": True, "como": "valor do campo", "conferido": True}

    leitor = DoisBlocos()
    resposta = mesa_ditar.ditar(
        programa="bloco de notas",
        texto="oi",
        executar=True,
        leitor=leitor,
        abrir=lambda _nome: None,
        dormir=_sem_espera,
    )
    # Havia duas janelas do mesmo processo e só uma publica campo: escrever na
    # primeira que aparece é sorteio, e o sorteio deu errado na medição real.
    assert leitor.pedidos == [(200, "oi")], "o texto tem de ir para a janela que publica o campo"
    assert resposta["executou"] is True


def test_aguentar_janela_fechada_no_meio_da_espera():
    from server import mesa_agir

    class Sumiu:
        def janelas(self):
            return []

        def janela_em_foco(self):
            return None

        def ler_janela(self, *a, **k):
            raise AssertionError("não devia ler")

    with pytest.raises(mesa_agir.AgirError) as erro:
        mesa_agir.escrever_na_janela(texto="oi", leitor=Sumiu(), handle=999)
    assert "não está mais aberta" in str(erro.value)


def test_escrever_sem_handle_tenta_a_outra_janela_do_mesmo_programa():
    """Com `--alvo notepad.exe` e dois Blocos de Notas, tentar só o primeiro é meio caminho."""
    vazio = {
        "janela": {"handle": 100, "titulo": "Sem título - Bloco de notas", "processo": "notepad.exe"},
        "fonte": "msaa",
        "raiz": _no(9, "Sem título - Bloco de notas", filhos=[_no(1, "", filhos=[_no(43, "Fechar", "Pressionar")])]),
    }
    cheio = _bruto_notepad()
    cheio["janela"] = {"handle": 200, "titulo": "notas.txt - Bloco de notas", "processo": "notepad.exe"}

    class DoisBlocos:
        def __init__(self):
            self.leituras = []
            self.pedidos = []

        def janelas(self):
            return [vazio["janela"], cheio["janela"]]

        def janela_em_foco(self):
            return vazio["janela"]

        def ler_janela(self, handle, profundidade, limite, fonte="auto"):
            self.leituras.append(int(handle))
            return json.loads(json.dumps(cheio if int(handle) == 200 else vazio))

        def executar_ref(self, handle, caminho, acao, texto="", caixa=None, acrescentar=False):
            self.pedidos.append((handle, texto))
            return {"executou": True, "como": "valor do campo", "conferido": True}

    leitor = DoisBlocos()
    resposta = mesa_agir.escrever_na_janela(
        texto="oi", executar=True, leitor=leitor, alvo="notepad.exe"
    )
    assert 100 in leitor.leituras and 200 in leitor.leituras, "tinha de olhar as duas"
    assert leitor.pedidos == [(200, "oi")]
    assert resposta["executou"] is True
