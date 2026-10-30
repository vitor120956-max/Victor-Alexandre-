"""Agenda de compromissos e prazos — local, sem conta e sem modelo.

O pedido: *“quero que ele guarde o que eu tenho para tal dia e me avise quando eu
perguntar”*. Não é calendário na nuvem: é um arquivo JSON na raiz de dados, com
data interpretada de forma **determinística** e sempre mostrada de volta para
conferência.

A regra de ouro desta camada: **nunca adivinhar data em silêncio.** Se a frase
não disser uma data reconhecível, ele recusa e pede — em vez de marcar no dia
errado. Quando reconhece, devolve o que entendeu por extenso:

    “marca audiência amanhã às 14h”  →  “sexta-feira, 30/10/2026 às 14:00”

Formatos aceitos (todos sem modelo):
- data: `2026-11-05`, `05/11/2026`, `05/11`, `hoje`, `amanhã`, `depois de amanhã`,
  `daqui a N dias`, e os dias da semana (`segunda`…`domingo`, sempre o próximo);
- hora: `às 14h`, `14h30`, `14:30`, `14 horas`; sem hora, o compromisso fica às 09:00.

O arquivo é `agenda.json`; cada item tem id curto, título, quando (ISO), nota,
status (`aberto`/`concluido`) e quando foi criado. Nada sai da máquina.

**Lembretes (0.60.3).** Cada item guarda por quantos minutos antes avisar
(`avisar_antes`, 30 por padrão; 0 desliga). `devidos()` responde “o que precisa
de atenção agora”: o que já passou e o que chega dentro da janela. Quem mostra é
a tela — o JARVIS não tem serviço em segundo plano, então o aviso aparece
enquanto a janela estiver aberta. Essa limitação é dita, não escondida.
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from . import dados as dados_locais

VERSAO = "0.62.4"

ARQUIVO = "agenda.json"
MAX_ITENS = 2_000
MAX_TITULO = 200
MAX_NOTA = 2_000
HORA_PADRAO = (9, 0)
ANTECEDENCIA_PADRAO = 30
MAX_ANTECEDENCIA = 60 * 24 * 30

# 0 = segunda … 6 = domingo (o mesmo de `datetime.weekday()`)
DIAS_SEMANA = {
    "segunda": 0,
    "segunda-feira": 0,
    "terca": 1,
    "terça": 1,
    "terca-feira": 1,
    "terça-feira": 1,
    "quarta": 2,
    "quarta-feira": 2,
    "quinta": 3,
    "quinta-feira": 3,
    "sexta": 4,
    "sexta-feira": 4,
    "sabado": 5,
    "sábado": 5,
    "domingo": 6,
}

NOMES_SEMANA = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)


class AgendaError(Exception):
    """Recusa da agenda: nada foi gravado."""


# ---------------------------------------------------------------------------
# Leitura e escrita do arquivo
# ---------------------------------------------------------------------------


def _raiz(raiz: Path | None) -> Path:
    return Path(raiz) if raiz is not None else Path(dados_locais.raiz())


def _arquivo(raiz: Path | None = None) -> Path:
    return _raiz(raiz) / ARQUIVO


def _agora(agora: datetime | None) -> datetime:
    return agora.replace(microsecond=0) if agora is not None else datetime.now().replace(microsecond=0)


def carregar(raiz: Path | None = None) -> list[dict[str, Any]]:
    caminho = _arquivo(raiz)
    if not caminho.exists():
        return []
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    itens = dados.get("itens") if isinstance(dados, dict) else dados
    if not isinstance(itens, list):
        return []
    return [item for item in itens if isinstance(item, dict) and item.get("id") and item.get("titulo")]


def _salvar(raiz: Path | None, itens: list[dict[str, Any]]) -> None:
    caminho = _arquivo(raiz)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(
        json.dumps({"versao": VERSAO, "itens": itens}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporario.replace(caminho)


def _sem_acento(texto: str) -> str:
    tabela = str.maketrans("áàâãéêíóôõúüç", "aaaaeeiooouuc")
    return texto.lower().translate(tabela)


# ---------------------------------------------------------------------------
# Interpretar data e hora
# ---------------------------------------------------------------------------


def _hora_de(texto: str) -> tuple[int, int] | None:
    baixo = _sem_acento(texto)
    achado = re.search(r"\b(\d{1,2})\s*(?:h|hs|horas?)\s*(?:(\d{2}))?\b", baixo)
    if achado:
        hora = int(achado.group(1))
        minuto = int(achado.group(2) or 0)
    else:
        achado = re.search(r"\b(\d{1,2}):(\d{2})\b", baixo)
        if not achado:
            return None
        hora, minuto = int(achado.group(1)), int(achado.group(2))
    if 0 <= hora <= 23 and 0 <= minuto <= 59:
        return hora, minuto
    return None


def _data_de(texto: str, agora: datetime) -> tuple[date, str] | None:
    baixo = _sem_acento(texto)
    hoje = agora.date()

    if re.search(r"\bdepois de amanha\b", baixo):
        return hoje + timedelta(days=2), "depois de amanhã"
    if re.search(r"\bamanha\b", baixo):
        return hoje + timedelta(days=1), "amanhã"
    if re.search(r"\bhoje\b", baixo):
        return hoje, "hoje"
    achado = re.search(r"\bdaqui a (\d{1,3}) dias?\b", baixo)
    if achado:
        dias = int(achado.group(1))
        return hoje + timedelta(days=dias), f"daqui a {dias} dia(s)"

    achado = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", baixo)
    if achado:
        try:
            return date(int(achado.group(1)), int(achado.group(2)), int(achado.group(3))), "data ISO"
        except ValueError:
            return None
    achado = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", baixo)
    if achado:
        dia, mes = int(achado.group(1)), int(achado.group(2))
        ano_texto = achado.group(3)
        ano = hoje.year
        if ano_texto:
            ano = int(ano_texto)
            if ano < 100:
                ano += 2000
        try:
            candidata = date(ano, mes, dia)
        except ValueError:
            return None
        if not ano_texto and candidata < hoje:
            candidata = date(ano + 1, mes, dia)
        return candidata, "data numérica"

    for nome, indice in DIAS_SEMANA.items():
        if re.search(rf"\b{re.escape(nome)}\b", baixo):
            diante = (indice - hoje.weekday()) % 7
            if diante == 0:
                diante = 7  # “segunda” dita na segunda é a próxima
            return hoje + timedelta(days=diante), f"próxima {NOMES_SEMANA[indice]}"
    return None


def interpretar_quando(texto: str, *, agora: datetime | None = None) -> dict[str, Any]:
    """Converte o que o usuário escreveu em uma data/hora — e mostra como entendeu."""
    bruto = (texto or "").strip()
    if not bruto:
        raise AgendaError("Informe a data: `2026-11-05`, `05/11`, `amanhã`, `segunda às 14h`…")
    momento = _agora(agora)
    achada = _data_de(bruto, momento)
    if achada is None:
        raise AgendaError(
            f"Não reconheci uma data em “{bruto}”. Use `2026-11-05`, `05/11/2026`, "
            "`amanhã`, `depois de amanhã`, `daqui a 3 dias` ou `segunda às 14h`."
        )
    dia, motivo = achada
    hora = _hora_de(bruto) or HORA_PADRAO
    quando = datetime(dia.year, dia.month, dia.day, hora[0], hora[1])
    return {
        "quando": quando.isoformat(),
        "texto": formatar_quando(quando),
        "dia": quando.date().isoformat(),
        "hora": f"{hora[0]:02d}:{hora[1]:02d}",
        "como_entendi": motivo,
    }


def formatar_quando(quando: datetime | str) -> str:
    momento = datetime.fromisoformat(quando) if isinstance(quando, str) else quando
    return (
        f"{NOMES_SEMANA[momento.weekday()]}, {momento:%d/%m/%Y} "
        f"às {momento:%H:%M}"
    )


# ---------------------------------------------------------------------------
# Operações
# ---------------------------------------------------------------------------


def _id_novo(itens: list[dict[str, Any]]) -> str:
    usados = {item["id"] for item in itens}
    while True:
        novo = secrets.token_hex(3)
        if novo not in usados:
            return novo


def adicionar(
    *,
    titulo: str,
    quando: str,
    nota: str = "",
    avisar_antes: int = ANTECEDENCIA_PADRAO,
    raiz: Path | None = None,
    agora: datetime | None = None,
) -> dict[str, Any]:
    """Marca um compromisso. Recusa em vez de adivinhar a data."""
    nome = " ".join((titulo or "").split())
    if len(nome) < 2:
        raise AgendaError("O compromisso precisa de um título curto.")
    if len(nome) > MAX_TITULO:
        raise AgendaError(f"Título acima de {MAX_TITULO} caracteres.")
    entendido = interpretar_quando(quando, agora=agora)
    momento = _agora(agora)
    dia = datetime.fromisoformat(entendido["quando"])
    if dia < momento:
        raise AgendaError(
            f"“{entendido['texto']}” já passou. Para registrar algo antigo, use `agenda.listar` com histórico; "
            "para marcar, escolha uma data à frente."
        )
    itens = carregar(raiz)
    if len(itens) >= MAX_ITENS:
        raise AgendaError(f"A agenda já tem {MAX_ITENS} itens; conclua ou remova alguns.")
    try:
        antecedencia = max(0, min(int(avisar_antes), MAX_ANTECEDENCIA))
    except (TypeError, ValueError):
        raise AgendaError("`avisar_antes` precisa ser um número de minutos (0 desliga o aviso).") from None
    item = {
        "id": _id_novo(itens),
        "titulo": nome,
        "quando": entendido["quando"],
        "nota": (nota or "").strip()[:MAX_NOTA],
        "avisar_antes": antecedencia,
        "status": "aberto",
        "criado_em": momento.isoformat(),
    }
    itens.append(item)
    _salvar(raiz, itens)
    aviso = (
        f" Aviso {antecedencia} min antes." if antecedencia else " Sem aviso automático."
    )
    return {
        **item,
        "texto": entendido["texto"],
        "como_entendi": entendido["como_entendi"],
        "resposta": f"Marcado: {nome} — {entendido['texto']}.{aviso}",
    }


def _achar(ref: str, itens: list[dict[str, Any]]) -> dict[str, Any]:
    alvo = (ref or "").strip().lower()
    if not alvo:
        raise AgendaError("Informe o id (ou parte do título) do compromisso.")
    por_id = [item for item in itens if item["id"] == alvo]
    if por_id:
        return por_id[0]
    por_titulo = [item for item in itens if alvo in item["titulo"].lower()]
    if len(por_titulo) == 1:
        return por_titulo[0]
    if len(por_titulo) > 1:
        nomes = ", ".join(f"{item['id']} ({item['titulo']})" for item in por_titulo[:5])
        raise AgendaError(f"Mais de um compromisso combina com “{ref}”: {nomes}. Use o id.")
    raise AgendaError(f"Não achei compromisso com “{ref}.”")


def listar(
    *,
    raiz: Path | None = None,
    agora: datetime | None = None,
    dias: int = 0,
    incluir_concluidos: bool = False,
) -> dict[str, Any]:
    """Lista a agenda em ordem de data, marcando o que já passou."""
    momento = _agora(agora)
    limite = momento + timedelta(days=dias) if dias > 0 else None
    itens = carregar(raiz)
    escolhidos: list[dict[str, Any]] = []
    for item in itens:
        if item.get("status") == "concluido" and not incluir_concluidos:
            continue
        try:
            quando = datetime.fromisoformat(item["quando"])
        except (KeyError, ValueError):
            continue
        if limite is not None and quando > limite:
            continue
        escolhidos.append({**item, "atrasado": quando < momento and item.get("status") != "concluido"})
    escolhidos.sort(key=lambda item: item["quando"])
    proximo = next((item for item in escolhidos if not item["atrasado"]), None)
    return {
        "total": len(escolhidos),
        "itens": escolhidos,
        "proximo": proximo,
        "atrasados": sum(1 for item in escolhidos if item["atrasado"]),
        "agora": momento.isoformat(),
        "resposta": (
            f"{len(escolhidos)} compromisso(s) na agenda."
            if escolhidos
            else "A agenda está vazia para esse período."
        ),
    }


def concluir(ref: str, *, raiz: Path | None = None) -> dict[str, Any]:
    itens = carregar(raiz)
    item = _achar(ref, itens)
    item["status"] = "concluido"
    item["concluido_em"] = _agora(None).isoformat()
    _salvar(raiz, itens)
    return {**item, "resposta": f"Concluído: {item['titulo']}."}


def remover(ref: str, *, raiz: Path | None = None) -> dict[str, Any]:
    itens = carregar(raiz)
    item = _achar(ref, itens)
    restantes = [outro for outro in itens if outro["id"] != item["id"]]
    _salvar(raiz, restantes)
    return {"removido": item, "total": len(restantes), "resposta": f"Removido: {item['titulo']}."}


# ---------------------------------------------------------------------------
# Lembretes
# ---------------------------------------------------------------------------


def chave_do_lembrete(lembrete: dict[str, Any]) -> str:
    """Identidade estável para a tela não repetir o mesmo aviso."""
    return f"{lembrete.get('id')}|{lembrete.get('quando')}|{lembrete.get('tipo')}"


def devidos(
    *,
    raiz: Path | None = None,
    agora: datetime | None = None,
    antecedencia: int = ANTECEDENCIA_PADRAO,
    incluir_atrasados: bool = True,
) -> list[dict[str, Any]]:
    """O que precisa de atenção agora: o que passou e o que chega na janela.

    Cada item usa o próprio `avisar_antes`; o parâmetro `antecedencia` é só o
    padrão de quem não declarou nada (itens antigos, criados antes da 0.62.4).
    """
    momento = _agora(agora)
    try:
        padrao = max(0, min(int(antecedencia), MAX_ANTECEDENCIA))
    except (TypeError, ValueError):
        raise AgendaError("`antecedencia` precisa ser um número de minutos.") from None
    lembretes: list[dict[str, Any]] = []
    for item in carregar(raiz):
        if item.get("status") == "concluido":
            continue
        try:
            quando = datetime.fromisoformat(item["quando"])
        except (KeyError, ValueError):
            continue
        janela = item.get("avisar_antes")
        if not isinstance(janela, int):
            janela = padrao
        if janela <= 0:
            continue
        faltam = int((quando - momento).total_seconds() // 60)
        if faltam < 0:
            if not incluir_atrasados:
                continue
            lembretes.append(
                {
                    "id": item["id"],
                    "titulo": item["titulo"],
                    "quando": item["quando"],
                    "tipo": "atrasado",
                    "minutos": abs(faltam),
                    "texto": formatar_quando(quando),
                    "nota": item.get("nota", ""),
                }
            )
        elif faltam <= janela:
            lembretes.append(
                {
                    "id": item["id"],
                    "titulo": item["titulo"],
                    "quando": item["quando"],
                    "tipo": "chegando",
                    "minutos": faltam,
                    "texto": formatar_quando(quando),
                    "nota": item.get("nota", ""),
                }
            )
    lembretes.sort(key=lambda lembrete: (lembrete["tipo"] != "atrasado", lembrete["minutos"]))
    return lembretes


def texto_lembretes(lembretes: list[dict[str, Any]], *, agora: datetime | None = None) -> str:
    """Texto curto para o chat e para o aviso da tela."""
    if not lembretes:
        return "Nada vencendo agora."
    linhas: list[str] = []
    for lembrete in lembretes:
        if lembrete["tipo"] == "atrasado":
            quando = f"atrasado há {_duracao(lembrete['minutos'])}"
        elif lembrete["minutos"] <= 0:
            quando = "agora"
        else:
            quando = f"em {_duracao(lembrete['minutos'])}"
        linhas.append(f"• {lembrete['titulo']} — {lembrete['texto']} ({quando})")
    return "\n".join(linhas)


def _duracao(minutos: int) -> str:
    if minutos < 60:
        return f"{minutos} min"
    horas, resto = divmod(minutos, 60)
    if horas < 24:
        return f"{horas}h{resto:02d}" if resto else f"{horas}h"
    dias, horas = divmod(horas, 24)
    return f"{dias}d" + (f" {horas}h" if horas else "")


def texto(itens: list[dict[str, Any]], *, agora: datetime | None = None) -> str:
    """Texto do chat para a agenda."""
    momento = _agora(agora)
    if not itens:
        return "A agenda está vazia para esse período."
    linhas: list[str] = []
    for item in itens:
        quando = datetime.fromisoformat(item["quando"])
        marca = " ⚠️ atrasado" if quando < momento and item.get("status") != "concluido" else ""
        linhas.append(f"• [{item['id']}] {item['titulo']} — {formatar_quando(quando)}{marca}")
        if item.get("nota"):
            linhas.append(f"    {item['nota']}")
    return "\n".join(linhas)
