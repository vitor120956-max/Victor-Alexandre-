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

    def executar_ref(self, handle, caminho, acao, texto="", caixa=None, acrescentar=False, mouse=False):
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

    def executar_ref(self, handle, caminho, acao, texto="", caixa=None, acrescentar=False, mouse=False):
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

        def executar_ref(self, handle, caminho, acao, texto="", caixa=None, acrescentar=False, mouse=False):
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

        def executar_ref(self, handle, caminho, acao, texto="", caixa=None, acrescentar=False, mouse=False):
            self.pedidos.append((handle, texto))
            return {"executou": True, "como": "valor do campo", "conferido": True}

    leitor = DoisBlocos()
    resposta = mesa_agir.escrever_na_janela(
        texto="oi", executar=True, leitor=leitor, alvo="notepad.exe"
    )
    assert 100 in leitor.leituras and 200 in leitor.leituras, "tinha de olhar as duas"
    assert leitor.pedidos == [(200, "oi")]
    assert resposta["executou"] is True


# ---------------------------------------------------------------------------
# 0.89.2 — a janela minimizada publica só moldura (12 elementos)
# ---------------------------------------------------------------------------

def test_minimizada_vai_para_o_fim_da_lista():
    """Minimizada publica 12 elementos de moldura — não é a que serve."""
    janelas = [
        {"handle": 1, "titulo": "Sem título - Bloco de notas", "processo": "notepad.exe", "minimizada": True},
        {"handle": 2, "titulo": "notas.txt - Bloco de notas", "processo": "notepad.exe", "minimizada": False},
    ]
    achadas = mesa_ditar.janelas_do_programa(janelas, "notepad.exe", "Bloco de notas")
    assert [j["handle"] for j in achadas] == [2, 1]
    assert mesa_ditar.janela_do_programa(janelas, "notepad.exe", "Bloco de notas")["handle"] == 2


def test_programa_aberto_usa_o_pid_que_nasceu_da_abertura():
    """O que eu abri é a janela nova — não o Bloco de Notas velho da tarefa."""
    class Processo:
        pid = 777

    class LeitorComVelho:
        """Antes de abrir não havia janela; depois, a velha e a nova."""

        def __init__(self):
            self._abriu = False
            self.leituras = []
            self.pedidos = []

        def janelas(self):
            if not self._abriu:
                return []
            velho = {"handle": 10, "titulo": "velho - Bloco de notas", "processo": "notepad.exe", "pid": 111}
            novo = {"handle": 20, "titulo": "Sem título - Bloco de notas", "processo": "notepad.exe", "pid": 777}
            return [velho, novo]

        def abrir(self, _nome):
            self._abriu = True
            return Processo()

        def janela_em_foco(self):
            return None

        def ler_janela(self, handle, profundidade, limite, fonte="auto"):
            self.leituras.append(int(handle))
            bruto = json.loads(json.dumps(_bruto_notepad()))
            bruto["janela"] = {"handle": int(handle), "titulo": "Sem título - Bloco de notas", "processo": "notepad.exe"}
            return bruto

        def executar_ref(self, handle, caminho, acao, texto="", caixa=None, acrescentar=False, mouse=False):
            self.pedidos.append((handle, texto))
            return {"executou": True, "como": "valor do campo", "conferido": True}

    leitor = LeitorComVelho()
    resposta = mesa_ditar.ditar(
        programa="bloco de notas",
        texto="oi",
        executar=True,
        leitor=leitor,
        abrir=leitor.abrir,
        dormir=_sem_espera,
    )
    assert resposta["abriu"] is True
    assert leitor.pedidos == [(20, "oi")], "o pid novo é a janela que eu abri"


def test_o_erro_mostra_o_retrato_de_cada_janela():
    """“não achei lugar para escrever” sozinho não diz o que olhar."""
    somente_moldura = {
        "janela": {"handle": 10, "titulo": "Sem título - Bloco de notas", "processo": "notepad.exe", "minimizada": True},
        "fonte": "msaa",
        "raiz": _no(9, "Sem título - Bloco de notas", filhos=[_no(1, "", filhos=[_no(43, "Fechar", "Pressionar")])]),
    }

    class SoMoldura(LeitorAberto):
        def __init__(self):
            super().__init__(somente_moldura)

        def abrir(self, nome):
            return None

    leitor = SoMoldura()
    with pytest.raises(mesa_ditar.DitarError) as erro:
        mesa_ditar.ditar(
            programa="bloco de notas",
            texto="oi",
            executar=True,
            leitor=leitor,
            abrir=leitor.abrir,
            espera_campo=0,
            dormir=_sem_espera,
        )
    mensagem = str(erro.value)
    assert "Janelas que eu vi" in mensagem
    assert "minimizada" in mensagem
    assert "sem campo" in mensagem


def test_a_sonda_mostra_as_janelas_do_programa_sem_escrever():
    import importlib.util

    caminho = RAIZ / "arvore_sonda.py"
    spec = importlib.util.spec_from_file_location("arvore_sonda_prog", caminho)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)

    class Leitor:
        def janelas(self):
            return [
                {"handle": 10, "titulo": "velho - Bloco de notas", "processo": "notepad.exe", "pid": 1, "minimizada": True},
                {"handle": 20, "titulo": "Sem título - Bloco de notas", "processo": "notepad.exe", "pid": 2, "minimizada": False},
            ]

        def ler_janela(self, handle, profundidade, limite, fonte="auto"):
            if int(handle) == 10:
                return {
                    "janela": {"handle": 10, "titulo": "velho - Bloco de notas"},
                    "fonte": "msaa",
                    "raiz": _no(9, "velho", filhos=[_no(43, "Fechar", "Pressionar")]),
                }
            return json.loads(json.dumps(_bruto_notepad()))

    class Args:
        programa = "bloco de notas"
        profundidade = 6
        limite = 600
        fonte = "auto"
        json = False

    codigo = modulo._janelas_do_programa(Leitor(), Args(), mesa_ditar)
    assert codigo == 0


def test_janela_minimizada_e_restaurada_sem_mouse():
    """Minimizada publica 12 elementos — e não é preciso clicar nela."""
    mini = {
        "janela": {"handle": 10, "titulo": "Sem título - Bloco de notas", "processo": "notepad.exe", "minimizada": True},
        "fonte": "msaa",
        "raiz": _no(9, "Sem título - Bloco de notas", filhos=[_no(1, "", filhos=[_no(43, "Fechar", "Pressionar")])]),
    }
    normal = _bruto_notepad()
    normal["janela"] = {"handle": 10, "titulo": "Sem título - Bloco de notas", "processo": "notepad.exe"}

    class LeitorMinimizado(LeitorAberto):
        def __init__(self):
            super().__init__(mini)
            self.restaurado = []

        def restaurar(self, handle):
            self.restaurado.append(int(handle))
            return True

        def ler_janela(self, handle, profundidade, limite, fonte="auto"):
            consta = self.restaurado
            return json.loads(json.dumps(normal if consta else mini))

    leitor = LeitorMinimizado()
    resposta = mesa_ditar.ditar(
        programa="bloco de notas",
        texto="oi",
        executar=True,
        leitor=leitor,
        dormir=_sem_espera,
    )
    assert leitor.restaurado == [10], "tinha de restaurar a janela, não abrir outra"
    assert resposta["restaurada"] is True
    assert resposta["resumo"].startswith("Restaurei a janela do Bloco de notas.")
    assert leitor.pedidos and leitor.pedidos[0][3] == "oi"


def test_sem_executar_so_avisa_que_restauraria():
    mini = {
        "janela": {"handle": 10, "titulo": "Sem título - Bloco de notas", "processo": "notepad.exe", "minimizada": True},
        "fonte": "msaa",
        "raiz": _no(9, "x", filhos=[_no(43, "Fechar", "Pressionar")]),
    }
    leitor = LeitorAberto(mini)
    resposta = mesa_ditar.ditar(programa="bloco de notas", texto="oi", executar=False, leitor=leitor)
    assert resposta["precisa_restaurar"] is True
    assert "restauraria" in resposta["resumo"]
    assert leitor.pedidos == []


# ---------------------------------------------------------------------------
# 0.89.3 — a “janela do Bloco de notas” era o próprio terminal
# ---------------------------------------------------------------------------

def test_o_terminal_que_roda_o_comando_nao_e_o_programa():
    """O título do cmd é a linha de comando — e a linha diz “bloco de notas”.

    Na 0.89.2 o JARVIS abriu a janela do cmd, leu 12 elementos de moldura e
    disse que o Bloco de notas não aceita escrita. O Bloco de notas nem estava
    aberto: o que existia era o comando com o nome dele escrito no título.
    """
    janelas = [
        {
            "handle": 1,
            "titulo": 'C:\\Windows\\system32\\cmd.exe - .venv\\Scripts\\python arvore_sonda.py --programa "bloco de notas"',
            "processo": "cmd.exe",
            "pid": 10,
        }
    ]
    assert mesa_ditar.janelas_do_programa(janelas, "notepad.exe", "Bloco de notas") == []
    assert mesa_ditar.janela_do_programa(janelas, "notepad.exe", "Bloco de notas") is None


def test_titulo_que_apenas_contem_o_rotulo_nao_serve():
    """“bloco de notas” no meio de um título não é o programa."""
    janelas = [
        {"handle": 1, "titulo": "Como abrir o Bloco de notas mais rápido", "processo": "chrome.exe", "pid": 10},
        {"handle": 2, "titulo": "Bloco de notas", "processo": "", "pid": 11},
    ]
    achadas = mesa_ditar.janelas_do_programa(janelas, "notepad.exe", "Bloco de notas")
    assert [j["handle"] for j in achadas] == [2]


def test_processo_vence_titulo_sempre():
    janelas = [
        {"handle": 1, "titulo": "Bloco de notas — artigo", "processo": "chrome.exe", "pid": 10},
        {"handle": 2, "titulo": "qualquer coisa", "processo": "notepad.exe", "pid": 11},
    ]
    achadas = mesa_ditar.janelas_do_programa(janelas, "notepad.exe", "Bloco de notas")
    assert [j["handle"] for j in achadas] == [2], "o processo é a prova; o título é pista"


def test_a_janela_da_propria_sonda_e_ignorada():
    janelas = [
        {"handle": 1, "titulo": 'cmd.exe - python arvore_sonda.py --programa "bloco de notas"', "processo": "cmd.exe", "pid": 10},
        {"handle": 2, "titulo": "Sem título - Bloco de notas", "processo": "notepad.exe", "pid": 11},
    ]
    achadas = mesa_ditar.janelas_do_programa(janelas, "notepad.exe", "Bloco de notas")
    assert [j["handle"] for j in achadas] == [2]


# ---------------------------------------------------------------------------
# 0.89.3 — mouse como último recurso, e chegar na janela sem mouse
# ---------------------------------------------------------------------------

def test_trazer_para_a_frente_existe_e_nao_usa_mouse():
    fonte = (Path("server") / "arvore_windows.py").read_text(encoding="utf-8")
    inicio = fonte.index("def trazer_para_frente(")
    trecho = fonte[inicio : fonte.index("def clicar_fisico(")]
    assert "SetForegroundWindow" in trecho
    assert "BringWindowToTop" in trecho
    assert "mesa.mover" not in trecho and "mesa.clicar" not in trecho


def test_clique_fisico_usa_o_centro_da_caixa_medida():
    """Clique por coordenada só vale se a coordenada foi **medida**, não chutada."""
    fonte = (Path("server") / "arvore_windows.py").read_text(encoding="utf-8")
    inicio = fonte.index("def clicar_fisico(")
    trecho = fonte[inicio : fonte.index("def restaurar(")]
    assert "int(caixa[0]) + int(caixa[2]) // 2" in trecho
    assert "int(caixa[1]) + int(caixa[3]) // 2" in trecho
    assert "mesa.clicar(x, y)" in trecho
    # sem posição medida, não clica: coordenada inventada é pior que não agir
    assert "não tem posição medida" in trecho


def test_sem_mouse_o_erro_ensina_a_ligar_o_mouse():
    fonte = (Path("server") / "arvore_windows.py").read_text(encoding="utf-8")
    assert "Repita com --mouse e eu clico ali fisicamente." in fonte
    assert "if mouse and caixa:" in fonte


def test_a_sonda_e_a_skill_tem_a_opcao_mouse():
    sonda = (RAIZ / "arvore_sonda.py").read_text(encoding="utf-8")
    assert '"--mouse"' in sonda
    assert "mouse=args.mouse" in sonda
    registro = (Path("server") / "skill_registry.py").read_text(encoding="utf-8")
    assert "mouse: bool = Field(default=False" in registro
    assert "mouse=bool(data.mouse)" in registro


# ---------------------------------------------------------------------------
# 0.89.4 — Popen("notepad.exe") devolveu WinError 2 no PC do usuário
# ---------------------------------------------------------------------------

def test_o_caminho_do_programa_e_procurado_antes_de_abrir(tmp_path, monkeypatch):
    """O Windows do usuário não achou `notepad.exe` só pelo nome."""
    from server import pc

    pasta = tmp_path / "System32"
    pasta.mkdir()
    alvo = pasta / "notepad.exe"
    alvo.write_text("", encoding="utf-8")

    monkeypatch.setenv("SystemRoot", str(tmp_path))
    monkeypatch.setattr(pc.shutil, "which", lambda _nome: None)
    assert pc.caminho_do_programa("notepad.exe") == str(alvo)


def test_which_vence_quando_o_path_esta_certo(monkeypatch):
    from server import pc

    monkeypatch.setattr(pc.shutil, "which", lambda nome: r"C:\Windows\notepad.exe")
    assert pc.caminho_do_programa("notepad.exe") == r"C:\Windows\notepad.exe"


def test_sem_caminho_nenhum_devolve_vazio(monkeypatch):
    from server import pc

    monkeypatch.setenv("SystemRoot", "/nao/existe")
    monkeypatch.setattr(pc.shutil, "which", lambda _nome: None)
    assert pc.caminho_do_programa("inexistente.exe") == ""


def test_arquivo_nao_encontrado_nao_e_reportado_como_recusa():
    """FileNotFoundError é OSError — a ordem dos `except` decide a mensagem."""
    fonte = (Path("server") / "mesa_ditar.py").read_text(encoding="utf-8")
    inicio = fonte.index("def ditar(")
    trecho = fonte[inicio:]
    pos_file = trecho.index("except FileNotFoundError")
    pos_os = trecho.index("except OSError as exc:", pos_file)
    assert pos_file < pos_os, "o específico tem de vir antes do genérico"
    assert "não achei o" in trecho[pos_file:pos_os]


def test_abrir_direto_usa_o_resolvedor():
    fonte = (Path("server") / "mesa_ditar.py").read_text(encoding="utf-8")
    inicio = fonte.index("def abrir_direto(")
    trecho = fonte[inicio : fonte.index("def ditar(")]
    assert "pc.abrir_sem_shell(" in trecho
    assert "subprocess.Popen([executavel]" not in trecho


# ---------------------------------------------------------------------------
# 0.89.5 — nome falado × executável: os dois foram trocados
# ---------------------------------------------------------------------------

def test_quem_injeta_abrir_recebe_o_executavel_e_nao_o_nome_falado():
    """O erro na tela foi “não achei bloco de notas no PATH”.

    Ele mandou o nome de gente (“bloco de notas”) para quem procurar arquivo
    por nome de executável. Argumento trocado, não programa ausente.
    """
    recebidos: list[str] = []

    class Leitor:
        def janelas(self):
            return []

        def janela_em_foco(self):
            return None

    class Processo:
        pid = 0

    def abrir(alvo):
        recebidos.append(alvo)
        raise OSError("parei aqui: o que importava era o argumento")

    with pytest.raises(mesa_ditar.DitarError):
        mesa_ditar.ditar(
            programa="bloco de notas",
            texto="oi",
            executar=True,
            leitor=Leitor(),
            abrir=abrir,
            dormir=_sem_espera,
        )
    assert recebidos == ["notepad.exe"]


def test_a_camada_da_api_recebe_o_nome_falado(monkeypatch):
    """`pc.abrir_programa` resolve por dentro e respeita JARVIS_HOST_PC."""
    from server import pc

    recebidos: list[str] = []

    def abrir_programa(nome):
        recebidos.append(nome)
        raise pc.PcError("parei aqui: o que importava era o argumento")

    monkeypatch.setattr(pc, "abrir_programa", abrir_programa)

    class Leitor:
        def janelas(self):
            return []

        def janela_em_foco(self):
            return None

    with pytest.raises(mesa_ditar.DitarError):
        mesa_ditar.ditar(
            programa="bloco de notas",
            texto="oi",
            executar=True,
            leitor=Leitor(),
            dormir=_sem_espera,
        )
    assert recebidos == ["bloco de notas"]


def test_abrir_direto_tolera_nome_falado():
    """Receber “bloco de notas” e resolver é melhor que falhar por preciosismo."""
    fonte = (Path("server") / "mesa_ditar.py").read_text(encoding="utf-8")
    inicio = fonte.index("def abrir_direto(")
    trecho = fonte[inicio : fonte.index("def ditar(")]
    assert "endswith(\".exe\")" in trecho
    assert "pc.resolver(alvo)" in trecho


def test_o_diagnostico_diz_se_o_programa_esta_instalado(monkeypatch):
    """Uma rodada, duas respostas: está aberto? está instalado?"""
    import importlib.util

    from server import pc

    caminho = RAIZ / "arvore_sonda.py"
    spec = importlib.util.spec_from_file_location("arvore_sonda_prog2", caminho)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)

    class Leitor:
        def janelas(self):
            return []

    class Args:
        programa = "bloco de notas"
        profundidade = 6
        limite = 600
        fonte = "auto"
        json = False

    monkeypatch.setattr(pc, "caminho_do_programa", lambda exe: r"C:\Windows\System32\notepad.exe")
    assert modulo._janelas_do_programa(Leitor(), Args(), mesa_ditar) == 1

    monkeypatch.setattr(pc, "caminho_do_programa", lambda exe: "")
    assert modulo._janelas_do_programa(Leitor(), Args(), mesa_ditar) == 1
