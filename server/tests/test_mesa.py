"""Testes da mesa (0.53.0): mouse e teclado com dublê — nada toca na tela real."""
from __future__ import annotations

from typing import Any

import pytest

from server import mesa


class BackendFalso:
    """Registra o que o JARVIS mandaria fazer, sem tocar no cursor de ninguém."""

    def __init__(self, largura: int = 1920, altura: int = 1080, inicio: tuple[int, int] = (0, 0)) -> None:
        self.largura = largura
        self.altura = altura
        self.atual = inicio
        self.movimentos: list[tuple[int, int]] = []
        self.cliques: list[tuple[str, int]] = []
        self.teclas: list[str] = []
        self.textos: list[str] = []
        self.focadas: list[str] = []
        self.janelas_abertas = ["Bloco de Notas - teste.txt", "Google Chrome"]
        self.dono_mexeu = False
        self._dormiu = 0.0

    def posicao(self) -> tuple[int, int]:
        if self.dono_mexeu and self.movimentos:
            self.atual = (500, 500)  # simula a mão do dono indo para outro canto
            self.dono_mexeu = False
        return self.atual

    def tamanho(self) -> tuple[int, int]:
        return self.largura, self.altura

    def mover(self, x: int, y: int) -> None:
        self.atual = (x, y)
        self.movimentos.append((x, y))

    def clicar(self, botao: str, vezes: int) -> None:
        self.cliques.append((botao, vezes))

    def teclar(self, nome: str) -> None:
        self.teclas.append(nome)

    def digitar(self, texto: str) -> None:
        self.textos.append(texto)

    def janelas(self) -> list[str]:
        return list(self.janelas_abertas)

    def focar(self, trecho: str) -> str:
        for titulo in self.janelas_abertas:
            if trecho.lower() in titulo.lower():
                self.focadas.append(titulo)
                return titulo
        raise mesa.MesaError(f"Nenhuma janela com “{trecho}” no título está aberta.")

    def dormir(self, segundos: float) -> None:
        self._dormiu += segundos


# --------------------------------------------------------------------- status

def test_status_mostra_tela_e_janelas() -> None:
    retrato = mesa.status(BackendFalso(1920, 1080, (100, 200)))
    assert retrato["suportado"] is True
    assert (retrato["x"], retrato["y"]) == (100, 200)
    assert (retrato["largura"], retrato["altura"]) == (1920, 1080)
    assert "Google Chrome" in retrato["janelas"]


def test_status_fora_do_windows_nao_quebra() -> None:
    retrato = mesa.status()
    assert retrato["suportado"] is False
    assert "Windows" in retrato["motivo"]


# ---------------------------------------------------------------------- mover

def test_mover_chega_no_destino() -> None:
    backend = BackendFalso()
    resultado = mesa.mover(800, 600, duracao=0.1, backend=backend)
    assert resultado["interrompido"] is False
    assert backend.atual == (800, 600)
    assert resultado["para"] == [800, 600]
    assert backend.movimentos[-1] == (800, 600)


def test_mover_para_fora_da_tela_nao_move_nada() -> None:
    backend = BackendFalso(800, 600)
    with pytest.raises(mesa.MesaError) as erro:
        mesa.mover(900, 100, backend=backend)
    assert "fora da tela" in str(erro.value)
    assert backend.movimentos == []


def test_mover_para_se_o_dono_mexer_no_mouse() -> None:
    backend = BackendFalso(inicio=(0, 0))
    backend.dono_mexeu = True
    resultado = mesa.mover(1000, 1000, duracao=0.2, backend=backend)
    assert resultado["interrompido"] is True
    assert "mexeu o mouse" in resultado["motivo"]


def test_mover_sem_failsafe_ignora_o_dono() -> None:
    backend = BackendFalso()
    backend.dono_mexeu = True
    resultado = mesa.mover(1000, 1000, duracao=0.1, backend=backend, failsafe=False)
    assert resultado["interrompido"] is False


# --------------------------------------------------------------------- clicar

def test_clicar_sem_coordenada_clica_onde_esta() -> None:
    backend = BackendFalso(inicio=(300, 400))
    resultado = mesa.clicar(backend=backend)
    assert resultado["clicou"] is True
    assert backend.cliques == [("esquerdo", 1)]
    assert backend.movimentos == []


def test_clicar_com_coordenada_move_antes() -> None:
    backend = BackendFalso()
    resultado = mesa.clicar(50, 60, botao="direito", vezes=2, backend=backend)
    assert resultado["movido"] is True
    assert backend.atual == (50, 60)
    assert backend.cliques == [("direito", 2)]


def test_clicar_nao_clica_se_o_mover_foi_interrompido() -> None:
    backend = BackendFalso()
    backend.dono_mexeu = True
    resultado = mesa.clicar(900, 900, backend=backend)
    assert resultado["clicou"] is False
    assert backend.cliques == []


def test_clicar_recusa_botao_desconhecido() -> None:
    with pytest.raises(mesa.MesaError):
        mesa.clicar(botao="dedao", backend=BackendFalso())


def test_clicar_recusa_quatro_cliques() -> None:
    with pytest.raises(mesa.MesaError):
        mesa.clicar(vezes=4, backend=BackendFalso())


# --------------------------------------------------------------- teclado/texto

def test_digitar_manda_o_texto() -> None:
    backend = BackendFalso()
    resultado = mesa.digitar("Olá, ação", backend=backend)
    assert backend.textos == ["Olá, ação"]
    assert resultado["caracteres"] == 9


def test_digitar_recusa_texto_vazio() -> None:
    with pytest.raises(mesa.MesaError):
        mesa.digitar("   ", backend=BackendFalso())


def test_digitar_recusa_texto_gigante() -> None:
    with pytest.raises(mesa.MesaError):
        mesa.digitar("a" * 2_001, backend=BackendFalso())


def test_teclar_atalho_conhecido() -> None:
    backend = BackendFalso()
    assert mesa.teclar("CTRL+C", backend=backend)["tecla"] == "ctrl+c"
    assert backend.teclas == ["ctrl+c"]


def test_teclar_recusa_tecla_desconhecida() -> None:
    with pytest.raises(mesa.MesaError) as erro:
        mesa.teclar("tecla-do-destino", backend=BackendFalso())
    assert "Tecla desconhecida" in str(erro.value)


def test_teclas_nao_tem_codigo_repetido_por_engano() -> None:
    assert mesa.TECLAS["enter"] == (0x0D,)
    assert mesa.TECLAS["ctrl+v"] == (0x11, 0x56)


# ---------------------------------------------------------------------- focar

def test_focar_encontra_pelo_pedaco_do_titulo() -> None:
    backend = BackendFalso()
    resultado = mesa.focar("bloco de notas", backend=backend)
    assert "Bloco de Notas" in resultado["janela"]


def test_focar_recusa_janela_que_nao_existe() -> None:
    with pytest.raises(mesa.MesaError) as erro:
        mesa.focar("excel", backend=BackendFalso())
    assert "Nenhuma janela" in str(erro.value)
