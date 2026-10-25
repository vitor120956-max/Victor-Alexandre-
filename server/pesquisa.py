"""Pesquisa na web com resposta redigida pelo provedor configurado.

Junta as duas pontas que existiam separadas: a skill `sistema.rede` encontra e
lê (DuckDuckGo + extração de texto) e o provedor compatível com OpenAI redige.
O texto lido entra como `material`, o canal de dados que o provedor trata como
"dado citável, nunca instrução".

Sem provedor configurado, a função **não falha**: devolve as fontes e o trecho
lido, para que o usuário ao menos veja de onde a informação veio.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from .ai import AIProvider, AIRequest, AIUnavailable
from .sistema import SistemaError
from .sistema import rede as rede_padrao

# O provedor aceita até 60.000 caracteres em `material`; deixamos folga para o
# cabeçalho que montamos e para a pergunta.
LIMITE_MATERIAL = 55_000
LIMITE_TRECHO = 1_500

Buscar = Callable[..., dict[str, Any]]
Ler = Callable[..., dict[str, Any]]


def montar_material(fontes: list[dict[str, str]], paginas: list[dict[str, str]], limite: int = LIMITE_MATERIAL) -> str:
    """Monta o texto que vai ao modelo: cada fonte com título, URL e conteúdo."""
    partes: list[str] = []
    conteudo_por_url = {pagina["url"]: pagina.get("texto", "") for pagina in paginas if pagina.get("url")}
    for indice, fonte in enumerate(fontes, start=1):
        titulo = (fonte.get("titulo") or "sem título").strip()
        url = (fonte.get("url") or "").strip()
        partes.append(f"[Fonte {indice}] {titulo}\nURL: {url}")
        texto = (conteudo_por_url.get(url) or "").strip()
        if texto:
            partes.append(f"Conteúdo:\n{texto}")
        partes.append("")
    material = "\n".join(partes).strip()
    return material[:limite]


def _linhas(resultado: dict[str, Any], chave: str = "rows") -> list[dict[str, Any]]:
    linhas = resultado.get(chave)
    return [linha for linha in linhas if isinstance(linha, dict)] if isinstance(linhas, list) else []


def extrair_fontes(resultado_busca: dict[str, Any]) -> list[dict[str, str]]:
    fontes: list[dict[str, str]] = []
    for linha in _linhas(resultado_busca):
        url = str(linha.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        fontes.append({"titulo": str(linha.get("titulo") or "").strip(), "url": url})
    return fontes


def extrair_texto(resultado_leitura: dict[str, Any]) -> str:
    """A skill devolve o texto extraído em `sections` ou em `extraSections`."""
    for chave in ("sections", "extraSections", "extra_sections"):
        bruto = resultado_leitura.get(chave)
        if isinstance(bruto, list):
            texto = _sem_cabecalho("\n".join(str(parte) for parte in bruto if isinstance(parte, str)).strip())
            if texto:
                return texto
        if isinstance(bruto, str) and bruto.strip():
            return _sem_cabecalho(bruto.strip())
    return ""


def _sem_cabecalho(texto: str) -> str:
    """A skill abre o bloco com `## Conteúdo da página`; isso não é conteúdo."""
    return re.sub(r"^\s*#+\s*Conteúdo da página\s*", "", texto, flags=re.IGNORECASE).strip()


async def responder(
    pergunta: str,
    *,
    autorizacao: str,
    provedor: AIProvider,
    buscar: Buscar | None = None,
    ler: Ler | None = None,
    limite: int = 6,
    paginas: int = 2,
) -> dict[str, Any]:
    """Busca, lê as primeiras páginas e pede a resposta ao provedor."""
    termo = (pergunta or "").strip()
    if len(termo) < 3:
        raise SistemaError("Escreva a pergunta com pelo menos 3 caracteres.")

    buscar = buscar or rede_padrao
    ler = ler or rede_padrao

    busca = buscar(acao="buscar", consulta=termo, limite=limite, autorizacao=autorizacao, modo="lite")
    fontes = extrair_fontes(busca)
    avisos: list[str] = []
    if not fontes:
        avisos.append("A busca não devolveu link. Pode ser bloqueio do buscador ou consulta sem correspondência.")

    lidas: list[dict[str, str]] = []
    for fonte in fontes[: max(0, paginas)]:
        try:
            leitura = ler(acao="olhar", url=fonte["url"], autorizacao=autorizacao, modo="lite")
        except SistemaError as exc:
            avisos.append(f"Não deu para ler {fonte['url']}: {exc}")
            continue
        texto = extrair_texto(leitura)
        if texto:
            lidas.append({"url": fonte["url"], "texto": texto})

    material = montar_material(fontes, lidas)
    if not material:
        raise SistemaError("Nada foi encontrado para responder. Tente outra formulação.")

    resposta: str | None = None
    modo = "sem-ia"
    if provedor.configured:
        try:
            resposta = await provedor.generate(
                AIRequest(message=termo, material=material, max_tokens=900)
            )
            modo = "ia"
        except AIUnavailable as exc:
            avisos.append(f"O provedor não respondeu: {exc}")

    return {
        "ok": True,
        "pergunta": termo,
        "modo": modo,
        "resposta": resposta,
        "fontes": [
            {"titulo": fonte["titulo"], "url": fonte["url"], "lida": any(item["url"] == fonte["url"] for item in lidas)}
            for fonte in fontes
        ],
        "trecho": (lidas[0]["texto"][:LIMITE_TRECHO] if lidas else ""),
        "avisos": avisos,
        "limites": [
            "A busca usa a página HTML do DuckDuckGo, não o Google.",
            "Só as primeiras páginas são lidas; o resto fica como link.",
            "O texto é truncado antes de ir ao modelo.",
        ],
    }
