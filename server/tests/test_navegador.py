from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.skill_registry import build_registry
from server.navegador import (
    ACOES,
    ESTADOS,
    NavegadorError,
    checar_limites,
    checar_plano,
    ler_recibos,
    montar_roteiro,
    navegador_catalog,
    parse_snapshot,
    resolver_alvo,
)

@pytest.fixture()
def client(tmp_path) -> TestClient:
    return TestClient(create_app(registry=build_registry(tmp_path / "files")))


SNAP = """root
  heading "Exemplo de login" [level=1]
  textbox "E-mail" [ref=5, loc=css:#email]
  textbox "Senha" [ref=6, loc=unstable]
  button "Entrar" [ref=21, loc=role:button[name="Entrar"]]
  button "Entrar com Google" [ref=23]
  link "Esqueci a senha" [ref=22, url=https://example.com/reset]
  iframe [ref=12]
    textbox "Busca interna" [ref=901, loc=css:#q]
    button "Pesquisar" [ref=902]
  text "literal [ref=9, loc=unstable]"
"""

SNAP_BUSCA = """root
  heading "Busca de passagens" [level=1]
  textbox "Origem" [ref=3, loc=css:#origem]
  textbox "Destino" [ref=4, loc=css:#destino]
  combobox "Data de ida" [ref=7]
  button "Buscar passagens" [ref=11, loc=role:button[name="Buscar passagens"]]
"""


# ------------------------------------------------------------------ snapshot

def test_snapshot_reads_roles_names_refs_and_frames() -> None:
    arvore = parse_snapshot(SNAP)
    assert arvore.raiz is True
    assert len(arvore.nos) == 11
    assert len(arvore.acionaveis) == 7
    assert [frame.ref for frame in arvore.frames] == ["12"]
    busca = next(no for no in arvore.nos if no.ref == "901")
    assert busca.quadro == ["12"]
    assert busca.acionavel is True


def test_snapshot_keeps_bracket_inside_name_as_text() -> None:
    arvore = parse_snapshot(
        'root\n  button "literal [ref=9, loc=unstable]" [ref=3]\n'
    )
    no = arvore.nos[1]
    assert no.nome == "literal [ref=9, loc=unstable]"
    assert no.ref == "3"


def test_snapshot_reads_nested_brackets_in_locator() -> None:
    arvore = parse_snapshot(
        'root\n  button "x" [ref=1, loc=css:[data-ref="[ref=1]"]]\n'
    )
    no = arvore.nos[1]
    assert no.loc == 'css:[data-ref="[ref=1]"]'
    assert no.ref == "1"


def test_snapshot_accepts_bullets_and_escaped_quotes() -> None:
    arvore = parse_snapshot('- root\n  - button "diga \\"oi\\"" [ref=2]\n')
    assert arvore.raiz is True
    assert arvore.nos[1].nome == 'diga "oi"'


def test_snapshot_flags_duplicate_ref() -> None:
    arvore = parse_snapshot('root\n  button "A" [ref=1]\n  link "B" [ref=1]\n')
    kinds = {item["kind"] for item in arvore and []}
    assert kinds == set()
    from server.navegador import _achados_snapshot

    achados = _achados_snapshot(arvore)
    assert any(item["kind"] == "ref-duplicado" and item["group"] == "must" for item in achados)


def test_snapshot_without_actions_is_blocking() -> None:
    from server.navegador import _achados_snapshot

    arvore = parse_snapshot('root\n  heading "Só leitura" [level=1]\n  text "nada clicável"\n')
    achados = _achados_snapshot(arvore)
    assert any(item["kind"] == "sem-acionaveis" and item["group"] == "must" for item in achados)


def test_snapshot_without_root_and_odd_indent_warns() -> None:
    from server.navegador import _achados_snapshot

    arvore = parse_snapshot('button "A" [ref=1]\n   button "B" [ref=2]\n')
    kinds = {item["kind"] for item in _achados_snapshot(arvore)}
    assert "sem-raiz" in kinds
    assert "indentacao" in kinds


def test_snapshot_flags_actionable_without_ref_and_unstable_locator() -> None:
    from server.navegador import _achados_snapshot

    arvore = parse_snapshot('root\n  button "Salvar"\n  link "X" [ref=2, loc=ambiguous]\n')
    kinds = {item["kind"] for item in _achados_snapshot(arvore)}
    assert "acionavel-sem-ref" in kinds
    assert "loc-instavel" in kinds


def test_snapshot_flags_iframe_without_ref() -> None:
    from server.navegador import _achados_snapshot

    arvore = parse_snapshot('root\n  iframe\n    button "Dentro" [ref=5]\n')
    assert [frame.ref for frame in arvore.frames] == [""]
    assert any(item["kind"] == "iframe-sem-ref" for item in _achados_snapshot(arvore))


def test_snapshot_flags_control_without_name() -> None:
    from server.navegador import _achados_snapshot

    arvore = parse_snapshot('root\n  textbox [ref=7, loc=css:#q]\n')
    assert arvore.nos[1].nome == ""
    assert any(item["kind"] == "sem-nome" for item in _achados_snapshot(arvore))


def test_snapshot_rejects_empty_and_huge_text() -> None:
    with pytest.raises(NavegadorError):
        parse_snapshot("   \n\n")
    with pytest.raises(NavegadorError):
        parse_snapshot("root\n" + '  text "x"\n' * 2_100)


def test_snapshot_reads_plain_text_only_tree() -> None:
    arvore = parse_snapshot('root\n  paragraph "Um parágrafo qualquer."\n')
    assert arvore.acionaveis == []
    assert arvore.nos[1].papel == "paragraph"


# ---------------------------------------------------------------------- alvo

def test_target_by_ref_builds_command() -> None:
    resultado = resolver_alvo({"snapshot": SNAP, "alvo": "@21", "acao": "clicar", "modo": "full"})
    assert resultado["metrics"]["resolvido"] is True
    assert resultado["comando"] == 'await page.click("@21");'
    assert resultado["executed"] is False


def test_target_by_exact_text_is_case_sensitive() -> None:
    exato = resolver_alvo({"snapshot": SNAP, "alvo": 'text="Entrar"', "acao": "clicar", "modo": "full"})
    assert exato["metrics"]["candidatos"] == 1
    assert exato["comando"] == 'await page.click("@21");'


def test_target_unquoted_text_is_substring_and_ambiguous() -> None:
    resultado = resolver_alvo({"snapshot": SNAP, "alvo": "Entrar", "acao": "clicar", "modo": "full"})
    assert resultado["metrics"]["ambiguo"] is True
    assert resultado["metrics"]["resolvido"] is False
    assert any(item["kind"] == "ambiguo" for item in resultado["findings"])


def test_target_by_role_and_name() -> None:
    resultado = resolver_alvo({
        "snapshot": SNAP, "alvo": 'loc=role:button[name="Entrar"]', "acao": "clicar", "modo": "full",
    })
    assert resultado["metrics"]["resolvido"] is True
    assert resultado["metrics"]["tipo"] == "papel"


def test_target_by_role_name_substring() -> None:
    resultado = resolver_alvo({
        "snapshot": SNAP, "alvo": 'loc=role:textbox[name*="mail"]', "acao": "preencher", "modo": "full",
    })
    assert resultado["comando"] == 'await page.fill("@5", "<valor>");'


def test_target_by_css_uses_loc_from_snapshot() -> None:
    resultado = resolver_alvo({"snapshot": SNAP, "alvo": "loc=css:#q", "acao": "preencher", "modo": "full"})
    assert resultado["metrics"]["escopo"] == "frame @12"
    assert resultado["comando"] == 'await page.fill("@901", "<valor>");'


def test_target_by_href_matches_url() -> None:
    resultado = resolver_alvo({"snapshot": SNAP, "alvo": "loc=href:reset", "acao": "clicar", "modo": "full"})
    assert resultado["metrics"]["resolvido"] is True
    assert resultado["metrics"]["ref"] == "22"


def test_target_prefers_top_document_over_frames() -> None:
    snap = 'root\n  button "Abrir" [ref=1]\n  iframe [ref=3]\n    button "Abrir" [ref=31]\n'
    resultado = resolver_alvo({"snapshot": snap, "alvo": 'text="Abrir"', "acao": "clicar", "modo": "full"})
    assert resultado["metrics"]["escopo"] == "documento principal"
    assert resultado["metrics"]["ref"] == "1"


def test_target_falls_back_to_frame_when_top_has_none() -> None:
    snap = 'root\n  button "Abrir" [ref=1]\n  iframe [ref=3]\n    button "Buscar" [ref=31]\n'
    resultado = resolver_alvo({"snapshot": snap, "alvo": 'text="Buscar"', "acao": "clicar", "modo": "full"})
    assert resultado["metrics"]["escopo"] == "frame @3"


def test_target_nth_selects_one_of_many() -> None:
    resultado = resolver_alvo({
        "snapshot": SNAP, "alvo": "Entrar >> nth=1", "acao": "clicar", "modo": "full",
    })
    assert resultado["metrics"]["resolvido"] is True
    assert resultado["metrics"]["ref"] == "23"


def test_target_xpath_is_refused_with_alternative() -> None:
    with pytest.raises(NavegadorError) as erro:
        resolver_alvo({"snapshot": SNAP, "alvo": "xpath=//button", "acao": "clicar", "modo": "full"})
    assert "loc=role" in str(erro.value)


def test_target_unknown_action_is_refused() -> None:
    with pytest.raises(NavegadorError):
        resolver_alvo({"snapshot": SNAP, "alvo": "@21", "acao": "voar", "modo": "full"})


def test_target_empty_is_refused() -> None:
    with pytest.raises(NavegadorError):
        resolver_alvo({"snapshot": SNAP, "alvo": "  ", "modo": "full"})


def test_target_not_found_suggests_close_names() -> None:
    resultado = resolver_alvo({"snapshot": SNAP, "alvo": 'text="Entrar na conta"', "acao": "clicar", "modo": "full"})
    assert resultado["metrics"]["resolvido"] is False
    assert any("Entrar" in item["nome"] for item in resultado["sugestoes"])


def test_target_stale_ref_explains_renumbering() -> None:
    resultado = resolver_alvo({"snapshot": SNAP, "alvo": "@999", "acao": "clicar", "modo": "full"})
    assert any(item["kind"] == "ref-velha" for item in resultado["findings"])


def test_target_heading_is_not_actionable_for_click() -> None:
    resultado = resolver_alvo({"snapshot": SNAP, "alvo": 'text="Exemplo de login"', "acao": "clicar", "modo": "full"})
    assert resultado["metrics"]["resolvido"] is False
    assert any(item["kind"] == "nao-acionavel" for item in resultado["findings"])


def test_target_wait_accepts_non_actionable_heading() -> None:
    resultado = resolver_alvo({"snapshot": SNAP, "alvo": 'text="Exemplo de login"', "acao": "esperar", "modo": "full"})
    assert resultado["metrics"]["resolvido"] is True
    assert resultado["comando"].startswith("await page.waitForSelector(")


def test_target_label_only_where_api_accepts() -> None:
    clicavel = resolver_alvo({"snapshot": SNAP, "alvo": "@21", "acao": "clicar", "rotulo": "entrar na conta", "modo": "full"})
    assert 'label: "entrar na conta"' in clicavel["comando"]
    recusado = resolver_alvo({"snapshot": SNAP, "alvo": "@5", "acao": "preencher", "rotulo": "entrar na conta", "modo": "full"})
    assert any(item["kind"] == "rotulo-proibido" for item in recusado["findings"])


def test_target_long_label_is_a_nit() -> None:
    resultado = resolver_alvo({
        "snapshot": SNAP, "alvo": "@21", "acao": "clicar",
        "rotulo": "clicar no botão de entrar na conta principal do usuário", "modo": "full",
    })
    assert any(item["kind"] == "rotulo-longo" for item in resultado["findings"])


# ------------------------------------------------------------------- roteiro

def test_plan_has_three_rounds_and_snapshot_last() -> None:
    resultado = montar_roteiro({
        "objetivo": "buscar passagens para Recife", "url": "https://example.com",
        "snapshot": SNAP_BUSCA, "orcamento": 4, "modo": "full",
    })
    assert len(resultado["rodadas"]) == 3
    assert resultado["rodadas"][0]["codigo"].strip().endswith("console.log(await page.snapshot()); // último: vira a vista da próxima rodada")
    assert "task.finish({ keep: [] })" in resultado["rodadas"][2]["codigo"]


def test_plan_reuses_one_space_and_one_page() -> None:
    resultado = montar_roteiro({
        "objetivo": "buscar passagens", "url": "https://example.com",
        "snapshot": SNAP_BUSCA, "modo": "full",
    })
    codigo = "\n".join(rodada["codigo"] for rodada in resultado["rodadas"])
    assert codigo.count('taskSpace("') == 1
    assert "taskSpace(SPACE_ID)" in codigo
    assert "newPage(" not in codigo


def test_plan_fills_first_field_when_intent_is_fill() -> None:
    resultado = montar_roteiro({
        "objetivo": "preencher a origem com São Paulo", "url": "https://example.com",
        "snapshot": SNAP_BUSCA, "modo": "full",
    })
    assert 'page.fill("@3"' in resultado["rodadas"][1]["codigo"]


def test_plan_clicks_matching_button() -> None:
    resultado = montar_roteiro({
        "objetivo": "buscar passagens", "url": "https://example.com",
        "snapshot": SNAP_BUSCA, "modo": "full",
    })
    assert 'page.click("@11"' in resultado["rodadas"][1]["codigo"]


def test_plan_without_snapshot_only_localizes() -> None:
    resultado = montar_roteiro({"objetivo": "entrar no site", "url": "https://example.com", "modo": "full"})
    assert any(item["kind"] == "sem-snapshot" for item in resultado["findings"])
    assert resultado["rodadas"][1]["acoes"][0]["acao"] == "localizar"


def test_plan_without_url_warns() -> None:
    resultado = montar_roteiro({"objetivo": "buscar passagens", "snapshot": SNAP_BUSCA, "modo": "full"})
    assert any(item["kind"] == "sem-url" for item in resultado["findings"])


def test_plan_rejects_bad_and_short_input() -> None:
    with pytest.raises(NavegadorError):
        montar_roteiro({"objetivo": "ok", "modo": "full"})
    with pytest.raises(NavegadorError):
        montar_roteiro({"objetivo": "buscar passagens", "url": "example.com", "modo": "full"})


def test_plan_flags_budget_below_needed() -> None:
    resultado = montar_roteiro({
        "objetivo": "buscar passagens", "url": "https://example.com",
        "snapshot": SNAP_BUSCA, "orcamento": 2, "modo": "full",
    })
    assert any(item["kind"] == "orcamento" and item["group"] == "must" for item in resultado["findings"])


def test_plan_marks_risky_objective_and_hands_off() -> None:
    resultado = montar_roteiro({
        "objetivo": "comprar a passagem e pagar no cartão", "url": "https://example.com",
        "modo": "full", "orcamento": 4,
    })
    assert resultado["exigeConfirmacao"] is True
    assert "handOff" in resultado["rodadas"][1]["codigo"]


def test_plan_slug_cuts_on_word_boundary() -> None:
    resultado = montar_roteiro({
        "objetivo": "buscar passagens de São Paulo para Recife amanhã cedo", "url": "https://example.com",
        "modo": "full",
    })
    space = resultado["metrics"]["space"]
    assert not space.endswith("-")
    assert len(space) <= 60


# ------------------------------------------------------------------ checagem

def test_check_finds_fixed_wait_and_new_space() -> None:
    plano = 'const a = await taskSpace("x");\nawait page.waitForTimeout(2000);\nawait taskSpace("y");\n'
    resultado = checar_plano({"plano": plano, "modo": "full"})
    kinds = {item["kind"] for item in resultado["findings"]}
    assert "espera-fixa" in kinds
    assert "space-nova" in kinds


def test_check_finds_finish_twice_and_action_after_finish() -> None:
    plano = 'await task.finish({ keep: [] });\nawait task.finish({ keep: [] });\nawait page.click("@1");\n'
    resultado = checar_plano({"plano": plano, "modo": "full"})
    kinds = {item["kind"] for item in resultado["findings"]}
    assert "finish-duplo" in kinds
    assert "finish-cedo" in kinds


def test_check_rejects_label_on_fill_and_playwright_import() -> None:
    plano = 'import { chromium } from "playwright";\nawait page.fill("#a", "b", { label: "x" });\n'
    resultado = checar_plano({"plano": plano, "modo": "full"})
    kinds = {item["kind"] for item in resultado["findings"]}
    assert "rotulo-proibido" in kinds
    assert "playwright" in kinds


def test_check_rejects_relative_path_and_claim_without_approval() -> None:
    plano = 'await page.screenshot({ path: "rel.png" });\nconst t = await claimTaskSpace(4);\n'
    resultado = checar_plano({"plano": plano, "modo": "full"})
    kinds = {item["kind"] for item in resultado["findings"]}
    assert "caminho-relativo" in kinds
    assert "claim-sem-pedido" in kinds


def test_check_flags_plan_without_finish() -> None:
    plano = 'const t = await taskSpace("x");\nawait page.goto("https://example.com");\n'
    resultado = checar_plano({"plano": plano, "modo": "full"})
    assert any(item["kind"] == "finish-ausente" for item in resultado["findings"])


def test_check_reads_step_states() -> None:
    resultado = checar_plano({
        "passos": "clicar | @1 | coberto\npreencher | #email | desabilitado\nesperar | #ok | visivel",
        "modo": "full",
    })
    assert [item["veredito"] for item in resultado["passos"]] == ["bloqueado", "bloqueado", "revisar"]
    assert resultado["metrics"]["bloqueados"] == 2


def test_check_accepts_clean_plan_in_lite_mode() -> None:
    plano = (
        'const task = await taskSpace("busca-20261023");\n'
        'const page = task.page("p1");\n'
        'await page.goto("https://example.com");\n'
        "console.log(await page.snapshot());\n"
        "await task.finish({ keep: [] });\n"
    )
    resultado = checar_plano({"plano": plano, "modo": "lite"})
    assert resultado["findings"] == []


def test_check_requires_plan_or_steps() -> None:
    with pytest.raises(NavegadorError):
        checar_plano({"modo": "full"})


def test_check_reports_empty_steps() -> None:
    with pytest.raises(NavegadorError):
        checar_plano({"passos": "   \n", "plano": "const x = 1;", "modo": "full"})


# ------------------------------------------------------------------- recibos

def test_receipts_parse_actions_and_effects() -> None:
    log = "1. clique @21 ok popup=p2\n2. esperei #home ok 1200ms\n3. fechei keep=[]"
    resultado = ler_recibos({"log": log, "modo": "full"})
    assert [item["acao"] for item in resultado["recibos"]] == ["click", "wait", "finish"]
    assert resultado["recibos"][0]["popup"] == "p2"
    assert resultado["recibos"][1]["tempo"] == "1200ms"


def test_receipts_flag_missing_finish() -> None:
    resultado = ler_recibos({"log": "1. clique @1 ok\n2. snapshot", "modo": "full"})
    assert any(item["kind"] == "sem-finish" for item in resultado["findings"])


def test_receipts_flag_repeated_finish() -> None:
    resultado = ler_recibos({"log": "1. finish keep=[]\n2. finish keep=[]", "modo": "full"})
    assert any(item["kind"] == "finish-repetido" for item in resultado["findings"])


def test_receipts_flag_action_after_finish() -> None:
    resultado = ler_recibos({"log": "1. finish keep=[]\n2. clique @4 ok", "modo": "full"})
    assert any(item["kind"] == "acao-pos-finish" for item in resultado["findings"])


def test_receipts_flag_unhandled_popup_and_handled_popup() -> None:
    solto = ler_recibos({"log": "1. clique @1 ok popup=p2\n2. finish keep=[]", "modo": "full"})
    assert any(item["kind"] == "popup" for item in solto["findings"])
    tratado = ler_recibos({
        "log": '1. clique @1 ok popup=p2\n2. page("p2") abri o popup\n3. snapshot\n4. finish keep=[]',
        "modo": "full",
    })
    assert not any(item["kind"] == "popup" for item in tratado["findings"])


def test_receipts_flag_pending_dialog_and_download_unsaved() -> None:
    resultado = ler_recibos({
        "log": "1. clique @1 ok dialogo=confirmar\n2. baixei=relatorio.pdf\n3. finish keep=[]",
        "modo": "full",
    })
    kinds = {item["kind"] for item in resultado["findings"]}
    assert "dialogo" in kinds
    assert "download" in kinds


def test_receipts_accept_handled_dialog_and_saved_download() -> None:
    resultado = ler_recibos({
        "log": "1. clique @1 ok dialogo=confirmar\n2. aceitei o dialogo\n"
               "3. baixei=relatorio.pdf salvei=/tmp/rel.pdf\n4. snapshot\n5. finish keep=[]",
        "modo": "full",
    })
    kinds = {item["kind"] for item in resultado["findings"]}
    assert "dialogo" not in kinds
    assert "download" not in kinds


def test_receipts_flag_keep_with_many_pages() -> None:
    resultado = ler_recibos({"log": "1. snapshot\n2. finish keep=[p1, p2]", "modo": "full"})
    assert any(item["kind"] == "keep-demais" for item in resultado["findings"])


def test_receipts_flag_no_observation_and_receipt_is_not_proof() -> None:
    resultado = ler_recibos({"log": "1. clique @1 ok\n2. preenchi @2 ok\n3. finish keep=[]", "modo": "full"})
    kinds = {item["kind"] for item in resultado["findings"]}
    assert "sem-observacao" in kinds
    assert "recibo-nao-e-prova" in kinds


def test_receipts_flag_declared_failure() -> None:
    resultado = ler_recibos({"log": "1. clique @1 falhou timeout\n2. snapshot\n3. finish keep=[]", "modo": "full"})
    assert any(item["kind"] == "falha" for item in resultado["findings"])


def test_receipts_require_log() -> None:
    with pytest.raises(NavegadorError):
        ler_recibos({"log": "   ", "modo": "full"})


# ------------------------------------------------------------------- limites

def test_limits_block_credentials_payments_and_captcha() -> None:
    resultado = checar_limites({
        "acoes": "abrir o site\npreencher a senha\npagar o boleto\nresolver o captcha",
        "modo": "full",
    })
    assert [item["nivel"] for item in resultado["veredictos"]] == ["liberado", "bloqueado", "bloqueado", "bloqueado"]
    assert resultado["metrics"]["bloqueadas"] == 3


def test_limits_confirm_publication_and_deletion() -> None:
    resultado = checar_limites({"acoes": "publicar um comentário\nexcluir a conta antiga", "modo": "full"})
    assert [item["nivel"] for item in resultado["veredictos"]] == ["confirmar", "confirmar"]
    assert resultado["handoff"]


def test_limits_unknown_action_asks() -> None:
    resultado = checar_limites({"acoes": "fazer a coisa misteriosa", "modo": "full"})
    assert resultado["veredictos"][0]["nivel"] == "confirmar"
    assert resultado["veredictos"][0]["regra"] == "indefinida"


def test_limits_require_actions_and_cap_lines() -> None:
    with pytest.raises(NavegadorError):
        checar_limites({"acoes": "", "modo": "full"})
    with pytest.raises(NavegadorError):
        checar_limites({"acoes": "\n".join(["abrir"] * 61), "modo": "full"})


def test_limits_handoff_explains_takeover() -> None:
    resultado = checar_limites({"acoes": "preencher o token de acesso", "modo": "full"})
    assert "handOff" in resultado["handoff"]
    assert "takeOverTaskSpace" in resultado["handoff"]


# ------------------------------------------------------------------ catálogo

def test_catalog_lists_vocabulary() -> None:
    catalogo = navegador_catalog()
    assert catalogo["fonte"].startswith("citrolabs/ego-lite")
    assert len(catalogo["limites"]) == 11
    assert len(catalogo["padroes"]) == 15
    assert len(catalogo["acoes"]) == len(ACOES)
    assert {item["estado"] for item in catalogo["estados"]} == set(ESTADOS)


# ----------------------------------------------------------------------- API

def test_api_runs_every_navegador_skill(client: TestClient) -> None:
    alvo = client.post("/api/skills/navegador.alvo/execute", json={"parameters": {
        "snapshot": SNAP, "alvo": "@21", "acao": "clicar", "modo": "full",
    }}).json()
    assert alvo["ok"] is True
    assert alvo["result"]["metrics"]["resolvido"] is True
    assert alvo["result"]["executed"] is False
    assert alvo["result"]["readOnly"] is True

    snapshot = client.post("/api/skills/navegador.snapshot/execute", json={"parameters": {
        "snapshot": SNAP, "modo": "full",
    }}).json()
    assert snapshot["ok"] is True
    assert snapshot["result"]["metrics"]["acionaveis"] == 7

    roteiro = client.post("/api/skills/navegador.roteiro/execute", json={"parameters": {
        "objetivo": "buscar passagens", "url": "https://example.com",
        "snapshot": SNAP_BUSCA, "modo": "full",
    }}).json()
    assert roteiro["ok"] is True
    assert len(roteiro["result"]["rodadas"]) == 3

    checagem = client.post("/api/skills/navegador.checagem/execute", json={"parameters": {
        "plano": 'await page.waitForTimeout(10);\nawait task.finish({ keep: [] });', "modo": "full",
    }}).json()
    assert checagem["ok"] is True
    assert checagem["result"]["metrics"]["padroes"] >= 1

    recibos = client.post("/api/skills/navegador.recibos/execute", json={"parameters": {
        "log": "1. clique @1 ok\n2. snapshot\n3. finish keep=[]", "modo": "full",
    }}).json()
    assert recibos["ok"] is True
    assert len(recibos["result"]["recibos"]) == 3

    limites = client.post("/api/skills/navegador.limites/execute", json={"parameters": {
        "acoes": "pagar o boleto", "modo": "full",
    }}).json()
    assert limites["ok"] is True
    assert limites["result"]["metrics"]["bloqueadas"] == 1

    regras = client.post("/api/skills/navegador.regras/execute", json={"parameters": {}}).json()
    assert regras["ok"] is True
    assert len(regras["result"]["papeis"]) >= 8


def test_api_rejects_unknown_skill_and_bad_input(client: TestClient) -> None:
    assert client.post("/api/skills/navegador.nada/execute", json={"parameters": {}}).status_code == 404
    ruim = client.post("/api/skills/navegador.alvo/execute", json={"parameters": {
        "snapshot": SNAP, "alvo": "@21", "modo": "turbo",
    }}).json()
    assert ruim["ok"] is False
    assert "modo" in ruim["error"]["message"]
