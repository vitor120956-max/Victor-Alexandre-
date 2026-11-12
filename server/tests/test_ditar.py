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
