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
    no: dict[str, Any] = {"nome": nome, "papel": papel, "caminho": [0, 1]}
    if caixa:
        no["caixa"] = caixa
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

    # ------------------------------------------------------------ leitura
    def _no(self, nome: str, caixa: list[int], papel: int = 43) -> dict[str, Any]:
        return {"nome": nome, "papel": papel, "caixa": list(caixa), "acionavel": True, "caminho": [0, 1]}

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

    def ler_janela(self, _handle, _profundidade=8, _limite=1500):
        return self.montar()

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


def test_clique_recusado_para_no_passo_e_diz_o_motivo(monkeypatch, capsys):
    windows = WindowsFalso({"executou": False, "como": "nenhum", "motivo": "o botão não aceita clique."})
    script = _montar(monkeypatch, [PAGINA_INICIAL], windows, ConfiguradorFalso())

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
    script = _script()
    fila = list(paginas)
    estado = {"i": 0}

    def ler(_alvo):
        indice = min(estado["i"], len(fila) - 1)
        estado["i"] += 1
        return JANELA, fila[indice]

    monkeypatch.setattr(script, "_ler_janela", ler)

    # `_reler` é o “olhar de novo a mesma janela”: no dublê, o diálogo (a
    # segunda página da fila) fica na tela até o Create ser clicado — as listas
    # de expiração/limite não abrem aqui, e é o `_ler_janela` do passo 3 que
    # avança para a página seguinte, já criada.
    def reler(janela, _p=8, _l=1500):
        return janela, fila[min(1, len(fila) - 1)]

    monkeypatch.setattr(script, "_reler", reler)

    def esperar_pagina(_args, conta="", segundos=0):
        # A página já está aberta no dublê; os passos seguintes releem por
        # `_ler_janela`, que continua andando pela mesma fila.
        return JANELA, fila[0]

    monkeypatch.setattr(script, "_levar_ate_as_chaves", esperar_pagina)
    monkeypatch.setattr(script, "_texto_da_area", lambda: area["texto"])
    relogio = itertools.count()
    monkeypatch.setattr(
        script, "time", types.SimpleNamespace(time=lambda: next(relogio) * 0.5, sleep=lambda _s: None)
    )
    config = config or ConfiguradorAuto()
    monkeypatch.setattr(script, "_modulo_do_configurador", lambda: config)
    monkeypatch.setitem(sys.modules, "server.arvore_windows", windows or WindowsFalso())
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
    windows = WindowsFalso()
    script, config, args = _auto(monkeypatch, paginas, area, windows=windows)

    # O diálogo só some quando o “Create” é clicado — é assim no site, e é o
    # que a conferência do passo 3 lê para saber que a chave nasceu.
    aberto = {"sim": True}
    clique_de_verdade = windows.executar_ref

    def executar_ref(handle, caminho, acao, texto="", caixa=None, mouse=False, primeiro_mouse=False):
        if list(caixa or []) == [700, 640, 80, 28]:
            aberto["sim"] = False
        return clique_de_verdade(handle, caminho, acao, texto, caixa, mouse, primeiro_mouse)

    monkeypatch.setattr(windows, "executar_ref", executar_ref)
    monkeypatch.setattr(
        script,
        "_reler",
        lambda janela, _p=8, _l=1500: (janela, dialogo if aberto["sim"] else PAGINA_COM_COPIA),
    )
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


def test_auto_usa_o_site_do_provedor_pedido(monkeypatch):
    """O pedido foi “os sites onde estão as chaves” — não é só o OpenRouter."""
    area = {"texto": ""}
    paginas = [_pagina(_no("Create Key"))]
    script, config, args = _auto(monkeypatch, paginas, area, provedor="groq")
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


def test_o_dialogo_que_nao_abre_nao_vira_clique_no_new_key(monkeypatch, capsys):
    class NuncaAbre(Mundo):
        def executar_ref(self, handle, caminho, acao, texto="", caixa=None, mouse=False, primeiro_mouse=False):
            if list(caixa or []) == CAIXA_NEW_KEY:
                self.cliques.append(list(caixa))
                return {"executou": True, "como": "clique físico", "cursor_voltou": True}
            return super().executar_ref(handle, caminho, acao, texto, caixa, mouse, primeiro_mouse)

    mundo = NuncaAbre()
    script, config = _com_mundo(monkeypatch, mundo)

    assert script.passo_criar(_args()) == 1
    assert mundo.cliques == [CAIXA_NEW_KEY], "um clique só: não insiste no New key"
    assert config.gravadas == []
    assert "O diálogo não abriu" in capsys.readouterr().out


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
