"""Conserto: o erro vira diagnóstico, o diagnóstico vira dossiê e proposta.

O pedido foi: *“deu erro numa função, ele vai procurar para que serve e como
funciona, entende, testa, roda e, se funcionar, entrega”*.

O que estes testes travam:

- **o diário existe e não cresce sem fim** (`storage/erros.jsonl`, últimas 200);
- **o quadro certo**: o traceback cita `site-packages` e a stdlib, mas o que
  interessa é o último arquivo *deste* projeto — senão o diagnóstico aponta para
  o `json/decoder.py` e a correção vira chute;
- **a causa é regra, não palpite**: permissão, arquivo ausente, chave ausente,
  codificação, rede, timeout — e o que não casa é `desconhecida`, com todas as
  letras;
- **sem chave de IA, ele não escreve patch**: devolve o dossiê e diz por quê;
- **com provedor**, o diff passa pela régua do `evolucao.*` antes de ser
  oferecido — e o teste garante que nada é escrito no código vivo.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from server import conserto

RAIZ = Path(__file__).resolve().parents[2]

RASTRO_KEYERROR = """Traceback (most recent call last):
  File "/home/user/Victor-Alexandre-/server/app.py", line 417, in execute_skill
    result = await skill_registry.execute(skill_id, parametros, payload.dry_run)
  File "/home/user/Victor-Alexandre-/server/agente_local.py", line 800, in atender
    termo = dados["pedido"]
KeyError: 'pedido'
"""


# ------------------------------------------------------------------ o diário


def test_sem_erro_e_sem_diario_ele_diz_que_nao_tem_o_que_ler(tmp_path):
    achado = conserto.diagnosticar(raiz=tmp_path)
    assert achado["lido"] is False
    assert "erros.jsonl" in achado["motivo"]


def test_anotar_guarda_o_erro_e_erros_devolve_do_mais_novo(tmp_path):
    conserto.anotar(tipo="KeyError", mensagem="'pedido'", rastro=RASTRO_KEYERROR,
                    skill="agente.responder", raiz=tmp_path)
    conserto.anotar(tipo="ValueError", mensagem="vazio", rastro="", skill="x", raiz=tmp_path)
    itens = conserto.erros(raiz=tmp_path)
    assert [item["tipo"] for item in itens] == ["ValueError", "KeyError"]
    assert itens[0]["skill"] == "x"
    # A listagem não carrega traceback inteiro: é resumo, não despejo.
    assert all(item["rastro"] == "" for item in itens)


def test_o_diario_nao_cresce_sem_fim(tmp_path):
    arquivo = tmp_path / "erros.jsonl"
    linhas = [json.dumps({"tipo": f"E{i}", "mensagem": "", "rastro": "", "skill": ""}) for i in range(250)]
    arquivo.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    conserto.anotar(tipo="Nova", mensagem="", raiz=tmp_path)
    salvas = arquivo.read_text(encoding="utf-8").splitlines()
    assert len(salvas) == conserto.MAX_LINHAS_JOURNAL
    assert json.loads(salvas[-1])["tipo"] == "Nova"


def test_linha_corrompida_no_diario_nao_derruba_a_leitura(tmp_path):
    (tmp_path / "erros.jsonl").write_text('{"tipo":"A"}\n{isso nao e json\n{"tipo":"B"}\n', encoding="utf-8")
    assert [item["tipo"] for item in conserto.erros(raiz=tmp_path)] == ["B", "A"]


# ---------------------------------------------------------------- diagnosticar


def test_diagnostico_acha_arquivo_linha_e_funcao_do_projeto():
    achado = conserto.diagnosticar(erro=RASTRO_KEYERROR)
    assert achado["lido"] is True
    assert achado["onde"]["arquivo"] == "server/agente_local.py"
    assert achado["onde"]["linha"] == 800
    assert achado["onde"]["funcao"] == "atender"
    assert achado["fonte"] == "colado"


def test_ignora_quadro_da_biblioteca_e_escolhe_o_do_projeto():
    rastro = """Traceback (most recent call last):
  File "/usr/lib/python3.11/json/decoder.py", line 355, in raw_decode
    obj, end = self.scan_once(s, idx)
  File "/home/user/Victor-Alexandre-/server/limpeza.py", line 120, in _ler
    return json.loads(texto)
  File "/usr/lib/python3.11/json/__init__.py", line 346, in loads
    return _default_decoder.decode(s)
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
"""
    achado = conserto.diagnosticar(erro=rastro)
    assert achado["onde"]["arquivo"] == "server/limpeza.py"
    assert achado["causa"]["codigo"] == "json"


@pytest.mark.parametrize(
    "tipo, mensagem, esperado",
    [
        ("PermissionError", "[WinError 5] Acesso negado", "permissao"),
        ("FileNotFoundError", "No such file or directory: 'x'", "arquivo_ausente"),
        ("KeyError", "'caminho'", "chave_ausente"),
        ("AttributeError", "'NoneType' object has no attribute 'get'", "tipo_none"),
        ("TypeError", "atender() missing 1 required positional argument", "tipo_errado"),
        ("IndexError", "list index out of range", "indice"),
        ("ValueError", "could not convert string to float", "valor_invalido"),
        ("UnicodeDecodeError", "'utf-8' codec can't decode byte 0xe3", "unicode"),
        ("TimeoutError", "excedeu o tempo limite", "timeout"),
        ("ReadTimeout", "timed out", "timeout"),
        ("ConnectError", "[Errno 111] Connection refused", "rede"),
        ("RuntimeError", "algo que ninguém previu", "desconhecida"),
    ],
)
def test_a_causa_vem_de_regra_escrita(tipo, mensagem, esperado):
    assert conserto._causa(tipo, mensagem)["codigo"] == esperado


def test_a_causa_desconhecida_diz_que_e_desconhecida():
    causa = conserto._causa("RuntimeError", "x")
    assert causa["codigo"] == "desconhecida"
    assert "não casa" in causa["significa"]


def test_o_trecho_mostra_a_linha_com_marca():
    achado = conserto.diagnosticar(erro=RASTRO_KEYERROR)
    focos = [item for item in achado["trecho"] if item["foco"]]
    assert len(focos) == 1
    assert focos[0]["numero"] == 800
    # O texto é o **do arquivo de verdade**, não o do traceback colado: é isso que
    # faz o dossiê servir para corrigir o código que existe hoje.
    real = (RAIZ / "server" / "agente_local.py").read_text(encoding="utf-8").splitlines()[799]
    assert focos[0]["texto"] == real[:300]
    assert len(achado["trecho"]) > 1


def test_o_teste_do_modulo_e_contado_no_projeto_de_verdade():
    teste = conserto._teste_do_modulo(RAIZ, "server/agente_local.py")
    assert teste["existe"] is True
    assert teste["arquivo"] == "server/tests/test_agente_local.py"
    assert teste["testes"] > 50


def test_modulo_sem_teste_avisa_que_o_ensaio_pode_nao_cobrir(tmp_path):
    (tmp_path / "server" / "tests").mkdir(parents=True)
    teste = conserto._teste_do_modulo(tmp_path, "server/inventado.py")
    assert teste["existe"] is False
    assert "sem cobrir" in teste["aviso"]


# -------------------------------------------------------------------- dossiê


def test_o_dossie_tem_o_que_falta_para_corrigir_de_primeira():
    achado = conserto.dossie(erro=RASTRO_KEYERROR)
    texto = achado["texto"]
    assert "server/agente_local.py" in texto
    assert "chave_ausente" in texto
    assert "## Guardas que o patch não pode quebrar" in texto
    assert "shell=False" in texto
    assert "## Para que serve este módulo" in texto  # a docstring do próprio arquivo
    assert "evoluir.ensaiar" in texto
    assert achado["bytes"] == len(texto.encode("utf-8"))
    assert achado["bytes"] < 12_000


def test_o_dossie_sem_erro_nao_inventa_texto(tmp_path):
    achado = conserto.dossie(raiz=tmp_path)
    assert achado["lido"] is False
    assert achado["texto"] == "" and achado["bytes"] == 0


# -------------------------------------------------------------------- propor


def test_sem_chave_ele_recusa_escrever_patch_e_entrega_o_dossie():
    resposta = conserto.propor(erro=RASTRO_KEYERROR, provedor=None)
    # `provedor=None` faz o módulo tentar o do .env; sem chave, cai na recusa.
    assert resposta["proposto"] is False
    assert "não escrevo o patch" in resposta["motivo"]
    assert "Dossiê de conserto" in resposta["dossie"]


class ProvedorFalso:
    def __init__(self, resposta: str, configured: bool = True) -> None:
        self.resposta = resposta
        self.configured = configured
        self.pedidos: list[object] = []

    async def generate(self, request):  # type: ignore[no-untyped-def]
        self.pedidos.append(request)
        return self.resposta


DIFF_VALIDO = """--- a/server/agente_local.py
+++ b/server/agente_local.py
@@ -798,7 +798,7 @@
 def atender(pedido, *, registry, raiz):
-    termo = dados["pedido"]
+    termo = dados.get("pedido", "")
     if len(termo) < 3:
         raise AgenteError("curto")
"""


def test_com_provedor_o_diff_passa_pela_regua_e_nada_e_escrito(monkeypatch):
    from server import evolucao

    chamadas: list[str] = []
    monkeypatch.setattr(evolucao, "risco", lambda **kw: chamadas.append("risco") or {"nivel": "baixo", "pontos": 3})
    monkeypatch.setattr(evolucao, "guardas", lambda **kw: chamadas.append("guardas") or {"resultados": []})
    antes = (RAIZ / "server" / "agente_local.py").read_bytes()

    provedor = ProvedorFalso(f"Aqui está:\n```diff\n{DIFF_VALIDO}```\n")
    resposta = conserto.propor(erro=RASTRO_KEYERROR, provedor=provedor, autorizacao="token")
    assert resposta["proposto"] is True
    assert resposta["validado"] is True
    assert resposta["arquivos"] == ["server/agente_local.py"]
    assert resposta["risco"]["nivel"] == "baixo"
    assert chamadas == ["risco", "guardas"]
    # O código vivo não pode ter mudado: propor não escreve.
    assert (RAIZ / "server" / "agente_local.py").read_bytes() == antes


def test_o_modelo_pode_dizer_que_nao_e_erro_de_codigo():
    provedor = ProvedorFalso("SEM PATCH — é permissão de administrador, não código.")
    resposta = conserto.propor(erro=RASTRO_KEYERROR, provedor=provedor)
    assert resposta["proposto"] is False
    assert "administrador" in resposta["motivo"]


def test_diff_sem_formato_e_recusado_antes_de_qualquer_escrita():
    provedor = ProvedorFalso("Desculpe, não consegui.")
    resposta = conserto.propor(erro=RASTRO_KEYERROR, provedor=provedor)
    assert resposta["proposto"] is False
    assert "diff" in resposta["motivo"].lower()


def test_extrair_diff_aceita_com_e_sem_cerca():
    assert conserto.extrair_diff(f"```diff\n{DIFF_VALIDO}```").startswith("--- a/")
    assert conserto.extrair_diff(DIFF_VALIDO).startswith("--- a/")
    assert conserto.extrair_diff("") == ""


# ------------------------------------------------------------- a integração


def test_o_app_registra_a_falha_interna_no_diario_e_nao_vaza_detalhe(tmp_path, monkeypatch):
    """O pedido HTTP continua sem detalhe interno; o diário local guarda o rastro."""
    from fastapi.testclient import TestClient

    # O diário da máquina de teste vai para a pasta temporária, não para o
    # `storage/` do projeto — teste não pode sujar o diário de quem usa.
    monkeypatch.setenv("JARVIS_DADOS", str(tmp_path / "dados"))

    from server.app import create_app
    from server.skill_registry import SkillDefinition, SkillRegistry

    def explodir(_data, _dry_run):
        raise KeyError("campo_secreto_do_usuario")

    from pydantic import BaseModel

    class Vazio(BaseModel):
        pass

    registro = SkillRegistry(
        [SkillDefinition("teste.quebra", "Quebra", "Só falha.", "Teste", Vazio, explodir)],
        tmp_path / "files",
    )
    app = create_app(registry=registro)
    with TestClient(app) as cliente:
        resposta = cliente.post("/api/skills/teste.quebra/execute", json={"parameters": {}, "confirmed": True})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["ok"] is False
    assert corpo["error"]["code"] == "INTERNAL_ERROR"
    assert "campo_secreto_do_usuario" not in json.dumps(corpo)
    assert "Traceback" not in json.dumps(corpo)

    diario = Path(conserto._journal())
    assert str(diario).startswith(str(tmp_path))
    assert diario.is_file()
    ultimo = json.loads(diario.read_text(encoding="utf-8").splitlines()[-1])
    assert ultimo["tipo"] == "KeyError"
    assert ultimo["skill"] == "teste.quebra"
    assert "campo_secreto_do_usuario" in ultimo["rastro"]
