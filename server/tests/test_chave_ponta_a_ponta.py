"""O caminho inteiro, de ponta a ponta, contra um Chrome de mentira (0.91.21).

Os outros arquivos de teste provam pedaço por pedaço. Este prova o **fluxo
completo**, com o `main()` de verdade:

    pegar-chave.bat → --auto --autorizar → abrir → New key → nome →
    expiração → limite → Create → copiar → gravar no .env

O que é de mentira aqui é só o Windows: as janelas, a leitura da árvore de
acessibilidade, o clique e a área de transferência. O que é de verdade é o
script (`chave-no-navegador.py`), o reconhecimento (`server/chave_web.py`), a
montagem da árvore (`server/arvore.py`) e a escrita do `.env`
(`configurar-chave.py`). É o mais perto do PC do dono que dá para chegar sem o
PC do dono.

Cada cenário é uma coisa que **aconteceu de verdade** nas telas dele:

| cenário | o que aconteceu |
|---|---|
| página lenta | a página abriu carregando e o clique caiu num botão que ia sumir |
| leitura pobre | a leitura trouxe só a moldura (“Chrome Legacy Window”) |
| ação que mente | `accDoDefaultAction` devolveu sucesso e não abriu nada |
| primeiro clique | o primeiro clique só ativou a janela |
| nome no rótulo | o texto foi para “Name”, que é rótulo, e não para a caixa |
| botão apagado | o “Create” só acende com os três campos |
| chave antiga | já havia uma chave copiada antes; ela não pode ser confundida |

O Chrome falso **muda de estado quando é clicado** — é isso que transforma o
teste em fluxo, e não em retrato.
"""
from __future__ import annotations

import importlib.util
import itertools
import sys
import types
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[2]

CHAVE_VELHA = "sk-or-v1-" + "aa" * 32
CHAVE_NOVA = "sk-or-v1-" + "7c7c" + "bb" * 30


# ---------------------------------------------------------------------------
# O Chrome de mentira
# ---------------------------------------------------------------------------

def _nó(nome: str, papel: int, caixa: list[int] | None = None, acao: str = "") -> dict[str, Any]:
    """Um nó **cru**, como a sonda devolve (antes de `arvore.montar`)."""
    nó: dict[str, Any] = {"nome": nome, "papel": papel}
    if caixa:
        nó["caixa"] = list(caixa)
    if acao:
        nó["acao"] = acao
    return nó


# Posições medidas, como no painel do OpenRouter (print do dono).
CX_BUSCA = [270, 310, 320, 34]
CX_NEW_KEY = [884, 210, 104, 32]
CX_TITULO = [400, 180, 300, 30]
CX_ROTULO_NOME = [400, 300, 300, 24]
CX_NOME = [400, 330, 420, 38]
CX_EXPIRACAO = [400, 400, 420, 38]
CX_LIMITE = [400, 470, 420, 38]
CX_RESET = [400, 540, 420, 38]
CX_CREATE = [690, 640, 80, 34]
CX_COPIAR = [980, 500, 60, 28]


class ChromeFalso:
    """A janela do Chrome: página, painel, listas, cliques e a chave criada.

    `atraso` é quantas leituras ainda devolvem só a moldura — simula a página
    carregando. `moldura_a_cada` faz uma leitura pobre de vez em quando.
    `acao_mente` reproduz o defeito do Chrome: a ação do elemento devolve
    sucesso e não faz nada. `engole_o_primeiro_clique` reproduz o clique que só
    ativa a janela.
    """

    def __init__(
        self,
        *,
        atraso: int = 0,
        moldura_a_cada: int = 0,
        acao_mente: bool = True,
        engole_o_primeiro_clique: bool = False,
        publica_valor: bool = False,
        nome_digitado: bool = True,
        dorme_depois_do_clique: bool = False,
        so_na_leitura_crua: bool = False,
        acessibilidade_desligada: bool = False,
    ) -> None:
        self.atraso = atraso
        # Print de 15/11 (0.91.21): o painel abriu, o dono foi olhar o console,
        # a janela do Chrome ficou atrás — e a leitura passou a trazer 3
        # elementos. Aqui a janela “dorme” depois do clique e só acorda quando
        # alguém a traz para a frente.
        self.dorme_depois_do_clique = dorme_depois_do_clique
        self.dormindo = False
        self.trouxe_para_frente = 0
        # Print de 16/11 07:52 (0.91.22): com o painel aberto, a leitura normal
        # devolvia 3 elementos — a moldura. A vista **crua** da UIAutomation é
        # a que enxerga o modal. Aqui só ela mostra a página.
        self.so_na_leitura_crua = so_na_leitura_crua
        # Print de 16/11 08:35 (0.91.24): com o painel aberto, TODAS as leituras
        # devolveram 3 elementos. Não era a janela nem a vista: era o Chrome com
        # a acessibilidade desligada, esperando o sinal de leitor de tela do
        # Windows. Aqui ele dorme assim até alguém ligar o sinal.
        self.acessibilidade_desligada = acessibilidade_desligada
        self.sinal_de_leitor_pedido = 0
        self.fontes_pedidas: list[str] = []
        self.moldura_a_cada = moldura_a_cada
        self.acao_mente = acao_mente
        self.engole_o_primeiro_clique = engole_o_primeiro_clique
        self.publica_valor = publica_valor
        self.nome_digitado = nome_digitado

        self.tela = "chaves"
        self.nome = ""
        self.expira = ""
        self.limite = ""
        self.lista_aberta = ""
        self.criada = False
        self.chave_na_tela = ""

        self.leituras = 0
        self.cliques: list[dict[str, Any]] = []
        self.new_key_cliques = 0
        self._engoliu = False
        self.janela = {"handle": 4242, "titulo": "Keys | Settings | OpenRouter", "processo": "chrome"}

    # ------------------------------------------------------------- leitura
    def _moldura(self) -> list[dict[str, Any]]:
        return [
            _nó("Chrome Legacy Window", 9),
            _nó("Keys | Settings | OpenRouter", 1),
            _nó("Minimizar", 43),
            _nó("Maximizar", 43),
            _nó("Fechar", 43),
        ]

    def _pagina_chaves(self) -> list[dict[str, Any]]:
        return [
            _nó("Search by name or paste a key…", 42, CX_BUSCA, "escrever"),
            _nó("Switch account", 43),
            _nó("Personal", 43),
            _nó("Switch workspace", 43),
            _nó("Open menu", 43),
            _nó("Pages: Keys", 30),
            _nó("API keys", 41),
            _nó("Create and manage your API keys", 41),
            _nó("Information", 43),
            _nó("jarvis (f89)", 41),
            _nó("Hermes (054)", 41),
            _nó("New key", 43, CX_NEW_KEY, "clicar"),
        ]

    def _painel(self) -> list[dict[str, Any]]:
        filhos = [
            _nó("Create API key", 1, CX_TITULO),
            _nó("Name *", 41, CX_ROTULO_NOME),  # rótulo, não campo
            _nó(self.nome if self.publica_valor and self.nome else "", 42, CX_NOME, "escrever"),
            _nó(self.expira or "Select expiration", 46, CX_EXPIRACAO, "abrir"),
            _nó(self.limite or "Choose a credit limit", 46, CX_LIMITE, "abrir"),
            _nó("N/A", 46, CX_RESET, "abrir"),
        ]
        criar = _nó("Create", 43, CX_CREATE, "clicar")
        if not (self.nome and self.expira and self.limite):
            criar["desativado"] = True  # como no site: apagado até tudo preencher
        filhos.append(criar)
        if self.lista_aberta == "expiracao":
            filhos += [
                _nó(opcao, 34, [500, 430 + indice * 30, 200, 28], "clicar")
                for indice, opcao in enumerate(("30 days", "90 days", "1 year", "Never"))
            ]
        if self.lista_aberta == "limite":
            filhos += [
                _nó(opcao, 34, [500, 500 + indice * 30, 200, 28], "clicar")
                for indice, opcao in enumerate(("10", "100", "No limit"))
            ]
        return filhos

    def _pagina_criada(self) -> list[dict[str, Any]]:
        return [
            _nó("API keys", 41),
            _nó("Create and manage your API keys", 41),
            _nó("New key", 43, CX_NEW_KEY, "clicar"),
            _nó("jarvis-2026 (abc)", 41),
            _nó("Copy", 43, CX_COPIAR, "clicar"),
            _nó("Search by name or paste a key…", 42, CX_BUSCA, "escrever"),
        ]

    def raiz(self) -> dict[str, Any]:
        if self.dormindo:
            return {"nome": "API keys", "papel": 1, "filhos": self._moldura()}
        if self.atraso > 0:
            self.atraso -= 1
            return {"nome": "API keys", "papel": 1, "filhos": self._moldura()}
        if self.moldura_a_cada:
            self.leituras += 1
            if self.leituras % self.moldura_a_cada == 0:
                return {"nome": "API keys", "papel": 1, "filhos": self._moldura()}
        if self.criada:
            filhos = self._pagina_criada()
        elif self.tela == "dialogo":
            filhos = self._painel()
        else:
            filhos = self._pagina_chaves()
        return {"nome": "API keys", "papel": 1, "filhos": filhos}

    # ------------------------------------------------ o que o script chama
    def janelas(self):
        return [dict(self.janela)]

    def janela_em_foco(self):
        return dict(self.janela)

    def janela_muda(self, _handle=None) -> bool:
        return True

    def escolher_janela(self, _alvo="", janelas=None, foco=None):
        return dict((janelas or [self.janela])[0])

    def trazer_para_frente(self, _handle) -> bool:
        self.trouxe_para_frente += 1
        self.dormindo = False
        return True

    def teclado_na_janela(self, _handle) -> bool:
        return True

    # ---------------------------------------- acessibilidade (0.91.25)
    def leitor_de_tela(self):
        return not self.acessibilidade_desligada

    def acordar_acessibilidade(self, _handle=0):
        """O sinal de leitor de tela: o Chrome passa a publicar a página."""
        antes = not self.acessibilidade_desligada
        self.sinal_de_leitor_pedido += 1
        self.acessibilidade_desligada = False
        return {"antes": antes, "ligado": True, "depois": True}

    def desligar_leitor_de_tela(self):
        return True

    def janelas_filhas(self, _handle, _limite=24):
        return [{"handle": 5150, "classe": "Chrome_RenderWidgetHostHWND", "titulo": "Chrome Legacy Window"}]

    def ler_janela(self, _handle, profundidade=8, limite=1500, fonte="auto"):
        self.fontes_pedidas.append(fonte)
        if self.acessibilidade_desligada:
            # Só a moldura, em qualquer fonte: é o retrato do print.
            return {
                "janela": dict(self.janela),
                "raiz": {"nome": "API keys", "papel": 1, "filhos": self._moldura()},
                "fonte": "uia" if fonte == "auto" else fonte,
            }
        if self.so_na_leitura_crua and fonte != "uia_raw":
            # A vista de controle não vê o conteúdo: sobra a moldura.
            return {
                "janela": dict(self.janela),
                "raiz": {"nome": "API keys", "papel": 1, "filhos": self._moldura()},
                "fonte": "uia" if fonte == "auto" else fonte,
            }
        return {"janela": dict(self.janela), "raiz": self.raiz(), "fonte": "uia" if fonte == "auto" else fonte}

    def executar_ref(self, handle, caminho, acao, texto="", caixa=None, mouse=False, primeiro_mouse=False):
        caixa = list(caixa or [])
        self.cliques.append(
            {"caixa": caixa, "acao": acao, "mouse": mouse, "primeiro_mouse": primeiro_mouse, "texto": texto}
        )
        resultado: dict[str, Any] = {"executou": True, "como": "ação padrão do elemento"}

        if acao == "digitar":
            return self._digitar(caixa, texto)

        # A ação do elemento: no Chrome ela diz que sim e não faz nada.
        if self.acao_mente and not primeiro_mouse:
            return resultado

        if caixa == CX_NEW_KEY:
            self.new_key_cliques += 1
            if self.engole_o_primeiro_clique and not self._engoliu:
                self._engoliu = True
                return {**resultado, "como": "clique físico em 936,226", "cursor_voltou": True}
            self.tela = "dialogo"
            self.dormindo = self.dorme_depois_do_clique
            return {**resultado, "como": "clique físico em 936,226", "cursor_voltou": True}
        if caixa == CX_EXPIRACAO:
            self.lista_aberta = "expiracao"
            return resultado
        if caixa == CX_LIMITE:
            self.lista_aberta = "limite"
            return resultado
        if self.lista_aberta == "expiracao" and caixa and caixa[0] == 500 and 430 <= caixa[1] < 550:
            opcoes = ("30 days", "90 days", "1 year", "Never")
            self.expira = opcoes[(caixa[1] - 430) // 30]
            self.lista_aberta = ""
            return resultado
        if self.lista_aberta == "limite" and caixa and caixa[0] == 500 and 500 <= caixa[1] < 600:
            opcoes = ("10", "100", "No limit")
            self.limite = opcoes[(caixa[1] - 500) // 30]
            self.lista_aberta = ""
            return resultado
        if caixa == CX_CREATE:
            if self.nome and self.expira and self.limite:
                self.criada = True
                self.tela = "criada"
                self.chave_na_tela = CHAVE_NOVA
            return resultado
        if caixa == CX_COPIAR:
            self.copiado_para_area = self.chave_na_tela
            return resultado
        return resultado

    def _digitar(self, caixa: list[int], texto: str) -> dict[str, Any]:
        if caixa == CX_NOME:
            if self.nome_digitado:
                self.nome = texto
            return {
                "executou": True,
                "como": "clique físico no campo + teclado",
                "cursor_voltou": True,
                "conferido": True if self.publica_valor else None,
            }
        # Clicar no rótulo “Name” e mandar teclas: não escreve nada (foi o defeito).
        return {"executou": True, "como": "clique físico no campo + teclado", "conferido": False}


# ---------------------------------------------------------------------------
# O resto do Windows e o .env de verdade
# ---------------------------------------------------------------------------

class ConfiguradorDeVerdade:
    """O `configurar-chave.py` real, com o `.env` apontado para a pasta do teste."""

    def __init__(self, modulo, caminho: Path, area: dict[str, str]) -> None:
        self.modulo = modulo
        self.caminho = caminho
        self.area = area
        modulo.ENV = caminho

    def __getattr__(self, nome):
        return getattr(self.modulo, nome)

    def chave_da_area_de_transferencia(self):
        texto = self.area.get("texto", "")
        achadas = self.modulo.chaves_do_texto(self.modulo.sem_controle(texto))
        if not achadas:
            raise RuntimeError("o que está copiado não tem cara de chave.")
        return texto, achadas[0]


def _script():
    spec = importlib.util.spec_from_file_location(
        "chave_no_navegador_ponta_a_ponta", RAIZ / "chave-no-navegador.py"
    )
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


def _ambiente(monkeypatch, tmp_path: Path, chrome: ChromeFalso, *, area_inicial: str = ""):
    """Monta o mundo: Chrome, área de transferência, `.env` e relógio."""
    script = _script()
    area = {"texto": area_inicial, "copiado": ""}

    # o `.env` de verdade, com o provedor já escolhido (o caso do duplo clique)
    spec = importlib.util.spec_from_file_location("configurar_chave_pap", RAIZ / "configurar-chave.py")
    configurar = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(configurar)
    env = tmp_path / ".env"
    env.write_text(
        "JARVIS_AI_PROVIDER=openrouter\n"
        "JARVIS_AI_BASE_URL=https://openrouter.ai/api/v1\n"
        "JARVIS_AI_MODEL=deepseek/deepseek-chat-v3-0324:free\n"
        f"JARVIS_AI_API_KEY={CHAVE_VELHA}\n",
        encoding="utf-8",
    )
    configurador = ConfiguradorDeVerdade(configurar, env, area)

    # o botão “Copy” do Chrome falso põe a chave na área
    original = chrome.executar_ref

    def executar_ref(*args, **kwargs):
        resultado = original(*args, **kwargs)
        if getattr(chrome, "copiado_para_area", ""):
            area["texto"] = chrome.copiado_para_area
            chrome.copiado_para_area = ""
        return resultado

    monkeypatch.setattr(chrome, "executar_ref", executar_ref)

    monkeypatch.setitem(sys.modules, "server.arvore_windows", chrome)
    monkeypatch.setattr(script, "_modulo_do_configurador", lambda: configurador)
    monkeypatch.setattr(script, "_configurar_ambiente", lambda: None)
    monkeypatch.setattr(script, "_avisar_jarvis_aberto", lambda: True)
    monkeypatch.setattr(script, "_texto_da_area", lambda: area.get("texto", ""))
    monkeypatch.setattr(script, "_copiar_pela_pagina", lambda _janela: False)
    monkeypatch.setattr(script, "_levar_ate_as_chaves", lambda _args, conta="", segundos=0: (chrome.janela, _montar(chrome)))

    relógio = itertools.count()
    monkeypatch.setattr(
        script,
        "time",
        types.SimpleNamespace(time=lambda: next(relógio) * 1.0, sleep=lambda _s: None),
    )
    monkeypatch.setattr(script.sys, "platform", "win32")

    def abrir_no_navegador(_endereco: str) -> bool:
        return True

    monkeypatch.setattr(configurar, "abrir_no_navegador", abrir_no_navegador)
    return script, configurador, env, area


def _montar(chrome: ChromeFalso) -> dict[str, Any]:
    """A árvore montada, do jeito que o script recebe (usa o `arvore` de verdade)."""
    from server import arvore

    return arvore.montar(
        {"janela": chrome.janela, "raiz": chrome.raiz(), "fonte": "uia"},
        14,
        3000,
        com_caminho=True,
    )


def _rodar(script) -> int:
    """O `main()` de verdade — é o que o duplo clique no `.bat` executa."""
    return script.main(["--auto", "--autorizar"])


def _chave_gravada(env: Path) -> str:
    for linha in env.read_text(encoding="utf-8-sig").splitlines():
        if linha.strip().startswith("JARVIS_AI_API_KEY="):
            return linha.split("=", 1)[1].strip()
    return ""


# ---------------------------------------------------------------------------
# Os cenários
# ---------------------------------------------------------------------------

def test_o_duplo_clique_cria_copia_e_grava_a_chave(monkeypatch, tmp_path, capsys):
    """O caminho feliz: página pronta, clique de mouse, três campos, cópia."""
    chrome = ChromeFalso()
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)

    assert _rodar(script) == 0

    assert chrome.tela == "criada"
    assert chrome.nome.startswith("jarvis-"), "o nome padrão é jarvis-AAAA-MM-DD"
    assert chrome.expira == "Never", "a chave que expira derruba o JARVIS depois"
    assert chrome.limite == "No limit"
    assert _chave_gravada(env) == CHAVE_NOVA, "a chave NOVA tem de estar no .env"
    assert CHAVE_VELHA not in env.read_text(encoding="utf-8")

    saida = capsys.readouterr().out
    assert "clique do mouse" in saida
    assert "expiração: escolhendo “Never”" in saida
    assert "limite: escolhendo “No limit”" in saida


def test_pagina_lenta_espera_em_vez_de_desistir(monkeypatch, tmp_path):
    """A página que abre carregando: foi o primeiro travamento do dono."""
    chrome = ChromeFalso(atraso=6)
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)

    assert _rodar(script) == 0
    assert _chave_gravada(env) == CHAVE_NOVA


def test_leitura_pobre_no_meio_do_caminho_nao_faz_o_script_desistir(monkeypatch, tmp_path):
    """A moldura aparecendo de vez em quando: foi o print dos “3 elementos”."""
    chrome = ChromeFalso(moldura_a_cada=3)
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)

    assert _rodar(script) == 0
    assert _chave_gravada(env) == CHAVE_NOVA


def test_acao_do_elemento_que_mente_nao_impede_a_chave(monkeypatch, tmp_path):
    """`accDoDefaultAction` devolve sucesso e não abre nada — o clique resolve."""
    chrome = ChromeFalso(acao_mente=True)
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)

    assert _rodar(script) == 0
    pedidos_de_mouse = [c for c in chrome.cliques if c["caixa"] == CX_NEW_KEY and c["primeiro_mouse"]]
    assert pedidos_de_mouse, "o clique de verdade é o que abre o painel"
    assert _chave_gravada(env) == CHAVE_NOVA


def test_primeiro_clique_que_so_ativa_a_janela_e_seguido_de_outro(monkeypatch, tmp_path):
    chrome = ChromeFalso(engole_o_primeiro_clique=True)
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)
    # o primeiro clique se perde e a falha grava o relatório: na pasta do teste
    monkeypatch.setattr(script, "__file__", str(tmp_path / "chave-no-navegador.py"))

    assert _rodar(script) == 0
    assert chrome.new_key_cliques >= 2, "o segundo clique é o que aperta o botão"
    assert _chave_gravada(env) == CHAVE_NOVA


def test_o_nome_vai_para_a_caixa_e_nao_para_o_rotulo(monkeypatch, tmp_path):
    """No painel real, “Name” é rótulo e a caixa é outro elemento."""
    chrome = ChromeFalso()
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)

    assert _rodar(script) == 0

    escritas = [c for c in chrome.cliques if c["acao"] == "digitar"]
    assert escritas, "alguma coisa foi digitada"
    assert all(c["caixa"] == CX_NOME for c in escritas), "o texto não pode ir para o rótulo"
    assert all(c["caixa"] != CX_ROTULO_NOME for c in chrome.cliques)
    assert _chave_gravada(env) == CHAVE_NOVA


def test_campo_que_nao_publica_valor_ainda_assim_digita(monkeypatch, tmp_path):
    """O campo do Chrome não publica valor: quem confirma é o botão acender."""
    chrome = ChromeFalso(publica_valor=False)
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)

    assert _rodar(script) == 0
    assert chrome.nome.startswith("jarvis-")
    assert _chave_gravada(env) == CHAVE_NOVA


def test_chave_velha_na_area_de_transferencia_nao_e_confundida(monkeypatch, tmp_path):
    """Ele já tinha copiado outra coisa antes: a nova é que vale."""
    chrome = ChromeFalso()
    script, _config, env, area = _ambiente(monkeypatch, tmp_path, chrome, area_inicial=CHAVE_VELHA)

    assert _rodar(script) == 0
    assert area["texto"] == CHAVE_NOVA
    assert _chave_gravada(env) == CHAVE_NOVA


def test_sem_painel_nao_grava_e_diz_o_que_falta(monkeypatch, tmp_path, capsys):
    """Se o painel nunca abrir, nada é gravado — e a mensagem diz o motivo."""
    class NuncaAbre(ChromeFalso):
        def executar_ref(self, *args, **kwargs):
            resultado = super().executar_ref(*args, **kwargs)
            if self.tela == "dialogo":  # o painel “abriu” e sumiu em seguida
                self.tela = "chaves"
            return resultado

    chrome = NuncaAbre()
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)
    monkeypatch.setattr(script, "__file__", str(tmp_path / "chave-no-navegador.py"))

    _rodar(script)
    saida = capsys.readouterr().out

    assert _chave_gravada(env) == CHAVE_VELHA, "sem chave nova, o .env fica como estava"
    assert "NÃO DEI" in saida
    assert "elementos com nome" in saida, "desistir exige dizer o que a leitura viu"


def test_sem_autorizar_nada_e_clicado_e_nada_e_gravado(monkeypatch, tmp_path):
    chrome = ChromeFalso()
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)

    assert script.main(["--auto"]) == 0

    assert chrome.cliques == []
    assert _chave_gravada(env) == CHAVE_VELHA


def test_o_env_fica_com_as_outras_linhas_e_a_chave_nova(monkeypatch, tmp_path):
    """Trocar a chave não pode mexer no provedor, na base nem no modelo."""
    chrome = ChromeFalso()
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)

    assert _rodar(script) == 0
    texto = env.read_bytes().decode("utf-8")
    assert "JARVIS_AI_PROVIDER=openrouter" in texto
    assert "https://openrouter.ai/api/v1" in texto
    assert "deepseek/deepseek-chat-v3-0324:free" in texto
    assert _chave_gravada(env) == CHAVE_NOVA
    assert "\r\n" in texto, "o .env é gravado em CRLF, para o Bloco de Notas"


def test_ele_avisa_a_api_que_esta_aberta(monkeypatch, tmp_path, capsys):
    """Depois de gravar, a API aberta relê o `.env` — sem reiniciar."""
    chrome = ChromeFalso()
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)
    avisos: list[bool] = []

    def avisar() -> bool:
        avisos.append(True)
        return True

    monkeypatch.setattr(script, "_avisar_jarvis_aberto", avisar)

    assert _rodar(script) == 0
    assert avisos == [True]
    assert "passou a usar esta chave agora" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Regressões: um cenário por print que o dono mandou
# ---------------------------------------------------------------------------

def test_regressao_0_91_16_o_painel_aberto_e_lido(monkeypatch, tmp_path):
    """Print de 15/11: painel aberto na tela e “não apareceu na leitura”.

    Aqui a leitura só traz o painel a partir da terceira tentativa (a página
    ainda montava o resto), e o clique é o de mouse — como na tela dele.
    """
    chrome = ChromeFalso(atraso=2)
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)

    assert _rodar(script) == 0
    assert chrome.expira == "Never"
    assert _chave_gravada(env) == CHAVE_NOVA


def test_regressao_0_91_17_a_moldura_nao_vira_veredito(monkeypatch, tmp_path):
    """Print de 15/11 18:30: 3 elementos — a moldura do Chrome — e nada criado."""
    chrome = ChromeFalso(moldura_a_cada=2)
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)

    assert _rodar(script) == 0
    assert _chave_gravada(env) == CHAVE_NOVA


def test_regressao_0_91_18_a_acao_que_mente_e_contornada(monkeypatch, tmp_path, capsys):
    """Print de 15/11 19:04: “ação padrão do elemento”, 70 s, painel fechado."""
    chrome = ChromeFalso(acao_mente=True)
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)

    assert _rodar(script) == 0
    saida = capsys.readouterr().out
    assert "clique do mouse" in saida
    assert _chave_gravada(env) == CHAVE_NOVA


def test_regressao_0_91_19_o_nome_e_digitado(monkeypatch, tmp_path, capsys):
    """“apertou em new key mas nao digitou um nome” — 15/11."""
    chrome = ChromeFalso()
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)

    assert _rodar(script) == 0
    assert chrome.nome.startswith("jarvis-")
    assert "nome: digitado" in capsys.readouterr().out
    assert _chave_gravada(env) == CHAVE_NOVA


def test_regressao_0_91_20_o_botao_aparece_na_terceira_leitura(monkeypatch, tmp_path):
    """“o botão de criar não está na árvore desta janela” — com ele na tela."""
    chrome = ChromeFalso(atraso=3)
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)

    assert _rodar(script) == 0
    assert _chave_gravada(env) == CHAVE_NOVA


def test_regressao_0_91_22_janela_atras_do_console_nao_e_painel_fechado(monkeypatch, tmp_path, capsys):
    """Print de 15/11 20:32: o painel aberto na tela e “NÃO DEI: 3 elementos”.

    A sequência do print: ele clicou em “New key”, o painel abriu, o dono foi
    olhar o console, a janela do Chrome ficou **atrás** — e a leitura passou a
    devolver só a moldura (3 elementos). O script tratou isso como “o painel
    não abriu”, desistiu, e ainda escreveu “a página foi lida inteira e o botão
    estava nela” — que era falso.

    Aqui o Chrome falso dorme exatamente assim: depois do clique, só publica a
    moldura. Quem o acorda é o `trazer_para_frente`, que é o que o script tem
    de fazer sozinho.
    """
    chrome = ChromeFalso(dorme_depois_do_clique=True)
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)
    monkeypatch.setattr(script, "__file__", str(tmp_path / "chave-no-navegador.py"))

    assert _rodar(script) == 0

    saida = capsys.readouterr().out
    assert chrome.trouxe_para_frente > 0, "acordar a janela é o que devolve a leitura"
    assert "a leitura tinha caído" in saida, "o dono precisa ver por que a leitura mudou"
    assert "lida inteira" not in saida, "ele não pode dizer que leu o que não leu"
    assert chrome.tela == "criada"
    assert _chave_gravada(env) == CHAVE_NOVA


def test_regressao_0_91_22_sem_conseguir_ler_a_pagina_a_mensagem_e_a_verdadeira(
    monkeypatch, tmp_path, capsys
):
    """Quando o Windows não deixa trazer a janela, a desculpa tem de ser a certa.

    Antes: “o clique não abriu o painel — a página foi lida inteira”. Depois:
    “não consegui ver a página do Chrome”. O dono precisa saber se o problema é
    a leitura ou o clique — foi confundir os dois que custou cinco rodadas.
    """
    class NuncaAcorda(ChromeFalso):
        def trazer_para_frente(self, _handle) -> bool:
            self.trouxe_para_frente += 1
            return False  # o Windows recusa: outro programa tem o foco

        def janela_em_foco(self):
            return {"handle": 999, "titulo": "Prompt de Comando"}

    chrome = NuncaAcorda(dorme_depois_do_clique=True)
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)
    monkeypatch.setattr(script, "__file__", str(tmp_path / "chave-no-navegador.py"))

    _rodar(script)
    saida = capsys.readouterr().out

    assert _chave_gravada(env) == CHAVE_VELHA, "sem chave, o .env fica como estava"
    assert "NÃO consegui ver a" in saida
    assert "lida inteira" not in saida, "não pode afirmar uma leitura que não houve"
    assert "clique uma vez no Chrome" in saida, "o dono tem de saber o que fazer"


def test_regressao_0_91_25_chrome_com_acessibilidade_desligada_e_acordado(monkeypatch, tmp_path, capsys):
    """Print de 16/11 08:35: painel aberto, e as CINCO leituras com 3 elementos.

    O diagnóstico da 0.91.24 provou que não era a janela nem a vista: auto, uia,
    uia_raw, uia_content e msaa devolveram todos a moldura. O que faltava era o
    sinal de **leitor de tela** do Windows, sem o qual o Chrome não publica a
    página. Aqui o Chrome falso nasce assim e só acorda com o sinal.
    """
    chrome = ChromeFalso(acessibilidade_desligada=True)
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)
    monkeypatch.setattr(script, "__file__", str(tmp_path / "chave-no-navegador.py"))

    assert _rodar(script) == 0

    assert chrome.sinal_de_leitor_pedido >= 1, "o sinal é o que faz o Chrome publicar"
    assert chrome.tela == "criada"
    assert _chave_gravada(env) == CHAVE_NOVA
    assert "modo leitor de tela" in capsys.readouterr().out


def test_regressao_0_91_25_o_sinal_de_leitor_de_tela_e_desfeito_no_fim(monkeypatch, tmp_path):
    """O modo leitor de tela é emprestado: o programa devolve como estava."""
    chrome = ChromeFalso(acessibilidade_desligada=True)
    script, _config, _env, _area = _ambiente(monkeypatch, tmp_path, chrome)

    pedidos: list[str] = []
    monkeypatch.setattr(chrome, "desligar_leitor_de_tela", lambda: pedidos.append("desfeito") or True)

    assert _rodar(script) == 0
    assert pedidos == ["desfeito"], "sem devolver, o Windows ficaria em modo leitor de tela"


def test_regressao_0_91_25_o_diagnostico_mostra_o_sinal_e_as_janelas_filhas(monkeypatch, tmp_path, capsys):
    """O relatório tem de responder *por que* 3 elementos — não só contar."""
    chrome = ChromeFalso(acessibilidade_desligada=True)
    script, _config, _env, _area = _ambiente(monkeypatch, tmp_path, chrome)
    monkeypatch.setattr(script, "__file__", str(tmp_path / "chave-no-navegador.py"))

    assert script.main(["--diagnostico"]) == 0

    saida = capsys.readouterr().out
    assert "Modo leitor de tela do Windows: desligado" in saida
    assert "Janelas filhas do Chrome: 1" in saida
    assert "Chrome_RenderWidgetHostHWND" in saida
    assert "DEPOIS de ligar o modo leitor de tela" in saida
    assert "Funcionou: a leitura" in saida


def test_regressao_0_91_24_o_diagnostico_nao_cria_chave_nem_toca_no_env(monkeypatch, tmp_path):
    """A promessa do comando, cobrada: nada de chave nova, nada no `.env`."""
    chrome = ChromeFalso()
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)
    monkeypatch.setattr(script, "__file__", str(tmp_path / "chave-no-navegador.py"))

    antes = env.read_text(encoding="utf-8")
    assert script.main(["--diagnostico"]) == 0

    assert chrome.cliques == []
    assert chrome.tela == "chaves"
    assert env.read_text(encoding="utf-8") == antes


def test_regressao_0_91_23_a_vista_crua_enxerga_o_painel_que_a_de_controle_nao_ve(
    monkeypatch, tmp_path, capsys
):
    """Print de 16/11 07:52: painel aberto na tela e “3 elementos” outra vez.

    Na 0.91.22 ele acordou a janela e continuou vendo 3 elementos — porque o
    problema não era a janela atrás: era a **vista** de acessibilidade. Com o
    modal aberto, o site esconde a página da tecnologia assistiva, e a vista de
    controle passa a devolver só a moldura. A vista **crua** continua vendo
    tudo — inclusive o painel e os campos.

    Este é o teste do fluxo inteiro nesse mundo: ele tem de achar o painel pela
    leitura crua, digitar o nome, escolher “No expiration”, criar e gravar.
    """
    chrome = ChromeFalso(so_na_leitura_crua=True)
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)
    monkeypatch.setattr(script, "__file__", str(tmp_path / "chave-no-navegador.py"))

    assert _rodar(script) == 0

    assert "uia_raw" in chrome.fontes_pedidas, "a vista crua é a que vê o painel"
    assert chrome.tela == "criada"
    assert chrome.nome.startswith("jarvis-")
    assert chrome.expira == "Never"
    assert _chave_gravada(env) == CHAVE_NOVA


def test_regressao_0_91_23_depois_de_achar_a_vista_boa_ele_para_de_procurar(
    monkeypatch, tmp_path
):
    """Achada a vista que mostra a página, ele não paga as outras de novo.

    Ler cinco vistas a cada passo custaria caro (a crua lê centenas de nós) e
    tornaria o caminho lento a ponto de a página mudar no meio.
    """
    chrome = ChromeFalso(so_na_leitura_crua=True)
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)
    monkeypatch.setattr(script, "__file__", str(tmp_path / "chave-no-navegador.py"))

    assert _rodar(script) == 0
    assert _chave_gravada(env) == CHAVE_NOVA

    depois_da_primeira = chrome.fontes_pedidas[chrome.fontes_pedidas.index("uia_raw") + 1 :]
    assert "auto" not in depois_da_primeira, (
        "com a fonte preferida conhecida, a leitura automática (que já falhou) não é paga de novo"
    )


# ---------------------------------------------------------------------------
# O que não pode regredir, meça como medir
# ---------------------------------------------------------------------------

def test_tudo_cabe_num_numero_pequeno_de_leituras(monkeypatch, tmp_path):
    """Sem page-load problem, o caminho inteiro não devia custar dezenas de leituras.

    Não é um limite de performance: é um sinal de que não ficou laço perdido.
    """
    chrome = ChromeFalso()
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)

    assert _rodar(script) == 0

    assert chrome.leituras <= 40, f"leu {chrome.leituras} vezes — sinal de laço perdido"
    assert chrome.new_key_cliques == 1, "com a página pronta, um clique basta"


def test_nenhum_clique_sai_sem_autorizacao(monkeypatch, tmp_path):
    chrome = ChromeFalso()
    script, _config, env, _area = _ambiente(monkeypatch, tmp_path, chrome)

    script.main(["--auto"])  # sem --autorizar

    assert chrome.cliques == []
    assert chrome.tela == "chaves"
