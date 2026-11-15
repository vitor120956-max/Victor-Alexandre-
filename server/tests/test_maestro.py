"""Maestro — o que ele promete e o que ele recusa (0.91.0).

Os testes daqui seguem a mesma regra das outras frentes: **decisão fixada em
teste**. As quatro decisões que não podem voltar atrás:

1. planejar não executa nada — nem leitura de rede;
2. passo com efeito não roda sem autorização;
3. erro em um passo para a fila, e o resultado diz onde parou;
4. o maestro não rouba do ranking o pedido que uma skill só já resolve.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from server import agente_local
from server import maestro
from server import skill_registry as registro_de_skills


@pytest.fixture()
def registry(tmp_path: Path):
    return registro_de_skills.build_registry(tmp_path / "files")


def _plano(pedido: str, registry) -> dict[str, Any]:
    return maestro.planejar(pedido, registry=registry)


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------

def test_o_catalogo_tem_os_quatro_procedimentos_de_estreia():
    assert [p.id for p in maestro.PROCEDIMENTOS] == [
        "pesquisar-guardar",
        "baixar-repositorio",
        "consertar-erro",
        "escrever-no-programa",
    ]


def test_todo_passo_nomeia_uma_skill_que_existe_no_registro(registry):
    """Catálogo fechado não inventa passo: se a skill sumir, isto quebra."""
    existentes = {item["id"] for item in registry.list()}
    usadas: list[str] = []
    for procedimento in maestro.PROCEDIMENTOS:
        for passo in procedimento.passos:
            usadas.append(passo.skill)
            assert passo.skill in existentes, f"{procedimento.id} usa {passo.skill}, que não existe"


def test_o_catalogo_publica_os_passos_na_ordem(registry):
    dados = asyncio.run(registry.execute("maestro.catalogo", {}))
    assert dados["total"] == 4
    por_id = {item["id"]: item for item in dados["procedimentos"]}
    assert [p["skill"] for p in por_id["consertar-erro"]["passos"]] == [
        "conserto.diagnosticar",
        "conserto.dossie",
        "conserto.propor",
    ]
    assert "conserto.propor" in dados["texto"]


# ---------------------------------------------------------------------------
# Escolha do procedimento
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "pedido, esperado",
    [
        ("pesquisa o clima de Palhoça e guarda em clima.txt", "pesquisar-guardar"),
        ("procura passagens e salva no arquivo passagens.txt", "pesquisar-guardar"),
        ("baixa o repositório https://github.com/vitor120956-max/Victor-Alexandre- e analisa", "baixar-repositorio"),
        ("conserta o erro que apareceu no meu programa", "consertar-erro"),
        ("arruma o erro do meu programa", "consertar-erro"),
        ('escreve "oi, mundo" no bloco de notas', "escrever-no-programa"),
    ],
)
def test_o_pedido_casa_com_o_procedimento_declarado(pedido, esperado):
    achado = maestro.escolher_procedimento(pedido)
    assert achado is not None
    assert achado.id == esperado


@pytest.mark.parametrize(
    "pedido",
    ["faz um bolo de cenoura", "qual o significado da vida", "toca uma música"],
)
def test_pedido_fora_do_catalogo_nao_casa(pedido):
    assert maestro.escolher_procedimento(pedido) is None


def test_a_escolha_e_deterministica():
    """Mesmo pedido, mesma resposta — 20 vezes, e sem depender de sorteio."""
    pedido = "conserta o erro do meu programa"
    ids = {maestro.escolher_procedimento(pedido).id for _ in range(20)}
    assert ids == {"consertar-erro"}


def test_pedido_sem_procedimento_e_recusado_sem_executar(registry):
    with pytest.raises(maestro.MaestroError) as erro:
        _plano("faz um bolo de cenoura", registry)
    assert "não tenho procedimento" in str(erro.value)
    assert "consertar-erro" in str(erro.value)  # diz o que existe


# ---------------------------------------------------------------------------
# Plano: nada roda
# ---------------------------------------------------------------------------

class _RegistroEspiao:
    """Registro que delata qualquer execução durante o planejamento."""

    def __init__(self, real) -> None:
        self.real = real
        self.executadas: list[str] = []

    def list(self):
        return self.real.list()

    def get(self, skill_id):
        return self.real.get(skill_id)

    async def execute(self, skill_id, parameters, dry_run=False):
        self.executadas.append(skill_id)
        raise AssertionError(f"planejar executou {skill_id}")


@pytest.mark.parametrize(
    "pedido",
    [
        "pesquisa o clima de Palhoça e guarda em clima.txt",
        "baixa o repositório https://github.com/vitor120956-max/Victor-Alexandre- e analisa",
        "conserta o erro do meu programa",
    ],
)
def test_planejar_nao_executa_nada(pedido, registry):
    espiao = _RegistroEspiao(registry)
    plano = maestro.planejar(pedido, registry=espiao)
    assert espiao.executadas == []
    assert plano["passos"], "o plano precisa ter passo"


def test_o_plano_diz_a_skill_de_cada_passo_e_o_porque(registry):
    plano = _plano("pesquisa o clima de Palhoça e guarda em clima.txt", registry)
    assert [p["skill"] for p in plano["passos"]] == ["sistema.rede", "files.write"]
    assert all(p["porque"] for p in plano["passos"])
    assert plano["passos"][1]["efeito"] is True
    assert plano["precisa_autorizacao"] is True
    assert plano["passos"][1]["vem_do_passo"] == ["content (do passo 1)"]


def test_o_plano_tira_o_verbo_e_o_destino_da_consulta(registry):
    plano = _plano("pesquisa o clima de Palhoça e guarda em clima.txt", registry)
    assert plano["slots"]["pedido_limpo"] == "clima de Palhoça"
    assert plano["slots"]["arquivo"] == "clima.txt"


def test_sem_url_o_plano_ja_avisa_que_falta_dado(registry):
    plano = _plano("baixa o repositório e analisa", registry)
    assert plano["passos"][0]["faltando"] == ["url"]


def test_o_plano_nao_grava_arquivo(registry, tmp_path):
    _plano("pesquisa o clima e guarda em clima.txt", registry)
    assert not (tmp_path / "files" / "clima.txt").exists()


# ---------------------------------------------------------------------------
# Referências entre passos
# ---------------------------------------------------------------------------

def _contexto(pedido="pedido inteiro", slots=None, saidas=None):
    return maestro._contexto(pedido, slots or {"arquivo": "clima.txt"}, saidas or [])


def test_referencia_ao_pedido_e_aos_slots():
    contexto = _contexto()
    assert maestro.resolver_valor("$pedido", contexto=contexto) == "pedido inteiro"
    assert maestro.resolver_valor("$arquivo", contexto=contexto) == "clima.txt"


def test_referencia_a_saida_de_outro_passo():
    contexto = _contexto(saidas=[{"slug": "dono__repo", "rows": [{"titulo": "A", "url": "https://a"}]}])
    assert maestro.resolver_valor("$1.slug", contexto=contexto) == "dono__repo"


def test_modelo_interpola_resumo_e_linhas():
    saida = {
        "summary": ["2 resultado(s).", "Fonte: ddg."],
        "rows": [{"titulo": "Clima", "url": "https://exemplo/clima"}],
    }
    contexto = _contexto(saidas=[saida])
    texto = maestro.resolver_valor("{{1.resumo}}\n{{1.linhas}}", contexto=contexto)
    assert "2 resultado(s)." in texto
    assert "Fonte: ddg." in texto
    assert "- Clima — https://exemplo/clima" in texto


def test_chave_que_nao_existe_vira_vazio_e_nao_quebra():
    contexto = _contexto(saidas=[{"slug": "x"}])
    assert maestro.resolver_valor("$1.nao_existe", contexto=contexto) == ""
    assert maestro.resolver_valor("$9.slug", contexto=contexto) == ""
    assert maestro.resolver_valor("{{3.slug}}", contexto=contexto) == ""


def test_a_referencia_nao_avalia_codigo():
    """`$...` é busca de campo, não expressão: nada de `__class__` nem chamada."""
    contexto = _contexto(saidas=[{"slug": "x"}])
    assert maestro.resolver_valor("$1.__class__", contexto=contexto) == ""
    assert maestro.resolver_valor("$1.slug()", contexto=contexto) == ""


def test_campo_obrigatorio_vazio_barra_o_passo():
    passo = {"n": 1, "skill": "repos.baixar", "campos": {"url": "$url"}, "obrigatorios": ["url"]}
    with pytest.raises(maestro.MaestroError) as erro:
        maestro.campos_do_passo(passo, contexto=_contexto(slots={"url": ""}))
    assert "url" in str(erro.value)


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

def _executador_falso(chamadas, *, falha_em=None):
    async def falso(skill, campos, dry):
        chamadas.append((skill, dict(campos)))
        if skill == falha_em:
            raise RuntimeError("quebrou de propósito")
        if skill == "sistema.rede":
            return {"summary": ["1 resultado."], "rows": [{"titulo": "Clima", "url": "https://exemplo/clima"}]}
        if skill.startswith("conserto."):
            return {"lido": True, "fonte": "texto colado", "resumo": f"{skill}: achado o ponto"}
        return {"slug": "dono__repo", "ok": True}

    return falso


def test_sem_autorizacao_para_antes_do_passo_com_efeito(registry):
    plano = _plano("pesquisa o clima e guarda em clima.txt", registry)
    chamadas: list[tuple[str, dict[str, Any]]] = []
    resultado = asyncio.run(maestro.executar(plano, registry=registry, executador=_executador_falso(chamadas)))

    assert [c[0] for c in chamadas] == ["sistema.rede"]
    assert resultado["ok"] is False
    assert resultado["parou_em"] == 2
    assert resultado["parou_motivo"] == "precisa_autorizacao"
    assert "parei no passo 2" in resultado["resumo"]
    assert "1 passo(s) antes disso foram concluídos" in resultado["resumo"]


def test_com_autorizacao_roda_em_ordem_e_passa_o_resultado_adiante(registry):
    plano = _plano("pesquisa o clima e guarda em clima.txt", registry)
    chamadas: list[tuple[str, dict[str, Any]]] = []
    resultado = asyncio.run(
        maestro.executar(plano, registry=registry, autorizar=True, executador=_executador_falso(chamadas))
    )

    assert resultado["ok"] is True
    assert resultado["parou_em"] is None
    assert [c[0] for c in chamadas] == ["sistema.rede", "files.write"]
    conteudo = chamadas[1][1]["content"]
    assert chamadas[1][1]["path"] == "clima.txt"
    assert "1 resultado." in conteudo
    assert "https://exemplo/clima" in conteudo


def test_erro_num_passo_para_a_fila_e_diz_onde_parou(registry):
    plano = _plano("conserta o erro do meu programa", registry)
    chamadas: list[tuple[str, dict[str, Any]]] = []
    resultado = asyncio.run(
        maestro.executar(
            plano, registry=registry, autorizar=True, executador=_executador_falso(chamadas, falha_em="conserto.dossie")
        )
    )

    assert resultado["ok"] is False
    assert resultado["parou_em"] == 2
    assert resultado["parou_motivo"] == "erro"
    assert resultado["passo_que_parou"]["skill"] == "conserto.dossie"
    assert "quebrou de propósito" in resultado["motivo"]
    assert [c[0] for c in chamadas] == ["conserto.diagnosticar", "conserto.dossie"]
    assert len(resultado["passos"]) == 1, "o passo que falhou não conta como concluído"


def test_passo_que_roda_e_nao_le_nada_para_a_fila(registry):
    """0.91.1: `conserto.diagnosticar` devolvia `lido: false` e a fila seguia.

    Dossiê de erro que não existe é pior que dossiê nenhum. O passo declara
    `exigir="lido"`, e o maestro confere isso antes de aceitar o passo.
    """
    plano = _plano("conserta o erro do meu programa", registry)

    async def sem_erro(skill, campos, dry):
        if skill == "conserto.diagnosticar":
            return {"lido": False, "motivo": "Não há erro no diário e você não colou nenhum."}
        raise AssertionError(f"não devia rodar {skill}")

    resultado = asyncio.run(maestro.executar(plano, registry=registry, autorizar=True, executador=sem_erro))

    assert resultado["ok"] is False
    assert resultado["parou_em"] == 1
    assert resultado["parou_motivo"] == "nao_confirmado"
    assert "Não há erro no diário" in resultado["motivo"]
    assert resultado["passos"] == []


def test_o_plano_avisa_o_que_cada_passo_precisa_confirmar(registry):
    plano = _plano("conserta o erro do meu programa", registry)
    assert plano["passos"][0]["exigir"] == "lido"
    texto = maestro.texto_do_plano(plano)
    assert "só vale se voltar lido=true" in texto


def test_a_execucao_mostra_o_que_cada_passo_trouxe(registry):
    plano = _plano("conserta o erro do meu programa", registry)
    chamadas: list[tuple[str, dict[str, Any]]] = []
    resultado = asyncio.run(
        maestro.executar(plano, registry=registry, autorizar=True, executador=_executador_falso(chamadas))
    )
    texto = maestro.texto_da_execucao(resultado)
    assert "1. conserto.diagnosticar — feito" in texto
    assert "voltou: conserto.diagnosticar: achado o ponto" in texto


def test_passo_sem_dado_para_antes_de_rodar(registry):
    plano = _plano("baixa o repositório e analisa", registry)
    chamadas: list[tuple[str, dict[str, Any]]] = []
    resultado = asyncio.run(
        maestro.executar(plano, registry=registry, autorizar=True, executador=_executador_falso(chamadas))
    )
    assert resultado["parou_em"] == 1
    assert resultado["parou_motivo"] == "falta_dado"
    assert chamadas == []


def test_a_saida_de_um_passo_vira_entrada_do_proximo_de_verdade(registry, tmp_path):
    """Ponta a ponta com o registro real: um passo grava, o outro lê o que foi gravado."""
    procedimento = maestro.Procedimento(
        id="teste-gravar-e-ler",
        nome="Gravar e ler",
        exemplo="",
        precisa=(),
        passos=(
            maestro.Passo(skill="files.write", campos={"path": "nota.txt", "content": "# {{pedido}}\nok"}, porque="gravar"),
            maestro.Passo(skill="files.read", campos={"path": "$1.written"}, porque="ler de volta o que foi gravado"),
        ),
    )
    plano = maestro.planejar("grava uma nota", registry=registry, procedimento=procedimento)
    resultado = asyncio.run(maestro.executar(plano, registry=registry, autorizar=True))

    assert resultado["ok"] is True, resultado
    assert (tmp_path / "files" / "nota.txt").read_text(encoding="utf-8") == "# grava uma nota\nok"
    lido = resultado["passos"][1]["saida"]
    assert "ok" in json.dumps(lido, ensure_ascii=False)


# ---------------------------------------------------------------------------
# As skills do maestro
# ---------------------------------------------------------------------------

def test_a_skill_planejar_nao_executa_e_devolve_texto(registry):
    dados = asyncio.run(registry.execute("maestro.planejar", {"pedido": "conserta o erro do meu programa"}))
    assert dados["procedimento"] == "consertar-erro"
    assert "1. conserto.diagnosticar" in dados["texto"]
    assert "nada foi executado" in dados["texto"].lower()


def test_a_skill_executar_em_simulacao_nao_executa(registry):
    dados = asyncio.run(
        registry.execute("maestro.executar", {"pedido": "conserta o erro do meu programa"}, dry_run=True)
    )
    assert dados["executado"] is False
    assert "Plano para" in dados["texto"]


def test_a_skill_executar_sem_autorizacao_para_no_efeito(registry):
    dados = asyncio.run(
        registry.execute("maestro.executar", {"pedido": "baixa o repositório https://github.com/dono/repo e analisa"})
    )
    assert dados["executado"] is True
    assert dados["parou_em"] == 1
    assert dados["parou_motivo"] == "precisa_autorizacao"


def test_a_skill_executar_aceita_procedimento_por_id(registry):
    dados = asyncio.run(
        registry.execute(
            "maestro.executar",
            {"pedido": "conserta o erro do meu programa", "procedimento": "consertar-erro"},
            dry_run=True,
        )
    )
    assert dados["procedimento"] == "consertar-erro"


def test_procedimento_desconhecido_vira_erro_de_skill(registry):
    with pytest.raises(registro_de_skills.SkillError):
        asyncio.run(registry.execute("maestro.planejar", {"pedido": "conserta o erro", "procedimento": "inventado"}))


# ---------------------------------------------------------------------------
# O chat: o maestro não rouba o que uma skill só resolve
# ---------------------------------------------------------------------------

def test_o_chat_mostra_o_plano_do_objetivo_de_varios_passos(registry):
    resultado = asyncio.run(
        agente_local.atender(
            "pesquisa o clima de Palhoça e guarda em clima.txt",
            registry=registry,
            raiz=Path("/tmp/raiz-maestro"),
            consultar_web=False,
        )
    )
    assert resultado["acao"] == "plano"
    assert resultado["via"] == "maestro"
    assert resultado["plano"]["procedimento"] == "pesquisar-guardar"
    assert "nada rodou" in resultado["resposta"].lower()


def test_o_chat_nao_rouba_o_pedido_de_um_passo_so(registry):
    """“escreve oi no bloco de notas” continua indo para o ranking, como em 0.90.0."""
    resultado = agente_local._resposta_de_orquestracao("escreve oi no bloco de notas", registry)
    assert resultado is None


def test_o_chat_nao_orquestra_pedido_sem_procedimento(registry):
    assert agente_local._resposta_de_orquestracao("faz um bolo de cenoura", registry) is None


# ---------------------------------------------------------------------------
# Unicidade de vocabulário e comportamento de texto
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("texto", ["Pesquisa o CLIMA de Palhoça", "  BAixa   repositório ", "ÃÉÎÕÜ ç"])
def test_normalizar_e_igual_ao_do_agente(texto):
    """O maestro copiou a função para não fechar ciclo de importação — não pode divergir."""
    assert maestro._normalizar(texto) == agente_local.normalizar(texto)


def test_o_texto_da_execucao_diz_o_que_foi_feito_e_onde_parou(registry):
    plano = _plano("conserta o erro do meu programa", registry)
    chamadas: list[tuple[str, dict[str, Any]]] = []
    resultado = asyncio.run(
        maestro.executar(
            plano, registry=registry, autorizar=True, executador=_executador_falso(chamadas, falha_em="conserto.propor")
        )
    )
    texto = maestro.texto_da_execucao(resultado)
    assert "1. conserto.diagnosticar — feito" in texto
    assert "2. conserto.dossie — feito" in texto
    assert "Parei no passo 3 (conserto.propor)" in texto


# ---------------------------------------------------------------------------
# A sonda do PC
# ---------------------------------------------------------------------------

def _sonda():
    import importlib.util

    caminho = Path(__file__).resolve().parents[2] / "arvore_sonda.py"
    spec = importlib.util.spec_from_file_location("arvore_sonda_maestro", caminho)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


def _args(**extra):
    base = {"json": False, "catalogo": False, "orquestrar": "", "autorizar": False, "procedimento": ""}
    base.update(extra)
    return argparse.Namespace(**base)


def test_a_sonda_lista_o_catalogo(capsys):
    codigo = _sonda()._orquestrar(_args(catalogo=True))
    assert codigo == 0
    saida = capsys.readouterr().out
    assert "consertar-erro" in saida


def test_a_sonda_mostra_o_plano_sem_autorizar(capsys):
    codigo = _sonda()._orquestrar(_args(orquestrar="conserta o erro do meu programa"))
    assert codigo == 0
    saida = capsys.readouterr().out
    assert "conserto.diagnosticar" in saida
    assert "nada foi executado" in saida.lower()


def test_a_sonda_recusa_objetivo_fora_do_catalogo(capsys):
    codigo = _sonda()._orquestrar(_args(orquestrar="faz um bolo de cenoura"))
    assert codigo == 1
    assert "não tenho procedimento" in capsys.readouterr().out


def test_a_sonda_le_o_env_do_pc(tmp_path, monkeypatch):
    """0.91.0 lia `JARVIS_HOST_REDE=1` no `.env` e continuava dizendo “Rede desligada”.

    Só o `server/app.py` carregava o `.env`; o `arvore_sonda.py` roda solto no
    terminal e não carregava. Medido no sandbox antes da correção.
    """
    monkeypatch.delenv("JARVIS_HOST_REDE", raising=False)
    (tmp_path / ".env").write_text("JARVIS_HOST_REDE=1\n", encoding="utf-8")

    assert _sonda()._configurar_ambiente(tmp_path) is True
    import os

    assert os.environ.get("JARVIS_HOST_REDE") == "1"
    monkeypatch.delenv("JARVIS_HOST_REDE", raising=False)


def test_o_env_do_pc_nao_sobrescreve_o_que_ja_estava_no_ambiente(tmp_path, monkeypatch):
    """Quem exportou a variável no terminal continua mandando."""
    monkeypatch.setenv("JARVIS_HOST_REDE", "1")
    (tmp_path / ".env").write_text("JARVIS_HOST_REDE=0\n", encoding="utf-8")

    _sonda()._configurar_ambiente(tmp_path)
    import os

    assert os.environ["JARVIS_HOST_REDE"] == "1"


def test_o_erro_do_pedido_comeca_no_traceback():
    """A frase do pedido não pode virar “o erro” que vai para o diagnóstico."""
    pedido = "conserta esse erro: Traceback (most recent call last):\n  File \"x.py\", line 1\nKeyError: 'a'"
    erro = maestro.slots_do_pedido(pedido)["erro"]
    assert erro.startswith("Traceback")
    assert "conserta esse erro" not in erro


def test_erro_de_uma_linha_vai_inteiro():
    assert maestro.slots_do_pedido("conserta o erro KeyError: 'a'")["erro"] == "conserta o erro KeyError: 'a'"
