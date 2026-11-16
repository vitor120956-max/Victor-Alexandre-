"""O piloto do navegador, com o Windows trocado por dublês (0.91.10).

Aqui não existe Chrome, nem `ctypes`, nem área de transferência: `_ler_janela`
devolve páginas montadas à mão e `server.arvore_windows` é um módulo falso que
só anota o que foi pedido. O que estes testes provam é o que dá para provar sem
a máquina do dono:

1. a sequência inteira — criar, nomear, criar de novo, copiar, ler, gravar —
   acontece na ordem, e cada clique sai com a autorização certa;
2. sem `--autorizar` nada é clicado, e o texto diz como autorizar;
3. `--sem-mouse` chega ao executor como "não mexe no ponteiro";
4. quando o clique não sai, o script **para ali** e diz o motivo — antes da
   0.91.10 ele seguia em frente e culpava o passo seguinte.
"""
from __future__ import annotations

import importlib.util
import itertools
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from server import chave_web

RAIZ = Path(__file__).resolve().parents[2]


def _script():
    spec = importlib.util.spec_from_file_location(
        "chave_no_navegador_duble", RAIZ / "chave-no-navegador.py"
    )
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


def _no(nome: str, caixa: list[int] | None = None, papel: int = 43) -> dict[str, Any]:
    """Um nó como a leitura de verdade devolve: papel **e** código, ação e caixa.

    O `codigo` importa: é por ele (e pela ação) que o script separa a caixa de
    texto do rótulo ao lado — “Name” e a caixa são dois nós no painel real.
    """
    no: dict[str, Any] = {"nome": nome, "papel": papel, "codigo": papel, "caminho": [0, 1]}
    if caixa:
        no["caixa"] = caixa
        no["acionavel"] = True
        no["acao"] = "escrever" if papel == 42 else "clicar"
    return no


def _pagina(*nos: dict[str, Any]) -> dict[str, Any]:
    return {
        "alvo": "chrome — API Keys | OpenRouter",
        "fonte": "uia",
        "arvore": {"nome": "API Keys", "papel": 1, "filhos": list(nos)},
    }


PAGINA_INICIAL = _pagina(_no("Create Key", [812, 200, 90, 28]))
PAGINA_DO_NOME = _pagina(_no("Key name", [400, 300, 320, 30], papel=42), _no("Create", [700, 380, 80, 28]))
PAGINA_CRIADA = _pagina(_no("Create", [700, 380, 80, 28]))
PAGINA_COM_COPIA = _pagina(_no("Copy", [980, 500, 60, 28]))

JANELA = {"handle": 4242, "titulo": "API Keys | OpenRouter", "processo": "chrome"}


class WindowsFalso:
    """Só o que o script usa: `executar_ref`, e ele só anota."""

    def __init__(self, resultado: dict[str, Any] | None = None) -> None:
        self.chamadas: list[dict[str, Any]] = []
        self.resultado = resultado or {
            "executou": True,
            "como": "clique físico em 857,214",
            "cursor_voltou": True,
        }

    def trazer_para_frente(self, _handle) -> bool:
        return True

    def teclado_na_janela(self, _handle) -> bool:
        return True

    def janela_muda(self, _handle) -> bool:
        return True

    def ler_janela(self, handle, _profundidade=8, _limite=1500, fonte="auto"):
        """O bruto, como o Windows devolve — quem monta é `arvore.montar`."""
        return {
            "janela": {"handle": handle, "titulo": "API Keys | OpenRouter", "processo": "chrome"},
            "raiz": {
                "nome": "API Keys",
                "papel": 1,
                "filhos": [{"nome": "Create Key", "papel": 43, "caixa": [812, 200, 90, 28]}],
            },
            "fonte": "uia",
        }

    def executar_ref(self, handle, caminho, acao, texto="", caixa=None, mouse=False, primeiro_mouse=False):
        self.chamadas.append(
            {
                "handle": handle,
                "caminho": caminho,
                "acao": acao,
                "texto": texto,
                "caixa": caixa,
                "mouse": mouse,
                "primeiro_mouse": primeiro_mouse,
            }
        )
        return dict(self.resultado)


class ConfiguradorFalso:
    def __init__(self, chave: str = "sk-or-v1-" + "ab" * 34, erro: bool = False) -> None:
        self.chave = chave
        self.erro = erro
        self.gravadas: list[str] = []

    def chave_da_area_de_transferencia(self):
        if self.erro:
            raise RuntimeError("a área de transferência está vazia.")
        return f" {self.chave}\n", self.chave

    def descrever_area(self, limpo: str, chave: str) -> str:
        return f"  Copiado: {len(limpo.strip())} caractere(s); chave reconhecida {chave[:5]}…{chave[-4:]}"


def _args(**extra: Any):
    base = types.SimpleNamespace(
        alvo="chrome",
        nome="jarvis-teste",
        autorizar=True,
        mouse=False,
        sem_mouse=False,
        conta="",
    )
    for chave, valor in extra.items():
        setattr(base, chave, valor)
    return base


# Caixas fixas de cada controle do mundo falso — o clique é identificado por
# elas, como no Windows de verdade (o `caminho` muda a cada leitura).
CAIXA_NEW_KEY = [1400, 200, 100, 30]
CAIXA_NOME = [400, 300, 320, 30]
CAIXA_EXPIRACAO = [400, 380, 320, 30]
CAIXA_LIMITE = [400, 460, 320, 30]
CAIXA_CREATE = [700, 640, 80, 28]
CAIXA_COPIAR = [980, 200, 60, 28]

OPCOES_EXPIRACAO = ("30 days", "90 days", "1 year", "Never")
OPCOES_LIMITE = ("5", "10", "No limit")


class Mundo:
    """O OpenRouter de mentira: o diálogo “Create API key”, com as três listas.

    Ele responde a **cliques por caixa** e muda de estado — é o que permite
    testar a sequência de verdade: New key → diálogo → nome → expiração →
    limite → Create → chave na tela.
    """

    def __init__(self, *, expira: str = "", limite: str = "") -> None:
        # As opções ficam na instância (e não no módulo) para cada teste poder
        # montar o diálogo do jeito que quiser sem mexer no vizinho.
        self.opcoes_expiracao = OPCOES_EXPIRACAO
        self.opcoes_limite = OPCOES_LIMITE
        self.tela = "chaves"
        self.nome = ""
        self.expira = expira
        self.limite = limite
        self.lista_aberta = ""
        self.criada = False
        self.cliques: list[list[int]] = []
        self.pedidos: list[dict[str, Any]] = []

    # ------------------------------------------------------------ leitura
    def _no(self, nome: str, caixa: list[int], papel: int = 43) -> dict[str, Any]:
        return {
            "nome": nome,
            "papel": papel,
            "codigo": papel,
            "caixa": list(caixa),
            "acionavel": True,
            "acao": "escrever" if papel == 42 else "clicar",
            "caminho": [0, 1],
        }

    def montar(self) -> dict[str, Any]:
        if self.tela == "chaves":
            filhos = [self._no("New key", CAIXA_NEW_KEY)]
        else:
            filhos = [
                self._no("Create API key", [400, 180, 300, 30], papel=1),
                self._no("Name", CAIXA_NOME, papel=42),
                self._no(self.expira or "Select expiration", CAIXA_EXPIRACAO),
                self._no(self.limite or "Choose a credit limit", CAIXA_LIMITE),
                self._no("Create", CAIXA_CREATE),
            ]
            if self.lista_aberta == "expiracao":
                filhos += [
                    self._no(opcao, [500, 400 + indice * 30, 200, 30])
                    for indice, opcao in enumerate(self.opcoes_expiracao)
                ]
            if self.lista_aberta == "limite":
                filhos += [
                    self._no(opcao, [500, 600 + indice * 30, 200, 30])
                    for indice, opcao in enumerate(self.opcoes_limite)
                ]
        if self.criada:
            filhos = [self._no("Copy", CAIXA_COPIAR), self._no("API keys", [100, 100, 120, 30], papel=1)]
        return {
            "alvo": "chrome — Keys | Settings | OpenRouter",
            "fonte": "uia",
            "arvore": {"nome": "OpenRouter", "filhos": filhos},
        }

    # ------------------------------------------------------------- clique
    def executar_ref(self, handle, caminho, acao, texto="", caixa=None, mouse=False, primeiro_mouse=False):
        caixa = list(caixa or [])
        self.cliques.append(caixa)
        # Anota o pedido: a 0.91.18 é a versão em que o clique de verdade passou
        # a ser o primeiro degrau, e isso tem de ser visível no teste.
        self.pedidos.append({"mouse": mouse, "primeiro_mouse": primeiro_mouse, "caixa": caixa})
        nome = self._nome_da_caixa(caixa)
        if acao == "digitar":
            self.nome = texto
            return {"executou": True, "como": "clique físico no campo", "cursor_voltou": True}
        if caixa == CAIXA_NEW_KEY:
            self.tela = "dialogo"
        elif caixa == CAIXA_EXPIRACAO:
            self.lista_aberta = "" if self.lista_aberta == "expiracao" else "expiracao"
        elif caixa == CAIXA_LIMITE:
            self.lista_aberta = "" if self.lista_aberta == "limite" else "limite"
        elif self.lista_aberta == "expiracao" and caixa and caixa[0] == 500 and 400 <= caixa[1] < 600:
            self.expira = nome
            self.lista_aberta = ""
        elif self.lista_aberta == "limite" and caixa and caixa[0] == 500 and caixa[1] >= 600:
            self.limite = nome
            self.lista_aberta = ""
        elif caixa == CAIXA_CREATE:
            # Só cria com os três campos preenchidos — como no site de verdade.
            if self.nome and self.expira and self.limite:
                self.criada = True
        return {
            "executou": True,
            "como": f"clique físico em {caixa[0]},{caixa[1]}" if caixa else "clique",
            "cursor_voltou": True,
        }

    # o driver relê pelo handle: aqui a janela nunca “fecha”
    def janela_muda(self, _handle) -> bool:
        return True

    def ler_janela(self, _handle, _profundidade=8, _limite=1500, fonte="auto"):
        self.fontes = getattr(self, "fontes", []) + [fonte]
        montada = self.montar()
        return {
            "janela": {"handle": 4242, "titulo": montada.get("alvo") or "OpenRouter", "processo": "chrome"},
            "raiz": montada.get("arvore"),
            "fonte": "uia",
        }

    def trazer_para_frente(self, _handle) -> bool:
        return True

    def teclado_na_janela(self, _handle) -> bool:
        return True

    def digitar(self, texto: str) -> None:
        self.digitado = texto

    def _nome_da_caixa(self, caixa: list[int]) -> str:
        mapa = {
            tuple(CAIXA_NEW_KEY): "New key",
            tuple(CAIXA_NOME): "Name",
            tuple(CAIXA_EXPIRACAO): "Select expiration",
            tuple(CAIXA_LIMITE): "Choose a credit limit",
            tuple(CAIXA_CREATE): "Create",
            tuple(CAIXA_COPIAR): "Copy",
        }
        if tuple(caixa) in mapa:
            return mapa[tuple(caixa)]
        if caixa and caixa[0] == 500:
            indice = (caixa[1] - 400) // 30
            if caixa[1] < 600 and 0 <= indice < len(self.opcoes_expiracao):
                return self.opcoes_expiracao[indice]
            indice = (caixa[1] - 600) // 30
            if 0 <= indice < len(self.opcoes_limite):
                return self.opcoes_limite[indice]
        return "?"


def _montar(monkeypatch, paginas: list[dict[str, Any]], windows: WindowsFalso, config: ConfiguradorFalso):
    script = _script()
    fila = list(paginas)

    # Cada tela da fila fica de pé por algumas leituras: o passo do diálogo
    # relê a janela várias vezes (nome, expiração, limite) antes de clicar.
    repetidas = [tela for tela in fila for _ in range(4)] or [PAGINA_COM_COPIA]

    def ler(_alvo):
        return JANELA, repetidas.pop(0) if len(repetidas) > 1 else (repetidas[0] if repetidas else PAGINA_COM_COPIA)

    monkeypatch.setattr(script, "_ler_janela", ler)
    monkeypatch.setattr(script, "_modulo_do_configurador", lambda: config)
    monkeypatch.setattr(script, "_gravar", lambda _modulo, chave: config.gravadas.append(chave) or 0)
    relogio = itertools.count()
    monkeypatch.setattr(
        script,
        "time",
        types.SimpleNamespace(time=lambda: next(relogio) * 10.0, sleep=lambda _s: None),
    )
    monkeypatch.setitem(sys.modules, "server.arvore_windows", windows)
    # O passo 4 da 0.91.12 tenta o texto da página (mesa de verdade: no Linux
    # não há teclado) e depois o botão “Copy”; aqui a área responde na hora,
    # que é o que o dono veria no Windows.
    monkeypatch.setattr(script, "_copiar_pela_pagina", lambda _janela: False)
    monkeypatch.setattr(
        script, "_esperar_chave", lambda _modulo, _antes, segundos=0: (config.chave, config.chave)
    )
    return script


def _com_mundo(monkeypatch, mundo: Mundo, config: ConfiguradorFalso | None = None):
    """Liga o script a um OpenRouter de mentira com estado (o diálogo de verdade)."""
    script = _script()
    monkeypatch.setattr(script, "_ler_janela", lambda _alvo, **_k: (JANELA, mundo.montar()))
    monkeypatch.setattr(script, "_reler", lambda janela, _p=8, _l=1500: (janela, mundo.montar()))
    relogio = itertools.count()
    monkeypatch.setattr(
        script,
        "time",
        types.SimpleNamespace(time=lambda: next(relogio) * 1.0, sleep=lambda _s: None),
    )
    monkeypatch.setitem(sys.modules, "server.arvore_windows", mundo)
    config = config or ConfiguradorFalso()
    monkeypatch.setattr(script, "_modulo_do_configurador", lambda: config)
    monkeypatch.setattr(script, "_gravar", lambda _modulo, chave: config.gravadas.append(chave) or 0)
    monkeypatch.setattr(script, "_copiar_pela_pagina", lambda _janela: False)
    monkeypatch.setattr(
        script, "_esperar_chave", lambda _modulo, _antes, segundos=0: (config.chave, config.chave)
    )
    return script, config


def test_a_sequencia_inteira_preenche_o_dialogo_cria_copia_e_grava(monkeypatch, capsys):
    """O caminho completo, com o diálogo de três campos que o dono fotografou."""
    mundo = Mundo()
    script, config = _com_mundo(monkeypatch, mundo)

    codigo = script.passo_criar(_args())
    saida = capsys.readouterr().out

    assert codigo == 0
    assert mundo.nome == "jarvis-teste"
    assert mundo.expira == "Never", "prazo mais longo: chave que expira derruba o JARVIS depois"
    assert mundo.limite == "No limit"
    assert mundo.criada is True
    assert config.gravadas == [config.chave]
    assert "expiração: escolhendo “Never”" in saida
    assert "cursor voltou" in saida


def test_sem_autorizar_nada_e_clicado(monkeypatch, capsys):
    windows = WindowsFalso()
    script = _montar(monkeypatch, [PAGINA_INICIAL], windows, ConfiguradorFalso())

    codigo = script.passo_criar(_args(autorizar=False))

    assert codigo == 0
    assert windows.chamadas == []
    assert "--autorizar" in capsys.readouterr().out


def test_sem_mouse_chega_ao_executor_como_pedido(monkeypatch):
    class MundoSemMouse(Mundo):
        def __init__(self) -> None:
            super().__init__()
            self.mouses: list[bool] = []

        def executar_ref(self, handle, caminho, acao, texto="", caixa=None, mouse=False, primeiro_mouse=False):
            self.mouses.append(bool(mouse))
            return super().executar_ref(handle, caminho, acao, texto, caixa, mouse, primeiro_mouse)

    mundo = MundoSemMouse()
    config = ConfiguradorFalso(chave="sk-or-v1-" + "cd" * 34)
    script, _config = _com_mundo(monkeypatch, mundo, config)

    assert script.passo_criar(_args(sem_mouse=True)) == 0
    assert mundo.mouses, "houve cliques"
    assert not any(mundo.mouses), "--sem-mouse não pode mover o ponteiro em nenhum passo"


def test_clique_recusado_para_no_passo_e_diz_o_motivo(monkeypatch, capsys, tmp_path):
    windows = WindowsFalso({"executou": False, "como": "nenhum", "motivo": "o botão não aceita clique."})
    script = _montar(monkeypatch, [PAGINA_INICIAL], windows, ConfiguradorFalso())
    # a falha grava o relatório na pasta do script: aqui, na temporária
    monkeypatch.setattr(script, "__file__", str(tmp_path / "chave-no-navegador.py"))

    codigo = script.passo_criar(_args())
    saida = capsys.readouterr().out

    assert codigo == 1
    assert "1. NÃO DEI" in saida
    assert "não aceita clique" in saida
    assert len(windows.chamadas) == 1, "parou no primeiro passo, não inventou os outros"


def test_area_de_transferencia_vazia_diz_o_que_fazer(monkeypatch, capsys):
    config = ConfiguradorFalso(erro=True)
    script = _montar(monkeypatch, [], WindowsFalso(), config)

    codigo = script.passo_pegar(_args())

    assert codigo == 1
    assert "--pegar" in capsys.readouterr().out


@pytest.mark.parametrize("nome", ["Copy", "Copiar", "Create Key"])
def test_o_script_tem_a_opcao_do_mouse_documentada(nome):
    texto = (RAIZ / "chave-no-navegador.py").read_text(encoding="utf-8")
    assert "--sem-mouse" in texto


# ------------------------------------------------- gravar sem perguntar nada
#
# O duplo clique em `pegar-chave.bat` não pode parar em três perguntas que já
# têm resposta no .env. Antes da 0.91.11, trocar a chave chamava o questionário
# inteiro da primeira configuração.

def test_com_provedor_ja_escolhido_grava_so_a_chave(tmp_path, monkeypatch):
    import importlib.util as _imp

    caminho_cc = RAIZ / "configurar-chave.py"
    spec_cc = _imp.spec_from_file_location("config_para_teste", caminho_cc)
    cc = _imp.module_from_spec(spec_cc)
    spec_cc.loader.exec_module(cc)

    env = tmp_path / ".env"
    env.write_text(
        "JARVIS_AI_PROVIDER=openrouter\n"
        "JARVIS_AI_BASE_URL=https://openrouter.ai/api/v1\n"
        "JARVIS_AI_MODEL=deepseek/deepseek-chat-v3-0324:free\n"
        "JARVIS_AI_API_KEY=sk-or-v1-velha\n"
        "# comentario do dono\n"
    )
    monkeypatch.setattr(cc, "ENV", env)

    def perguntou(*_a, **_k):
        raise AssertionError("não podia perguntar nada: o provedor já estava gravado")

    monkeypatch.setattr(cc, "perguntar", perguntou)

    nova = "sk-or-v1-" + "9f" * 34
    assert _script()._gravar(cc, nova) == 0

    escrito = env.read_text()
    assert f"JARVIS_AI_API_KEY={nova}" in escrito
    assert "# comentario do dono" in escrito, "as outras linhas ficam como estavam"
    assert "deepseek" in escrito
    assert b"\r\n" in env.read_bytes(), ".env é CRLF"


def test_sem_provedor_gravado_cai_no_questionario(tmp_path, monkeypatch):
    import importlib.util as _imp

    spec_cc = _imp.spec_from_file_location("config_para_teste2", RAIZ / "configurar-chave.py")
    cc = _imp.module_from_spec(spec_cc)
    spec_cc.loader.exec_module(cc)
    env = tmp_path / ".env"
    env.write_text("JARVIS_AI_PROVIDER=\n")
    monkeypatch.setattr(cc, "ENV", env)
    chamado: list[list[str]] = []
    monkeypatch.setattr(cc, "principal", lambda argv: chamado.append(argv) or 0)

    assert _script()._gravar(cc, "sk-or-v1-" + "aa" * 34) == 0
    assert chamado == [["--chave", "sk-or-v1-" + "aa" * 34]]


# ----------------------------------------------------------- o duplo clique

def test_o_bat_existe_e_e_ascii_com_crlf():
    bruto = (RAIZ / "pegar-chave.bat").read_bytes()
    texto = bruto.decode("ascii")  # o console do 1607 não mostra acento
    assert bruto.count(b"\r\n") == texto.count("\n") == texto.count("\r")


def test_o_bat_tenta_sozinho_e_tem_o_plano_b_ao_lado():
    """0.91.12 — o duplo clique tenta fazer tudo; se não der, lê o que ele copiou.

    `--abrir` saiu de cena: abrir sozinho era o problema que o dono apontou
    (“ele deve abrir os sites [...] para ele poder copiar e colar”). O `--auto`
    abre, cria, copia e grava; o `--pegar` fica como segunda chance, no mesmo
    arquivo, sem precisar de outro comando.
    """
    texto = (RAIZ / "pegar-chave.bat").read_text(encoding="ascii")
    assert "--auto --autorizar" in texto
    assert "--pegar" in texto
    assert ".venv\\Scripts\\python.exe" in texto
    assert 'set "PYTHON=' in texto, "o caminho do python tem de estar definido"


def test_o_bat_nao_tem_salto_para_rotulo_inexistente():
    import re

    texto = (RAIZ / "pegar-chave.bat").read_text(encoding="ascii")
    rotulos = set(re.findall(r"^:(\w+)", texto, re.M))
    saltos = set(re.findall(r"goto\s+(\w+)", texto))
    assert saltos <= rotulos, f"salto sem rótulo: {saltos - rotulos}"
    assert "tentar" in rotulos, "tem de dar para tentar de novo sem fechar a janela"


# ------------------------------------------------- o comando único (--auto)
#
# “Ele deve abrir os sites onde estão as chaves para ele poder copiar e colar
# na própria pasta.” — o `--auto` é isto: abrir, criar, copiar e gravar, sem
# pedir comando nenhum no meio. E, se não puder clicar, esperar a cópia do dono
# em vez de terminar com erro.

CHAVE_NOVA = "sk-or-v1-" + "7c" * 34
CHAVE_VELHA = "sk-or-v1-antiga-copiada-ontem-0123456789abcdef"


class ConfiguradorAuto(ConfiguradorFalso):
    """Configurador com um `.env` em memória e um navegador que abre."""

    CHAVE = "JARVIS_AI_API_KEY"

    def __init__(self, provedor: str = "openrouter") -> None:
        super().__init__(chave=CHAVE_NOVA)
        self.ENV = Path("/nao/existe/.env")
        self.texto = f"JARVIS_AI_PROVIDER={provedor}\nJARVIS_AI_BASE_URL=https://openrouter.ai/api/v1\n"
        self.abertos: list[str] = []
        self.gravada: str = ""

    def texto_base(self) -> str:
        return self.texto

    def ler_valor(self, texto: str, nome: str):
        for linha in texto.splitlines():
            if linha.startswith(nome + "="):
                return linha.split("=", 1)[1]
        return None

    def definir(self, texto: str, nome: str, valor: str) -> str:
        return texto + f"{nome}={valor}\n"

    def gravar(self, texto, _caminho=None):
        self.gravada = texto
        return ".env"

    def mascarar(self, chave: str) -> str:
        return f"{chave[:5]}…{chave[-4:]} ({len(chave)} caracteres)"

    def guia_do_provedor(self, provedor: str, _base: str):
        onde = {
            "openrouter": "openrouter.ai/keys",
            "groq": "console.groq.com/keys",
        }.get(provedor.strip().lower(), "")
        return {"nome": provedor, "onde": onde}

    def abrir_no_navegador(self, endereco: str) -> bool:
        self.abertos.append(endereco)
        return True

    def chaves_do_texto(self, texto: str) -> list[str]:
        import re

        return re.findall(r"sk-or-v1-[A-Za-z0-9]{20,}", texto)

    def sem_controle(self, texto: str) -> str:
        return texto


def _auto(monkeypatch, paginas, area, windows=None, config=None, **extra):
    """O `--auto` com um site de mentira que **muda quando é clicado**.

    Modelar o site (e não a leitura) é o que deixa o dublê honesto: a página
    das chaves mostra “New key”; o clique troca a tela pelo painel; o clique em
    “Create” troca pela página já criada. É assim que o Chrome do dono se
    comporta — e é o que permite testar a espera da página e a do painel.
    """
    script = _script()
    pagina = {"i": 0}

    def atual() -> dict[str, Any]:
        return paginas[min(pagina["i"], len(paginas) - 1)]

    def bruto(handle: int) -> dict[str, Any]:
        tela = atual()
        return {
            "janela": {"handle": handle, "titulo": str(tela.get("alvo") or "API Keys"), "processo": "chrome"},
            "raiz": tela.get("arvore"),
            "fonte": "uia",
        }

    modulo = windows or WindowsFalso()
    modulo.ler_janela = lambda handle, _p=8, _l=1500, fonte="auto": bruto(handle)
    clique = modulo.executar_ref

    def nome_do_botao(caixa_alvo) -> str:
        """Que botão tem esta caixa na tela de agora (para saber se ela muda)."""
        pilha = [atual().get("arvore")]
        while pilha:
            no = pilha.pop()
            if not isinstance(no, dict):
                continue
            if list(no.get("caixa") or []) == list(caixa_alvo or []):
                return str(no.get("nome") or "")
            pilha.extend(no.get("filhos") or [])
        return ""

    def executar(handle, caminho, acao, texto="", caixa=None, mouse=False, primeiro_mouse=False):
        resultado = clique(handle, caminho, acao, texto, caixa, mouse, primeiro_mouse)
        # Só os botões trocam a tela: digitar no nome não é navegação.
        nome = nome_do_botao(caixa)
        if any(marca in nome.lower() for marca in ("create", "new key")):
            pagina["i"] += 1
        return resultado

    modulo.executar_ref = executar
    monkeypatch.setitem(sys.modules, "server.arvore_windows", modulo)

    monkeypatch.setattr(script, "_ler_janela", lambda _alvo, **_k: (JANELA, atual()))
    monkeypatch.setattr(script, "_levar_ate_as_chaves", lambda _args, conta="", segundos=0: (JANELA, paginas[0]))
    monkeypatch.setattr(script, "_texto_da_area", lambda: area["texto"])
    relogio = itertools.count()
    monkeypatch.setattr(
        script, "time", types.SimpleNamespace(time=lambda: next(relogio) * 0.5, sleep=lambda _s: None)
    )
    config = config or ConfiguradorAuto()
    monkeypatch.setattr(script, "_modulo_do_configurador", lambda: config)
    base = _args(provedor="", espera_pagina=5, espera_colar=5)
    for chave, valor in extra.items():
        setattr(base, chave, valor)
    return script, config, base


def test_auto_abre_cria_copia_e_grava_a_chave_nova(monkeypatch, capsys):
    area = {"texto": CHAVE_VELHA}  # já havia uma chave copiada antes
    # O diálogo de verdade: nome, expiração e limite (as listas não abrem no
    # dublê, e o script segue avisando — o que importa aqui é o caminho inteiro).
    dialogo = _pagina(
        _no("Create API key"),
        _no("Key name", [400, 300, 320, 30], papel=42),
        _no("Select expiration", [400, 380, 320, 30]),
        _no("Choose a credit limit", [400, 460, 320, 30]),
        _no("Create", [700, 640, 80, 28]),
    )
    paginas = [_pagina(_no("Create Key", [812, 200, 90, 28])), dialogo, PAGINA_COM_COPIA]
    script, config, args = _auto(monkeypatch, paginas, area)
    # a página, depois de criar, tem a chave escrita nela: Ctrl+A/Ctrl+C copia isso
    monkeypatch.setattr(
        script,
        "_copiar_pela_pagina",
        lambda _janela: (area.__setitem__("texto", f"API Keys\n{CHAVE_NOVA}\nCopiar"), True)[1],
    )

    assert script.passo_auto(args) == 0

    assert config.abertos == ["openrouter.ai/keys"]
    assert CHAVE_NOVA in config.gravada
    assert CHAVE_VELHA not in config.gravada, "a chave copiada antes não pode ser confundida"
    assert "sk-or…7c7c" in capsys.readouterr().out


def test_auto_sem_botao_na_arvore_espera_o_dono_copiar(monkeypatch, capsys):
    """Página que não publica botão: o JARVIS não desiste, ele espera a cópia."""
    area = {"texto": CHAVE_VELHA}
    paginas = [_pagina(_no("Settings"), _no("Docs"))]
    script, config, args = _auto(monkeypatch, paginas, area, espera_colar=4)

    def copia_do_dono(_modulo, _antes, segundos=0):
        assert segundos == 4
        return (CHAVE_NOVA, CHAVE_NOVA)

    monkeypatch.setattr(script, "_esperar_chave", copia_do_dono)

    assert script.passo_auto(args) == 0
    assert "botões não estão na árvore" in capsys.readouterr().out
    assert CHAVE_NOVA in config.gravada


def test_auto_sem_autorizar_nao_abre_nem_cria(monkeypatch, capsys):
    area = {"texto": ""}
    script, config, args = _auto(monkeypatch, [_pagina(_no("Create Key"))], area, autorizar=False)

    assert script.passo_auto(args) == 0
    assert config.abertos == []
    assert config.gravada == ""
    assert "--autorizar" in capsys.readouterr().out


def test_auto_usa_o_site_do_provedor_pedido(monkeypatch, tmp_path):
    """O pedido foi “os sites onde estão as chaves” — não é só o OpenRouter."""
    area = {"texto": ""}
    paginas = [_pagina(_no("Create Key"))]
    script, config, args = _auto(monkeypatch, paginas, area, provedor="groq")
    # a página do dublê não tem painel; a falha grava o relatório na pasta do script
    monkeypatch.setattr(script, "__file__", str(tmp_path / "chave-no-navegador.py"))
    monkeypatch.setattr(script, "_esperar_chave", lambda _m, _a, segundos=0: (CHAVE_NOVA, CHAVE_NOVA))

    assert script.passo_auto(args) == 0
    assert config.abertos == ["console.groq.com/keys"]


def test_auto_sem_saber_o_provedor_nao_inventa(monkeypatch, capsys):
    area = {"texto": ""}
    config = ConfiguradorAuto(provedor="")
    script, _config, args = _auto(monkeypatch, [_pagina(_no("Create Key"))], area, config=config)

    assert script.passo_auto(args) == 1
    assert "Não sei qual provedor" in capsys.readouterr().out


def test_esperar_chave_ignora_o_que_ja_estava_copiado(monkeypatch):
    script = _script()
    area = {"texto": CHAVE_VELHA}
    monkeypatch.setattr(script, "_texto_da_area", lambda: area["texto"])
    relogio = itertools.count()
    monkeypatch.setattr(
        script, "time", types.SimpleNamespace(time=lambda: next(relogio) * 1.0, sleep=lambda _s: None)
    )

    assert script._esperar_chave(ConfiguradorAuto(), CHAVE_VELHA, segundos=3) is None


def test_copiar_pela_pagina_recusa_se_o_teclado_nao_esta_na_janela(monkeypatch):
    script = _script()

    class SemTeclado(WindowsFalso):
        def trazer_para_frente(self, _h):
            return True

        def teclado_na_janela(self, _h):
            return False

    monkeypatch.setitem(sys.modules, "server.arvore_windows", SemTeclado())
    assert script._copiar_pela_pagina({"handle": 1}) is False


# ------------------------------------------------- mais de uma janela aberta

def test_escolhe_a_janela_que_e_a_pagina_de_chaves(monkeypatch):
    """Chrome aberto com o e-mail e com as chaves: tem de ler a das chaves.

    Quando o dono já está com o navegador aberto, o link cai numa aba da janela
    em foco; escolher só por “chrome” empatava todas e podia ler a errada.
    """
    script = _script()
    janelas = [
        {"handle": 1, "titulo": "Caixa de entrada - Gmail", "processo": "chrome"},
        {"handle": 2, "titulo": "API Keys | OpenRouter", "processo": "chrome"},
    ]
    arvores = {
        1: {"janela": janelas[0], "fonte": "uia", "raiz": {"nome": "Caixa de entrada", "filhos": []}},
        2: {"janela": janelas[1], "fonte": "uia", "raiz": {"nome": "API Keys", "filhos": [
            {"nome": "Create Key", "papel": 43, "caixa": [10, 20, 80, 28], "filhos": []}]}},
    }

    class Windows(WindowsFalso):
        def janelas(self):
            return janelas

        def janela_em_foco(self):
            return janelas[0]

        def ler_janela(self, handle, _p=8, _l=1500):
            return arvores[int(handle)]

    monkeypatch.setitem(sys.modules, "server.arvore_windows", Windows())
    monkeypatch.setattr(script, "time", types.SimpleNamespace(time=lambda: 0.0, sleep=lambda _s: None))

    janela, montada = script._levar_ate_as_chaves(_args(), segundos=3)
    assert janela["handle"] == 2
    assert montada["arvore"]["nome"] == "API Keys"


def test_a_janela_em_foco_vem_primeiro(monkeypatch):
    script = _script()
    janelas = [
        {"handle": 10, "titulo": "Google Chrome", "processo": "chrome"},
        {"handle": 11, "titulo": "Outra janela do Chrome", "processo": "chrome"},
    ]

    class Windows(WindowsFalso):
        def janelas(self):
            return janelas

        def janela_em_foco(self):
            return janelas[1]

    monkeypatch.setitem(sys.modules, "server.arvore_windows", Windows())
    assert [j["handle"] for j in script._janelas_do_alvo("chrome")] == [11, 10]


# --------------------------------------------- o JARVIS aberto fica sabendo

def test_avisa_a_api_aberta_para_reler_o_env(monkeypatch):
    import io

    script = _script()
    chamadas = []

    class Resposta(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    def urlopen(pedido, timeout=0):
        chamadas.append((pedido.full_url, timeout))
        return Resposta(b'{"ok": true}')

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    assert script._avisar_jarvis_aberto() is True
    assert chamadas[0][0].endswith("/api/ai/recarregar")


def test_api_desligada_nao_e_erro(monkeypatch):
    script = _script()

    def sem_api(_pedido, timeout=0):
        raise OSError("conexão recusada")

    monkeypatch.setattr("urllib.request.urlopen", sem_api)
    assert script._avisar_jarvis_aberto() is False


# ------------------------------------------ atravessar o login (0.91.14)
#
# As três telas do dono, como ele as fotografou: Sign In do OpenRouter, a
# escolha de conta do Google (com duas contas) e, só então, API keys.

LOGIN = {
    "alvo": "chrome — Sign In | OpenRouter",
    "fonte": "uia",
    "arvore": {"nome": "Sign In", "filhos": [
        _no("GitHub"), _no("Google"), _no("Reddit"), _no("Email address"), _no("Continue")
    ]},
}
GOOGLE = {
    "alvo": "chrome — Fazer login nas Contas do Google",
    "fonte": "uia",
    "arvore": {"nome": "Escolha uma conta", "filhos": [
        _no("Victor vitor120956@gmail.com"),
        _no("Los PRO losproeduevi@gmail.com"),
        _no("Usar outra conta"),
    ]},
}
CHAVES = {
    "alvo": "chrome — Keys | Settings | OpenRouter",
    "fonte": "uia",
    "arvore": {"nome": "OpenRouter", "filhos": [
        _no("Keys"), _no("API keys"), _no("New key", [1400, 200, 100, 30])
    ]},
}


def _navegador_com_fila(monkeypatch, script, telas):
    """Um Chrome que mostra uma tela diferente a cada leitura."""
    fila = list(telas)

    def leitura(_alvo, maximo=3, **_k):
        tela = fila.pop(0) if len(fila) > 1 else fila[0]
        return [(JANELA, tela)]

    monkeypatch.setattr(script, "_ler_janelas", leitura)


def test_atravessa_login_google_conta_ate_as_chaves(monkeypatch, capsys):
    script = _script()
    windows = WindowsFalso()
    monkeypatch.setitem(sys.modules, "server.arvore_windows", windows)
    _navegador_com_fila(monkeypatch, script, [LOGIN, LOGIN, GOOGLE, GOOGLE, CHAVES])
    relogio = itertools.count()
    monkeypatch.setattr(
        script, "time", types.SimpleNamespace(time=lambda: next(relogio) * 1.0, sleep=lambda _s: None)
    )
    monkeypatch.setattr(script, "_perguntar_conta", lambda _contas: None)

    janela, montada = script._levar_ate_as_chaves(_args(conta="vitor120956"), segundos=30)

    assert montada is CHAVES
    clicados = [c for c in windows.chamadas if c["acao"] == "clicar"]
    assert len(clicados) == 2, "um clique no Google, um na conta — e nada mais"
    saida = capsys.readouterr().out
    assert "entrando pelo Google" in saida
    assert "vitor120956@gmail.com" in saida


def test_sem_saber_a_conta_ele_nao_chuta(monkeypatch, capsys):
    script = _script()
    monkeypatch.setitem(sys.modules, "server.arvore_windows", WindowsFalso())
    _navegador_com_fila(monkeypatch, script, [GOOGLE])
    relogio = itertools.count()
    monkeypatch.setattr(
        script, "time", types.SimpleNamespace(time=lambda: next(relogio) * 2.0, sleep=lambda _s: None)
    )
    monkeypatch.setattr(script, "_perguntar_conta", lambda _contas: None)

    with pytest.raises(script.PassoError) as erro:
        script._levar_ate_as_chaves(_args(conta=""), segundos=6)

    assert "--conta" in str(erro.value)
    assert "escolha de conta" in capsys.readouterr().out


def test_login_que_nao_passa_diz_para_entrar_uma_vez(monkeypatch):
    script = _script()
    monkeypatch.setitem(sys.modules, "server.arvore_windows", WindowsFalso())
    _navegador_com_fila(monkeypatch, script, [LOGIN])
    relogio = itertools.count()
    monkeypatch.setattr(
        script, "time", types.SimpleNamespace(time=lambda: next(relogio) * 2.0, sleep=lambda _s: None)
    )

    with pytest.raises(script.PassoError) as erro:
        script._levar_ate_as_chaves(_args(), segundos=6)

    assert "tela de login" in str(erro.value)


def test_a_conta_escolhida_fica_lembrada_no_env(monkeypatch, tmp_path):
    script = _script()
    config = ConfiguradorAuto()
    gravado = {}
    monkeypatch.setattr(
        script, "_guardar_conta", lambda _mod, email: gravado.setdefault("email", email) or True
    )
    monkeypatch.setattr(script, "_modulo_do_configurador", lambda: config)
    monkeypatch.setitem(sys.modules, "server.arvore_windows", WindowsFalso())

    estados = [(JANELA, GOOGLE, {"estado": "escolha de conta do Google", "conta_escolhida": None,
                                 "contas": [{"nome": "Victor vitor120956@gmail.com",
                                             "email": "vitor120956@gmail.com", "no": _no("Victor")}]})]
    monkeypatch.setattr(script, "_perguntar_conta", lambda contas: contas[0])

    assert script._tentar_entrar(_args(), estados, {"google": 0, "conta": 0}) is True
    assert gravado["email"] == "vitor120956@gmail.com"


# --------------------------------------- o diálogo de três campos (0.91.15)
#
# Medido na tela do dono: “Create API key” pede Name, Expiration e Credit
# limit. Com a expiração vazia o botão “Create” fica apagado — o clique não
# cria nada e não devolve erro. Era esse o travamento.

def test_sem_expiracao_nao_finge_que_criou(monkeypatch, capsys):
    class SemListas(Mundo):
        """Um site em que as listas suspensas não abrem (ou não publicam opções)."""

        def montar(self):
            arvore = super().montar()
            for filho in arvore["arvore"]["filhos"]:
                filho.pop("caixa", None) if False else None
            arvore["arvore"]["filhos"] = [
                no for no in arvore["arvore"]["filhos"] if no["nome"] not in OPCOES_EXPIRACAO + OPCOES_LIMITE
            ]
            return arvore

    mundo = SemListas()
    script, config = _com_mundo(monkeypatch, mundo)

    codigo = script.passo_criar(_args())
    saida = capsys.readouterr().out

    assert codigo == 1
    assert mundo.criada is False
    assert config.gravadas == [], "nada pode ser gravado sem chave"
    assert "CONTINUA aberto" in saida
    assert "expiração" in saida


def test_sem_never_escolhe_o_maior_prazo(monkeypatch):
    mundo = Mundo()
    mundo.opcoes_expiracao = ("7 days", "30 days", "90 days")
    script, _config = _com_mundo(monkeypatch, mundo)

    assert script.passo_criar(_args()) == 0
    assert mundo.expira == "90 days"


def test_o_dialogo_que_nao_abre_nao_vira_clique_no_new_key(monkeypatch, capsys, tmp_path):
    class NuncaAbre(Mundo):
        def executar_ref(self, handle, caminho, acao, texto="", caixa=None, mouse=False, primeiro_mouse=False):
            if list(caixa or []) == CAIXA_NEW_KEY:
                self.cliques.append(list(caixa))
                return {"executou": True, "como": "clique físico", "cursor_voltou": True}
            return super().executar_ref(handle, caminho, acao, texto, caixa, mouse, primeiro_mouse)

    mundo = NuncaAbre()
    script, config = _com_mundo(monkeypatch, mundo)
    # a falha grava o relatório na pasta do script: aqui vai para a temporária,
    # para a suíte não deixar arquivo no repositório
    monkeypatch.setattr(script, "__file__", str(tmp_path / "chave-no-navegador.py"))

    assert script.passo_criar(_args()) == 1
    # A escada da 0.91.18 tenta três degraus (mouse, mouse de novo, ação do
    # elemento) — e para. O que não pode acontecer é seguir para o “Create” da
    # página e dizer que criou.
    assert mundo.cliques == [CAIXA_NEW_KEY] * 3
    assert config.gravadas == []
    saida = capsys.readouterr().out
    assert "Nada foi criado" in saida
    assert "rode de novo" in saida


# ---------------------------------------------------------------------------
# 0.91.16 — o diálogo estava na tela e a leitura não o via
#
# Medido no PC do dono: print com “Create API key” aberto, e a saída dizendo
# “o diálogo de criação não apareceu na leitura”. O painel mora no fim de um
# documento grande; a leitura de 8 níveis parava antes.

def _fundo_do_documento() -> dict[str, Any]:
    """O diálogo de verdade — “Create API key” com os três campos."""
    return {
        "nome": "Create API key",
        "papel": 1,
        "filhos": [
            {"nome": "Name", "papel": 42, "caixa": [400, 300, 320, 30]},
            {"nome": "Select expiration", "papel": 43, "caixa": [400, 380, 320, 30]},
            {"nome": "Choose a credit limit", "papel": 43, "caixa": [400, 460, 320, 30]},
        ],
    }


def _enterrado(niveis: int) -> dict[str, Any]:
    """O diálogo dentro de `niveis` grupos — como no documento do Chrome."""
    raiz = _fundo_do_documento()
    for nivel in range(niveis):
        raiz = {"nome": f"grupo {nivel}", "papel": 1, "filhos": [raiz]}
    return raiz


class DuasJanelas:
    """Duas janelas do Chrome: a página numa, o painel na outra.

    É o caso que a escolha por nome não distingue: as duas são “chrome”.
    """

    def __init__(self, raiz_por_handle: dict[int, dict[str, Any]]) -> None:
        self.raizes = raiz_por_handle
        self.leituras: list[tuple[int, int]] = []

    def _janela(self, handle: int) -> dict[str, Any]:
        return {"handle": handle, "titulo": "API Keys | OpenRouter", "processo": "chrome"}

    def janelas(self):
        return [self._janela(handle) for handle in self.raizes]

    def janela_em_foco(self):
        return self._janela(next(iter(self.raizes)))

    def escolher_janela(self, _alvo, janelas=None, foco=None):
        return (janelas or self.janelas())[0]

    def janela_muda(self, _handle) -> bool:
        return True

    def ler_janela(self, handle, profundidade=8, limite=1500):
        self.leituras.append((int(handle), int(profundidade)))
        return {
            "janela": self._janela(int(handle)),
            "raiz": self.raizes[int(handle)],
            "fonte": "uia",
        }


def _relogio(monkeypatch, script) -> None:
    """Relógio que **anda**: fixo já pendurou a suíte uma vez (300 s)."""
    relogio = itertools.count()
    monkeypatch.setattr(
        script,
        "time",
        types.SimpleNamespace(time=lambda: next(relogio) * 0.5, sleep=lambda _s: None),
    )


def test_a_leitura_rasa_nao_ve_o_painel_e_a_funda_ve(monkeypatch):
    """A prova do erro: com 8 níveis, nada; com a leitura funda, o diálogo."""
    from server import arvore, chave_web

    bruto = {"janela": {"handle": 4242}, "raiz": _enterrado(12), "fonte": "uia"}
    assert chave_web.e_dialogo_de_criacao(arvore.montar(bruto, 8, 1500)) is False
    assert chave_web.e_dialogo_de_criacao(arvore.montar(bruto, 14, 3000)) is True


def test_esperar_dialogo_le_fundo_e_acha_o_painel_enterrado(monkeypatch):
    from server import chave_web

    script = _script()
    janelas = DuasJanelas({4242: _enterrado(12)})
    monkeypatch.setitem(sys.modules, "server.arvore_windows", janelas)
    _relogio(monkeypatch, script)

    janela = {"handle": 4242, "titulo": "API Keys | OpenRouter", "processo": "chrome"}
    achada, montada = script._esperar_dialogo(_args(), janela)

    assert int(achada["handle"]) == 4242
    assert chave_web.e_dialogo_de_criacao(montada)
    assert any(profundidade >= 12 for _handle, profundidade in janelas.leituras), (
        "a espera tem de reler fundo — foi a leitura rasa que disse “não apareceu”"
    )


def test_esperar_dialogo_olha_as_outras_janelas_do_navegador(monkeypatch):
    """O clique pode cair na janela A e o painel abrir na janela B."""
    script = _script()
    pagina = {"nome": "API Keys", "papel": 1, "filhos": [{"nome": "New key", "papel": 43}]}
    janelas = DuasJanelas({4242: pagina, 5151: _fundo_do_documento()})
    monkeypatch.setitem(sys.modules, "server.arvore_windows", janelas)
    _relogio(monkeypatch, script)

    janela = {"handle": 4242, "titulo": "API Keys | OpenRouter", "processo": "chrome"}
    achada, _montada = script._esperar_dialogo(_args(), janela)

    assert int(achada["handle"]) == 5151, "o painel estava na outra janela"


def test_a_falta_do_dialogo_diz_quantos_elementos_a_leitura_viu():
    """"não apareceu" sem números não ajuda quem está vendo o diálogo na tela."""
    script = _script()

    texto = script._diagnostico_da_leitura(PAGINA_INICIAL)

    assert "2 elementos" in texto or "elementos com nome" in texto
    assert "Create Key" in texto, "dizer o que a leitura viu é o que torna o erro investigável"


# ---------------------------------------------------------------------------
# 0.91.17 — “acho que a página demorou e ele tentou antes de aparecer”
#
# Dois sintomas nas telas do dono:
#   print 1: a página ainda carregava e o clique caiu num botão que ia sumir;
#   print 2: o painel estava aberto e a leitura trouxe 3 nomes (a moldura).

def _moldura() -> dict[str, Any]:
    """O que o Chrome publica quando a leitura não chega na página."""
    return _pagina(
        _no("Chrome Legacy Window"),
        _no("Keys | Settings | OpenRouter"),
        _no("Notifications"),
    )


def _pagina_rica() -> dict[str, Any]:
    return _pagina(
        _no("API Keys"),
        _no("Create Key"),
        _no("Search"),
        _no("Keys"),
        _no("Settings"),
        _no("jarvis"),
        _no("Hermes"),
        _no("meugerador"),
        _no("Docs"),
    )


class MolduraOuPagina:
    """A escolha automática cai na moldura; a UIA mostra a página. É o print 2."""

    def __init__(self, moldura: dict, pagina: dict) -> None:
        self.moldura, self.pagina = moldura, pagina
        self.pedidas: list[str] = []

    def _janela(self, handle: int) -> dict[str, Any]:
        return {"handle": handle, "titulo": "Keys | Settings | OpenRouter", "processo": "chrome"}

    def janela_muda(self, _handle) -> bool:
        return True

    def ler_janela(self, handle, _profundidade=8, _limite=1500, fonte="auto"):
        self.pedidas.append(fonte)
        tela = self.pagina if fonte == "uia" else self.moldura
        return {"janela": self._janela(int(handle)), "raiz": tela["arvore"], "fonte": fonte}


def test_leitura_pobre_e_repetida_pela_uia_e_acha_a_pagina(monkeypatch):
    """O print 2: 3 nomes não são “a página não tem o painel” — é leitura ruim."""
    script = _script()
    falso = MolduraOuPagina(_moldura(), _pagina_rica())
    monkeypatch.setitem(sys.modules, "server.arvore_windows", falso)

    _janela, montada = script._reler(JANELA, script.PROFUNDA, script.TETO_FUNDO)

    assert script._nomes(montada) >= 8, "com a moldura sozinha o script conclui errado"
    assert "uia" in falso.pedidas, "leitura pobre tem de ser repetida pela UIAutomation"


def test_esperar_dialogo_nao_desiste_por_causa_de_uma_leitura_pobre(monkeypatch, capsys):
    """Duas leituras ruins seguidas não são resposta: o painel aparece depois."""
    script = _script()
    dialogo = _pagina(
        _no("Create API key"), _no("Key name", papel=42), _no("Select expiration"), _no("Create")
    )
    fila = [_moldura(), _moldura(), dialogo]
    monkeypatch.setattr(script, "_reler", lambda janela, _p=8, _l=1500: (janela, fila.pop(0) if len(fila) > 1 else fila[0]))
    relogio = itertools.count()
    monkeypatch.setattr(
        script, "time", types.SimpleNamespace(time=lambda: next(relogio) * 0.5, sleep=lambda _s: None)
    )

    _janela, montada = script._esperar_dialogo(_args(), JANELA)

    assert any(no.get("nome") == "Create" for no in chave_web.elementos(montada))
    assert "esperando o painel abrir" in capsys.readouterr().out


def test_a_falta_do_painel_diz_que_a_leitura_veio_pobre():
    """“não apareceu” sozinho não distingue página sem painel de leitura ruim."""
    script = _script()

    texto = script._diagnostico_da_leitura(_moldura())

    assert "elementos com nome" in texto
    assert "fonte" in texto, "dizer de qual fonte veio é o que permite investigar"
    assert "veio pobre" in texto


def test_o_relatorio_da_falha_guarda_as_tres_leituras(tmp_path, monkeypatch):
    """Falhou? Fica um arquivo na pasta com o que cada fonte mostrou."""
    script = _script()
    falso = MolduraOuPagina(_moldura(), _pagina_rica())
    monkeypatch.setitem(sys.modules, "server.arvore_windows", falso)
    monkeypatch.setattr(script, "__file__", str(tmp_path / "chave-no-navegador.py"))

    resultado = script._gravar_relatorio(JANELA)

    arquivo = tmp_path / "chave-leitura.txt"
    assert resultado["arquivo"] and arquivo.exists()
    texto = arquivo.read_text(encoding="utf-8")
    for fonte in ("auto", "uia", "msaa"):
        assert fonte in texto
    assert "primeiros:" in texto


def test_espera_a_pagina_parar_de_carregar_antes_de_clicar(monkeypatch, capsys):
    """O print 1: clicar enquanto a página monta é o mesmo que não clicar."""
    script = _script()
    vazia = _pagina(_no("Nova guia"))
    fila = [vazia, _pagina_rica(), _pagina_rica()]
    monkeypatch.setattr(
        script, "_reler", lambda janela, _p=8, _l=1500: (janela, fila.pop(0) if len(fila) > 1 else fila[0])
    )
    relogio = itertools.count()
    monkeypatch.setattr(
        script, "time", types.SimpleNamespace(time=lambda: next(relogio) * 1.0, sleep=lambda _s: None)
    )

    _janela, montada = script._esperar_pagina_pronta(_args(), JANELA, vazia)

    assert chave_web.procurar(montada, chave_web.PADROES_CRIAR), "só clica com o botão na tela"
    assert "carregando" in capsys.readouterr().out


def test_leitura_que_despenca_depois_do_create_nao_vira_veredito(monkeypatch, capsys):
    """43 nomes → 3 nomes: quem falhou foi a leitura, não o clique.

    Sem esta regra, o script diria “o painel continua aberto, não criou” com a
    chave criada na conta — e não tentaria copiar.
    """
    class Despenca(Mundo):
        def __init__(self) -> None:
            super().__init__()
            self.despencou = False

        def executar_ref(self, handle, caminho, acao, texto="", caixa=None, mouse=False, primeiro_mouse=False):
            resultado = super().executar_ref(handle, caminho, acao, texto, caixa, mouse, primeiro_mouse)
            if list(caixa or []) == CAIXA_CREATE:
                self.despencou = True
            return resultado

        def montar(self):
            if not self.despencou:
                arvore = super().montar()
                if self.tela == "dialogo":
                    arvore["arvore"]["filhos"] += [
                        self._no(f"chave {indice}", [100, 900 + indice, 40, 20])
                        for indice in range(10)
                    ]
                return arvore
            moldura = _moldura()
            moldura["alvo"] = "Keys | Settings | OpenRouter"
            return moldura

    mundo = Despenca()
    script, config = _com_mundo(monkeypatch, mundo)
    monkeypatch.setattr(script, "_copiar_pela_pagina", lambda _janela: True)

    codigo = script.passo_criar(_args())
    saida = capsys.readouterr().out

    assert codigo == 0
    assert "despencou" in saida
    assert "CONTINUA aberto" not in saida, "leitura ruim não é prova de que o painel ficou aberto"
    assert config.gravadas == [config.chave]


def test_se_o_painel_nao_abrir_numa_pagina_legivel_ele_tenta_uma_vez_mais(monkeypatch, capsys, tmp_path):
    """O print 1: a página já estava legível (43 elementos) e o painel não veio.

    Com prova de que o painel **não** está aberto, repetir o clique é seguro —
    e foi o que faltou: ele desistiu na primeira tentativa e mandou o dono
    clicar à mão.
    """
    class Engasga(Mundo):
        def __init__(self) -> None:
            super().__init__()
            self.cliques_new_key = 0

        def montar(self):
            arvore = super().montar()
            if self.tela == "chaves":
                arvore["arvore"]["filhos"] += [
                    self._no(f"chave {indice}", [100, 500 + indice, 40, 20]) for indice in range(8)
                ]
            return arvore

        def executar_ref(self, handle, caminho, acao, texto="", caixa=None, mouse=False, primeiro_mouse=False):
            if list(caixa or []) == CAIXA_NEW_KEY:
                self.cliques_new_key += 1
                if self.cliques_new_key == 1:  # o primeiro clique se perde
                    self.cliques.append(list(caixa))
                    return {"executou": True, "como": "clique físico", "cursor_voltou": True}
            return super().executar_ref(handle, caminho, acao, texto, caixa, mouse, primeiro_mouse)

    mundo = Engasga()
    script, config = _com_mundo(monkeypatch, mundo)
    # a primeira tentativa falha de propósito e grava o relatório: vai para a
    # pasta temporária, não para o repositório
    monkeypatch.setattr(script, "__file__", str(tmp_path / "chave-no-navegador.py"))

    codigo = script.passo_criar(_args())
    saida = capsys.readouterr().out

    assert codigo == 0
    assert mundo.cliques_new_key == 2, "uma nova tentativa, não dez"
    assert "segunda vez" in saida
    assert config.gravadas == [config.chave]


# ---------------------------------------------------------------------------
# 0.91.18 — o clique que abre o painel é o do mouse, não a “ação do elemento”
#
# Medido no PC do dono: `accDoDefaultAction` devolveu S_OK e o painel não abriu.
# O `.bat` não passa `--mouse`, então o clique físico nunca era tentado.

def test_o_clique_no_new_key_e_do_mouse_por_padrao(monkeypatch):
    mundo = Mundo()
    script, _config = _com_mundo(monkeypatch, mundo)

    assert script.passo_criar(_args()) == 0

    primeiro = mundo.pedidos[0]
    assert primeiro["mouse"] is True
    assert primeiro["primeiro_mouse"] is True, (
        "a ação do elemento devolve sucesso sem fazer nada no Chrome; o clique de verdade vem antes"
    )


def test_sem_mouse_nenhum_pedido_de_clique_fisico(monkeypatch):
    mundo = Mundo()
    script, _config = _com_mundo(monkeypatch, mundo)

    assert script.passo_criar(_args(sem_mouse=True)) == 0

    assert mundo.pedidos, "alguma coisa foi clicada"
    assert all(p["mouse"] is False and p["primeiro_mouse"] is False for p in mundo.pedidos)


def test_se_o_primeiro_clique_nao_abrir_o_painel_ele_clica_de_novo(monkeypatch, capsys, tmp_path):
    """O primeiro clique pode só ativar a janela — o segundo é o que aperta."""
    class EngoleOImediato(Mundo):
        def __init__(self) -> None:
            super().__init__()
            self.engoliu = False

        def executar_ref(self, handle, caminho, acao, texto="", caixa=None, mouse=False, primeiro_mouse=False):
            if list(caixa or []) == CAIXA_NEW_KEY and not self.engoliu:
                self.engoliu = True
                self.cliques.append(list(caixa))
                self.pedidos.append({"mouse": mouse, "primeiro_mouse": primeiro_mouse, "caixa": list(caixa)})
                return {"executou": True, "como": "clique físico em 0,0", "cursor_voltou": True}
            return super().executar_ref(handle, caminho, acao, texto, caixa, mouse, primeiro_mouse)

    mundo = EngoleOImediato()
    script, config = _com_mundo(monkeypatch, mundo)
    monkeypatch.setattr(script, "__file__", str(tmp_path / "chave-no-navegador.py"))

    assert script.passo_criar(_args()) == 0
    saida = capsys.readouterr().out

    new_key = [p for p in mundo.pedidos if p["caixa"] == CAIXA_NEW_KEY]
    assert len(new_key) == 2
    assert all(p["primeiro_mouse"] for p in new_key), "as duas tentativas são de clique de verdade"
    assert "segunda vez" in saida
    assert config.gravadas == [config.chave]


def test_a_janela_tem_de_estar_na_frente_antes_do_clique(monkeypatch, capsys):
    class NuncaVemParaFrente(Mundo):
        def executa_foco_falso(self):  # pragma: no cover - só documenta a ideia
            return None

    mundo = NuncaVemParaFrente()
    script, config = _com_mundo(monkeypatch, mundo)
    monkeypatch.setattr(script, "_garantir_na_frente", lambda _janela, segundos=2.0: False)

    # Mesmo sem conseguir trazer a janela, o clique é tentado — mas o dono é avisado.
    assert script.passo_criar(_args()) == 0
    assert "não consegui pôr a janela na frente" in capsys.readouterr().out


def test_garantir_na_frente_confere_pelo_windows(monkeypatch):
    script = _script()
    foco = {"handle": 4242, "titulo": "API Keys | OpenRouter"}
    falso = types.SimpleNamespace(
        trazer_para_frente=lambda _h: True,
        janela_em_foco=lambda: foco,
    )
    monkeypatch.setitem(sys.modules, "server.arvore_windows", falso)

    assert script._garantir_na_frente({"handle": 4242}) is True

    falso.janela_em_foco = lambda: {"handle": 9999}
    monkeypatch.setattr(script, "time", types.SimpleNamespace(time=lambda: 0.0, sleep=lambda _s: None))
    # com a janela sempre atrás, a confirmação falha — e isso não é exceção
    assert script._garantir_na_frente({"handle": 4242}, segundos=0.0) is False


def test_ctrl_c_nao_vira_traceback(monkeypatch, capsys):
    """Ctrl+C é do dono: tem de sair com uma frase, não com 8 linhas de erro."""
    script = _script()

    def interrompido(_args):
        raise KeyboardInterrupt

    monkeypatch.setattr(script, "passo_auto", interrompido)
    monkeypatch.setattr(script, "_configurar_ambiente", lambda: None)
    monkeypatch.setattr(script.sys, "platform", "win32")

    codigo = script.main(["--auto"])
    saida = capsys.readouterr().out

    assert codigo == 130
    assert "Ctrl+C" in saida
    assert "nada foi gravado" in saida.lower()


def test_pegar_nao_anuncia_como_nova_a_chave_que_ja_estava(monkeypatch, capsys):
    """No PC do dono, o `--pegar` salvou a chave VELHA e o `.bat` disse “pronto”.

    Estava pronto mesmo — com a chave de antes. A frase tem de dizer isso.
    """
    script = _script()
    gravadas: list[str] = []

    class Modulo:
        CHAVE = "JARVIS_AI_API_KEY"

        def chave_da_area_de_transferencia(self):
            return f" {CHAVE_VELHA}\n", CHAVE_VELHA

        def descrever_area(self, _limpo, chave):
            return f"  chave na área: {chave[:10]}…"

    monkeypatch.setattr(script, "_modulo_do_configurador", lambda: Modulo())
    monkeypatch.setattr(script, "_chave_do_env", lambda _modulo: CHAVE_VELHA)
    monkeypatch.setattr(script, "_gravar", lambda _modulo, chave: gravadas.append(chave) or 0)

    assert script.passo_pegar(_args()) == 0
    saida = capsys.readouterr().out

    assert gravadas == [], "não regrava o que já está igual"
    assert "MESMA" in saida
    assert "COPIAR" in saida


def test_pegar_chave_nova_grava_como_sempre(monkeypatch, capsys):
    script = _script()
    gravadas: list[str] = []

    class Modulo:
        CHAVE = "JARVIS_AI_API_KEY"

        def chave_da_area_de_transferencia(self):
            return f" {CHAVE_NOVA}\n", CHAVE_NOVA

        def descrever_area(self, _limpo, chave):
            return f"  chave na área: {chave[:10]}…"

    monkeypatch.setattr(script, "_modulo_do_configurador", lambda: Modulo())
    monkeypatch.setattr(script, "_chave_do_env", lambda _modulo: CHAVE_VELHA)
    monkeypatch.setattr(script, "_gravar", lambda _modulo, chave: gravadas.append(chave) or 0)

    assert script.passo_pegar(_args()) == 0
    assert gravadas == [CHAVE_NOVA]
    assert "MESMA" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# 0.91.19 — “apertou em New key mas não digitou o nome”
#
# No painel de verdade, “Name” é um rótulo e a caixa de texto é outro nó. O
# script procurava por nome, achava o **rótulo**, clicava nele e mandava as
# teclas para o nada — e seguia dizendo que tinha escrito.

CAIXA_NOME_REAL = [400, 330, 300, 30]
CAIXA_BUSCA = [60, 100, 300, 30]


class PainelReal(Mundo):
    """O painel como o Chrome publica: rótulo separado da caixa, busca na página."""

    def montar(self) -> dict[str, Any]:
        if self.tela == "chaves":
            return {
                "alvo": "chrome — Keys | Settings | OpenRouter",
                "fonte": "uia",
                "arvore": {
                    "nome": "OpenRouter",
                    "filhos": [
                        self._no("Search by name or paste a key…", CAIXA_BUSCA),
                        self._no("New key", CAIXA_NEW_KEY),
                    ],
                },
            }
        filhos = [
            self._no("Create API key", [400, 180, 300, 30], papel=1),
            self._no("Name *", [400, 300, 300, 30], papel=41),
            self._no("e.g. “ChatbotKey”", CAIXA_NOME_REAL, papel=42),  # caixa de edição
            self._no(self.expira or "Select expiration", CAIXA_EXPIRACAO),
            self._no(self.limite or "Choose a credit limit", CAIXA_LIMITE),
            # Como no site: o Create só acende com os três campos preenchidos.
            # É essa luz que serve de prova quando o campo não publica o valor.
            self._no("Create", CAIXA_CREATE),
        ]
        create = next(no for no in filhos if no["nome"] == "Create")
        if not (self.nome and self.expira and self.limite):
            create["acionavel"] = False
        if self.lista_aberta == "expiracao":
            filhos += [
                self._no(opcao, [500, 400 + indice * 30, 200, 30])
                for indice, opcao in enumerate(self.opcoes_expiracao)
            ]
        if self.lista_aberta == "limite":
            filhos += [
                self._no(opcao, [500, 600 + indice * 30, 200, 30])
                for indice, opcao in enumerate(self.opcoes_limite)
            ]
        if self.criada:
            filhos = [self._no("Copy", CAIXA_COPIAR), self._no("API keys", [100, 100, 120, 30], papel=1)]
        return {
            "alvo": "chrome — Keys | Settings | OpenRouter",
            "fonte": "uia",
            "arvore": {"nome": "OpenRouter", "filhos": filhos},
        }


def test_o_nome_vai_para_a_caixa_e_nao_para_o_rotulo(monkeypatch, capsys):
    mundo = PainelReal()
    script, config = _com_mundo(monkeypatch, mundo)

    assert script.passo_criar(_args()) == 0
    saida = capsys.readouterr().out

    digitou_em = [p["caixa"] for p in mundo.pedidos if p["caixa"] == CAIXA_NOME_REAL]
    assert digitou_em, "o texto tem de ir para a caixa de texto"
    assert [400, 300, 300, 30] not in [p["caixa"] for p in mundo.pedidos], "o rótulo não recebe clique de escrita"
    assert CAIXA_BUSCA not in [p["caixa"] for p in mundo.pedidos], "a busca da página não é o campo do nome"
    assert mundo.nome == "jarvis-teste"
    assert "nome: digitado" in saida
    assert config.gravadas == [config.chave]


def test_sem_caixa_de_texto_na_leitura_o_script_nao_finge_que_digitou(monkeypatch, capsys, tmp_path):
    class SemCaixa(PainelReal):
        def montar(self):
            arvore = super().montar()
            if self.tela == "dialogo":
                arvore["arvore"]["filhos"] = [
                    no for no in arvore["arvore"]["filhos"] if no["nome"] != "e.g. “ChatbotKey”"
                ]
            return arvore

    mundo = SemCaixa()
    script, config = _com_mundo(monkeypatch, mundo)
    monkeypatch.setattr(script, "_digitar_na_janela", lambda _janela, _texto: False)
    monkeypatch.setattr(script, "__file__", str(tmp_path / "chave-no-navegador.py"))

    codigo = script.passo_criar(_args())
    saida = capsys.readouterr().out

    assert codigo == 1, "sem nome o Create fica apagado: não pode dizer que criou"
    assert "nenhuma caixa de texto" in saida
    assert "APAGADO" in saida, "botão apagado não se clica — e o dono tem de saber"
    assert config.gravadas == []


def test_quando_o_campo_diz_que_nao_recebeu_o_texto_ele_tenta_outro_degrau(monkeypatch, capsys):
    """`conferido=False` é a única prova direta de que as teclas não entraram."""
    class Confere(Mundo):
        def __init__(self) -> None:
            super().__init__()
            self.tentativas_de_escrita = 0

        def executar_ref(self, handle, caminho, acao, texto="", caixa=None, mouse=False, primeiro_mouse=False):
            if acao == "digitar":
                self.tentativas_de_escrita += 1
                self.cliques.append(list(caixa or []))
                self.pedidos.append({"mouse": mouse, "primeiro_mouse": primeiro_mouse, "caixa": caixa})
                if self.tentativas_de_escrita == 1:
                    # o clique caiu fora: o campo publica valor e continua vazio
                    return {"executou": True, "como": "clique físico no campo + teclado", "conferido": False}
                self.nome = texto
                return {"executou": True, "como": "foco + teclado", "conferido": True}
            return super().executar_ref(handle, caminho, acao, texto, caixa, mouse, primeiro_mouse)

    mundo = Confere()
    script, config = _com_mundo(monkeypatch, mundo)

    assert script.passo_criar(_args()) == 0
    saida = capsys.readouterr().out

    assert mundo.tentativas_de_escrita >= 2, "conferido=False tem de levar a uma segunda tentativa"
    assert "não mostra o texto" in saida
    assert config.gravadas == [config.chave]


def test_create_apagado_e_o_sinal_de_que_o_nome_nao_entrou(monkeypatch, capsys, tmp_path):
    """O campo não publica valor: quem diz se o nome entrou é o botão acender.

    Se ele continua apagado, o script reescreve o nome do zero (com Ctrl+A, para
    não virar “jarvis-testejarvis-teste”) — uma vez só.
    """
    class NaoPega(Mundo):
        """O clique no campo não escreve nada na primeira vez."""

        def __init__(self) -> None:
            super().__init__()
            self.escritas = 0

        def montar(self):
            arvore = super().montar()
            if self.tela == "dialogo":
                create = next(no for no in arvore["arvore"]["filhos"] if no["nome"] == "Create")
                if not (self.nome and self.expira and self.limite):
                    create["acionavel"] = False
            return arvore

        def executar_ref(self, handle, caminho, acao, texto="", caixa=None, mouse=False, primeiro_mouse=False):
            if acao == "digitar":
                self.escritas += 1
                self.cliques.append(list(caixa or []))
                self.pedidos.append({"mouse": mouse, "primeiro_mouse": primeiro_mouse, "caixa": caixa})
                # a primeira escrita "sai" mas não entra no campo
                if self.escritas > 2:
                    self.nome = texto
                return {"executou": True, "como": "clique físico no campo + teclado", "conferido": None}
            return super().executar_ref(handle, caminho, acao, texto, caixa, mouse, primeiro_mouse)

    mundo = NaoPega()
    script, config = _com_mundo(monkeypatch, mundo)
    monkeypatch.setattr(script, "__file__", str(tmp_path / "chave-no-navegador.py"))
    reescritas: list[str] = []
    monkeypatch.setattr(
        script, "_digitar_substituindo", lambda _janela, texto: (reescritas.append(texto), True)[1]
    )

    codigo = script.passo_criar(_args())
    saida = capsys.readouterr().out

    assert "continua apagado" in saida
    assert reescritas == ["jarvis-teste"], "reescreve uma vez, do zero"
    # a reescrita aqui é o dublê: o botão continua apagado e o script para sem gravar
    assert codigo == 1
    assert config.gravadas == []


def test_botao_de_criar_nao_e_o_titulo_do_painel():
    script = _script()
    from server import chave_web

    painel = {
        "alvo": "chrome — Keys",
        "arvore": {
            "nome": "página",
            "filhos": [
                {"nome": "Create API key", "papel": 1, "codigo": 1, "caixa": [400, 180, 300, 30], "acionavel": True},
                {"nome": "Create", "papel": 43, "codigo": 43, "caixa": [700, 640, 80, 28], "acionavel": False},
            ],
        },
    }

    botao = script._botao_de_criar(painel)

    assert botao is not None
    assert botao["nome"] == "Create", "o título também contém “create” — e não é botão"
    assert chave_web.normalizar(botao["nome"]) in script.ROTULOS_DO_CRIAR


# ---------------------------------------------------------------------------
# 0.91.20 — “o botão não está na árvore” com o botão na tela
#
# O dono mandou o print: a página inteira, “New key” visível no canto, e o
# script dizendo que o botão não estava na leitura. Ele desistia na **primeira**
# tentativa, usando a leitura que tinha em mãos.

def test_ele_insiste_ate_o_botao_aparecer_na_leitura(monkeypatch, capsys):
    """Leitura pobre nas primeiras tentativas não é resposta: ele relê."""
    script = _script()
    fila = [
        _moldura(),          # ainda carregando
        _moldura(),          # ainda carregando
        _pagina_rica(),      # a página, com “Create Key”
    ]
    monkeypatch.setattr(
        script, "_reler", lambda janela, _p=8, _l=1500: (janela, fila.pop(0) if len(fila) > 1 else fila[0])
    )
    relogio = itertools.count()
    monkeypatch.setattr(
        script, "time", types.SimpleNamespace(time=lambda: next(relogio) * 1.0, sleep=lambda _s: None)
    )

    janela, botao, montada = script._achar_elemento(
        JANELA, chave_web.PADROES_CRIAR, rotulo="o botão “New key”"
    )

    assert botao["nome"] == "Create Key"
    assert script._nomes(montada) >= 8
    assert "não veio na primeira leitura" in capsys.readouterr().out


def test_se_o_botao_nunca_aparecer_ele_diz_o_que_viu(monkeypatch, capsys, tmp_path):
    script = _script()
    monkeypatch.setattr(script, "_reler", lambda janela, _p=8, _l=1500: (janela, _moldura()))
    relogio = itertools.count()
    monkeypatch.setattr(
        script, "time", types.SimpleNamespace(time=lambda: next(relogio) * 10.0, sleep=lambda _s: None)
    )
    monkeypatch.setattr(script, "__file__", str(tmp_path / "chave-no-navegador.py"))

    with pytest.raises(script.PassoError) as erro:
        script._achar_elemento(JANELA, chave_web.PADROES_CRIAR, rotulo="o botão “New key”")

    texto = str(erro.value)
    assert "não achei o botão" in texto
    assert "elementos com nome" in texto, "desistir exige dizer o que a leitura viu"
    assert "Chrome Legacy Window" in texto
    assert (tmp_path / "chave-leitura.txt").exists(), "a falha grava o relatório"


def test_a_espera_da_pagina_usa_leitura_funda(monkeypatch, capsys):
    """A leitura que decide “pronto” é a mesma que vai clicar: não pode ser rasa."""
    script = _script()
    pedidas: list[int] = []

    def reler(janela, profundidade=8, _limite=1500):
        pedidas.append(profundidade)
        return janela, _pagina_rica()

    monkeypatch.setattr(script, "_reler", reler)
    relogio = itertools.count()
    monkeypatch.setattr(
        script, "time", types.SimpleNamespace(time=lambda: next(relogio) * 1.0, sleep=lambda _s: None)
    )

    script._esperar_pagina_pronta(_args(), JANELA, _moldura())

    assert pedidas and all(profundidade >= script.PROFUNDA for profundidade in pedidas)


def test_pagina_que_nao_sossega_diz_quantos_elementos_viu(monkeypatch, capsys):
    script = _script()
    # leituras sempre diferentes: a página nunca “para”
    leituras = itertools.count(3)

    def reler(janela, _p=8, _l=1500):
        quantidade = next(leituras)
        nomes = [_no(f"elemento {indice}", [100, 100 + indice * 10, 80, 20]) for indice in range(quantidade)]
        return janela, _pagina(*nomes)

    monkeypatch.setattr(script, "_reler", reler)
    relogio = itertools.count()
    monkeypatch.setattr(
        script, "time", types.SimpleNamespace(time=lambda: next(relogio) * 5.0, sleep=lambda _s: None)
    )

    script._esperar_pagina_pronta(_args(), JANELA, _moldura())

    assert "não sossegou" in capsys.readouterr().out


def test_sem_botao_o_passo_nao_segue_para_o_create(monkeypatch, capsys, tmp_path):
    """Sem o botão de criar, nada é clicado e nada é gravado."""
    mundo = Mundo()
    script_, config = _com_mundo(monkeypatch, mundo)
    monkeypatch.setattr(script_, "_reler", lambda janela, _p=8, _l=1500: (janela, _moldura()))
    monkeypatch.setattr(script_, "__file__", str(tmp_path / "chave-no-navegador.py"))
    relogio = itertools.count()
    monkeypatch.setattr(
        script_, "time", types.SimpleNamespace(time=lambda: next(relogio) * 10.0, sleep=lambda _s: None)
    )

    codigo = script_.passo_criar(_args())
    saida = capsys.readouterr().out

    assert codigo == 1
    assert "não achei o botão" in saida
    assert "New key" in saida or "New key" in saida.replace("“", "").replace("”", "")
    assert config.gravadas == []
