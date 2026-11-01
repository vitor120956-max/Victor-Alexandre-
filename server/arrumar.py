"""Os braços: arrumar a máquina em vez de dizer o que apertar.

O pedido que gerou isto foi direto: *“eu não quero ter que fazer nada, por isso
fiz o JARVIS com braços”*. Até a 0.71.0 o `maquina.debloat` diagnosticava e
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
ESPACO_SEGURO = {"temp-usuario", "temp-windows", "update-cache", "lixeira", "delivery"}

# No "modo ousado" entra o que é reversível com uma linha. `hiberfil.sys` volta
# com `powercfg /h on`. O que **não** volta fica fora dos dois modos:
#   - WinSxS (DISM /ResetBase)   -> apaga versão antiga de componente para sempre;
#   - Windows.old               -> a versão anterior do Windows deixa de existir;
#   - C:\Windows\Installer      -> é o cache de desinstalação dos MSI;
#   - Prefetch                  -> deixa o programa abrir mais rápido.
ESPACO_OUSADO = {"hiberfil"}


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


def elevado() -> bool | None:
    """A API está rodando como administrador?

    `True`/`False` no Windows; `None` quando não dá para saber (fora dele). Serve
    para avisar **antes**: desativar tarefa (`schtasks /Change`) e serviço
    (`sc config`) exige elevação, e sem ela o plano termina em 13 falhas iguais —
    que foi exatamente o que aconteceu em 01/11/2026 e virou “o JARVIS não
    funcionou”, quando o certo era “a janela não estava elevada”.
    """
    if platform.system() != "Windows":
        return None
    try:
        import ctypes  # noqa: PLC0415

        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except (AttributeError, OSError, TypeError):
        return None


# Tipos de ação que o Windows só deixa fazer com elevação. Processo (taskkill do
# próprio usuário) e cache (arquivo do próprio usuário) não entram nesta lista.
TIPOS_QUE_PEDEM_ADMIN = {"tarefa", "servico", "app"}


def _causa_da_falha(saida: str) -> str:
    """Traduz a saída do Windows numa causa curta, para dizer o que fazer.

    Sem isso o relatório dizia “13 falharam — o diário diz qual”, e o usuário
    tinha que abrir um JSON para descobrir que era só falta de administrador.
    """
    texto = (saida or "").lower()
    if any(p in texto for p in (
        "acesso negado", "access is denied", "access denied", "erro 5", "error 5",
        "requires elevation", "solicita eleva", "5 (0x5)", "negado",
    )):
        return "admin"
    sumiu = (
        ("encontr" in texto or "existe" in texto or "no such" in texto)
        and any(p in texto for p in ("não", "nao", "cannot", "could not", "does not"))
    )
    if sumiu or any(p in texto for p in (
        "cannot find", "does not exist", "no such", "já existe", "already exists",
        "não existe", "nao existe", "não foi encontrado",
    )):
        return "sumiu"
    if any(p in texto for p in ("timeout", "tempo limite", "timed out", "demorou")):
        return "tempo"
    if any(p in texto for p in ("não está em execução", "not running", "inativo")):
        return "parado"
    return "outro"


MOTIVO_DA_CAUSA = {
    "admin": "falta de administrador — a API não está elevada",
    "sumiu": "o item já não existe na máquina (alguém removeu antes)",
    "tempo": "o comando passou do tempo e foi interrompido",
    "parado": "já estava parado; não havia o que desativar",
    "pulado": "pulado: o processo saiu ou o PID mudou antes da ação",
    "outro": "o Windows recusou por outro motivo — a saída está no diário",
}


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


def _de_apps(ousado: bool = False) -> list[dict[str, Any]]:
    dados = limpeza_local.analisar_apps(limpeza_local.medir_apps())
    aceitos = {VEREDITO_EXECUTAVEL} | ({"cuidado"} if ousado else set())
    itens = []
    for app in dados["apps"]:
        if app["veredito"] not in aceitos:
            continue
        itens.append(
            _item("app", app["id"], app["nome"], app["comando"], app["desfazer"],
                  f"~{app['tamanho_estimado_mb']} MB de disco", {"pacote": app["pacote"]})
        )
    return itens


def _de_tarefas(ousado: bool = False) -> list[dict[str, Any]]:
    dados = limpeza_local.analisar_tarefas(limpeza_local.medir_tarefas())
    aceitos = {VEREDITO_EXECUTAVEL} | ({"cuidado"} if ousado else set())
    return [
        _item("tarefa", t["tarefa"].rsplit("\\", 1)[-1], t["nome"], t["comando"], t["desfazer"])
        for t in dados
        if t["veredito"] in aceitos
    ]


def _de_servicos(ousado: bool = False) -> list[dict[str, Any]]:
    dados = limpeza_local.analisar_servicos(limpeza_local.medir_servicos())
    aceitos = {VEREDITO_EXECUTAVEL} | ({"cuidado"} if ousado else set())
    return [
        _item("servico", s["servico"], s["nome"], s["comando"], s["desfazer"])
        for s in dados
        if s["veredito"] in aceitos
    ]


def _de_espaco(ousado: bool = False) -> list[dict[str, Any]]:
    dados = limpeza_local.analisar_espaco(limpeza_local.medir_pastas(medir=True))
    permitidos = ESPACO_SEGURO | (ESPACO_OUSADO if ousado else set())
    itens = []
    for item in dados:
        if item["id"] not in permitidos:
            continue
        if not item.get("comando"):
            continue
        ganho = f"{round(item['tamanho_mb'])} MB" if item.get("tamanho_mb") else item.get("ganho", "")
        itens.append(_item("espaco", item["id"], item["nome"], item["comando"], "", ganho))
    return itens


def planejar(*, processos: bool = True, apps: bool = True, tarefas: bool = True,
             servicos: bool = True, espaco: bool = True, ousado: bool = False) -> dict[str, Any]:
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
        itens += _de_apps(ousado)
    if tarefas:
        itens += _de_tarefas(ousado)
    if servicos:
        itens += _de_servicos(ousado)
    if espaco:
        itens += _de_espaco(ousado)
    por_tipo: dict[str, int] = {}
    for item in itens:
        por_tipo[item["tipo"]] = por_tipo.get(item["tipo"], 0) + 1
    # O aviso vem antes, não depois: 13 de 16 falharam em 01/11/2026 só porque a
    # janela da API não estava elevada, e o plano não dizia isso.
    precisa = sum(1 for item in itens if item["tipo"] in TIPOS_QUE_PEDEM_ADMIN)
    esta_elevado = elevado()
    return {
        "sistema": sistema,
        "lido": True,
        "itens": itens,
        "total": len(itens),
        "por_tipo": por_tipo,
        "resumo": _resumo_plano(itens),
        "ousado": ousado,
        "elevado": esta_elevado,
        "precisam_admin": precisa,
        "aviso_admin": (
            ""
            if esta_elevado is not False or precisa == 0
            else (
                f"Atenção: esta janela não está como administrador. {precisa} de "
                f"{len(itens)} ação(ões) — tarefas, serviços e apps de loja — vão falhar "
                "com “acesso negado”. Processo e cache funcionam assim mesmo. Para fazer "
                "tudo: feche a API e abra o arrumar-pc.bat com o botão direito → "
                "“Executar como administrador”."
            )
        ),
        "regra": (
            "Sem o modo ousado, só entra o que é 'sobra'. Com ele, entra também o "
            "'cuidado' que tem volta (Xbox, Teams, Search, Superfetch, hibernação). "
            "O que não tem volta — WinSxS, Windows.old, Installer, Prefetch, driver "
            "e essencial — fica de fora nos dois modos."
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


# ---------------------------------------------------------------------------
# Instantâneo: a foto de antes (a ideia do backup, no tamanho certo)
# ---------------------------------------------------------------------------
#
# Backup "na nuvem" do Windows inteiro não resolve — driver e componente de
# sistema não são dados, e baixar 20 GB de volta é pior que desfazer com uma
# linha. O que resolve de verdade são duas coisas baratas:
#
#   1. **instantâneo** (KB, aqui embaixo): a lista do que estava instalado,
#      ligado e ativo antes da limpeza. É o que permite reinstalar pela Store e
#      saber o estado original de cada serviço;
#   2. **ponto de restauração** (o do próprio Windows): religa driver, serviço e
#      registro. Ocupa 1 a 2 GB **no disco local** e é o único mecanismo que o
#      Windows tem para voltar o sistema inteiro.
#
# O instantâneo vai para `storage/limpezas/instantaneo-<data>.json` — pequeno o
# bastante para caber num Drive, num pen drive ou num anexo, e grande o
# suficiente para reconstruir o estado.


def instantaneo() -> dict[str, Any]:
    """Foto do estado atual: apps de loja, serviços e tarefas com seus modos."""
    if platform.system() != "Windows":
        return {"sistema": platform.system(), "lido": False, "motivo": "Instantâneo é do Windows."}
    apps = []
    for pacote in limpeza_local.medir_apps():
        nome = str(pacote.get("Name") or "").strip()
        if nome:
            apps.append({"nome": nome, "completo": pacote.get("PackageFullName") or ""})
    servicos = limpeza_local.medir_servicos()
    tarefas = limpeza_local.medir_tarefas()
    return {
        "sistema": platform.system(),
        "lido": True,
        "quando": datetime.now().isoformat(timespec="seconds"),
        "versao": _versao_jarvis(),
        "apps": apps,
        "servicos": servicos,
        "tarefas": tarefas,
        "resumo": f"{len(apps)} app(s), {len(servicos)} serviço(s), {len(tarefas)} tarefa(s).",
    }


def _versao_jarvis() -> str:
    try:
        dados = json.loads((Path(__file__).resolve().parent.parent / "package.json").read_text(encoding="utf-8"))
        return str(dados.get("version") or "?")
    except (OSError, ValueError):
        return "?"


def gravar_instantaneo(foto: dict[str, Any] | None = None, raiz: Path | None = None) -> str | None:
    """Grava a foto em `storage/limpezas/instantaneo-<data>.json`. Devolve o caminho."""
    dados = foto if foto is not None else instantaneo()
    if not dados.get("lido"):
        return None
    pasta = _pasta_diario(raiz)
    pasta.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    caminho = pasta / f"instantaneo-{marca}.json"
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(caminho)


PONTO_SCRIPT = (
    "Checkpoint-Computer -Description 'JARVIS antes da limpeza' "
    "-RestorePointType 'MODIFY_SETTINGS' -ErrorAction Stop; 'criado'"
)


def ponto_de_restauracao(rodar_ps: Callable[[str], tuple[int, str]] | None = None) -> dict[str, Any]:
    """Cria um ponto de restauração do Windows (o 'backup' que realmente volta).

    Não bloqueia a limpeza quando falha: em muitas máquinas a Proteção do Sistema
    está desligada, e aí o certo é dizer isso e seguir — com o instantâneo no
    lugar. Criar ponto exige administrador.
    """
    if platform.system() != "Windows":
        return {"criado": False, "motivo": "Ponto de restauração é do Windows."}
    executor = rodar_ps or (lambda script: _ps(script))
    codigo, saida = executor(PONTO_SCRIPT)
    if codigo == 0 and "criado" in (saida or "").lower():
        return {"criado": True, "motivo": ""}
    return {
        "criado": False,
        "motivo": (
            "Não consegui criar o ponto de restauração. Causa comum: a Proteção do "
            "Sistema está desligada, ou a janela não está como administrador. "
            "O instantâneo da lista de apps/serviços/tarefas foi gravado de qualquer forma. "
            f"Resposta do Windows: {(saida or '').strip()[:200]}"
        ),
    }


def _ps(script: str, timeout: int = 300) -> tuple[int, str]:
    """PowerShell fixo do módulo — nunca texto do usuário."""
    try:
        concluido = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=CRIACAO_SEM_JANELA if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    return concluido.returncode, ((concluido.stdout or "") + (concluido.stderr or "")).strip()


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
    ponto: bool | Callable[[], dict[str, Any]] | None = None,
    foto: dict[str, Any] | None = None,
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

    # 1) foto de antes — barata e sempre possível. Se falhar (PowerShell fora do
    #    ar, política de execução, disco cheio), a limpeza continua: perder a
    #    foto é ruim, não limpar por causa dela é pior.
    try:
        instantaneo_gravado = gravar_instantaneo(foto, raiz_diario)
    except (OSError, ValueError, RuntimeError):
        instantaneo_gravado = None

    # 2) ponto de restauração — o "backup" que o Windows sabe restaurar.
    #    Falhar aqui não cancela: a máquina pode ter a Proteção desligada.
    if ponto is None or ponto is True:
        resultado_ponto = ponto_de_restauracao()
    elif callable(ponto):
        resultado_ponto = ponto()
    elif ponto is False:
        resultado_ponto = {"criado": False, "motivo": "Desligado para esta execução."}
    else:
        resultado_ponto = {"criado": False, "motivo": "Opção não reconhecida."}

    executor = rodar or (lambda comando: rodar_comando(comando))
    acoes: list[dict[str, Any]] = []
    for item in dados.get("itens", []):
        if item.get("tipo") == "processo":
            if not _processo_ainda_e_o_mesmo(item):
                acoes.append(_acao(item, False, "pulado: o processo já saiu ou o PID mudou"))
                continue
        try:
            codigo, saida = executor(item["comando"])
        except ArrumarError as exc:
            acoes.append(_acao(item, False, str(exc)))
            continue
        acoes.append(_acao(item, codigo == 0, saida))

    registro = {
        "quando": (agora or datetime.now()).isoformat(timespec="seconds"),
        "sistema": platform.system(),
        "elevado": elevado(),
        "instantaneo": instantaneo_gravado,
        "ponto_de_restauracao": resultado_ponto,
        "acoes": acoes,
        "resumo": _resumo_execucao(acoes),
    }
    caminho = _gravar_diario(registro, raiz_diario)
    return {
        "executado": True,
        "acoes": acoes,
        "feitas": sum(1 for a in acoes if a["ok"]),
        "falhas": sum(1 for a in acoes if not a["ok"]),
        "falhas_por_causa": _contar_causas(acoes),
        "nao_feitas": [
            {"nome": a.get("nome"), "tipo": a.get("tipo"), "comando": a.get("comando"),
             "motivo": a.get("motivo"), "causa": a.get("causa"), "saida": (a.get("saida") or "")[:300]}
            for a in acoes if not a["ok"]
        ],
        "elevado": elevado(),
        "como_resolver": _como_resolver(acoes),
        "resumo": registro["resumo"],
        "diario": caminho,
        "instantaneo": instantaneo_gravado,
        "ponto_de_restauracao": resultado_ponto,
        "como_voltar_tudo": (
            "Ponto de restauração: tecle Win+R, digite rstrui e escolha o ponto "
            "'JARVIS antes da limpeza'. O instantâneo lista o que reinstalar pela Store."
        ) if resultado_ponto.get("criado") else (
            "O ponto de restauração não foi criado. O instantâneo lista os apps, "
            "serviços e tarefas como estavam; maquina.desfazer reverte o que tem volta."
        ),
        "desfazer": "maquina.desfazer reverte app, tarefa e serviço do último diário.",
    }


def _acao(item: dict[str, Any], ok: bool, saida: str) -> dict[str, Any]:
    """A ação com o motivo da falha já traduzido — não só a saída crua."""
    acao = {**item, "ok": ok, "saida": saida}
    if not ok:
        causa = _causa_da_falha(saida)
        if (saida or "").lower().startswith("pulado"):
            causa = "pulado"
        acao["causa"] = causa
        acao["motivo"] = MOTIVO_DA_CAUSA.get(causa, MOTIVO_DA_CAUSA["outro"])
    return acao


def _contar_causas(acoes: list[dict[str, Any]]) -> dict[str, int]:
    contagem: dict[str, int] = {}
    for acao in acoes:
        if acao.get("ok"):
            continue
        causa = str(acao.get("causa") or "outro")
        contagem[causa] = contagem.get(causa, 0) + 1
    return contagem


def _como_resolver(acoes: list[dict[str, Any]]) -> str:
    """Uma frase acionável por causa — o que fazer depois de ver a falha."""
    causas = _contar_causas(acoes)
    if not causas:
        return "Nada a resolver: todas as ações funcionaram."
    partes: list[str] = []
    if causas.get("admin"):
        partes.append(
            f"{causas['admin']} precisam de administrador: feche esta janela e abra o "
            "arrumar-pc.bat com o botão direito → “Executar como administrador”. "
            "Nada do que falhou ficou pela metade."
        )
    if causas.get("sumiu"):
        partes.append("O que já não existia não precisa de ação: é o Windows tendo mudado sozinho.")
    if causas.get("tempo"):
        partes.append("O que estourou o tempo pode ser tentado de novo; o diário tem a saída.")
    if causas.get("pulado"):
        partes.append(
            "O processo pulado saiu (ou o PID mudou) entre a leitura e o comando — "
            "era isso que a checagem de identidade devia fazer."
        )
    if causas.get("parado"):
        partes.append("O que já estava parado não precisava ser desativado.")
    if causas.get("outro"):
        partes.append("Para os demais, a saída do Windows está no diário, item por item.")
    return " ".join(partes)


def _resumo_execucao(acoes: list[dict[str, Any]]) -> str:
    """Uma frase que serve para decidir o próximo passo.

    Antes, 13 falhas viravam “normalmente falta de administrador; o diário diz
    qual”. Isso jogava no usuário a tarefa de abrir um JSON. Agora a causa vem
    contada: “13 falharam por falta de administrador”.
    """
    if not acoes:
        return "Não havia nada para arrumar."
    feitas = [a for a in acoes if a["ok"]]
    falhas = [a for a in acoes if not a["ok"]]
    ram = sum(
        int(str(a.get("ganho") or "0").split()[0] or 0)
        for a in feitas if a["tipo"] == "processo" and a.get("ganho")
    )
    if not feitas:
        partes = [f"Nenhuma das {len(acoes)} ações funcionou."]
    else:
        partes = [f"Arrumado: {len(feitas)} de {len(acoes)} ações."]
        if ram:
            partes.append(f"Devolveu cerca de {ram} MB de RAM fechando processos de sobra.")
    if falhas:
        causas = _contar_causas(acoes)
        nomes = {
            "admin": "por falta de administrador",
            "sumiu": "porque o item já não existia",
            "tempo": "por tempo esgotado",
            "pulado": "puladas de propósito (o PID mudou)",
            "parado": "por já estarem paradas",
            "outro": "por outros motivos",
        }
        detalhe = ", ".join(f"{quantidade} {nomes.get(causa, causa)}" for causa, quantidade in causas.items())
        partes.append(f"{len(falhas)} falharam: {detalhe}.")
        if causas.get("admin"):
            partes.append(
                "Para resolver as de administrador: botão direito no arrumar-pc.bat → "
                "“Executar como administrador”."
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
    parser.add_argument("--ousado", action="store_true", help="Incluir o 'cuidado' que tem volta (Xbox, Teams, Search, hibernação).")
    parser.add_argument("--sem-ponto", action="store_true", help="Não tentar criar ponto de restauração.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    from . import sistema as sistema_mod  # noqa: PLC0415

    token = sistema_mod.token_host()
    if not token:
        print("  Não achei o token em storage/host-token.txt. Suba o JARVIS uma vez.")
        return 1

    if not args.desfazer:
        plano = planejar(ousado=args.ousado)
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
            else executar(
                autorizacao=token,
                plano=planejar(ousado=args.ousado),
                confirmado=True,
                ponto=False if args.sem_ponto else None,
            )
        )
    except ArrumarError as exc:
        print(f"  {exc}")
        return 1
    print()
    print(f"  {resultado.get('resumo')}")
    if resultado.get("instantaneo"):
        print(f"  Instantâneo: {resultado['instantaneo']}")
    ponto = resultado.get("ponto_de_restauracao") or {}
    if ponto.get("criado"):
        print("  Ponto de restauração criado: rstrui (Win+R) volta tudo.")
    elif ponto.get("motivo"):
        print(f"  Ponto de restauração: {ponto['motivo'][:120]}")
    if resultado.get("diario"):
        print(f"  Diário: {resultado['diario']}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
