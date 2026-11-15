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
        self.gravadas: list[list[str]] = []

    def chave_da_area_de_transferencia(self):
        if self.erro:
            raise RuntimeError("a área de transferência está vazia.")
        return f" {self.chave}\n", self.chave

    def descrever_area(self, limpo: str, chave: str) -> str:
        return f"  Copiado: {len(limpo.strip())} caractere(s); chave reconhecida {chave[:5]}…{chave[-4:]}"

    def principal(self, argv: list[str]) -> int:
        self.gravadas.append(list(argv))
        return 0


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
    relogio = itertools.count()
    monkeypatch.setattr(
        script,
        "time",
        types.SimpleNamespace(time=lambda: next(relogio) * 10.0, sleep=lambda _s: None),
    )
    monkeypatch.setitem(sys.modules, "server.arvore_windows", windows)
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
    assert config.gravadas == [["--chave", config.chave]]
    assert "1." in saida and "5." in saida
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
