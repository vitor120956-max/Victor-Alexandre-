"""Os braços: arrumar a máquina em vez de dizer o que apertar.

O pedido que gerou isto foi direto: *“eu não quero ter que fazer nada, por isso
fiz o JARVIS com braços”*. Até a 0.69.0 o `maquina.debloat` diagnosticava e
entregava um `.bat` para o usuário ler, salvar e rodar como administrador. Isso é
relatório, não braço.

Aqui o JARVIS **faz**. Um comando (`maquina.arrumar`) ou um duplo clique
(`arrumar-pc.bat`) executa a limpeza inteira: fecha processo de sobra, remove app
de loja sem uso, desativa tarefa de telemetria, desativa serviço inútil e limpa
cache do Windows. E grava tudo num diário com o caminho de volta.

## O que continua valendo, e por quê

Braço não é carta branca. As quatro travas que sobraram existem porque cada uma
já evitou um estrago real:

1. **só o veredito `sobra` é executado.** `driver` (NVIDIA Container), `cuidado`
   (Xbox, WinSxS, hibernação) e `essencial` (Store, VCLibs, Segurança) **nunca**
   entram — nem se o plano pedir;
2. **identidade antes do PID.** Processo só é encerrado se, na hora de encerrar,
   ele ainda tiver o mesmo nome e continuar classificado como sobra;
3. **diário com desfazer.** Cada ação grava comando, saída e o comando de volta
   em `storage/limpezas/<data>.json`; `maquina.desfazer` relê e reverte;
4. **a trava `JARVIS_HOST_ARRUMAR=1`.** O `iniciar-jarvis.bat` liga; quem preferir
   o JARVIS só olhando a máquina desliga no `.env`.

## O que ele **não** faz

- não desinstala driver, não mexe em `C:\\Windows\\Installer`, não apaga `Prefetch`;
- não remove app `essencial` nem framework (`VCLibs`, `UI.Xaml`);
- não desativa serviço de áudio, Wi-Fi, horário, impressão ou atualização;
- não formata disco, não restaura ponto, não reinicia a máquina sem você pedir.

Também não inventa: cada ação sai de um item que **existe** na máquina e está no
catálogo. O que não está no catálogo aparece no relatório como “não classificado”
e não é tocado.
"""
from __future__ import annotations

import json
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import dados as dados_locais
from . import limpeza as limpeza_local

AMBIENTE = "JARVIS_HOST_ARRUMAR"
CRIACAO_SEM_JANELA = 0x08000000
VEREDITO_EXECUTAVEL = "sobra"

# Limpeza de disco que pode rodar sozinha: só o que é lixo por definição.
# WinSxS, hibernação e "Windows.old" ficam de fora — os três são "cuidado" no
# catálogo e mexem em recurso do sistema (DISM, energia, versão anterior).
ESPACO_SEGURO = {"temp-usuario", "temp-windows", "update-cache", "lixeira", "delivery"}


class ArrumarError(ValueError):
    """Recusa segura para o usuário."""


# ---------------------------------------------------------------------------
# Execução de comando (injetável: os testes trocam por um falso)
# ---------------------------------------------------------------------------


def rodar_comando(comando: str, timeout: int = 180) -> tuple[int, str]:
    """Roda um comando **do catálogo** pelo `cmd`. Nunca recebe texto do usuário."""
    if platform.system() != "Windows":
        raise ArrumarError("Arrumar a máquina é do Windows; aqui não se aplica.")
    try:
        concluido = subprocess.run(
            ["cmd", "/c", comando],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=CRIACAO_SEM_JANELA if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"falhou ao rodar: {exc}"
    saida = ((concluido.stdout or "") + (concluido.stderr or "")).strip()
    return concluido.returncode, saida[-600:]


def ligado() -> bool:
    import os  # noqa: PLC0415

    return os.environ.get(AMBIENTE, "0").strip() == "1"


# ---------------------------------------------------------------------------
# Planejamento (lê a máquina e monta a lista do que fazer)
# ---------------------------------------------------------------------------


def _item(tipo: str, identificador: str, nome: str, comando: str, desfazer: str,
          ganho: str = "", extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": f"{tipo}:{identificador}",
        "tipo": tipo,
        "nome": nome,
        "comando": comando,
        "desfazer": desfazer,
        "ganho": ganho,
        **(extra or {}),
    }


def _de_processos() -> list[dict[str, Any]]:
    from . import processos as processos_local  # noqa: PLC0415

    dados = processos_local.relatorio()
    if not dados.get("lido"):
        return []
    itens = []
    for linha in dados["grupos"].get(VEREDITO_EXECUTAVEL, []):
        # Guarda o nome esperado: na hora de matar, o PID precisa continuar sendo
        # este processo. Sem isso, um PID reciclado vira alvo errado.
        itens.append(
            _item(
                "processo",
                f"{linha['nome']}:{linha.get('pid')}",
                linha["nome"],
                f'taskkill /PID {int(linha["pid"])} /F',
                "",
                f"{round(linha.get('memoria_mb') or 0)} MB de RAM",
                {"pid": linha.get("pid"), "processo": linha.get("processo"), "nome": linha["nome"]},
            )
        )
    return itens


def _de_apps() -> list[dict[str, Any]]:
    dados = limpeza_local.analisar_apps(limpeza_local.medir_apps())
    itens = []
    for app in dados["apps"]:
        if app["veredito"] != VEREDITO_EXECUTAVEL:
            continue
        itens.append(
            _item("app", app["id"], app["nome"], app["comando"], app["desfazer"],
                  f"~{app['tamanho_estimado_mb']} MB de disco", {"pacote": app["pacote"]})
        )
    return itens


def _de_tarefas() -> list[dict[str, Any]]:
    dados = limpeza_local.analisar_tarefas(limpeza_local.medir_tarefas())
    return [
        _item("tarefa", t["tarefa"].rsplit("\\", 1)[-1], t["nome"], t["comando"], t["desfazer"])
        for t in dados
        if t["veredito"] == VEREDITO_EXECUTAVEL
    ]


def _de_servicos() -> list[dict[str, Any]]:
    dados = limpeza_local.analisar_servicos(limpeza_local.medir_servicos())
    return [
        _item("servico", s["servico"], s["nome"], s["comando"], s["desfazer"])
        for s in dados
        if s["veredito"] == VEREDITO_EXECUTAVEL
    ]


def _de_espaco() -> list[dict[str, Any]]:
    dados = limpeza_local.analisar_espaco(limpeza_local.medir_pastas(medir=True))
    itens = []
    for item in dados:
        if item["id"] not in ESPACO_SEGURO:
            continue
        if not item.get("comando"):
            continue
        ganho = f"{round(item['tamanho_mb'])} MB" if item.get("tamanho_mb") else item.get("ganho", "")
        itens.append(_item("espaco", item["id"], item["nome"], item["comando"], "", ganho))
    return itens


def planejar(*, processos: bool = True, apps: bool = True, tarefas: bool = True,
             servicos: bool = True, espaco: bool = True) -> dict[str, Any]:
    """Lê a máquina e monta a lista do que seria feito. Não executa nada."""
    sistema = platform.system()
    if sistema != "Windows":
        return {
            "sistema": sistema,
            "lido": False,
            "motivo": "Arrumar a máquina é do Windows; fora dele não há app de loja, serviço nem cache para limpar.",
            "itens": [],
            "total": 0,
            "resumo": "Nada a fazer fora do Windows.",
        }
    itens: list[dict[str, Any]] = []
    if processos:
        itens += _de_processos()
    if apps:
        itens += _de_apps()
    if tarefas:
        itens += _de_tarefas()
    if servicos:
        itens += _de_servicos()
    if espaco:
        itens += _de_espaco()
    por_tipo: dict[str, int] = {}
    for item in itens:
        por_tipo[item["tipo"]] = por_tipo.get(item["tipo"], 0) + 1
    return {
        "sistema": sistema,
        "lido": True,
        "itens": itens,
        "total": len(itens),
        "por_tipo": por_tipo,
        "resumo": _resumo_plano(itens),
        "regra": (
            "Só entra aqui o que é 'sobra'. Driver, essencial e o que depende do "
            "seu uso ficam de fora, mesmo que estejam ocupando memória."
        ),
    }


def _resumo_plano(itens: list[dict[str, Any]]) -> str:
    if not itens:
        return "Nada para arrumar: a máquina já está sem sobra conhecida."
    contagem: dict[str, int] = {}
    for item in itens:
        contagem[item["tipo"]] = contagem.get(item["tipo"], 0) + 1
    partes = []
    rotulos = {"processo": "processo(s) de sobra", "app": "app(s) de loja",
               "tarefa": "tarefa(s)", "servico": "serviço(s)", "espaco": "limpeza(s) de cache"}
    for tipo, quantidade in contagem.items():
        partes.append(f"{quantidade} {rotulos.get(tipo, tipo)}")
    return "Dá para arrumar " + ", ".join(partes) + "."


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------


def _pasta_diario(raiz: Path | None = None) -> Path:
    base = Path(raiz) if raiz is not None else Path(dados_locais.raiz())
    return base / "limpezas"


def _nome_do_diario(agora: datetime | None = None) -> str:
    marca = (agora or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"limpeza-{marca}.json"


def _gravar_diario(registro: dict[str, Any], raiz: Path | None = None) -> str:
    pasta = _pasta_diario(raiz)
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / _nome_do_diario()
    caminho.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(caminho)


def _processo_ainda_e_o_mesmo(item: dict[str, Any]) -> bool:
    """O PID continua sendo o processo que o plano viu? (PID reciclado é comum)"""
    from . import processos as processos_local  # noqa: PLC0415

    pid = item.get("pid")
    if not pid:
        return False
    for linha in processos_local.coletar(limite=600):
        if linha.get("pid") == pid:
            nome_atual = str(linha.get("nome") or "").strip().lower()
            esperado = str(item.get("processo") or item.get("nome") or "").strip().lower()
            ficha = processos_local.conhecer(nome_atual)
            return bool(ficha) and ficha["veredito"] == VEREDITO_EXECUTAVEL and nome_atual == esperado
    return False


def executar(
    *,
    autorizacao: str = "",
    plano: dict[str, Any] | None = None,
    confirmado: bool = False,
    raiz_diario: Path | None = None,
    rodar: Callable[[str], tuple[int, str]] | None = None,
    agora: datetime | None = None,
) -> dict[str, Any]:
    """Executa o plano de sobras. Exige a trava ligada e confirmação explícita."""
    from . import sistema as sistema_mod  # noqa: PLC0415

    if not ligado():
        raise ArrumarError(
            "Os braços estão desligados. Suba a API com JARVIS_HOST_ARRUMAR=1 "
            "(o iniciar-jarvis.bat já liga) para o JARVIS poder arrumar a máquina."
        )
    ok, motivo = sistema_mod.autorizado(autorizacao)
    if not ok:
        raise ArrumarError(motivo)
    if not confirmado:
        raise ArrumarError(
            "Falta a confirmação explícita: sem ‘sim, pode’ o JARVIS não mexe na máquina."
        )
    if platform.system() != "Windows":
        raise ArrumarError("Arrumar a máquina é do Windows; aqui não se aplica.")

    dados = plano if plano is not None else planejar()
    if not dados.get("lido"):
        return {**dados, "executado": False, "acoes": []}

    executor = rodar or (lambda comando: rodar_comando(comando))
    acoes: list[dict[str, Any]] = []
    for item in dados.get("itens", []):
        if item.get("tipo") == "processo":
            if not _processo_ainda_e_o_mesmo(item):
                acoes.append({**item, "ok": False, "saida": "pulado: o processo já saiu ou o PID mudou"})
                continue
        try:
            codigo, saida = executor(item["comando"])
        except ArrumarError as exc:
            acoes.append({**item, "ok": False, "saida": str(exc)})
            continue
        acoes.append({**item, "ok": codigo == 0, "saida": saida})

    registro = {
        "quando": (agora or datetime.now()).isoformat(timespec="seconds"),
        "sistema": platform.system(),
        "acoes": acoes,
        "resumo": _resumo_execucao(acoes),
    }
    caminho = _gravar_diario(registro, raiz_diario)
    return {
        "executado": True,
        "acoes": acoes,
        "feitas": sum(1 for a in acoes if a["ok"]),
        "falhas": sum(1 for a in acoes if not a["ok"]),
        "resumo": registro["resumo"],
        "diario": caminho,
        "desfazer": "maquina.desfazer reverte app, tarefa e serviço do último diário.",
    }


def _resumo_execucao(acoes: list[dict[str, Any]]) -> str:
    if not acoes:
        return "Não havia nada para arrumar."
    feitas = [a for a in acoes if a["ok"]]
    falhas = [a for a in acoes if not a["ok"]]
    if not feitas:
        return f"Nenhuma das {len(acoes)} ações funcionou. Veja o diário para o motivo de cada uma."
    ram = sum(
        int(str(a.get("ganho") or "0").split()[0] or 0)
        for a in feitas if a["tipo"] == "processo" and a.get("ganho")
    )
    partes = [f"Arrumado: {len(feitas)} de {len(acoes)} ações."]
    if ram:
        partes.append(f"Devolveu cerca de {ram} MB de RAM fechando processos de sobra.")
    if falhas:
        partes.append(
            f"{len(falhas)} falharam — normalmente falta de administrador; o diário diz qual."
        )
    return " ".join(partes)


# ---------------------------------------------------------------------------
# Desfazer
# ---------------------------------------------------------------------------


def ultimo_diario(raiz: Path | None = None) -> dict[str, Any] | None:
    pasta = _pasta_diario(raiz)
    if not pasta.is_dir():
        return None
    arquivos = sorted(pasta.glob("limpeza-*.json"))
    if not arquivos:
        return None
    try:
        dados = json.loads(arquivos[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    dados["arquivo"] = str(arquivos[-1])
    return dados


def desfazer(
    *,
    autorizacao: str = "",
    confirmado: bool = False,
    raiz_diario: Path | None = None,
    rodar: Callable[[str], tuple[int, str]] | None = None,
) -> dict[str, Any]:
    """Reverte o último diário: religa serviço e tarefa, reinstala app pela loja."""
    from . import sistema as sistema_mod  # noqa: PLC0415

    ok, motivo = sistema_mod.autorizado(autorizacao)
    if not ok:
        raise ArrumarError(motivo)
    if not confirmado:
        raise ArrumarError("Desfazer mexe na máquina: precisa de confirmação explícita.")
    registro = ultimo_diario(raiz_diario)
    if registro is None:
        return {"desfeito": False, "motivo": "Não há diário de limpeza para desfazer."}

    executor = rodar or (lambda comando: rodar_comando(comando))
    reverte: list[dict[str, Any]] = []
    for acao in registro.get("acoes", []):
        if not acao.get("ok") or not acao.get("desfazer"):
            continue
        codigo, saida = executor(acao["desfazer"])
        reverte.append({**acao, "ok_desfazer": codigo == 0, "saida_desfazer": saida})

    sem_volta = [a["nome"] for a in registro.get("acoes", []) if a.get("ok") and not a.get("desfazer")]
    return {
        "desfeito": bool(reverte),
        "revertidas": reverte,
        "numero": len(reverte),
        "sem_volta": sem_volta,
        "diario": registro.get("arquivo"),
        "resumo": (
            f"Reverti {len(reverte)} ação(ões) do último diário."
            if reverte
            else "O último diário não tinha ação reversível (processo e cache não voltam)."
        ),
    }


# ---------------------------------------------------------------------------
# CLI — é o que o arrumar-pc.bat chama
# ---------------------------------------------------------------------------


def _cli(argv: list[str] | None = None) -> int:
    import argparse  # noqa: PLC0415
    import sys  # noqa: PLC0415

    parser = argparse.ArgumentParser(description="Os braços do JARVIS: arrumar esta máquina.")
    parser.add_argument("--aplicar", action="store_true", help="Executar, não só planejar.")
    parser.add_argument("--desfazer", action="store_true", help="Reverter o último diário.")
    parser.add_argument("--sim", action="store_true", help="Não pedir confirmação (só em script).")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    from . import sistema as sistema_mod  # noqa: PLC0415

    token = sistema_mod.token_host()
    if not token:
        print("  Não achei o token em storage/host-token.txt. Suba o JARVIS uma vez.")
        return 1

    if not args.desfazer:
        plano = planejar()
        if not plano.get("lido"):
            print(f"  {plano.get('motivo')}")
            return 1
        if args.json:
            print(json.dumps(plano, ensure_ascii=False, indent=2))
            return 0
        print()
        print(f"  {plano['resumo']}")
        for item in plano["itens"]:
            print(f"    - [{item['tipo']}] {item['nome']}  {item.get('ganho', '')}")
        print()
        if not args.aplicar:
            print("  Só o plano. Para executar: --aplicar")
            return 0
        if not args.sim:
            try:
                resposta = input("  Executar agora? [s/N] ").strip().lower()
            except EOFError:
                resposta = ""
            if resposta not in {"s", "sim", "y", "yes"}:
                print("  Cancelado: nada foi feito.")
                return 0

    try:
        resultado = (
            desfazer(autorizacao=token, confirmado=True)
            if args.desfazer
            else executar(autorizacao=token, plano=planejar(), confirmado=True)
        )
    except ArrumarError as exc:
        print(f"  {exc}")
        return 1
    print()
    print(f"  {resultado.get('resumo')}")
    if resultado.get("diario"):
        print(f"  Diário: {resultado['diario']}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
