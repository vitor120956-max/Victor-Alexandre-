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


# ------------------------------------------------------------------ o mouse

def test_posicao_medida_permite_clicar_com_o_mouse():
    """“Copy” com caixa na tela é clicável pelo mouse; sem caixa, não."""
    pagina = _pagina("Create Key")
    pagina["arvore"]["filhos"].append(_no("Copy", caixa=[812, 400, 70, 28]))
    dados = chave_web.diagnostico(pagina)
    assert dados["pode_clicar_com_mouse"] is True
    assert dados["posicoes"]["copiar"] == [812, 400, 70, 28]
    assert "o mouse acerta" in chave_web.texto_do_diagnostico(dados)


def test_sem_posicao_o_diagnostico_nao_promete_mouse():
    dados = chave_web.diagnostico(_pagina("Create Key", "Copy"))
    assert dados["pode_clicar_com_mouse"] is False
    assert dados["posicoes"]["copiar"] is None
    assert "sem posição medida" in chave_web.texto_do_diagnostico(dados)


def test_caixa_zerada_nao_vale_como_posicao():
    assert chave_web.caixa_de({"caixa": [0, 0, 0, 0]}) is None
    assert chave_web.caixa_de({"caixa": [1, 2]}) is None
    assert chave_web.caixa_de(None) is None
    assert chave_web.caixa_de({"caixa": [10, 20, 30, 40]}) == [10, 20, 30, 40]


def _script():
    import importlib.util
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("chave_no_navegador_teste", raiz / "chave-no-navegador.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_a_mensagem_do_clique_diz_que_o_cursor_voltou():
    texto = _script()._descrever_clique({"como": "clique físico em 812,414", "cursor_voltou": True})
    assert "cursor voltou" in texto


def test_sem_mouse_a_mensagem_e_a_acao_do_elemento():
    texto = _script()._descrever_clique({"como": "ação padrão do elemento"})
    assert texto == "ação padrão do elemento"


def test_o_botao_que_fecha_o_dialogo_e_so_create():
    """O diálogo do OpenRouter pede “Create”, não “Create Key”.

    A 0.91.9 só conhecia o rótulo longo: com o diálogo aberto, o passo 3
    procurava “create key”, não achava e dizia que a página tinha mudado.
    """
    dados = chave_web.diagnostico(_pagina("Key name", "Create"))
    assert chave_web.procurar(_pagina("Key name", "Create"), chave_web.PADROES_CONFIRMAR)[0]["nome"] == "Create"
    assert dados["pode_criar"] is False, "o rótulo curto não é o da página, é o do diálogo"


# ------------------------------------------------- em qual das três páginas
#
# Telas medidas no PC do dono (0.91.14): abrir openrouter.ai/keys sem sessão
# cai em “Sign In | OpenRouter”; o Google abre a escolha de conta; só depois
# aparece “API keys” com o botão “New key”.

def _login_openrouter() -> dict[str, Any]:
    return {
        "alvo": "chrome — Sign In | OpenRouter",
        "fonte": "uia",
        "arvore": {"nome": "Sign In", "filhos": [
            _no("GitHub"), _no("Google"), _no("Reddit"),
            _no("Email address"), _no("Continue"), _no("Use passkey instead"),
        ]},
    }


def _escolha_de_conta() -> dict[str, Any]:
    return {
        "alvo": "chrome — Fazer login nas Contas do Google",
        "fonte": "uia",
        "arvore": {"nome": "Escolha uma conta", "filhos": [
            _no("Victor vitor120956@gmail.com"),
            _no("Los PRO losproeduevi@gmail.com"),
            _no("Usar outra conta"),
        ]},
    }


def _pagina_de_chaves_do_openrouter() -> dict[str, Any]:
    return {
        "alvo": "chrome — Keys | Settings | OpenRouter",
        "fonte": "uia",
        "arvore": {"nome": "OpenRouter", "filhos": [
            _no("Keys"), _no("API keys"), _no("Create and manage your API keys."),
            _no("New key"), _no("Search by name or paste a key..."),
        ]},
    }


def test_reconhece_a_tela_de_login():
    dados = chave_web.onde_estou(_login_openrouter())
    assert dados["estado"] == chave_web.ESTADO_LOGIN
    assert "login" in chave_web.texto_do_estado(dados)


def test_reconhece_a_escolha_de_conta_do_google():
    dados = chave_web.onde_estou(_escolha_de_conta())
    assert dados["estado"] == chave_web.ESTADO_GOOGLE
    assert [c["email"] for c in dados["contas"]] == [
        "vitor120956@gmail.com",
        "losproeduevi@gmail.com",
    ]


def test_reconhece_a_pagina_de_chaves_com_botao_new_key():
    dados = chave_web.onde_estou(_pagina_de_chaves_do_openrouter())
    assert dados["estado"] == chave_web.ESTADO_CHAVES
    assert chave_web.diagnostico(_pagina_de_chaves_do_openrouter())["criar"] == ["New key"]


def test_login_nao_e_confundido_com_a_pagina_de_chaves():
    """O defeito da 0.91.12: “OpenRouter” no título fazia a tela de login passar
    por página de chaves, e o JARVIS parava pedindo um botão que não existia."""
    assert chave_web.e_pagina_de_chaves(_login_openrouter()) is False


def test_casa_a_conta_pedida_por_pedaco_do_email():
    contas = chave_web.contas_visiveis(_escolha_de_conta())
    assert chave_web.casar_conta(contas, "vitor120956")["email"] == "vitor120956@gmail.com"
    assert chave_web.casar_conta(contas, "VITOR")["email"] == "vitor120956@gmail.com"
    assert chave_web.casar_conta(contas, "lospro")["email"] == "losproeduevi@gmail.com"


def test_conta_ambigua_nao_e_escolhida_no_chute():
    contas = chave_web.contas_visiveis(_escolha_de_conta())
    assert chave_web.casar_conta(contas, "@gmail.com") is None
    assert chave_web.casar_conta(contas, "") is None
    assert chave_web.casar_conta(contas, "ninguem") is None


def test_texto_de_apoio_nao_ganha_do_botao():
    """“Create and manage your API keys.” é parágrafo; “Create” é botão.

    Os dois casam com `PADROES_CONFIRMAR`. Sem a ordem por acionável, o passo
    que confirma a criação podia “clicar” no parágrafo e dizer que deu certo —
    um clique que não acontece e um relatório que mente.
    """
    pagina = _pagina()
    pagina["arvore"]["filhos"] = [
        {"nome": "Create and manage your API keys.", "papel": 41, "acionavel": False},
        {"nome": "Create", "papel": 43, "acionavel": True},
    ]
    assert chave_web.procurar(pagina, chave_web.PADROES_CONFIRMAR)[0]["nome"] == "Create"


# ------------------------------------------------- o diálogo “Create API key”
#
# A tela do dono tem três campos com asterisco: Name, Expiration e Credit
# limit. Sem a expiração, o botão “Create” fica apagado.

def test_reconhece_o_dialogo_de_criacao():
    pagina = _pagina("Create API key", "Name", "Select expiration", "Create")
    assert chave_web.e_dialogo_de_criacao(pagina) is True
    assert chave_web.e_dialogo_de_criacao(_pagina("API keys", "New key")) is False


def test_expiracao_escolhe_o_maior_prazo_e_prefere_never():
    assert chave_web.melhor_expiracao(["30 days", "90 days", "1 year", "Never"]) == "Never"
    assert chave_web.melhor_expiracao(["7 days", "30 days", "1 year"]) == "1 year"
    assert chave_web.melhor_expiracao(["Nunca", "30 dias"]) == "Nunca"
    assert chave_web.melhor_expiracao(["Selecione", "Escolha"]) is None


def test_limite_prefere_o_que_nao_trava_a_chave():
    assert chave_web.melhor_limite(["5", "10", "No limit"]) == "No limit"
    assert chave_web.melhor_limite(["Sem limite", "5"]) == "Sem limite"
    assert chave_web.melhor_limite(["5", "10"]) is None


def test_nomes_novos_acha_as_opcoes_da_lista_aberta():
    antes = _pagina("Create API key", "Select expiration", "Create")
    depois = _pagina("Create API key", "Select expiration", "Create", "30 days", "Never")
    novos = [no["nome"] for no in chave_web.nomes_novos(antes, depois)]
    assert novos == ["30 days", "Never"]


def test_nomes_novos_ignora_texto_longo_demais():
    antes = _pagina("Create API key")
    frase = "Uma frase enorme de ajuda que não é opção de nada e só explica o campo"
    assert len(frase) > 60
    depois = _pagina("Create API key", frase)
    assert chave_web.nomes_novos(antes, depois) == []


def test_o_botao_create_key_da_pagina_nao_e_o_dialogo_aberto():
    """Regressão da 0.91.16: “Create Key” é o **botão** e existe o tempo todo.

    Com ele na lista de títulos, a página das chaves passava por “diálogo
    aberto”: a espera terminava na hora e o script ia preencher uma caixa que
    ainda não estava na tela.
    """
    pagina = _pagina("Create Key", "Copy")
    assert chave_web.e_dialogo_de_criacao(pagina) is False


def test_o_dialogo_e_reconhecido_pelos_campos_quando_o_titulo_nao_vem():
    """No PC do dono o painel estava na tela e o título não veio na leitura.

    Os campos, porém, vieram: “Expiration” e “Credit limit” só existem ali.
    """
    sem_titulo = {"alvo": "chrome — API Keys", "fonte": "uia", "arvore": {
        "nome": "página", "papel": 1, "filhos": [
            _no("Name", papel=42),
            _no("Select expiration"),
            _no("Choose a credit limit"),
        ]
    }}
    assert chave_web.e_dialogo_de_criacao(sem_titulo) is True


def test_so_a_marca_de_campo_sem_nome_precisa_do_create():
    """Marca de campo sozinha não basta: a página também fala de limite.

    O que fecha a prova é a marca **e** (o campo de nome **ou** a palavra
    criar) — é o que separa o painel aberto de um texto de ajuda qualquer.
    """
    so_marca = {"alvo": "chrome — API Keys", "fonte": "uia", "arvore": {
        "nome": "página", "papel": 1, "filhos": [_no("Key limit: 1000 credits")],
    }}
    assert chave_web.e_dialogo_de_criacao(so_marca) is False

    com_create = {"alvo": "chrome — API Keys", "fonte": "uia", "arvore": {
        "nome": "página", "papel": 1,
        "filhos": [_no("Key limit: 1000 credits"), _no("Create")],
    }}
    assert chave_web.e_dialogo_de_criacao(com_create) is True


# ---------------------------------------- o campo do nome (0.91.19)
#
# No painel de verdade “Name” e a caixa de texto são **dois nós**: o rótulo é
# texto, a caixa é onde se escreve. Clicar no rótulo e mandar as teclas não
# escreve nada — foi o que deixou o campo vazio no PC do dono.

def _caixa(nome: str, x: int, y: int, *, papel: int = 42, acao: str = "escrever") -> dict[str, Any]:
    return {
        "nome": nome,
        "papel": papel,
        "codigo": papel,
        "caixa": [x, y, 300, 30],
        "acionavel": True,
        "acao": acao,
    }


def _painel(*nos: dict[str, Any]) -> dict[str, Any]:
    return {"alvo": "chrome — Keys", "fonte": "uia", "arvore": {"nome": "página", "papel": 1, "filhos": list(nos)}}


def test_campo_do_nome_e_a_caixa_e_nao_o_rotulo():
    painel = _painel(
        _caixa("Create API key", 400, 180, papel=1, acao=""),
        _caixa("Name *", 400, 300, papel=41, acao="clicar"),  # rótulo
        _caixa("e.g. “ChatbotKey”", 400, 330),  # a caixa
        _caixa("Select expiration", 400, 400, acao="abrir"),
    )

    campo = chave_web.campo_do_nome(painel)

    assert campo is not None
    assert campo["nome"] == "e.g. “ChatbotKey”", "quem recebe o texto é a caixa"


def test_campo_do_nome_ignora_a_busca_da_pagina_atras_do_painel():
    """A página tem “Search by name or paste a key…” lá em cima — não é o nome."""
    painel = _painel(
        _caixa("Search by name or paste a key…", 60, 100),  # busca da página
        _caixa("Create API key", 400, 180, papel=1, acao=""),
        _caixa("Name *", 400, 300, papel=41, acao="clicar"),
        _caixa("e.g. “ChatbotKey”", 400, 330),
        _caixa("Select expiration", 400, 400, acao="abrir"),
    )

    campo = chave_web.campo_do_nome(painel)

    assert campo is not None
    assert campo["caixa"][1] == 330


def test_sem_nome_nenhum_a_caixa_acima_da_expiracao_e_a_do_nome():
    """Caixa sem nome publicado: quem decide é a posição no painel."""
    painel = _painel(
        _caixa("Create API key", 400, 180, papel=1, acao=""),
        _caixa("Name *", 400, 300, papel=41, acao="clicar"),
        _caixa("", 400, 330),  # a caixa sem nome
        _caixa("Select expiration", 400, 400, acao="abrir"),
        _caixa("Choose a credit limit", 400, 500, acao="abrir"),
    )

    campo = chave_web.campo_do_nome(painel)

    assert campo is not None
    assert campo["caixa"][1] == 330


def test_rotulo_nao_conta_como_campo_de_escrita():
    rotulo = {"nome": "Name *", "papel": 41, "codigo": 41, "caixa": [400, 300, 300, 30], "acionavel": True, "acao": "clicar"}

    assert chave_web.e_campo_de_escrita(rotulo) is False
