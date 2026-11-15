"""Achar o botão na página do provedor — sem Chrome, sem Windows, sem tela (0.91.9).

A divisão é a mesma das outras frentes: a **regra** (achar, comparar, dizer o que
falta) mora em `server/chave_web.py` e é testada aqui; o **driver** (ler a janela
e clicar) mora no script e só roda no Windows.

O que estes testes protegem:

1. O diagnóstico não clica e não promete: ele diz o que existe.
2. A comparação ignora acento e maiúscula — a página é em inglês, o usuário fala
   português, e "Criar Chave" tem de casar tanto quanto "Create Key".
3. Nome curto ganha de nome longo: "Copy" é o botão; "Copy the key to the
   clipboard" costuma ser o texto vizinho.
"""
from __future__ import annotations

from typing import Any

from server import chave_web


def _no(nome: str, papel: int = 43, **extra: Any) -> dict[str, Any]:
    return {"nome": nome, "papel": papel, **extra}


def _pagina(
    *nomes: str, alvo: str = "chrome — API Keys | OpenRouter", raiz: str = "API Keys"
) -> dict[str, Any]:
    return {
        "alvo": alvo,
        "fonte": "uia",
        "arvore": {"nome": raiz, "papel": 1, "filhos": [_no(nome) for nome in nomes]},
    }


def test_acha_o_botao_de_criar_e_o_de_copiar():
    dados = chave_web.diagnostico(_pagina("Create Key", "Copy"))
    assert dados["pode_criar"] is True
    assert dados["pode_copiar"] is True
    assert dados["criar"] == ["Create Key"]


def test_casa_portugues_tambem():
    dados = chave_web.diagnostico(_pagina("Criar Chave", "Copiar"))
    assert dados["pode_criar"] is True
    assert dados["pode_copiar"] is True


def test_nome_curto_vem_primeiro():
    """“Copy” é o botão; “Copy the key to the clipboard” é o texto de apoio."""
    dados = chave_web.diagnostico(_pagina("Copy the key to the clipboard", "Copy"))
    assert dados["copiar"][0] == "Copy"


def test_pagina_sem_botao_diz_que_nao_da_e_aponta_o_caminho_que_funciona():
    dados = chave_web.diagnostico(_pagina("Settings", "Docs"))
    assert dados["pode_criar"] is False
    texto = chave_web.texto_do_diagnostico(dados)
    assert "--pegar" in texto
    assert "--criar --autorizar" not in texto


def test_janela_sem_arvore_nao_inventa_diagnostico():
    dados = chave_web.diagnostico({"alvo": "chrome — Nova guia", "fonte": "", "arvore": None})
    assert dados["elementos_com_nome"] == 0
    assert dados["pode_criar"] is False
    assert "não publicou nenhum elemento" in chave_web.texto_do_diagnostico(dados)


def test_reconhece_que_a_pagina_e_a_certa():
    assert chave_web.e_pagina_de_chaves(_pagina("Create Key", alvo="chrome — OpenRouter"))
    assert not chave_web.e_pagina_de_chaves(
        _pagina("Receitas de bolo", alvo="chrome — Tudo Gostoso", raiz="Receitas")
    )


def test_o_nome_da_chave_leva_a_data_para_poder_apagar_depois():
    nome = chave_web.nome_sugerido()
    assert nome.startswith("jarvis-")
    assert len(nome) == len("jarvis-2026-11-15")


def test_arvore_aninhada_fundo_e_percorrida():
    arvore = {
        "alvo": "chrome — API Keys",
        "arvore": {"nome": "raiz", "filhos": [
            {"nome": "seção", "filhos": [{"nome": "Create Key", "filhos": []}]}
        ]},
    }
    assert chave_web.diagnostico(arvore)["pode_criar"] is True
