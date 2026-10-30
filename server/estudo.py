"""Estudo com repetição espaçada — local, determinístico, sem modelo.

A ideia veio de fora, e vale dizer de onde: o **DeepTutor** (HKUDS) trata
aprendizado como um laço — material, pergunta, resposta, retorno — em vez de
“explique isto” uma vez e esquecer. O que sobrevive aqui, sem GPU e sem chave, é
o laço de repetição espaçada: cada cartão guarda quando deve voltar, e volta
antes de ser esquecido.

Três peças, todas determinísticas:

1. **Cartões a partir de texto.** O material que você já tem (resumo, capítulo,
   anotação) vira pergunta/resposta por três padrões explícitos:
   definição (“X é Y”), verbete (“Termo — definição”, “**Termo**: …”) e título
   com o primeiro parágrafo. Nada de resumir com modelo: o que não casa com os
   padrões é descartado, e o relatório diz quantas linhas foram ignoradas.
2. **Agenda SM-2.** Cada resposta vira uma nota de 0 a 5; a nota mexe na
   facilidade do cartão e no intervalo até a próxima revisão. Cartão errado volta
   amanhã; cartão fácil some por semanas. É o mesmo algoritmo do SuperMemo 2,
   sem biblioteca externa.
3. **Boletim.** Retenção (acertos ÷ respostas), cartões vencidos, o que mais
   erra e a sequência de dias estudados. Números medidos, não elogio.

Limites ditos na cara: o arquivo é `estudo.json` na raiz de dados; nada sai da
máquina; e o JARVIS não tem serviço em segundo plano — o que vence aparece
quando você abre a tela.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from . import dados as dados_locais

VERSAO = "0.64.0"

ARQUIVO = "estudo.json"
MAX_BARALHOS = 60
MAX_CARTOES_POR_BARALHO = 2_000
MAX_TEXTO = 200_000
MAX_FRENTE = 300
MAX_VERSO = 2_000
MAX_GERADOS = 60

# SM-2: facilidade mínima e o quanto cada nota mexe nela.
FACILIDADE_MIN = 1.3
FACILIDADE_PADRAO = 2.5
NOTA_MIN, NOTA_MAX = 0, 5
# Notas por nome — é o que a tela manda, para ninguém decorar número.
NOTAS = {
    "errei": 0,
    "dificil": 3,
    "difícil": 3,
    "bom": 4,
    "facil": 5,
    "fácil": 5,
}
ROTULO_NOTA = {0: "errei", 3: "difícil", 4: "bom", 5: "fácil"}


class EstudoError(ValueError):
    """Erro esperado do estudo, seguro para o usuário."""


# ------------------------------------------------------------------ armazenamento


def _raiz(raiz: Path | None) -> Path:
    return Path(raiz) if raiz is not None else Path(dados_locais.raiz())


def _arquivo(raiz: Path | None = None) -> Path:
    return _raiz(raiz) / ARQUIVO


def _agora(agora: datetime | None) -> datetime:
    return agora.replace(microsecond=0) if agora is not None else datetime.now().replace(microsecond=0)


def _vazio() -> dict[str, Any]:
    return {"versao": VERSAO, "baralhos": {}, "historico": []}


def carregar(raiz: Path | None = None) -> dict[str, Any]:
    """Lê o arquivo. Arquivo ausente ou corrompido vira estudo vazio, não exceção."""
    caminho = _arquivo(raiz)
    if not caminho.exists():
        return _vazio()
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _vazio()
    if not isinstance(dados, dict):
        return _vazio()
    baralhos = dados.get("baralhos")
    if not isinstance(baralhos, dict):
        baralhos = {}
    limpos: dict[str, Any] = {}
    for chave, baralho in baralhos.items():
        if not isinstance(baralho, dict):
            continue
        cartoes = [c for c in baralho.get("cartoes") or [] if isinstance(c, dict) and c.get("id")]
        limpos[str(chave)] = {
            "nome": str(baralho.get("nome") or chave)[:120],
            "criado": str(baralho.get("criado") or ""),
            "cartoes": cartoes[:MAX_CARTOES_POR_BARALHO],
        }
    historico = [h for h in dados.get("historico") or [] if isinstance(h, dict)]
    return {"versao": VERSAO, "baralhos": limpos, "historico": historico[-5_000:]}


def _salvar(raiz: Path | None, estado: dict[str, Any]) -> None:
    caminho = _arquivo(raiz)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    temporario.replace(caminho)


# ------------------------------------------------------------------ texto


def _sem_acento(texto: str) -> str:
    """Minúsculo e sem acento — para comparar, nunca para mostrar."""
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def _limpar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def _slug(nome: str) -> str:
    base = _sem_acento(nome)
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return (base or "baralho")[:48]


def _id(frente: str, nome: str) -> str:
    """Id estável: o mesmo cartão no mesmo baralho não duplica."""
    return hashlib.sha1((_sem_acento(nome) + "|" + _sem_acento(frente)).encode("utf-8")).hexdigest()[:12]


# ------------------------------------------------------------------ geração de cartões

# "Direito civil é o ramo que ..." -> pergunta pela definição.
_RE_DEFINICAO = re.compile(
    r"^(?P<termo>[A-ZÁÉÍÓÚÂÊÔÃÕÇ][^.!?]{2,80}?)\s+(?P<verbo>é|são|significa|consiste em|refere-se a|designa|corresponde a)\s+(?P<corpo>.{15,600})$"
)
# "**Termo**: definição" / "- Termo — definição" / "Termo: definição"
_RE_VERBETE = re.compile(
    r"^\s*(?:[-*+]\s+)?(?:\*\*|__)?(?P<termo>[^*_:\u2014-]{3,80}?)(?:\*\*|__)?\s*(?::|\s[\u2014-]\s|\s-\s)\s*(?P<corpo>.{15,600})$"
)
# Título de seção.
_RE_TITULO = re.compile(r"^\s{0,3}#{1,4}\s+(?P<titulo>.{3,120})$")
_RE_NAO_TEXTO = re.compile(r"^(?:https?://|!\[|\||```|<|\[[^\]]*\]\()")


def cartoes_de_texto(texto: str, *, maximo: int = MAX_GERADOS) -> dict[str, Any]:
    """Transforma material em candidatos de cartão, sem modelo.

    Devolve `cartoes` (frente, verso, tipo) e `ignoradas` — quantas linhas com
    conteúdo não casaram com nenhum padrão. Esse número é a honestidade da
    função: se 90% do texto é ignorado, ele não serve para virar cartão.
    """
    if not isinstance(texto, str) or not texto.strip():
        raise EstudoError("Escreva o material: um resumo, um capítulo, uma anotação.")
    if len(texto) > MAX_TEXTO:
        raise EstudoError(f"O material passa de {MAX_TEXTO} caracteres. Divida em partes.")
    limite = max(1, min(int(maximo), MAX_GERADOS))

    cartoes: list[dict[str, str]] = []
    vistos: set[str] = set()
    ignoradas = 0
    linhas = texto.splitlines()
    titulo_pendente = ""

    def adicionar(frente: str, verso: str, tipo: str) -> None:
        # "Posse: é o exercício..." vira verso "o exercício..." — o "é" já está
        # na pergunta, repetir no verso só atrapalha a leitura.
        verso = re.sub(r"^(?:é|são|consiste em|refere-se a|designa)\s+", "", verso.strip())
        chave = _sem_acento(_limpar(frente))
        if not chave or chave in vistos:
            return
        vistos.add(chave)
        cartoes.append({"frente": frente[:MAX_FRENTE], "verso": verso[:MAX_VERSO], "tipo": tipo})

    for bruta in linhas:
        linha = bruta.strip()
        if not linha:
            continue
        if _RE_NAO_TEXTO.match(linha):
            continue

        titulo = _RE_TITULO.match(linha)
        if titulo:
            titulo_pendente = _limpar(titulo.group("titulo"))
            continue

        if len(linha) < 20:
            continue

        achou = False

        definicao = _RE_DEFINICAO.match(linha)
        if definicao and len(cartoes) < limite:
            termo = _limpar(definicao.group("termo"))
            verbo = definicao.group("verbo")
            # Termo de verdade é curto: "Direito civil", "Posse". Frase longa
            # com "porque é" no meio vira pergunta sem sentido, então sai fora.
            if len(termo.split()) <= 6:
                adicionar(f"O que {verbo} {termo}?", _limpar(linha), "definicao")
                achou = True

        if not achou and len(cartoes) < limite:
            verbete = _RE_VERBETE.match(linha)
            if verbete:
                termo = _limpar(verbete.group("termo"))
                corpo = _limpar(verbete.group("corpo"))
                if len(termo.split()) <= 8 and len(corpo) >= 15:
                    adicionar(f"O que é {termo}?", corpo, "verbete")
                    achou = True

        if not achou and titulo_pendente and len(cartoes) < limite:
            # Título seguido do PRIMEIRO parágrafo: a primeira frase é a resposta.
            # Só o primeiro — senão o título gruda em parágrafo de outro assunto.
            frase = _limpar(re.split(r"(?<=[.!?])\s", linha)[0])
            if len(frase) >= 30:
                adicionar(
                    f"Segundo o material, o que se diz sobre {titulo_pendente}?",
                    frase[:MAX_VERSO],
                    "titulo",
                )
                achou = True
        titulo_pendente = ""

        if not achou and len(linha) >= 40:
            ignoradas += 1

        if len(cartoes) >= limite:
            break

    if not cartoes:
        raise EstudoError(
            "Nenhum cartão saiu deste texto. Ele precisa de frases do tipo "
            "“X é Y” ou de verbetes “Termo: definição”. Escreva um cartão à mão."
        )
    return {
        "cartoes": cartoes[:limite],
        "gerados": len(cartoes[:limite]),
        "ignoradas": ignoradas,
        "tipos": sorted({c["tipo"] for c in cartoes[:limite]}),
        "aviso": (
            "Cartão gerado por padrão de frase, não por modelo: confira o verso "
            "antes de estudar por ele."
        ),
    }


# ------------------------------------------------------------------ baralhos


def _baralho(estado: dict[str, Any], chave: str) -> dict[str, Any]:
    baralho = estado["baralhos"].get(chave)
    if not baralho:
        raise EstudoError(f'Não existe o baralho "{chave}". Veja os que existem em estudo.progresso.')
    return baralho


def _resolver_chave(estado: dict[str, Any], nome: str) -> str:
    """Aceita o id do baralho ou o nome, sem exigir que a pessoa lembre o slug."""
    if not nome:
        return ""
    if nome in estado["baralhos"]:
        return nome
    alvo = _sem_acento(nome)
    for chave, baralho in estado["baralhos"].items():
        if _sem_acento(baralho["nome"]) == alvo:
            return chave
    candidatos = [c for c, b in estado["baralhos"].items() if alvo in _sem_acento(b["nome"])]
    if len(candidatos) == 1:
        return candidatos[0]
    return nome.lower()


def baralhos(raiz: Path | None = None) -> list[dict[str, Any]]:
    """Lista os baralhos com o que vence hoje — sem carregar cartão na tela."""
    estado = carregar(raiz)
    hoje = date.today().isoformat()
    saida = []
    for chave, baralho in sorted(estado["baralhos"].items()):
        cartoes = baralho["cartoes"]
        vencidos = [c for c in cartoes if str(c.get("vence") or hoje) <= hoje]
        saida.append(
            {
                "baralho": chave,
                "nome": baralho["nome"],
                "cartoes": len(cartoes),
                "vencidos": len(vencidos),
                "novos": sum(1 for c in cartoes if int(c.get("reps") or 0) == 0),
                "criado": baralho.get("criado", ""),
            }
        )
    return saida


def criar(nome: str, *, raiz: Path | None = None, agora: datetime | None = None) -> dict[str, Any]:
    """Cria (ou reaproveita) um baralho pelo nome."""
    limpo = _limpar(nome or "")
    if len(limpo) < 2:
        raise EstudoError("Dê um nome ao baralho, com pelo menos 2 letras.")
    estado = carregar(raiz)
    chave = _slug(limpo)
    if chave in estado["baralhos"]:
        return {"baralho": chave, "nome": estado["baralhos"][chave]["nome"], "criado": False}
    if len(estado["baralhos"]) >= MAX_BARALHOS:
        raise EstudoError(f"Já existem {MAX_BARALHOS} baralhos. Apague um antes de criar outro.")
    estado["baralhos"][chave] = {"nome": limpo[:120], "criado": _agora(agora).isoformat(), "cartoes": []}
    _salvar(raiz, estado)
    return {"baralho": chave, "nome": limpo, "criado": True}


def adicionar(
    baralho: str,
    *,
    texto: str = "",
    frente: str = "",
    verso: str = "",
    raiz: Path | None = None,
    agora: datetime | None = None,
) -> dict[str, Any]:
    """Põe cartões no baralho: de um texto, de um par frente/verso, ou dos dois.

    Cartão que já existe (mesma frente, mesmo baralho) não entra de novo — o
    relatório diz quantos foram pulados em vez de duplicar em silêncio.
    """
    estado = carregar(raiz)
    chave = _resolver_chave(estado, baralho)
    if chave not in estado["baralhos"]:
        criado = criar(baralho, raiz=raiz, agora=agora)
        chave = criado["baralho"]
        estado = carregar(raiz)
    alvo = _baralho(estado, chave)

    hoje = _agora(agora).date().isoformat()
    candidatos: list[dict[str, str]] = []
    relatorio: dict[str, Any] = {"gerados": 0, "ignoradas": 0}

    if texto.strip():
        gerado = cartoes_de_texto(texto)
        candidatos.extend(gerado["cartoes"])
        relatorio = {"gerados": gerado["gerados"], "ignoradas": gerado["ignoradas"]}

    if frente.strip() or verso.strip():
        if len(frente.strip()) < 2 or len(verso.strip()) < 1:
            raise EstudoError("Cartão à mão precisa de frente e verso — frente com 2 letras ou mais.")
        candidatos.append(
            {"frente": _limpar(frente)[:MAX_FRENTE], "verso": _limpar(verso)[:MAX_VERSO], "tipo": "manual"}
        )

    if not candidatos:
        raise EstudoError("Nada para adicionar: mande um texto ou um par frente/verso.")

    existentes = {str(c.get("id")) for c in alvo["cartoes"]}
    novos = 0
    pulados = 0
    for candidato in candidatos:
        ident = _id(candidato["frente"], alvo["nome"])
        if ident in existentes:
            pulados += 1
            continue
        if len(alvo["cartoes"]) >= MAX_CARTOES_POR_BARALHO:
            raise EstudoError(f'O baralho chegou a {MAX_CARTOES_POR_BARALHO} cartões.')
        alvo["cartoes"].append(
            {
                "id": ident,
                "frente": candidato["frente"],
                "verso": candidato["verso"],
                "tipo": candidato.get("tipo", "manual"),
                "criado": _agora(agora).isoformat(),
                "reps": 0,
                "facilidade": FACILIDADE_PADRAO,
                "intervalo": 0,
                "vence": hoje,
                "acertos": 0,
                "erros": 0,
            }
        )
        existentes.add(ident)
        novos += 1

    _salvar(raiz, estado)
    return {
        "baralho": chave,
        "nome": alvo["nome"],
        "adicionados": novos,
        "pulados": pulados,
        "total": len(alvo["cartoes"]),
        "ignoradas": relatorio.get("ignoradas", 0),
        "aviso": relatorio.get("aviso", ""),
    }


# ------------------------------------------------------------------ SM-2


def _nota(valor: Any) -> int:
    if isinstance(valor, str):
        chave = _sem_acento(valor).strip()
        if chave in NOTAS:
            return NOTAS[chave]
        if chave in {"0", "1", "2", "3", "4", "5"}:
            return int(chave)
        raise EstudoError('Nota inválida. Use "errei", "difícil", "bom", "fácil" ou 0 a 5.')
    try:
        numero = int(valor)
    except (TypeError, ValueError) as exc:
        raise EstudoError('Nota inválida. Use "errei", "difícil", "bom", "fácil" ou 0 a 5.') from exc
    if not NOTA_MIN <= numero <= NOTA_MAX:
        raise EstudoError(f"A nota vai de {NOTA_MIN} a {NOTA_MAX}.")
    return numero


def agendar(cartao: dict[str, Any], nota: int, hoje: date) -> dict[str, Any]:
    """Aplica o SM-2 e devolve o cartão novo. Função pura — fácil de testar."""
    facilidade = float(cartao.get("facilidade") or FACILIDADE_PADRAO)
    intervalo = int(cartao.get("intervalo") or 0)
    reps = int(cartao.get("reps") or 0)

    if nota < 3:
        reps = 0
        intervalo = 1
    else:
        if reps == 0:
            intervalo = 1
        elif reps == 1:
            intervalo = 6
        else:
            intervalo = max(1, int(round(intervalo * facilidade)))
        reps += 1

    # SM-2 puro: a nota mexe na facilidade em qualquer resposta.
    delta = 0.1 - (5 - nota) * (0.08 + (5 - nota) * 0.02)
    facilidade = max(FACILIDADE_MIN, round(facilidade + delta, 2))

    novo = dict(cartao)
    novo["facilidade"] = facilidade
    novo["intervalo"] = intervalo
    novo["reps"] = reps
    novo["vence"] = (hoje + timedelta(days=intervalo)).isoformat()
    novo["acertos"] = int(cartao.get("acertos") or 0) + (1 if nota >= 3 else 0)
    novo["erros"] = int(cartao.get("erros") or 0) + (0 if nota >= 3 else 1)
    return novo


def _hoje(agora: datetime | None) -> date:
    return _agora(agora).date()


def revisar(
    baralho: str = "",
    *,
    limite: int = 20,
    raiz: Path | None = None,
    agora: datetime | None = None,
    incluir_futuros: bool = False,
) -> dict[str, Any]:
    """O que estudar agora: cartões vencidos, do mais atrasado para o menos."""
    estado = carregar(raiz)
    hoje = _hoje(agora).isoformat()
    limite = max(1, min(int(limite), 100))

    chaves = [baralho] if baralho else list(estado["baralhos"])
    if baralho:
        resolvida = _resolver_chave(estado, baralho)
        if resolvida not in estado["baralhos"]:
            existentes = ", ".join(sorted(estado["baralhos"])) or "nenhum ainda"
            raise EstudoError(
                f'Não existe o baralho "{baralho}". Existem: {existentes}. '
                "Veja os números em estudo.progresso."
            )
        chaves = [resolvida]

    pendentes: list[dict[str, Any]] = []
    for chave in chaves:
        for cartao in estado["baralhos"][chave]["cartoes"]:
            vence = str(cartao.get("vence") or hoje)
            if incluir_futuros or vence <= hoje:
                pendentes.append({**cartao, "baralho": chave, "vencido_ha": _dias(vence, hoje)})

    pendentes.sort(key=lambda c: (c["vencido_ha"] * -1, -int(c.get("erros") or 0)))
    escolhidos = pendentes[:limite]
    return {
        "hoje": hoje,
        "total_vencidos": len(pendentes),
        "mostrando": len(escolhidos),
        "cartoes": [
            {
                "id": c["id"],
                "baralho": c["baralho"],
                "frente": c["frente"],
                "verso": c["verso"],
                "tipo": c.get("tipo", ""),
                "vencido_ha": c["vencido_ha"],
                "erros": int(c.get("erros") or 0),
                "reps": int(c.get("reps") or 0),
            }
            for c in escolhidos
        ],
        "restantes": len(pendentes) - len(escolhidos),
        "notas": [{"nota": n, "rotulo": ROTULO_NOTA[n]} for n in (0, 3, 4, 5)],
    }


def _dias(vence: str, hoje: str) -> int:
    try:
        return (date.fromisoformat(hoje) - date.fromisoformat(vence)).days
    except ValueError:
        return 0


def responder(
    cartao_id: str,
    nota: Any,
    *,
    raiz: Path | None = None,
    agora: datetime | None = None,
) -> dict[str, Any]:
    """Registra a resposta de um cartão e devolve quando ele volta."""
    estado = carregar(raiz)
    valor = _nota(nota)
    momento = _agora(agora)

    for chave, baralho in estado["baralhos"].items():
        for indice, cartao in enumerate(baralho["cartoes"]):
            if cartao.get("id") != cartao_id:
                continue
            novo = agendar(cartao, valor, momento.date())
            baralho["cartoes"][indice] = novo
            estado["historico"].append(
                {"quando": momento.isoformat(), "baralho": chave, "cartao": cartao_id, "nota": valor}
            )
            _salvar(raiz, estado)
            return {
                "cartao": cartao_id,
                "baralho": chave,
                "nota": valor,
                "rotulo": ROTULO_NOTA.get(valor, str(valor)),
                "intervalo_dias": novo["intervalo"],
                "volta_em": novo["vence"],
                "facilidade": novo["facilidade"],
                "reps": novo["reps"],
            }

    raise EstudoError("Não achei esse cartão. Ele pode ter vindo de outro baralho — abra o que vence hoje de novo.")


# ------------------------------------------------------------------ boletim


def progresso(*, raiz: Path | None = None, agora: datetime | None = None) -> dict[str, Any]:
    """Boletim medido: retenção, vencidos, o que mais erra e dias seguidos."""
    estado = carregar(raiz)
    hoje = _hoje(agora)
    hoje_iso = hoje.isoformat()

    total = 0
    vencidos = 0
    novos = 0
    acertos = 0
    erros = 0
    por_baralho = []
    fracos: list[dict[str, Any]] = []

    for chave, baralho in sorted(estado["baralhos"].items()):
        cartoes = baralho["cartoes"]
        total += len(cartoes)
        v_baralho = sum(1 for c in cartoes if str(c.get("vence") or hoje_iso) <= hoje_iso)
        vencidos += v_baralho
        novos += sum(1 for c in cartoes if int(c.get("reps") or 0) == 0)
        a = sum(int(c.get("acertos") or 0) for c in cartoes)
        e = sum(int(c.get("erros") or 0) for c in cartoes)
        acertos += a
        erros += e
        por_baralho.append(
            {
                "baralho": chave,
                "nome": baralho["nome"],
                "cartoes": len(cartoes),
                "vencidos": v_baralho,
                "retencao": _retencao(a, e),
            }
        )
        for c in cartoes:
            if int(c.get("erros") or 0) >= 2:
                fracos.append(
                    {
                        "id": c["id"],
                        "baralho": chave,
                        "frente": c["frente"],
                        "erros": int(c.get("erros") or 0),
                    }
                )

    fracos.sort(key=lambda c: -c["erros"])
    dias = sorted({str(h.get("quando", ""))[:10] for h in estado["historico"] if h.get("quando")})
    return {
        "hoje": hoje_iso,
        "baralhos": por_baralho,
        "cartoes": total,
        "vencidos": vencidos,
        "novos": novos,
        "respostas": acertos + erros,
        "acertos": acertos,
        "erros": erros,
        "retencao": _retencao(acertos, erros),
        "sequencia_dias": _sequencia(dias, hoje),
        "dias_estudados": len(dias),
        "fracos": fracos[:10],
        "aviso": "" if total else "Nenhum cartão ainda: crie um baralho e cole o material.",
    }


def _retencao(acertos: int, erros: int) -> int:
    total = acertos + erros
    if not total:
        return 0
    return int(round(100 * acertos / total))


def _sequencia(dias: list[str], hoje: date) -> int:
    """Dias seguidos com pelo menos uma resposta, contando de hoje para trás."""
    if not dias:
        return 0
    conjunto = set(dias)
    cursor = hoje
    if cursor.isoformat() not in conjunto:
        cursor = cursor - timedelta(days=1)
        if cursor.isoformat() not in conjunto:
            return 0
    total = 0
    while cursor.isoformat() in conjunto:
        total += 1
        cursor = cursor - timedelta(days=1)
    return total


def resumo(dados: dict[str, Any]) -> str:
    """Uma linha para o chat: o que fazer agora, sem enfeite."""
    if not dados.get("cartoes"):
        return "Nenhum cartão ainda. Crie um baralho e cole um resumo para virar cartão."
    if dados.get("vencidos"):
        return (
            f"{dados['vencidos']} de {dados['cartoes']} cartões vencidos; "
            f"retenção {dados['retencao']}% em {dados['respostas']} respostas."
        )
    return f"Nada vencido. {dados['cartoes']} cartões em dia, retenção {dados['retencao']}%."


def novo_id() -> str:
    """Id curto para uso externo (testes, importação)."""
    return secrets.token_hex(6)
