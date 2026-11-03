"""Conserto: do erro real até a proposta que a camada de evolução já sabe ensaiar.

O pedido foi: *“tem como ele se auto programar? deu erro numa função, ele vai
procurar para que serve e como funciona, pesquisa, entende, testa, roda e, se
funcionar, entrega”*.

Metade disso **já existia** — e é a metade cara: `evolucao.py` prova que o diff
aplica, pontua o risco, confere as dez guardas, **ensai­a numa cópia rodando a
suíte real** e só então promove, com backup e token de uso único. O que faltava
era o começo e o fim do laço: ninguém ligava o erro a uma proposta, e o diff era
escrito à mão por você (ou por um modelo, colando o texto na tela).

Este módulo faz a ponte, em três passos, e nada além disso:

1. **`anotar`** — toda falha interna de skill vira uma linha em
   `storage/erros.jsonl` (tipo, mensagem, traceback, skill, versão). É o que
   permite o JARVIS saber que errou sem você copiar texto do terminal;
2. **`diagnosticar`** — abre o traceback, acha o quadro do próprio projeto, lê a
   linha, mostra o trecho com número, classifica a causa por regra e diz se
   existe teste daquele módulo. Puro: não escreve, não chama rede;
3. **`dossie`** — junta erro + trecho + teste + guardas num texto curto: é o que
   faz uma correção sair em uma tentativa em vez de dez.

A quarta peça, **`propor`**, só existe com chave de IA configurada: ela pede o
diff ao provedor e entrega o diff **já validado** por `evolucao` (aplica? risco?
guardas?). Escrever o patch na máquina viva continua sendo `evoluir.promover`,
com token, e com reinício da API — que é de propósito: um patch que derruba o
processo derrubaria junto o que saberia reverter.

O que este módulo **não** faz, e não vai passar a fazer por mágica:

- não corrige sem entender: sem chave, ele diagnostica e entrega o dossiê;
- não inventa a causa: cada classificação é uma regra escrita aqui embaixo, com
  o motivo — o que não casa vira `desconhecida` em vez de um palpite;
- não escreve em `server/`, não roda patch, não promove, não reinicia nada.
"""
from __future__ import annotations

import json
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import dados as dados_locais

VERSAO = "0.75.0"

MAX_ERRO = 20_000
MAX_TRECHO = 9
MAX_DOSSIE = 12_000
MAX_ARQUIVO_DOSSIE = 60_000
MAX_LINHAS_JOURNAL = 200

# ---------------------------------------------------------------------------
# Classificação da causa
# ---------------------------------------------------------------------------

# Cada regra é (código, expressão, o que significa, o que fazer). A ordem importa:
# a primeira que casar vence. Nada de “provavelmente”: o que não casa é
# `desconhecida`, e o dossiê diz isso.
REGRAS: tuple[tuple[str, str, str, str], ...] = (
    (
        "permissao",
        r"PermissionError|Access is denied|Acesso negado|WinError 5\b|EACCES",
        "o processo não tem permissão para o arquivo, a chave de registro ou o serviço",
        "Não é patch de código: é elevação (UAC) ou dono do arquivo. Rodar como administrador resolve o caso do serviço/tarefa.",
    ),
    (
        "arquivo_ausente",
        r"FileNotFoundError|No such file or directory|WinError 2\b|não pôde ser encontrado",
        "o caminho não existe nesta máquina",
        "O patch certo ou cria o arquivo com um padrão sensato, ou troca o caminho por um vindo de `dados.raiz()`. Confira se o teste usa caminho temporário.",
    ),
    (
        "chave_ausente",
        r"KeyError",
        "o dicionário/JSON não trouxe a chave esperada — formato antigo, campo opcional ou resposta vazia",
        "Normalmente é `.get(chave, padrão)` com um padrão que faça sentido, e um teste com o JSON sem esse campo.",
    ),
    (
        "tipo_none",
        r"AttributeError.*'NoneType'|NoneType.*has no attribute",
        "algo devolveu `None` onde o código esperava objeto",
        "A correção é guardar o `None` no ponto em que ele nasce, não espalhar `if` por todo mundo.",
    ),
    (
        "tipo_errado",
        r"TypeError",
        "argumento com tipo ou quantidade diferente do que a função espera",
        "Olhe a assinatura do quadro citado no traceback e o que o chamador passou.",
    ),
    (
        "indice",
        r"IndexError",
        "a lista acabou antes do índice esperado",
        "Quem chama precisa tratar lista vazia — o teste que faltava é justamente com zero itens.",
    ),
    (
        "valor_invalido",
        r"ValueError|ValidationError",
        "o valor chegou num formato que a função recusa",
        "Se o valor vem de fora, validar na borda (Pydantic ou regra explícita) e devolver erro legível.",
    ),
    (
        "unicode",
        r"UnicodeDecodeError|UnicodeEncodeError|codec can't",
        "leitura/escrita com codificação diferente da real (Windows ANSI × UTF-8, CRLF × LF)",
        "No Windows: ler `bytes` e decodificar com fallback, ou escrever com `\\r\\n` explícito. Foi o que já mordeu os `.bat` deste projeto.",
    ),
    (
        "json",
        r"JSONDecodeError|json.decoder",
        "o arquivo não é JSON válido — gravação interrompida ou arquivo vazio",
        "Gravar em arquivo temporário e renomear (atômico) evita metade desses casos.",
    ),
    (
        "timeout",
        r"TimeoutError|timed out|excedeu o tempo",
        "a operação não terminou dentro do limite",
        "Aumente o `timeout_seconds` da skill só com medição; antes disso, quebre o trabalho em partes.",
    ),
    (
        "rede",
        r"ConnectError|ConnectionError|HTTPStatusError|getaddrinfo|SSLError|ReadTimeout",
        "a rede recusou ou não respondeu",
        "Todo caminho de rede precisa de mensagem própria e de continuar funcionando offline.",
    ),
    (
        "subprocesso",
        r"FileNotFoundError.*cmd|WinError 2|subprocess",
        "o binário chamado não existe (ou não está no PATH desta máquina)",
        "Detecte a existência antes de chamar e explique em vez de estourar.",
    ),
)


def _causa(tipo: str, mensagem: str) -> dict[str, str]:
    alvo = f"{tipo}: {mensagem}"
    for codigo, padrao, significa, fazer in REGRAS:
        if re.search(padrao, alvo, re.I):
            return {"codigo": codigo, "significa": significa, "o_que_fazer": fazer}
    return {
        "codigo": "desconhecida",
        "significa": "não casa com nenhuma regra conhecida deste módulo",
        "o_que_fazer": "O dossiê tem o traceback inteiro e o trecho do código: é o material para analisar à mão ou com modelo.",
    }


# ---------------------------------------------------------------------------
# O diário de erros
# ---------------------------------------------------------------------------


def _journal(raiz: Path | None = None) -> Path:
    base = Path(raiz) if raiz is not None else Path(dados_locais.raiz())
    return base / "erros.jsonl"


def anotar(
    *,
    tipo: str,
    mensagem: str,
    rastro: str = "",
    skill: str = "",
    raiz: Path | None = None,
    agora: datetime | None = None,
) -> Path:
    """Guarda uma falha interna. Devolve o arquivo — quem chama não precisa saber.

    Falhar aqui **nunca** pode derrubar quem falhou: o diário é diagnóstico, não
    parte do trabalho. Por isso o `except` largo no chamador, não aqui.
    """
    arquivo = _journal(raiz)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    registro = {
        "quando": (agora or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "versao": VERSAO,
        "skill": (skill or "")[:80],
        "tipo": (tipo or "")[:120],
        "mensagem": (mensagem or "")[:1_000],
        "rastro": (rastro or "")[-MAX_ERRO:],
    }
    with arquivo.open("a", encoding="utf-8") as destino:
        destino.write(json.dumps(registro, ensure_ascii=False) + "\n")
    _podar(arquivo)
    return arquivo


def _podar(arquivo: Path, limite: int = MAX_LINHAS_JOURNAL) -> None:
    """Mantém só as últimas linhas: diário de erro não é arquivo histórico."""
    try:
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(linhas) <= limite:
        return
    arquivo.write_text("\n".join(linhas[-limite:]) + "\n", encoding="utf-8")


def erros(raiz: Path | None = None, limite: int = 20) -> list[dict[str, Any]]:
    """Os últimos erros, do mais novo para o mais antigo, sem o rastro completo."""
    arquivo = _journal(raiz)
    try:
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    itens: list[dict[str, Any]] = []
    for linha in reversed(linhas[-MAX_LINHAS_JOURNAL:]):
        try:
            registro = json.loads(linha)
        except json.JSONDecodeError:
            continue
        if isinstance(registro, dict):
            itens.append({**registro, "rastro": ""})
        if len(itens) >= limite:
            break
    return itens


def _ultimo_bruto(raiz: Path | None = None) -> dict[str, Any] | None:
    arquivo = _journal(raiz)
    try:
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for linha in reversed(linhas):
        try:
            registro = json.loads(linha)
        except json.JSONDecodeError:
            continue
        if isinstance(registro, dict):
            return registro
    return None


# ---------------------------------------------------------------------------
# Diagnosticar
# ---------------------------------------------------------------------------


def _quadro_do_projeto(rastro: str, projeto: Path) -> dict[str, Any] | None:
    """O último quadro cujo arquivo é deste projeto — não da biblioteca padrão.

    O último quadro costuma ser o da stdlib (`json/decoder.py`); o que interessa é
    o último arquivo nosso que apareceu no caminho do erro.
    """
    quadros = re.findall(r'File "([^"]+)", line (\d+), in (\S+)', rastro or "")
    escolhido: dict[str, Any] | None = None
    for caminho, linha, funcao in quadros:
        puro = Path(caminho.replace("\\", "/"))
        partes = puro.parts
        if "site-packages" in partes or puro.suffix != ".py":
            continue
        relat = caminho.replace("\\", "/")
        if "server/" in relat or relat.startswith("server/"):
            escolhido = {"arquivo": relat[relat.index("server/"):], "linha": int(linha), "funcao": funcao}
    return escolhido


def _trecho(projeto: Path, arquivo: str, linha: int, redor: int = 4) -> list[dict[str, Any]]:
    caminho = projeto / arquivo
    try:
        linhas = caminho.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    inicio = max(1, linha - redor)
    fim = min(len(linhas), linha + redor)
    return [
        {"numero": numero, "texto": linhas[numero - 1][:300], "foco": numero == linha}
        for numero in range(inicio, fim + 1)
    ]


def _teste_do_modulo(projeto: Path, arquivo: str) -> dict[str, Any]:
    """Existe teste para esse módulo? Quantos? É o que decide se dá para ensaiar."""
    nome = Path(arquivo).stem
    alvo = projeto / "server" / "tests" / f"test_{nome}.py"
    if not alvo.is_file():
        return {"existe": False, "arquivo": f"server/tests/test_{nome}.py", "testes": 0,
                "aviso": "Sem teste de mesmo nome: o ensaio da suíte pode passar sem cobrir justamente esse caminho."}
    try:
        texto = alvo.read_text(encoding="utf-8")
    except OSError:
        return {"existe": True, "arquivo": f"server/tests/test_{nome}.py", "testes": 0, "aviso": ""}
    return {
        "existe": True,
        "arquivo": f"server/tests/test_{nome}.py",
        "testes": len(re.findall(r"^def test_", texto, re.M)),
        "aviso": "",
    }


GUARDAS_QUE_O_PATCH_NAO_PODE_QUEBRAR = (
    "skill de leitura continua devolvendo `executed: false`",
    "caminho confinado: sem `..`, sem caminho absoluto vindo do usuário",
    "subprocesso sempre com `shell=False` e lista de argumentos",
    "token de host não é impresso nem devolvido por HTTP",
    "efeito colateral declarado em `side_effects=True` e confirmação exigida",
    "nenhum segredo embutido no código",
)


def diagnosticar(
    *,
    erro: str = "",
    projeto: Path | None = None,
    raiz: Path | None = None,
    registro: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lê um erro (colado ou do diário) e diz onde, o quê e por quê."""
    raiz_projeto = Path(projeto) if projeto is not None else Path(__file__).resolve().parents[1]
    fonte = "colado"
    dados: dict[str, Any] = {"skill": "", "tipo": "", "mensagem": "", "rastro": ""}
    if (erro or "").strip():
        dados["rastro"] = erro.strip()[-MAX_ERRO:]
        # `json.decoder.JSONDecodeError: ...` também é exceção — o nome pode vir
        # qualificado, e o `\w+` antigo parava no primeiro ponto.
        achado = re.search(
            r"^((?:\w+\.)*[A-Za-z_]*(?:Error|Exception|Interrupt|Exit))\s*:\s*(.*)$",
            dados["rastro"],
            re.M,
        )
        if achado:
            dados["tipo"] = achado.group(1)
            dados["mensagem"] = achado.group(2).strip()[:1_000]
    else:
        fonte = "diário"
        bruto = registro or _ultimo_bruto(raiz)
        if not bruto:
            return {
                "lido": False,
                "fonte": fonte,
                "motivo": (
                    "Não há erro no diário (`storage/erros.jsonl`) e você não colou nenhum. "
                    "O diário só registra falha interna de skill — erro de digitação não entra."
                ),
            }
        dados = bruto  # type: ignore[assignment]

    quadro = _quadro_do_projeto(str(dados.get("rastro") or ""), raiz_projeto)
    causa = _causa(str(dados.get("tipo") or ""), str(dados.get("mensagem") or ""))
    trecho = _trecho(raiz_projeto, quadro["arquivo"], quadro["linha"]) if quadro else []
    teste = _teste_do_modulo(raiz_projeto, quadro["arquivo"]) if quadro else {"existe": False, "arquivo": "", "testes": 0, "aviso": ""}
    return {
        "lido": True,
        "fonte": fonte,
        "quando": dados.get("quando", ""),
        "skill": dados.get("skill", ""),
        "excecao": {"tipo": dados.get("tipo", ""), "mensagem": dados.get("mensagem", "")},
        "onde": quadro or {},
        "trecho": trecho,
        "causa": causa,
        "teste": teste,
        "guardas": list(GUARDAS_QUE_O_PATCH_NAO_PODE_QUEBRAR),
        "proximo": (
            "Com o trecho e a causa, o passo é um diff: `conserto.dossie` monta o texto para "
            "um modelo (ou para você), `evoluir.ensaiar` testa na cópia e `evoluir.promover` aplica."
            if quadro
            else "O traceback não cita arquivo deste projeto: pode ser dependência, dado de entrada ou rede. O dossiê ainda ajuda."
        ),
    }


def dossie(
    *,
    erro: str = "",
    projeto: Path | None = None,
    raiz: Path | None = None,
    registro: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """O texto que faz a correção sair em uma tentativa: erro, código, teste, limites."""
    achado = diagnosticar(erro=erro, projeto=projeto, raiz=raiz, registro=registro)
    if not achado.get("lido"):
        return {**achado, "texto": "", "bytes": 0}

    raiz_projeto = Path(projeto) if projeto is not None else Path(__file__).resolve().parents[1]
    linhas: list[str] = ["# Dossiê de conserto — JARVIS", ""]
    linhas.append(f"- versão: {VERSAO}")
    linhas.append(f"- skill que falhou: {achado.get('skill') or 'não registrada'}")
    linhas.append(f"- exceção: {achado['excecao']['tipo']}: {achado['excecao']['mensagem']}")
    if achado["onde"]:
        linhas.append(f"- arquivo: `{achado['onde']['arquivo']}` linha {achado['onde']['linha']} (função `{achado['onde']['funcao']}`)")
    linhas.append(f"- causa classificada: **{achado['causa']['codigo']}** — {achado['causa']['significa']}")
    linhas.append(f"- o que costuma resolver: {achado['causa']['o_que_fazer']}")
    linhas.append(f"- teste do módulo: `{achado['teste'].get('arquivo') or 'nenhum'}` ({achado['teste'].get('testes', 0)} testes)")
    if achado["teste"].get("aviso"):
        linhas.append(f"- atenção: {achado['teste']['aviso']}")
    linhas.append("")
    linhas.append("## Guardas que o patch não pode quebrar")
    for guarda in achado["guardas"]:
        linhas.append(f"- {guarda}")
    linhas.append("")
    if achado["trecho"]:
        linhas.append("## Código em volta da linha")
        linhas.append("```python")
        for item in achado["trecho"]:
            marca = ">>" if item["foco"] else "  "
            linhas.append(f"{marca} {item['numero']:>4} | {item['texto']}")
        linhas.append("```")
        linhas.append("")

    # Documento de contexto: a docstring do módulo diz para que ele serve, e é o
    # “procurar para que serve” que o pedido citava — sem inventar nada.
    if achado["onde"]:
        module_path = raiz_projeto / achado["onde"]["arquivo"]
        try:
            inicio = module_path.read_text(encoding="utf-8")[:4_000]
        except OSError:
            inicio = ""
        doc = re.match(r'\s*"""(.*?)"""', inicio, re.S)
        if doc:
            linhas.append("## Para que serve este módulo (docstring do próprio arquivo)")
            linhas.append("```")
            linhas.append(doc.group(1).strip()[:2_000])
            linhas.append("```")
            linhas.append("")

    linhas.append("## Como devolver a correção")
    linhas.append("Um diff unificado completo, com `--- a/<arquivo>` e `+++ b/<arquivo>`, só o necessário.")
    linhas.append("O próximo passo é `evoluir.ensaiar` (roda a suíte real numa cópia) e depois `evoluir.promover`.")

    texto = "\n".join(linhas)[:MAX_DOSSIE]
    return {
        **achado,
        "texto": texto,
        "bytes": len(texto.encode("utf-8")),
    }


# ---------------------------------------------------------------------------
# Propor (só com chave de IA)
# ---------------------------------------------------------------------------

_PROMPT = (
    "Você conserta código Python de um projeto pessoal. Receba um dossiê com um erro real, "
    "o trecho do código e as guardas do projeto. Devolva **somente** um diff unificado "
    "completo, no formato `--- a/arquivo` / `+++ b/arquivo` com hunks `@@ -a,b +c,d @@`, "
    "aplicável com `patch -p1`. Não invente arquivo novo, não reformate o arquivo inteiro, "
    "não toque em nada fora do que o erro exige. Se o erro não for de código (permissão, "
    "rede, dado de entrada), responda exatamente: SEM PATCH — e o motivo em uma linha."
)


def extrair_diff(resposta: str) -> str:
    """Pega o diff da resposta do modelo, com ou sem cerca de código."""
    texto = (resposta or "").strip()
    cerca = re.search(r"```(?:diff|patch)?\s*\n(.*?)```", texto, re.S)
    if cerca:
        texto = cerca.group(1)
    linhas = [linha for linha in texto.splitlines() if not linha.startswith(("```", "~~~"))]
    return "\n".join(linhas).strip()


def propor(
    *,
    erro: str = "",
    projeto: Path | None = None,
    raiz: Path | None = None,
    provedor: Any | None = None,
    autorizacao: str = "",
    registrar: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Pede o diff a um modelo e devolve **validado** — sem escrever nada.

    Sem chave, recusa em vez de fingir: é o mesmo contrato de `distilar_ia`.
    """
    montado = dossie(erro=erro, projeto=projeto, raiz=raiz)
    if not montado.get("lido"):
        return montado
    if provedor is None:
        try:
            from .ai import OpenAICompatibleProvider  # noqa: PLC0415

            provedor = OpenAICompatibleProvider()
        except Exception:  # pragma: no cover - import defensivo
            provedor = None
    if provedor is None or not getattr(provedor, "configured", False):
        return {
            "lido": True,
            "proposto": False,
            "motivo": (
                "Sem chave de IA configurada, eu não escrevo o patch — inventar correção é pior "
                "que não corrigir. O dossiê abaixo é o que um modelo precisa para acertar de primeira."
            ),
            "dossie": montado["texto"],
        }

    import asyncio  # noqa: PLC0415

    from .ai import AIRequest  # noqa: PLC0415

    pedido = AIRequest(message=_PROMPT, material=montado["texto"][:MAX_ARQUIVO_DOSSIE], max_tokens=2_000)
    try:
        resposta = asyncio.run(provedor.generate(pedido))
    except Exception as exc:  # rede, cota, chave inválida
        return {"lido": True, "proposto": False, "motivo": f"O provedor não respondeu: {type(exc).__name__}."}

    if "SEM PATCH" in resposta.upper():
        motivo = resposta.replace("SEM PATCH", "").strip(" —:-") or "o modelo disse que não é erro de código."
        return {"lido": True, "proposto": False, "motivo": motivo, "dossie": montado["texto"]}

    diff = extrair_diff(resposta)
    if not diff:
        return {"lido": True, "proposto": False, "motivo": "O modelo respondeu sem diff reconhecível."}

    # A validação é da camada de evolução, não daqui: uma verdade só.
    from . import evolucao  # noqa: PLC0415

    try:
        arquivos = evolucao.ler_diff(diff)
    except Exception as exc:
        return {"lido": True, "proposto": False, "motivo": f"O diff não é aplicável: {exc}", "diff": diff}
    # Risco e guardas são a mesma régua do `evoluir.*` e exigem o mesmo token:
    # um diff sem essa checagem seria uma segunda verdade sobre segurança.
    try:
        risco = evolucao.risco(diff=diff, autorizacao=autorizacao)
        guardas = evolucao.guardas(diff=diff, autorizacao=autorizacao)
    except evolucao.EvolucaoError as exc:
        return {
            "lido": True,
            "proposto": True,
            "diff": diff,
            "arquivos": [item.caminho for item in arquivos],
            "validado": False,
            "motivo": f"Diff lido, mas a régua de risco não rodou: {exc}",
        }
    return {
        "lido": True,
        "proposto": True,
        "validado": True,
        "diff": diff,
        "arquivos": [item.caminho for item in arquivos],
        "risco": {"nivel": risco.get("nivel"), "pontos": risco.get("pontos")},
        "guardas": {"violadas": [g.get("codigo") for g in guardas.get("resultados", []) if g.get("estado") == "viola"]},
        "proximo": "`evoluir.ensaiar` roda a suíte real numa cópia com este diff. Nada foi escrito ainda.",
    }
