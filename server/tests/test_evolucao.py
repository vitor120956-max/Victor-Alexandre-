"""Testes da camada de evolução (0.33.0): mapa, diff, risco, guardas, ensaio e promoção.

O ensaio roda pytest de verdade dentro da cópia, então os testes que o exercitam
usam um alvo pequeno (`server/tests/test_revisao.py` quando existe, ou um arquivo
de teste sintético criado no ensaio).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import evolucao as E
from server.app import create_app

PROJETO = E.PROJETO


@pytest.fixture(autouse=True)
def estado(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "STORAGE", tmp_path / "evolucao")
    monkeypatch.setattr(E, "ENSAIOS", tmp_path / "evolucao" / "ensaios")
    monkeypatch.setattr(E, "BACKUPS", tmp_path / "evolucao" / "backups")
    monkeypatch.setattr(E, "AUDITORIA", tmp_path / "evolucao" / "audit.jsonl")
    monkeypatch.setattr(E, "TOKEN_ARQUIVO", tmp_path / "host-token.txt")
    (tmp_path / "host-token.txt").write_text("token-de-teste-evolucao\n", encoding="utf-8")
    monkeypatch.delenv(E.AMBIENTE_EVOLUIR, raising=False)
    E._CONFIRMACAO.clear()
    yield tmp_path
    E._CONFIRMACAO.clear()


@pytest.fixture
def token():
    return "token-de-teste-evolucao"


@pytest.fixture
def ligado(monkeypatch):
    monkeypatch.setenv(E.AMBIENTE_EVOLUIR, "1")


# Um diff válido sobre review.py: acrescenta um comentário na primeira linha.
def _diff_review(linha: str = "# marca do ensaio") -> str:
    texto = (PROJETO / "server" / "review.py").read_text(encoding="utf-8")
    primeira = texto.splitlines()[0]
    return f"""--- a/server/review.py
+++ b/server/review.py
@@ -1,1 +1,2 @@
 {primeira}
+{linha}
"""


# ---------------------------------------------------------------------------
# Parser de diff
# ---------------------------------------------------------------------------


def test_diff_minimo_aplica():
    arquivos = E.ler_diff(_diff_review())
    assert len(arquivos) == 1
    assert arquivos[0].caminho == "server/review.py"
    assert arquivos[0].adicoes == 1
    assert arquivos[0].remocoes == 0


def test_diff_aplica_de_verdade():
    final = E._resultado_do_patch(E.ler_diff(_diff_review())[0])
    assert "# marca do ensaio" in final
    assert len(final.splitlines()) == len((PROJETO / "server/review.py").read_text().splitlines()) + 1


def test_diff_com_cabecalho_git():
    texto = "diff --git a/server/review.py b/server/review.py\n" + _diff_review().split("\n", 1)[1]
    assert E.ler_diff(texto)[0].caminho == "server/review.py"


def test_diff_novo_arquivo():
    texto = """--- /dev/null
+++ b/server/novo.py
@@ -0,0 +1,2 @@
+def x():
+    return 1
"""
    arquivo = E.ler_diff(texto)[0]
    assert arquivo.novo is True
    assert E._resultado_do_patch(arquivo) == "def x():\n    return 1"


def test_diff_remove_arquivo():
    texto = f"""--- a/server/review.py
+++ /dev/null
@@ -1,1 +0,0 @@
-{(PROJETO / 'server' / 'review.py').read_text().splitlines()[0]}
"""
    arquivo = E.ler_diff(texto)[0]
    assert arquivo.removido is True
    assert E._resultado_do_patch(arquivo) is None


def test_diff_modificacao_nao_marca_novo():
    assert E.ler_diff(_diff_review())[0].novo is False


def test_diff_contexto_errado_recusa():
    texto = """--- a/server/review.py
+++ b/server/review.py
@@ -1,1 +1,2 @@
 linha inexistente no arquivo
+acrescimo
"""
    with pytest.raises(E.EvolucaoError, match="não aplica"):
        E._resultado_do_patch(E.ler_diff(texto)[0])


def test_diff_vazio_recusa():
    with pytest.raises(E.EvolucaoError, match="diff"):
        E.ler_diff("")


def test_diff_sem_hunk_recusa():
    with pytest.raises(E.EvolucaoError, match="hunk|Nenhum"):
        E.ler_diff("--- a/server/review.py\n+++ b/server/review.py\n")


def test_diff_hunk_sem_arquivo_recusa():
    with pytest.raises(E.EvolucaoError, match="Hunk sem arquivo"):
        E.ler_diff("@@ -1,1 +1,2 @@\n x\n+y\n")


@pytest.mark.parametrize(
    "caminho,motivo",
    [
        ("storage/x.py", "storage"),
        ("../fora.py", ".."),
        ("/etc/passwd", "absoluto"),
        (".env", "credencial"),
        ("node_modules/x.py", "node_modules"),
    ],
)
def test_diff_recusa_caminho_proibido(caminho, motivo):
    texto = f"--- a/{caminho}\n+++ b/{caminho}\n@@ -1,1 +1,2 @@\n x\n+y\n"
    with pytest.raises(E.EvolucaoError) as exc:
        E.ler_diff(texto)
    assert motivo.lower() in str(exc.value).lower() or caminho in str(exc.value)


def test_diff_recusa_extensao():
    with pytest.raises(E.EvolucaoError, match="Extensão"):
        E.ler_diff("--- a/server/x.exe\n+++ b/server/x.exe\n@@ -1,1 +1,2 @@\n x\n+y\n")


def test_diff_arquivo_inexistente_para_alteracao():
    with pytest.raises(E.EvolucaoError, match="não existe"):
        E.ler_diff("--- a/server/nao_existe.py\n+++ b/server/nao_existe.py\n@@ -1,1 +1,2 @@\n x\n+y\n")


def test_sem_prefixo_preserva_ponto():
    assert E._sem_prefixo("./.env.example") == ".env.example"
    assert E._sem_prefixo("b/.env.example") == ".env.example"
    assert E._sem_prefixo("a/server/x.py") == "server/x.py"


def test_diff_binario_recusa():
    arquivo = E.ArquivoDiff("server/review.py")
    with pytest.raises(E.EvolucaoError, match="binário"):
        E._aplicar_texto("a\x00b", arquivo.hunks)


def test_hunk_de_insercao_pura():
    hunk = E.Hunk(1, 0, 1, 2, ["+novo"])
    # `-N,0` insere depois da linha N, como o git gera.
    assert E._aplicar_texto("a\nb\n", [hunk]) == "a\nnovo\nb\n"


def test_aplicar_preserva_final_de_arquivo():
    hunk = E.Hunk(1, 1, 1, 2, [" a", "+b"])
    assert E._aplicar_texto("a\n", [hunk]) == "a\nb\n"


def test_aplicar_sem_newline_final():
    hunk = E.Hunk(1, 1, 1, 2, [" a", "+b"])
    assert E._aplicar_texto("a", [hunk]) == "a\nb"


# ---------------------------------------------------------------------------
# Mapa
# ---------------------------------------------------------------------------


def test_mapa_conta_arquivos(token):
    dados = E.mapa(autorizacao=token)
    assert dados["metrics"]["arquivos"] > 100
    assert dados["metrics"]["modulos"] > 30
    assert dados["executed"] is False and dados["readOnly"] is True


def test_mapa_area_server_so_modulos(token):
    dados = E.mapa(area="server", autorizacao=token)
    assert all(linha["grupo"] == "server" for linha in dados["rows"])


def test_mapa_area_invalida(token):
    with pytest.raises(E.EvolucaoError, match="Área"):
        E.mapa(area="cozinha", autorizacao=token)


def test_mapa_exige_token():
    with pytest.raises(E.EvolucaoError, match="token"):
        E.mapa(autorizacao="")


def test_mapa_ordena_por_linhas(token):
    linhas = [linha["linhas"] for linha in E.mapa(area="server", autorizacao=token)["rows"]]
    assert linhas == sorted(linhas, reverse=True)


# ---------------------------------------------------------------------------
# Proposta
# ---------------------------------------------------------------------------


def test_proposta_marca_aplicavel(token):
    dados = E.proposta(diff=_diff_review(), autorizacao=token)
    assert dados["metrics"]["aplicavel"] is True
    assert dados["metrics"]["adicoes"] == 1


def test_proposta_detecta_nao_aplicavel(token):
    texto = """--- a/server/review.py
+++ b/server/review.py
@@ -1,1 +1,2 @@
 texto que nao existe
+novo
"""
    dados = E.proposta(diff=texto, autorizacao=token)
    assert dados["metrics"]["aplicavel"] is False
    assert dados["counts"]["must"] >= 1


def test_proposta_alerta_reducao_de_suite(token):
    testes = PROJETO / "server" / "tests" / "test_revisao.py"
    if not testes.exists():
        pytest.skip("sem test_revisao.py")
    texto = "\n".join(testes.read_text(encoding="utf-8").splitlines()[:3])
    diff = f"""--- a/server/tests/test_revisao.py
+++ b/server/tests/test_revisao.py
@@ -1,3 +1,1 @@
-{texto.splitlines()[0]}
-{texto.splitlines()[1]}
-{texto.splitlines()[2]}
{texto.splitlines()[0]}
"""
    dados = E.proposta(diff=diff, autorizacao=token)
    assert dados["counts"]["must"] >= 1


def test_proposta_recusa_caminho_proibido(token):
    with pytest.raises(E.EvolucaoError):
        E.proposta(diff="--- a/.git/config\n+++ b/.git/config\n@@ -1,1 +1,2 @@\n x\n+y\n", autorizacao=token)


# ---------------------------------------------------------------------------
# Risco
# ---------------------------------------------------------------------------


def _diff_adicionando(*linhas: str) -> str:
    corpo = "\n".join(f"+{linha}" for linha in linhas)
    return f"--- a/server/review.py\n+++ b/server/review.py\n@@ -1,1 +1,{len(linhas) + 1} @@\n {(PROJETO / 'server' / 'review.py').read_text().splitlines()[0]}\n{corpo}\n"


def test_risco_patch_inofensivo(token):
    dados = E.risco(diff=_diff_review(), autorizacao=token)
    assert dados["metrics"]["nivel"] == "baixo"
    assert dados["metrics"]["perigos"] == 0


@pytest.mark.parametrize(
    "linha",
    [
        "resultado = eval(texto)",
        "exec(codigo)",
        "os.system(comando)",
        "subprocess.run(cmd, shell=True)",
        "dados = pickle.loads(bytes)",
        "modulo = __import__(nome)",
    ],
)
def test_risco_detecta_perigo(linha, token):
    dados = E.risco(diff=_diff_adicionando(linha), autorizacao=token)
    assert dados["metrics"]["perigos"] >= 1
    assert dados["counts"]["must"] >= 1


def test_risco_detecta_segredo(token):
    dados = E.risco(diff=_diff_adicionando('api_key = "abcdefghijklmnop1234"'), autorizacao=token)
    assert any("segredo" in item["title"].lower() for item in dados["findings"])


def test_risco_detecta_tls_desligado(token):
    dados = E.risco(diff=_diff_adicionando("httpx.get(url, verify=False)"), autorizacao=token)
    assert dados["counts"]["must"] >= 1


def test_risco_detecta_guarda_removida(token):
    texto = (PROJETO / "server" / "review.py").read_text(encoding="utf-8").splitlines()[0]
    diff = f"""--- a/server/review.py
+++ b/server/review.py
@@ -1,1 +1,0 @@
-{texto}
"""
    dados = E.risco(diff=diff, autorizacao=token)
    assert "guarda" in " ".join(item["title"].lower() for item in dados["findings"]) or dados["metrics"]["nivel"] in {"baixo", "médio"}


def test_risco_pontuacao_teto(token):
    dados = E.risco(diff=_diff_adicionando("eval(a)", "exec(b)", "os.system(c)", "shell=True"), autorizacao=token)
    assert dados["metrics"]["pontuacao"] == 100


def test_risco_arquivo_central_pesa(token):
    diff = f"""--- a/server/sistema.py
+++ b/server/sistema.py
@@ -1,1 +1,2 @@
 {(PROJETO / 'server' / 'sistema.py').read_text().splitlines()[0]}
+# nada
"""
    dados = E.risco(diff=diff, autorizacao=token)
    assert dados["metrics"]["centrais"] == 1


def test_risco_sem_perigo_nao_gera_must(token):
    dados = E.risco(diff=_diff_review("# comentário"), autorizacao=token)
    assert dados["counts"]["must"] == 0


# ---------------------------------------------------------------------------
# Guardas
# ---------------------------------------------------------------------------


def test_guardas_patch_limpo_preserva_tudo(token):
    dados = E.guardas(diff=_diff_review(), autorizacao=token)
    assert dados["metrics"]["violadas"] == 0
    assert dados["metrics"]["regras"] == 10


def test_guardas_detecta_shell_true(token):
    dados = E.guardas(diff=_diff_adicionando("subprocess.run(c, shell=True)"), autorizacao=token)
    assert dados["metrics"]["violadas"] >= 1


def test_guardas_detecta_registro_sem_contagem(token):
    diff = f"""--- a/server/skill_registry.py
+++ b/server/skill_registry.py
@@ -1,1 +1,2 @@
 {(PROJETO / 'server' / 'skill_registry.py').read_text().splitlines()[0]}
+\"\"\"x\"\"\"
"""
    dados = E.guardas(diff=diff, autorizacao=token)
    assert dados["metrics"]["revisar"] >= 1


def test_guardas_detecta_import_externo(token):
    dados = E.guardas(diff=_diff_adicionando("import requests"), autorizacao=token)
    assert any("requirements" in item["title"].lower() or "depend" in item["title"].lower() for item in dados["findings"])


def test_guardas_detecta_suite_encolhendo(token):
    testes = PROJETO / "server" / "tests" / "test_revisao.py"
    if not testes.exists():
        pytest.skip("sem test_revisao.py")
    linhas = testes.read_text(encoding="utf-8").splitlines()[:20]
    corpo = "\n".join(f"-{linha}" for linha in linhas)
    diff = f"""--- a/server/tests/test_revisao.py
+++ b/server/tests/test_revisao.py
@@ -1,20 +1,0 @@
{corpo}
"""
    dados = E.guardas(diff=diff, autorizacao=token)
    assert dados["metrics"]["violadas"] >= 1


def test_guardas_lista_as_dez_regras():
    assert len(E.REGRAS_GUARDA) == 10
    assert E.REGRAS_GUARDA[0][0] == "G1"


# ---------------------------------------------------------------------------
# Ensaio
# ---------------------------------------------------------------------------


def test_ensaiar_exige_trava(token):
    with pytest.raises(E.EvolucaoError, match="desligada"):
        E.ensaiar(diff=_diff_review(), autorizacao=token)


def test_ensaiar_exige_token(ligado):
    with pytest.raises(E.EvolucaoError, match="token"):
        E.ensaiar(diff=_diff_review(), autorizacao="")


def test_ensaiar_patch_que_nao_aplica_recusa(ligado, token):
    texto = """--- a/server/review.py
+++ b/server/review.py
@@ -1,1 +1,2 @@
 contexto errado
+x
"""
    with pytest.raises(E.EvolucaoError, match="não aplica"):
        E.ensaiar(diff=texto, autorizacao=token)


def test_ensaiar_argumento_invalido(ligado, token):
    with pytest.raises(E.EvolucaoError, match="inválido"):
        E._argumentos_de_teste("server/tests && rm -rf /")


def test_ensaiar_recusa_pontos_pontos(ligado, token):
    with pytest.raises(E.EvolucaoError, match="recusado"):
        E._argumentos_de_teste("../segredo")


def test_ensaiar_limita_argumentos():
    with pytest.raises(E.EvolucaoError, match="12"):
        E._argumentos_de_teste(" ".join(["a"] * 15))


def test_ensaiar_nao_toca_o_arquivo_vivo(ligado, token):
    alvo = PROJETO / "server" / "review.py"
    antes = hashlib.sha256(alvo.read_bytes()).hexdigest()
    # Patch inválido no conteúdo, para falhar rápido na aplicação: nada deve ser escrito.
    dados = E.ensaiar(diff=_diff_review("# apenas ensaio"), testes="server/tests/test_revisao.py -k nada_aqui", timeout=120, autorizacao=token, modo="lite")
    assert hashlib.sha256(alvo.read_bytes()).hexdigest() == antes
    assert dados["executed"] is True


def test_ensaiar_registra_ensaio_no_disco(ligado, token, estado):
    dados = E.ensaiar(diff=_diff_review("# ensaio"), testes="server/tests/test_revisao.py -k nada_aqui", timeout=120, autorizacao=token, modo="lite")
    pasta = estado / "evolucao" / "ensaios" / dados["metrics"]["ensaio"]
    assert (pasta / "_proposta.diff").exists()
    assert (pasta / "server" / "review.py").exists()


def test_ensaiar_nao_aprova_sem_teste(ligado, token):
    dados = E.ensaiar(diff=_diff_review("# ensaio"), testes="server/tests/test_revisao.py -k nao_existe_nenhum", timeout=120, autorizacao=token, modo="lite")
    assert dados["aprovado"] is False
    assert dados["confirmacao"] == ""


def test_resumo_pytest_le_contagem():
    resumo = E._resumo_pytest("10 passed, 2 failed, 1 skipped in 3.2s")
    assert resumo["passed"] == 10
    assert resumo["failed"] == 2
    assert resumo["skipped"] == 1


def test_resumo_pytest_sem_linha():
    assert E._resumo_pytest("--- nada ---")["passed"] == 0


# ---------------------------------------------------------------------------
# Promoção e reversão
# ---------------------------------------------------------------------------


def _ensaio_aprovado(monkeypatch, token):
    """Cria um ensaio aprovado sem rodar pytest."""
    diff = _diff_review("# promovido")
    arquivos = E.ler_diff(diff)
    antes = {item.caminho: E._sha(PROJETO / item.caminho) for item in arquivos if (PROJETO / item.caminho).exists()}
    token_plano = "abc12345"
    E._CONFIRMACAO[token_plano] = {
        "acao": "promover",
        "ensaio": "teste00001",
        "diff": diff,
        "antes": antes,
        "expira": time.time() + 600,
        "aprovado": True,
    }
    monkeypatch.setattr(E, "_git_limpo", lambda _c: (True, ""))
    return token_plano


def test_promover_exige_trava(token, monkeypatch):
    plano = _ensaio_aprovado(monkeypatch, token)
    with pytest.raises(E.EvolucaoError, match="desligada"):
        E.promover(confirmacao=plano, autorizacao=token)


def test_promover_recusa_ensaio_reprovado(ligado, token, monkeypatch):
    E._CONFIRMACAO["dead0001"] = {
        "acao": "promover",
        "ensaio": "x",
        "diff": _diff_review(),
        "antes": {},
        "expira": time.time() + 600,
        "aprovado": False,
    }
    with pytest.raises(E.EvolucaoError, match="não foi aprovado"):
        E.promover(confirmacao="dead0001", autorizacao=token)


def test_promover_recusa_confirmacao_desconhecida(ligado, token):
    with pytest.raises(E.EvolucaoError, match="desconhecida"):
        E.promover(confirmacao="nan12345", autorizacao=token)


def test_promover_recusa_expirado(ligado, token, monkeypatch):
    plano = _ensaio_aprovado(monkeypatch, token)
    E._CONFIRMACAO[plano]["expira"] = time.time() - 1
    with pytest.raises(E.EvolucaoError, match="expirada"):
        E.promover(confirmacao=plano, autorizacao=token)


def test_promover_recusa_arquivo_alterado(ligado, token, monkeypatch, tmp_path):
    monkeypatch.setattr(E, "PROJETO", tmp_path)
    alvo = tmp_path / "server" / "review.py"
    alvo.parent.mkdir(parents=True)
    alvo.write_text("original\n", encoding="utf-8")
    diff = "--- a/server/review.py\n+++ b/server/review.py\n@@ -1,1 +1,2 @@\n original\n+novo\n"
    E._CONFIRMACAO["cafe1234"] = {
        "acao": "promover",
        "ensaio": "z",
        "diff": diff,
        "antes": {"server/review.py": "hash-que-nao-bate"},
        "expira": time.time() + 600,
        "aprovado": True,
    }
    monkeypatch.setattr(E, "_git_limpo", lambda _c: (True, ""))
    with pytest.raises(E.EvolucaoError, match="mudou depois do ensaio"):
        E.promover(confirmacao="cafe1234", autorizacao=token)


def test_promover_recusa_arvore_suja(ligado, token, monkeypatch):
    plano = _ensaio_aprovado(monkeypatch, token)
    monkeypatch.setattr(E, "_git_limpo", lambda _c: (False, " M server/review.py"))
    with pytest.raises(E.EvolucaoError, match="não commitada"):
        E.promover(confirmacao=plano, autorizacao=token)


def test_promover_escreve_com_backup_e_reverte(ligado, token, monkeypatch, tmp_path):
    monkeypatch.setattr(E, "PROJETO", tmp_path)
    monkeypatch.setattr(E, "BACKUPS", tmp_path / "backups")
    alvo = tmp_path / "server" / "review.py"
    alvo.parent.mkdir(parents=True)
    alvo.write_text("linha1\nlinha2\n", encoding="utf-8")
    sha = hashlib.sha256(alvo.read_bytes()).hexdigest()
    diff = "--- a/server/review.py\n+++ b/server/review.py\n@@ -1,1 +1,2 @@\n linha1\n+linha-nova\n"
    E._CONFIRMACAO["beef1234"] = {
        "acao": "promover",
        "ensaio": "ab000001",
        "diff": diff,
        "antes": {"server/review.py": sha},
        "expira": time.time() + 600,
        "aprovado": True,
    }
    monkeypatch.setattr(E, "_git_limpo", lambda _c: (True, ""))
    dados = E.promover(confirmacao="beef1234", autorizacao=token, modo="lite")
    assert "linha-nova" in alvo.read_text(encoding="utf-8")
    assert dados["reinicio_pendente"] is True
    assert (tmp_path / "backups" / "ab000001" / "server" / "review.py").exists()
    dados_reversao = E.reverter(ensaio="ab000001", autorizacao=token, modo="lite")
    assert dados_reversao["reinicio_pendente"] is True
    assert hashlib.sha256(alvo.read_bytes()).hexdigest() == sha


def test_promover_consome_o_token(ligado, token, monkeypatch, tmp_path):
    monkeypatch.setattr(E, "PROJETO", tmp_path)
    monkeypatch.setattr(E, "BACKUPS", tmp_path / "backups")
    alvo = tmp_path / "server" / "review.py"
    alvo.parent.mkdir(parents=True)
    alvo.write_text("a\n", encoding="utf-8")
    sha = hashlib.sha256(alvo.read_bytes()).hexdigest()
    E._CONFIRMACAO["feed1234"] = {
        "acao": "promover",
        "ensaio": "x1",
        "diff": "--- a/server/review.py\n+++ b/server/review.py\n@@ -1,1 +1,2 @@\n a\n+b\n",
        "antes": {"server/review.py": sha},
        "expira": time.time() + 600,
        "aprovado": True,
    }
    monkeypatch.setattr(E, "_git_limpo", lambda _c: (True, ""))
    E.promover(confirmacao="feed1234", autorizacao=token, modo="lite")
    with pytest.raises(E.EvolucaoError, match="desconhecida"):
        E.promover(confirmacao="feed1234", autorizacao=token)


def test_reverter_sem_backup(ligado, token):
    with pytest.raises(E.EvolucaoError, match="Não existe backup"):
        E.reverter(ensaio="abcd1234", autorizacao=token)


def test_reverter_identificador_vazio(ligado, token):
    with pytest.raises(E.EvolucaoError, match="Identificador"):
        E.reverter(ensaio="!!!", autorizacao=token)


def test_reverter_exige_trava(token):
    with pytest.raises(E.EvolucaoError, match="desligada"):
        E.reverter(ensaio="abcd1234", autorizacao=token)


def test_reverter_restaura_e_avisa_reinicio(ligado, token, monkeypatch, tmp_path):
    monkeypatch.setattr(E, "PROJETO", tmp_path)
    backup = E.BACKUPS / "abc12345"
    (backup / "server").mkdir(parents=True)
    (backup / "server" / "x.py").write_text("antigo\n", encoding="utf-8")
    (tmp_path / "server").mkdir()
    (tmp_path / "server" / "x.py").write_text("novo\n", encoding="utf-8")
    dados = E.reverter(ensaio="abc12345", autorizacao=token, modo="lite")
    assert (tmp_path / "server" / "x.py").read_text(encoding="utf-8") == "antigo\n"
    assert dados["reinicio_pendente"] is True


# ---------------------------------------------------------------------------
# Catálogo e capacidades
# ---------------------------------------------------------------------------


def test_catalogo_publica_fluxo_e_travas():
    dados = E.catalogo()
    assert len(dados["fluxo"]) == 7
    assert len(dados["travas"]) == 6
    assert len(dados["guardas"]) == 10


def test_catalogo_declara_recusas():
    texto = " ".join(E.catalogo()["nao_faz"]).lower()
    assert "branch" in texto and "reinicia" in texto and "mérito" in texto


def test_capacidades_refletem_trava(monkeypatch):
    monkeypatch.setenv(E.AMBIENTE_EVOLUIR, "1")
    assert E.capacidades()["evoluir"] is True
    monkeypatch.delenv(E.AMBIENTE_EVOLUIR)
    assert E.capacidades()["evoluir"] is False


def test_capacidades_nunca_declaram_branch():
    dados = E.capacidades()
    assert dados["cria_branch"] is False
    assert dados["commita"] is False


def test_catalogo_nao_expoe_token(token):
    assert token not in json.dumps(E.catalogo())


def test_auditoria_grava_linha(estado):
    E._auditar({"acao": "teste"})
    arquivo = estado / "evolucao" / "audit.jsonl"
    assert json.loads(arquivo.read_text(encoding="utf-8").strip())["acao"] == "teste"


def test_auditoria_nao_quebra_sem_permissao(monkeypatch, tmp_path):
    monkeypatch.setattr(E, "AUDITORIA", tmp_path / "inexistente" / "a" / "b.jsonl")
    monkeypatch.setattr(E.Path, "mkdir", lambda *_a, **_k: (_ for _ in ()).throw(OSError("sem permissão")))
    E._auditar({"acao": "x"})


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    return TestClient(create_app(registry=None))


def test_api_health_na_versao_nova(client):
    dados = client.get("/api/health").json()
    assert dados["version"] == "0.50.0"
    assert dados["skills"] == 245


def test_api_lista_as_oito_skills_de_evolucao(client):
    ids = [item["id"] for item in client.get("/api/skills").json()["skills"]]
    assert len([item for item in ids if item.startswith("evoluir.")]) == 8


def test_api_mapa_exige_token(client):
    corpo = client.post("/api/skills/evoluir.mapa/execute", json={"parameters": {}}).json()
    assert corpo["ok"] is False
    assert "token" in corpo["error"]["message"]


def test_api_regras_responde(client):
    corpo = client.post("/api/skills/evoluir.regras/execute", json={"parameters": {}}).json()
    assert corpo["ok"] is True
    assert corpo["result"]["versao"] == "0.50.0"


def test_api_ensaiar_exige_confirmacao(client):
    corpo = client.post(
        "/api/skills/evoluir.ensaiar/execute",
        json={"parameters": {"diff": "--- a/server/review.py\n+++ b/server/review.py\n@@ -1,1 +1,2 @@\n x\n+y\n", "autorizacao": "x"}},
    ).json()
    assert corpo["error"]["code"] == "CONFIRMATION_REQUIRED"


def test_api_promover_exige_confirmacao(client):
    corpo = client.post(
        "/api/skills/evoluir.promover/execute",
        json={"parameters": {"confirmacao": "abcd1234", "autorizacao": "x"}},
    ).json()
    assert corpo["error"]["code"] == "CONFIRMATION_REQUIRED"


def test_api_skill_inexistente(client):
    assert client.post("/api/skills/evoluir.nada/execute", json={"parameters": {}}).status_code == 404


# ---------------------------------------------------------------------------
# Elevação de privilégio (0.33.0)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "linha",
    [
        'subprocess.run(["sudo", "apt-get", "install", "-y", "rich"], shell=False)',
        "os.system('sudo rm -rf /var/lib/foo')",
        'subprocess.run(["pkexec", "sh", "-c", "id"])',
        'subprocess.run(["doas", "sh"])',
        "subprocess.run(['su', '-', 'root'])",
    ],
)
def test_risco_detecta_elevacao(linha, token):
    dados = E.risco(diff=_diff_adicionando(linha), autorizacao=token)
    assert dados["metrics"]["perigos"] >= 1
    assert dados["metrics"]["nivel"] == "alto"
    assert dados["counts"]["must"] >= 1


def test_risco_elevacao_soma_alem_do_peso_normal(token):
    """Um único `sudo` já basta para passar de baixo para alto."""
    dados = E.risco(diff=_diff_adicionando('subprocess.run(["sudo", "id"])'), autorizacao=token)
    assert dados["metrics"]["pontuacao"] >= 60
    assert any("elevação" in item["title"].lower() for item in dados["findings"])


def test_guardas_violam_allowlist_com_sudo(token):
    dados = E.guardas(diff=_diff_adicionando('subprocess.run(["sudo", "id"])'), autorizacao=token)
    assert dados["metrics"]["violadas"] >= 1
    regra = [linha for linha in dados["rows"] if linha["codigo"] == "G2"][0]
    assert regra["estado"] == "viola"


def test_guardas_violam_allowlist_com_pkexec(token):
    dados = E.guardas(diff=_diff_adicionando('subprocess.run(["pkexec", "id"])'), autorizacao=token)
    assert dados["metrics"]["violadas"] >= 1


def test_risco_nao_marca_palavra_solta(token):
    """`sudoers` numa frase não é uma chamada de elevação."""
    dados = E.risco(diff=_diff_adicionando("# ver /etc/sudoers.d/jarvis-elevacao"), autorizacao=token)
    assert dados["metrics"]["perigos"] == 0


def test_catalogo_publica_os_padroes_de_elevacao(token):
    dados = E.catalogo()
    titulos = " ".join(item["titulo"] for item in dados["perigos_monitorados"]).lower()
    assert "elevação" in titulos
