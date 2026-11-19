"""O que o JARVIS não faz — cobrado por máquina (0.91.46).

O dono perguntou:

    e oq mais o jarvis atualmente ele nao faz?

Uma lista de limitações escrita à mão envelhece mal. Este projeto já pagou por
isso: o README dizia “PDF não tem OCR” três versões depois de o OCR existir, e
a frase ficou no ar até esta versão. Então a lista vive em `docs/NAO-FAZ.md` **e**
é conferida aqui, nas duas direções:

- as **lacunas** afirmadas no documento continuam sendo lacuna (no dia em que
  forem fechadas, o teste quebra e obriga a mover a linha);
- o que o documento diz que **já funciona** continua funcionando (para a lista
  não virar um “não faz” mentiroso).

Não é teste de estilo: é a diferença entre “não faz” e “não fazia”.
"""
from __future__ import annotations

import re
from pathlib import Path

from server import ai, ocr
from server.app import create_app
from server.skill_registry import build_registry

RAIZ = Path(__file__).resolve().parents[2]
DOC = RAIZ / "docs" / "NAO-FAZ.md"


def _texto_doc() -> str:
    assert DOC.is_file(), "docs/NAO-FAZ.md sumiu — a lista de limites mora nele"
    return DOC.read_text(encoding="utf-8")


def _ids_de_skill(tmp_path: Path) -> set[str]:
    registry = build_registry(tmp_path / "files")
    return {skill["id"] for skill in registry.list()}


# ---------------------------------------------------------------------------
# O documento
# ---------------------------------------------------------------------------

def test_o_documento_existe_e_separa_os_tres_tipos_de_nao_fazer():
    texto = _texto_doc()
    for secao in (
        "Não faz e não tem como",
        "Não faz por decisão",
        "Não faz hoje, mas dá para fazer",
        "Já faz",
    ):
        assert secao in texto, f"a seção “{secao}” desapareceu do documento"
    # A origem da lista é a pergunta do dono, e a resposta não pode virar promessa.
    assert "oq mais o jarvis" in texto
    assert "Como esta lista é cobrada" in texto


def test_o_readme_aponta_para_a_lista():
    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    assert "docs/NAO-FAZ.md" in readme
    # E a seção de limites do README não pode contradizer o documento.
    assert "PDF não tem OCR" not in readme


# ---------------------------------------------------------------------------
# As lacunas continuam sendo lacunas
# ---------------------------------------------------------------------------

def test_comparar_dois_apks_continua_sem_botao_nem_rota(tmp_path: Path):
    """O documento diz: existe `jogo.comparar()`, não existe `/api/jogo/comparar`.

    Quando a rota (ou o botão) chegar, este teste quebra de propósito — é o
    convite a mover a linha para “já faz”.
    """
    from server import jogo

    assert hasattr(jogo, "comparar"), "o código de comparação sumiu: a lacuna mudou de forma"

    app = create_app(registry=build_registry(tmp_path / "files"))
    caminhos = {rota.path for rota in app.routes if hasattr(rota, "path")}
    assert "/api/jogo/comparar" not in caminhos
    assert "/api/jogo/upload" in caminhos  # sanidade: a leitura das rotas funciona


def test_instalar_o_apk_no_celular_continua_sem_skill(tmp_path: Path):
    """O documento promete: o módulo tem ADB, mas não há `celular.instalar`."""
    ids = _ids_de_skill(tmp_path)
    assert not [item for item in ids if item == "celular.instalar"]
    assert "celular.preparar" in ids, "o ADB continua sendo baixado por esta skill"
    # E não existe família `jogo.*`: a análise do jogo é rota, não skill.
    assert not [item for item in ids if item.startswith("jogo.")]


def test_a_ia_continua_sendo_texto_puro():
    """Sem visão: o campo de conteúdo é `str`; não há imagem na mensagem."""
    conteudo = ai.HistoryMessage.model_fields["content"].annotation
    assert conteudo is str
    assert "image_url" not in (RAIZ / "server" / "ai.py").read_text(encoding="utf-8")


def test_a_resposta_continua_inteira_e_nao_em_fluxo():
    """Streaming seria outra arquitetura; o documento diz que não há."""
    for arquivo in (RAIZ / "server").glob("*.py"):
        assert "StreamingResponse" not in arquivo.read_text(encoding="utf-8"), (
            f"{arquivo.name} passou a usar StreamingResponse — atualize docs/NAO-FAZ.md "
            "se o streaming virou recurso"
        )


def test_a_api_continua_escutando_so_na_maquina_local():
    iniciar = (RAIZ / "iniciar.py").read_text(encoding="utf-8")
    assert 'default="127.0.0.1"' in iniciar
    # Expor na rede é opção explícita, nunca padrão.
    assert "--host 0.0.0.0" in iniciar


# ---------------------------------------------------------------------------
# O que o documento diz que já funciona continua funcionando
# ---------------------------------------------------------------------------

def test_ocr_de_pdf_escaneado_existe_de_verdade():
    """A frase que o README repetia por engano: “PDF não tem OCR”."""
    assert callable(getattr(ocr, "extrair_pdf", None))
    assert callable(getattr(ocr, "extrair_imagem", None))
    biblioteca = (RAIZ / "server" / "biblioteca.py").read_text(encoding="utf-8")
    assert "ocr.extrair_pdf" in biblioteca, "a biblioteca deixou de usar o OCR de PDF"


def test_o_ditado_e_a_fala_continuam_no_navegador():
    """O documento diz que voz é do navegador — não de um modelo de áudio."""
    hook = (RAIZ / "src" / "hooks" / "useSpeechInput.ts").read_text(encoding="utf-8")
    assert "webkitSpeechRecognition" in hook or "SpeechRecognition" in hook
    ajustes = (RAIZ / "src" / "pages" / "SettingsPage.tsx").read_text(encoding="utf-8")
    assert "speechSynthesis" in ajustes


def test_o_obb_e_a_analise_de_apk_continuam_entrando():
    """O documento lista os dois como “já faz”; sem eles, a lista mente."""
    jogo = (RAIZ / "server" / "jogo.py").read_text(encoding="utf-8")
    assert "EXTENSOES_OBB" in jogo
    assert "relatar_obb" in jogo
    assert "MAXIMO_BYTES = 2_000_000_000" in jogo


def test_o_documento_nao_cita_numeros_que_o_codigo_desmente():
    """Um “não faz” com número errado é pior que nenhum: confere o teto."""
    from server import jogo

    texto = _texto_doc()
    for achado in re.findall(r"(\d[\d.]*)\s?(MB|GB)", texto):
        valor, unidade = achado
        numero = float(valor.replace(".", "").replace(",", "."))
        limite = numero * (1e9 if unidade == "GB" else 1e6)
        assert limite <= jogo.MAXIMO_BYTES + 1, (
            f"o documento fala de {valor} {unidade}, acima do teto real "
            f"({jogo.rotulo_bytes(jogo.MAXIMO_BYTES)})"
        )
