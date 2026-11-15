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
        alvo="chrome", nome="jarvis-teste", autorizar=True, mouse=False, sem_mouse=False
    )
    for chave, valor in extra.items():
        setattr(base, chave, valor)
    return base


def _montar(monkeypatch, paginas: list[dict[str, Any]], windows: WindowsFalso, config: ConfiguradorFalso):
    script = _script()
    fila = list(paginas)

    def ler(_alvo):
        return JANELA, fila.pop(0) if fila else PAGINA_COM_COPIA

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


def test_a_sequencia_inteira_cria_copia_e_grava(monkeypatch, capsys):
    windows = WindowsFalso()
    config = ConfiguradorFalso()
    script = _montar(
        monkeypatch,
        [PAGINA_INICIAL, PAGINA_DO_NOME, PAGINA_CRIADA, PAGINA_COM_COPIA],
        windows,
        config,
    )

    codigo = script.passo_criar(_args())
    saida = capsys.readouterr().out

    assert codigo == 0
    assert [c["acao"] for c in windows.chamadas] == ["clicar", "digitar", "clicar", "clicar"]
    assert windows.chamadas[1]["texto"] == "jarvis-teste"
    assert all(c["mouse"] is True for c in windows.chamadas), "com --autorizar o mouse é o padrão"
    assert config.gravadas == [config.chave]
    assert "1." in saida and "4." in saida and "5." not in saida
    assert "cursor voltou" in saida


def test_sem_autorizar_nada_e_clicado(monkeypatch, capsys):
    windows = WindowsFalso()
    script = _montar(monkeypatch, [PAGINA_INICIAL], windows, ConfiguradorFalso())

    codigo = script.passo_criar(_args(autorizar=False))

    assert codigo == 0
    assert windows.chamadas == []
    assert "--autorizar" in capsys.readouterr().out


def test_sem_mouse_chega_ao_executor_como_pedido(monkeypatch):
    windows = WindowsFalso({"executou": True, "como": "ação padrão do elemento"})
    config = ConfiguradorFalso(chave="sk-or-v1-" + "cd" * 34)
    script = _montar(
        monkeypatch,
        [PAGINA_INICIAL, PAGINA_DO_NOME, PAGINA_CRIADA, PAGINA_COM_COPIA],
        windows,
        config,
    )

    assert script.passo_criar(_args(sem_mouse=True)) == 0
    assert [c["mouse"] for c in windows.chamadas] == [False, False, False, False]


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

    def esperar_pagina(_alvo, segundos=0):
        # A página já está aberta no dublê; os passos seguintes releem por
        # `_ler_janela`, que continua andando pela mesma fila.
        assert segundos == 5
        return JANELA, fila[0]

    monkeypatch.setattr(script, "_esperar_pagina", esperar_pagina)
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
    paginas = [
        _pagina(_no("Create Key", [812, 200, 90, 28])),
        _pagina(_no("Key name", [400, 300, 320, 30], papel=42), _no("Create", [700, 380, 80, 28])),
        _pagina(_no("Create", [700, 380, 80, 28])),
    ]
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
    relogio = itertools.count()
    monkeypatch.setattr(
        script, "time", types.SimpleNamespace(time=lambda: next(relogio) * 1.0, sleep=lambda _s: None)
    )

    janela, montada = script._esperar_pagina("chrome", segundos=3)
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
