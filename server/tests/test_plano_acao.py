"""O plano de ação não pode prometer o que o scanner não mediu (0.95.1).

Estes testes existem por um motivo específico: o módulo é uma **tabela de
ligação** entre o que o diagnóstico acha e o que o executor faz. Tabela de
ligação apodrece calada — foi o que aconteceu com `EVIDENCIA_MEDIDA` na 0.92.9,
que pedia `app-travado` enquanto o scanner emitia `app-nao-responde`. O
resultado era a tela dizer “sem medida” com a medida na mão.

Por isso o teste central aqui não confere texto: ele confere **identificador**.
Todo `id` de problema citado em `plano_acao` tem de existir de fato entre os que
`diagnostico_celular.analisar()` emite.
"""

from __future__ import annotations

import re


from server import diagnostico_celular as dc
from server import plano_acao as pa


# ---------------------------------------------------------------------------
# O contrato com o scanner
# ---------------------------------------------------------------------------

# Os ids que o scanner emite. Este conjunto é extraído do próprio código do
# diagnóstico, e o teste abaixo confere que a extração pegou tudo o que os
# testes de `test_diagnostico_celular` já sabem que existe.
IDS_DO_SCANNER = {
    "armazenamento-cheio",
    "armazenamento-apertado",
    "memoria-baixa",
    "app-nao-responde",
    "app-travando",
    "frame-lento",
    "aquecendo",
    "bateria-quente-carregando",
    "bateria-gasta",
    "bateria-saude",
    "patch-antigo",
    "build-de-teste",
    "root",
    "toque-fantasma",
}


def _ids_citados_no_codigo() -> set[str]:
    """Todo `"algum-id"` citado em `plano_acao`, sem os que são ids de ação.

    Os ids de ação são os que aparecem como primeiro argumento de `_acao(`.
    """
    fonte = (pa.__file__ or "")
    texto = open(fonte, encoding="utf-8").read()
    acoes = set(re.findall(r'_acao\(\s*\n?\s*"([a-z-]+)"', texto))
    literais = set(re.findall(r'"([a-z]+(?:-[a-z]+)+)"', texto))
    # `jarvis_faz`, `sem-medida`, nomes de campo e afins não são ids de problema
    ruido = {
        "jarvis-faz", "sem-medida", "app-nao-responde-e", "nao-ha-medida",
        "limpar-cache", "limpar-dados", "fechar-app", "abrir-app", "instalar-apk",
        "acao-sem-medida", "sem-como", "voce-faz", "falta-medir",
        "jarvis-executa", "como-autorizar", "onde-no-aparelho",
        "ja-faz", "nao-faz", "em-vez-disso",
    }
    return {i for i in literais - acoes - ruido if i in _todos_os_ids_possiveis(texto)}


def _todos_os_ids_possiveis(texto: str) -> set[str]:
    """Os literais que o módulo compara com `problemas` — via `in problemas`."""
    return set(re.findall(r'"([a-z]+(?:-[a-z]+)+)" in problemas', texto))


def test_todo_id_de_problema_citado_existe_no_scanner():
    """O teste que a 0.92.9 não tinha: id inventado derruba aqui, não na tela."""
    citados = _ids_citados_no_codigo()
    desconhecidos = citados - IDS_DO_SCANNER
    assert not desconhecidos, (
        f"plano_acao cita id que o scanner não emite: {sorted(desconhecidos)}. "
        f"Ids válidos: {sorted(IDS_DO_SCANNER)}"
    )


def test_a_lista_de_ids_do_teste_nao_ficou_velha():
    """Se o scanner ganhar um problema novo, este teste avisa em vez de apodrecer.

    Ele não exige atualizar nada por obrigação: só impede que a lista acima vire
    ficção. Um id novo no código do scanner aparece aqui como diferença.
    """
    fonte = open(dc.__file__ or "", encoding="utf-8").read()
    emitidos = set(re.findall(r'_problema\(\s*\n?\s*"([a-z-]+)"', fonte))
    assert emitidos, "não consegui ler os ids do scanner — o parser do teste quebrou"
    faltando = emitidos - IDS_DO_SCANNER
    assert not faltando, (
        f"o scanner emite id que a lista deste teste não tem: {sorted(faltando)}. "
        "Acrescente em IDS_DO_SCANNER e veja se o plano de ação cobre."
    )


# ---------------------------------------------------------------------------
# O plano em si
# ---------------------------------------------------------------------------


def _relatorio(**problemas) -> dict:
    """Um relatório mínimo com os problemas que o teste quer.

    Usa a mesma forma que `_problema()` produz: o texto medido fica em
    `medido`, não em `detalhe`. O primeiro teste deste módulo usava `detalhe`
    e passava enquanto o campo real era outro — nome de app invisível.
    """
    return {
        "problemas": [
            {"id": k, "titulo": v, "medido": v, "causa": "", "limite": ""}
            for k, v in problemas.items()
        ],
        "secoes": [],
    }


def test_sem_problema_nao_ha_acao_e_isso_e_dito():
    """Relatório limpo devolve lista vazia — e a frase certa, não um silêncio."""
    plano = pa.planejar(_relatorio())
    assert plano["jarvis_executa"] == []
    assert plano["voce_faz"] == []
    assert plano["falta_medir"], "sem medida tem de ser dito, não escondido"
    assert "falta medida" in plano["veredito"]


def test_app_travando_vira_acao_que_o_jarvis_pode_executar():
    """O caso do relatório real: `com.dti.telefonica` travando no logcat."""
    relatorio = _relatorio(**{"app-travando": "Há app fechando sozinho — com.dti.telefonica"})
    plano = pa.planejar(relatorio)
    fechar = next(a for a in plano["jarvis_executa"] if a["id"] == "fechar-app-travado")
    # o pacote sai do texto do achado, não de um palpite
    assert fechar["pacote"] == "com.dti.telefonica"
    assert fechar["reversivel"] is True
    # e o limite não pode prometer que resolve para sempre
    assert "não" in fechar["limite"].lower() or "próximo" in fechar["limite"].lower()


def test_o_pacote_do_app_nao_e_inventado_quando_o_achado_nao_diz():
    """Sem pacote no texto, a ação de fechar **não** aparece com nome de chute."""
    relatorio = _relatorio(**{"app-nao-responde": "Um app parou de responder"})
    plano = pa.planejar(relatorio)
    assert not any(a["id"] == "fechar-app-travado" for a in plano["jarvis_executa"])
    # mas o caminho manual continua, esse não depende de saber o nome
    assert any(a["id"] == "limpar-cache-app-travado" for a in plano["voce_faz"])


def test_armazenamento_cheio_nao_vira_acao_do_jarvis():
    """Apagar arquivo do dono é irreversível: o plano é dele, não do JARVIS."""
    plano = pa.planejar(_relatorio(**{"armazenamento-cheio": "95% cheio"}))
    assert plano["jarvis_executa"] == []
    liberar = next(a for a in plano["voce_faz"] if a["id"] == "liberar-espaco")
    assert liberar["reversivel"] is False or "sem volta" in liberar["limite"].lower()
    assert "Ajustes" in liberar["onde_no_aparelho"]


def test_toda_acao_tem_evidencia_que_o_scanner_emite():
    """Ação sem evidência é opinião. Cada uma tem de citar id que existe."""
    relatorio = _relatorio(
        **{
            "app-travando": "com.dti.telefonica",
            "armazenamento-cheio": "95%",
            "memoria-baixa": "6%",
            "aquecendo": "72 °C",
            "bateria-gasta": "-18%/h",
            "patch-antigo": "2025-01-01",
        }
    )
    plano = pa.planejar(relatorio)
    todas = plano["jarvis_executa"] + plano["voce_faz"]
    assert todas
    for acao in todas:
        assert acao["evidencia"], f"{acao['id']} não diz qual medida a sustenta"
        for evidencia in acao["evidencia"]:
            assert evidencia in IDS_DO_SCANNER, f"{acao['id']} cita {evidencia}"


def test_o_jarvis_so_promete_executar_o_que_ele_sabe_executar():
    """`jarvis_faz=True` tem de apontar para uma ação real de `acoes.py`.

    Se alguém marcar uma ação como executável sem existir executor, isso vira
    promessa falsa na tela — o dono autoriza e nada acontece.
    """
    assert set(pa.EXECUTAVEIS) == {"fechar-app", "abrir-app", "instalar-apk"}
    plano = pa.planejar(
        _relatorio(**{
            "app-travando": "com.dti.telefonica",
            "memoria-baixa": "6%",
            "armazenamento-cheio": "95%",
        })
    )
    for acao in plano["jarvis_executa"]:
        # o comando declarado tem de ser uma das três skills que existem
        assert any(skill in acao["comando"] for skill in pa.EXECUTAVEIS), (
            f"{acao['id']} diz que o JARVIS faz, mas não aponta para skill existente"
        )


def test_o_plano_nao_esconde_o_que_nao_da_para_fazer():
    """“Sem como” tem de trazer o porquê e a alternativa — nunca um não seco."""
    plano = pa.planejar(_relatorio(**{"memoria-baixa": "6%"}))
    assert len(plano["sem_como"]) >= 3
    for item in plano["sem_como"]:
        assert item["porque"].strip()
        assert item["em_vez_disso"].strip()
    # o pedido que o dono fez de fato está na lista, com a explicação do adb
    entrar = next(i for i in plano["sem_como"] if "entrar no meu celular" in i["pedido"])
    assert "adb" in entrar["porque"]


def test_nada_executa_sem_a_trava_e_o_plano_diz_onde_ela_fica():
    """O plano informa como autorizar — e não autoriza nada por conta própria."""
    plano = pa.planejar(_relatorio(**{"app-travando": "com.x.y"}))
    assert "JARVIS_ACOES=1" in plano["como_autorizar"]
    assert "confirmado" in plano["como_autorizar"]
    # o módulo não importa nada de execução: é dado, não efeito
    from pathlib import Path

    fonte = Path(pa.__file__ or "").read_text(encoding="utf-8")
    for proibido in ("import subprocess", "import os.system", "from . import acoes"):
        assert proibido not in fonte, f"plano_acao não pode executar nada: {proibido}"
