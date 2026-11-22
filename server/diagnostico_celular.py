"""Scanner do celular: medir, achar o problema e dizer o que resolve (0.92.3).

O dono, com o aparelho na mão: *“vou testar com o meu cll, quero ver se consigo
melhorar e otimizar e ver uns problemas que ele está apresentando — talvez
passando um scanner nele a gente consegue resolver”*.

Isso muda a natureza da resposta. A 0.92.2 (`anatomia.py`) descreve o aparelho:
“é um SM-A346B, Android 14, 8 GB”. Este módulo **julga**: pega a mesma leitura de
somente-leitura e transforma em **achados**, cada um com

- **o que foi medido** (o número, e de onde ele veio);
- **a causa provável**;
- **o que fazer**, em passos que a pessoa executa;
- **o limite** — o que aquilo não resolve.

A regra da casa continua: **nada é alterado no aparelho**. Não há `pm
uninstall`, não há `settings put`, não há `reboot`. O scanner diz *o que* fazer e
*por quê*; quem mexe é o dono, na tela dele. E quando o ganho de uma sugestão
não foi medido, ela **diz isso** em vez de prometer.

O que este módulo mede, e por que cada coisa:

| medida | comando (todos de leitura) | o problema que ela revela |
|---|---|---|
| bateria | `dumpsys battery`, `charge_full`/`charge_full_design` | bateria gasta, aquecida, carregando errado |
| armazenamento | `df -k /data` | aparelho cheio (o maior causador de lentidão real) |
| memória | `/proc/meminfo` | pouca RAM livre, troca constante |
| processos | `ps -A -o RSS,NAME` | app comendo memória em segundo plano |
| térmica | `/sys/class/thermal/thermal_zone*` | aquecimento e *throttling* |
| patch | `ro.build.version.security_patch` | sistema sem correção de segurança há meses |
| reinício | `/proc/uptime`, `ro.boot.bootreason` | aparelho ligado há semanas; reinício travado |
| travamentos | `logcat -b crash -d -t 80` | app que fecha sozinho |
| ajustes | `settings get global window_animation_scale` | animação em 1.0 num aparelho lento |
| apps | `pm list packages -3` | excesso de app instalado (espaço e segundo plano) |
| root/build | `ro.build.tags`, `ro.debuggable`, `which su` | build de teste / aparelho destravado |

Guardas: exige `JARVIS_HOST_CELULAR=1` (a mesma variável do resto do
celular), `adb` instalado e o aparelho **autorizado** na tela. Sem isso, a
resposta é a frase que ensina a chegar lá.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Callable

from . import anatomia, celular

AMBIENTE = anatomia.AMBIENTE_ANDROID
TIMEOUT = 25
MAX_SAIDA = 80_000

# Limiares. Ficam em constantes nomeadas porque a tela, o texto do console e os
# testes precisam concordar — e porque mudar um número aqui muda a explicação.
ARMAZENAMENTO_ALTO = 88.0      # % usado em /data
ARMAZENAMENTO_MEDIO = 78.0
MEMORIA_LIVRE_MINIMA = 12.0    # % de RAM disponível
BATERIA_SAUDE_MINIMA = 80.0    # % da capacidade de fábrica
TEMPERATURA_ZONA_ALTA = 70.0   # °C numa zona térmica
TEMPERATURA_BATERIA_ALTA = 40.0
PATCH_VELHO_DIAS = 240
UPTIME_DIAS = 15
ANIMACAO_CHEIA = 0.9
APP_GASTANDO_MB = 700          # um processo sozinho com isso é achado
RECOMENDACAO_APPS = 40         # terceiros instalados

NAO_FAZ = (
    "Não desinstala, não limpa cache, não muda ajuste, não reinicia e não apaga nada: só mede e explica.",
    "Não recarrega a bateria nem conserta hardware — quando o problema é físico, ele diz que é físico.",
    "Não mede o que o Android não publica: uso por app sem root, saúde de célula de bateria de iPhone, temperatura de GPU de celular.",
    "Não usa número que não saiu do aparelho: toda frase tem a medida que a sustenta.",
)


class DiagnosticoError(RuntimeError):
    """Falha explicada em português, pronta para a tela."""


# ---------------------------------------------------------------------------
# Coleta — tudo de leitura
# ---------------------------------------------------------------------------

# A lista completa do que roda. Um teste a confere palavra por palavra: se
# alguém acrescentar aqui um comando de efeito, o teste cai antes do dono.
COMANDOS: tuple[tuple[str, ...], ...] = (
    ("shell", "getprop"),
    ("shell", "dumpsys", "battery"),
    (
        "shell",
        "for f in /sys/class/power_supply/battery/*; do echo \"$f=$(cat $f 2>/dev/null)\"; done",
    ),
    ("shell", "df", "-k"),
    ("shell", "cat", "/proc/meminfo"),
    ("shell", "cat", "/proc/uptime"),
    ("shell", "ps", "-A", "-o", "RSS,NAME"),
    ("shell", "dumpsys", "diskstats"),
    (
        "shell",
        "for z in /sys/class/thermal/thermal_zone*; do echo \"$(cat $z/type 2>/dev/null):$(cat $z/temp 2>/dev/null)\"; done",
    ),
    ("shell", "settings", "get", "global", "window_animation_scale"),
    ("shell", "settings", "get", "global", "transition_animation_scale"),
    ("shell", "settings", "get", "global", "animator_duration_scale"),
    ("shell", "pm", "list", "packages", "-3"),
    ("shell", "logcat", "-b", "crash", "-d", "-t", "80"),
    ("shell", "which", "su"),
    # 0.92.4 — o sintoma do dono: “a tela trava, o frame fica lento, começa a se
    # mexer sozinho e só para quando desliga e liga a tela”. Três leituras
    # respondem isso: o que tocou por último, o que o sistema registrou de ANR,
    # e quem está desenhando os quadros.
    ("shell", "dumpsys", "input"),
    ("shell", "dumpsys", "window", "displays"),
    ("shell", "logcat", "-b", "system", "-d", "-t", "400"),
    ("shell", "dumpsys", "gfxinfo"),
)

_PALAVRAS_PROIBIDAS = {
    "install", "uninstall", "push", "pull", "reboot", "rm", "mv", "cp",
    "settings",  # o `settings get` é lido à parte, abaixo
    "format", "wipe", "keyevent", "input", "am", "pm", "su",
}


def _auditar_comandos() -> None:
    """Confere a lista na importação — barato, e falha cedo se alguém errar."""
    for comando in COMANDOS:
        corpo = " ".join(comando)
        if comando[:2] == ("shell", "settings"):
            assert corpo.endswith(("get", "window_animation_scale", "transition_animation_scale", "animator_duration_scale")), corpo
            continue
        if comando[:2] == ("shell", "pm"):
            assert comando[2:] == ("list", "packages", "-3"), corpo
            continue
        if comando[:2] in {("shell", "dumpsys"), ("shell", "logcat")}:
            # `dumpsys` sem argumento de escrita só imprime estado; `logcat -d`
            # lê o buffer e encerra. Nenhum dos dois altera o aparelho.
            assert "clear" not in comando and "set" not in comando, corpo
            continue
        if comando[:3] == ("shell", "which", "su"):
            # `which su` só pergunta se existe binário de superusuário. Não
            # executa `su` — e é a única leitura sobre root que o módulo faz.
            continue
        for palavra in corpo.split():
            assert palavra not in _PALAVRAS_PROIBIDAS, f"comando de efeito na lista: {corpo}"


_auditar_comandos()


def ligado() -> bool:
    return celular.ligado()


def _agora(agora: datetime | None = None) -> datetime:
    return agora or datetime.now(timezone.utc)


def _por_que_nao_apareceu() -> str:
    """O `adb` não viu nada — mas o Windows pode estar vendo. Diz qual é o caso.

    0.95.2 — esta mensagem era uma frase só (“confira o cabo, ligue a Depuração
    USB”), e ela mandou o dono conferir um cabo que estava bom: a pasta “A34”
    aparecia no Explorer com o aparelho conectado. `celular.windows_ve()` já
    sabia separar driver faltando de cabo solto desde a 0.92.x — só não era
    consultado aqui.

    A ordem importa: primeiro o que o Windows vê (é o dado mais barato e o mais
    decisivo), e só depois as hipóteses genéricas.
    """
    try:
        sonda = celular.windows_ve()
    except Exception:  # noqa: BLE001 - sonda de USB não pode derrubar o diagnóstico
        sonda = {"consulta": False}

    if sonda.get("consulta"):
        telefones = sonda.get("telefones") or []
        if sonda.get("com_problema"):
            return (
                "O Windows vê o celular na USB, mas com problema de driver — é por isso que o "
                "`adb` não enxerga. Instale o **Samsung USB Driver for Mobile Phones** "
                "(o mesmo que o Kies/ Smart Switch instala), desconecte e reconecte o cabo. "
                "Depois disso o aparelho aparece em `adb devices`."
            )
        if celular.sem_driver_samsung(telefones):
            return (
                "O Windows vê um aparelho Samsung na USB, mas com nome genérico "
                "(“USB Composite Device” / “MTP”) — é o driver da Samsung que falta, e é "
                "por isso que o `adb` não o vê. Instale o **Samsung USB Driver for Mobile "
                "Phones**, reconecte o cabo e rode de novo. A Depuração USB pode já estar certa."
            )
        if telefones:
            return (
                "O Windows vê o celular, mas o `adb` não. Na tela do aparelho, confira: "
                "(1) Opções do desenvolvedor → **Depuração USB** ligada; "
                "(2) **Depuração sem fio** desligada (as duas brigam pela mesma porta); "
                "(3) o aviso “Permitir depuração USB?” aceito — e marque “Sempre permitir "
                "deste computador”. Se o aviso não aparece, desligue e religue a Depuração USB "
                "com o cabo conectado."
            )
        desconhecidos = sonda.get("desconhecidos") or []
        if desconhecidos:
            return (
                "O Windows vê um dispositivo USB que não consegue identificar (falha de "
                "descritor) — troque a porta e o cabo antes de qualquer outra coisa. Se "
                "persistir, é o driver: **Samsung USB Driver for Mobile Phones**."
            )
        genericos = sonda.get("genericos") or []
        if genericos:
            return (
                "O Windows **não** vê nenhum celular na USB — ele vê outros dispositivos "
                "(hub, teclado). Então é cabo, porta ou o aparelho não está conectado: "
                "use cabo de dados, troque a porta e, com o celular desbloqueado, veja se "
                "aparece a pergunta “Permitir depuração USB?”."
            )

    return (
        "Nenhum Android apareceu. Confira o cabo (tem de ser de dados, não só de carga), "
        "ligue a Depuração USB em Opções do desenvolvedor e aceite o aviso na tela."
    )


def _serial(alvo: str, rodar: Callable[[list[str]], tuple[int, str, str]]) -> str:
    escolhido = (alvo or "").strip()
    if escolhido:
        return escolhido
    conectados = anatomia.aparelhos(rodar=rodar)
    prontos = [a for a in conectados if a.get("estado") == "device"]
    if not prontos:
        if conectados:
            raise DiagnosticoError(
                "O aparelho está na USB, mas não autorizou este computador. Desbloqueie a tela "
                "e toque em “Permitir” no aviso “Permitir depuração USB?”."
            )
        raise DiagnosticoError(_por_que_nao_apareceu())
    return prontos[0]["serial"]


def coletar(
    alvo: str = "",
    *,
    rodar: Callable[[list[str]], tuple[int, str, str]] | None = None,
) -> dict[str, Any]:
    """Roda a lista de leitura e devolve cada saída crua, com os comandos usados."""
    if not celular.ligado():
        raise DiagnosticoError(
            "O scanner do celular está desligado. Acrescente `set JARVIS_HOST_CELULAR=1` no "
            "iniciar-jarvis.bat, feche e abra de novo."
        )
    executor = rodar or (lambda argumentos: anatomia._rodar(argumentos, timeout=TIMEOUT))  # noqa: SLF001
    try:
        adb = anatomia._adb()  # noqa: SLF001 - mesma mensagem de “Preparar celular”
    except anatomia.AnatomiaError as exc:
        # O erro do `adb` ausente é do outro módulo; aqui ele vira o erro deste,
        # para a tela e o console tratarem um só tipo.
        raise DiagnosticoError(str(exc)) from exc
    serial = _serial(alvo, executor)

    saidas: dict[str, str] = {}
    falhas: list[str] = []
    for comando in COMANDOS:
        chave = " ".join(comando[1:])
        try:
            codigo, saida, erro = executor([adb, "-s", serial, *comando])
        except anatomia.AnatomiaError as exc:
            falhas.append(f"“{chave}”: {exc}")
            continue
        if codigo != 0 and not saida:
            falhas.append(f"“{chave}”: {(erro or 'sem resposta').strip()[:200]}")
            continue
        saidas[chave] = anatomia._cortar(saida, MAX_SAIDA)  # noqa: SLF001
    return {
        "serial": serial,
        "saidas": saidas,
        "falhas": falhas,
        "comandos": [" ".join(("adb", "-s", serial, *c)) for c in COMANDOS],
    }


# ---------------------------------------------------------------------------
# Leitura das saídas — funções puras, testáveis sem aparelho
# ---------------------------------------------------------------------------

def ler_propriedades(texto: str) -> dict[str, str]:
    return anatomia._propriedades(texto)  # noqa: SLF001 - mesma sintaxe [chave]: [valor]


def ler_dumpsys_battery(texto: str) -> dict[str, str]:
    campos: dict[str, str] = {}
    for linha in (texto or "").splitlines():
        if ":" not in linha:
            continue
        chave, valor = linha.split(":", 1)
        campos[chave.strip()] = valor.strip()
    return campos


def ler_power_supply(texto: str) -> dict[str, str]:
    """`/sys/class/power_supply/battery/*` — o único lugar com ciclo e capacidade."""
    campos: dict[str, str] = {}
    for linha in (texto or "").splitlines():
        if "=" not in linha:
            continue
        caminho, valor = linha.split("=", 1)
        campos[caminho.rsplit("/", 1)[-1].strip()] = valor.strip()
    return campos


def ler_df(texto: str) -> dict[str, dict[str, float]]:
    """Uso por ponto de montagem, em bytes e em porcentagem calculada de verdade.

    O `df` do Android imprime `Use%` arredondado; a conta com total/disponível é
    mais fiel e serve para o limiar.
    """
    pontos: dict[str, dict[str, float]] = {}
    for linha in (texto or "").splitlines():
        partes = linha.split()
        if len(partes) < 6 or not partes[0].startswith("/dev/"):
            continue
        try:
            total = float(partes[1]) * 1024
            livre = float(partes[3]) * 1024
        except ValueError:
            continue
        if total <= 0:
            continue
        ponto = partes[-1]
        usado = total - livre
        pontos[ponto] = {
            "total": total,
            "livre": livre,
            "usado": usado,
            "pct": round(usado / total * 100, 1),
        }
    return pontos


def ler_meminfo(texto: str) -> dict[str, int]:
    valores: dict[str, int] = {}
    for linha in (texto or "").splitlines():
        partes = linha.replace(":", " ").split()
        if len(partes) >= 2 and partes[1].isdigit():
            valores[partes[0]] = int(partes[1]) * 1024
    return valores


def ler_uptime(texto: str) -> float:
    """Segundos desde o boot (`/proc/uptime` = “12345.67 999.99”)."""
    try:
        return float((texto or "").split()[0])
    except (IndexError, ValueError):
        return 0.0


def ler_top_processos(texto: str, limite: int = 12) -> list[dict[str, Any]]:
    """`ps -A -o RSS,NAME` — os que mais ocupam memória.

    O Android varia o formato entre versões (`RSS` em KB, nome com espaço). O
    parser aceita linha cujo primeiro campo é número e descarta o resto — melhor
    uma lista curta e verdadeira do que uma longa e inventada.
    """
    processos: list[dict[str, Any]] = []
    for linha in (texto or "").splitlines():
        partes = linha.split(None, 1)
        if len(partes) != 2 or not partes[0].isdigit():
            continue
        processos.append({"nome": partes[1].strip(), "kb": int(partes[0])})
    processos.sort(key=lambda item: item["kb"], reverse=True)
    return processos[:limite]


def ler_termica(texto: str) -> list[dict[str, Any]]:
    sensores: list[dict[str, Any]] = []
    for linha in (texto or "").splitlines():
        if ":" not in linha:
            continue
        tipo, valor = linha.split(":", 1)
        valor = valor.strip()
        if not valor.lstrip("-").isdigit():
            continue
        numero = int(valor)
        celsius = numero / 1000 if abs(numero) > 1000 else float(numero)
        sensores.append({"nome": tipo.strip() or "sensor", "c": round(celsius, 1)})
    sensores.sort(key=lambda item: item["c"], reverse=True)
    return sensores


def ler_escala(valor: str) -> float | None:
    try:
        return float((valor or "").strip())
    except ValueError:
        return None


def ler_crash(texto: str) -> list[str]:
    """Nomes de pacote que aparecem num `FATAL EXCEPTION` do buffer de crash."""
    pacotes: list[str] = []
    for linha in (texto or "").splitlines():
        achado = re.search(r"Process: ([A-Za-z0-9_.]+)", linha) or re.search(
            r"FATAL EXCEPTION[^\n]*", linha
        )
        if not achado:
            continue
        nome = achado.group(1) if achado.groups() else ""
        if nome and nome not in pacotes:
            pacotes.append(nome)
    return pacotes[:8]


def ler_apps(texto: str) -> list[str]:
    return sorted(
        linha.strip().removeprefix("package:")
        for linha in (texto or "").splitlines()
        if linha.strip().startswith("package:")
    )


_RE_JANELA = re.compile(r"m(?:CurrentFocus|FocusedApp|FocusedWindow)=(.+)")


def ler_janela_em_foco(texto: str) -> str:
    """Qual janela está em foco — é ela que recebe o toque.

    O `dumpsys window displays` publica a linha inteira (`mCurrentFocus=Window{abc
    u0 com.app/com.app.MainActivity}`); o formato muda entre fabricantes, então o
    que vale é achar `pacote/atividade` em qualquer posição da linha.
    """
    for linha in (texto or "").splitlines():
        achado = _RE_JANELA.search(linha)
        if not achado:
            continue
        valor = achado.group(1).strip().rstrip("}")
        if not valor or valor.startswith("null"):
            continue
        # Primeiro tenta `u0 pacote/atividade` (o formato do Android moderno).
        dentro = re.search(r"\bu0\s+([A-Za-z0-9_.]+/[A-Za-z0-9_.$]+)", valor)
        if dentro:
            return dentro.group(1)
        # Senão, qualquer `pacote/atividade` solto na linha.
        solto = re.search(r"([A-Za-z0-9_.]+/[A-Za-z0-9_.$]+)", valor)
        if solto:
            return solto.group(1)
    return ""


def ler_input_dumpsys(texto: str) -> dict[str, Any]:
    """O que o `dumpsys input` diz sobre o toque: dispositivo e último evento.

    Interessa o **dispositivo de entrada** (nome do controlador de toque) e há
    quanto tempo foi o último toque. Sem esses dois, não dá para separar “a tela
    se mexeu sozinha” de “o app reagiu a um toque que chegou atrasado”.
    """
    nomes: list[str] = []
    for linha in (texto or "").splitlines():
        achado = re.search(r"Name:\s*['\"]?([^'\"\n]+)", linha)
        if achado:
            nome = achado.group(1).strip()
            if nome and nome not in nomes:
                nomes.append(nome)
    return {"dispositivos": nomes[:8]}


def ler_anr(texto: str) -> list[dict[str, str]]:
    """`ANR in <pacote>` e `Reason:` — o app que parou de responder.

    ANR é o “não está respondendo” do Android: a tela trava, o toque some ou é
    entregue tarde. O motivo separa “app travado” de “sistema sobrecarregado”.
    """
    achados: list[dict[str, str]] = []
    linhas = (texto or "").splitlines()
    for indice, linha in enumerate(linhas):
        achado = re.search(r"ANR in ([A-Za-z0-9_.]+)", linha)
        if not achado:
            continue
        pacote = achado.group(1)
        motivo = ""
        for seguinte in linhas[indice + 1:indice + 4]:
            if "Reason:" in seguinte:
                motivo = seguinte.split("Reason:", 1)[1].strip()
                break
        if not any(item["pacote"] == pacote for item in achados):
            achados.append({"pacote": pacote, "motivo": motivo})
    return achados[:6]


def ler_gfxinfo(texto: str) -> dict[str, Any]:
    """Tempo de desenho por app. É o número por trás de “o frame fica lento”.

    O `dumpsys gfxinfo` publica `Total frames rendered`, `Janky frames` e o
    percentual de quadros lentos por pacote. Só é lido o pacote com mais quadros
    travados — o resto seria lista para rolar.
    """
    atual = ""
    pacotes: list[dict[str, Any]] = []
    for linha in (texto or "").splitlines():
        achado = re.search(r"(?<!\S)([A-Za-z][A-Za-z0-9_.]*)\s*/\s*\d+", linha)
        if achado:
            atual = achado.group(1)
            continue
        total = re.search(r"Total frames rendered:\s*(\d+)", linha)
        janky = re.search(r"Janky frames:\s*(\d+)\s*\(([\d.]+)%\)", linha)
        if total and atual:
            pacotes.append({"pacote": atual, "quadros": int(total.group(1))})
        elif janky and pacotes:
            pacotes[-1].update(
                {"travados": int(janky.group(1)), "pct_travados": float(janky.group(2))}
            )
    validos = [p for p in pacotes if p.get("quadros")]
    if not validos:
        return {}
    pior = max(validos, key=lambda p: (p.get("pct_travados", 0), p.get("travados", 0)))
    return pior


def _dias_desde(data_iso: str, agora: datetime) -> int | None:
    texto = (data_iso or "").strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", texto):
        return None
    try:
        quando = datetime.strptime(texto, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return max(0, (agora - quando).days)


def _mb(bytes_: float) -> str:
    return f"{bytes_ / (1024 * 1024):,.0f} MB".replace(",", ".")


def _gb(bytes_: float) -> str:
    return f"{bytes_ / (1024 ** 3):,.1f} GB".replace(",", ".").replace(".", ",")


# ---------------------------------------------------------------------------
# Julgamento
# ---------------------------------------------------------------------------

def _problema(
    identificador: str,
    gravidade: str,
    titulo: str,
    medido: str,
    causa: str,
    fazer: list[str],
    limite: str,
) -> dict[str, Any]:
    return {
        "id": identificador,
        "gravidade": gravidade,
        "titulo": titulo,
        "medido": medido,
        "causa": causa,
        "o_que_fazer": fazer,
        "limite": limite,
    }


def _otimizacao(
    identificador: str,
    titulo: str,
    ganho: str,
    como: list[str],
    risco: str,
    medido: bool,
) -> dict[str, Any]:
    return {
        "id": identificador,
        "titulo": titulo,
        "ganho": ganho,
        "como": como,
        "risco": risco,
        "medido": medido,
    }


def analisar(
    medido: dict[str, Any],
    *,
    agora: datetime | None = None,
) -> dict[str, Any]:
    """Transforma a leitura em achados. Nenhum número entra sem ter sido medido."""
    quando = _agora(agora)
    saidas: dict[str, str] = medido.get("saidas", {})
    props = ler_propriedades(saidas.get("getprop", ""))
    bateria = ler_dumpsys_battery(saidas.get("dumpsys battery", ""))
    energia = ler_power_supply(
        next((v for k, v in saidas.items() if k.startswith("for f in /sys/class/power_supply")), "")
    )
    discos = ler_df(saidas.get("df -k", ""))
    memoria = ler_meminfo(saidas.get("cat /proc/meminfo", ""))
    uptime = ler_uptime(saidas.get("cat /proc/uptime", ""))
    processos = ler_top_processos(saidas.get("ps -A -o RSS,NAME", ""))
    sensores = ler_termica(
        next((v for k, v in saidas.items() if k.startswith("for z in /sys/class/thermal")), "")
    )
    animacao = ler_escala(saidas.get("settings get global window_animation_scale", ""))
    apps = ler_apps(saidas.get("pm list packages -3", ""))
    crashes = ler_crash(saidas.get("logcat -b crash -d -t 80", ""))
    # 0.92.4 — sintoma de tela: trava, frame lento, “se mexe sozinho”, e o
    # desligar/ligar da tela resolve. Três medidas separam as causas: ANR (app que
    # não responde), quadro travado (o desenho atrasou) e toque fantasma (entrada
    # chegando sem dedo na tela).
    anrs = ler_anr(saidas.get("logcat -b system -d -t 400", ""))
    gfx = ler_gfxinfo(saidas.get("dumpsys gfxinfo", ""))
    janela = ler_janela_em_foco(saidas.get("dumpsys window displays", ""))
    entrada = ler_input_dumpsys(saidas.get("dumpsys input", ""))
    root = (saidas.get("which su", "") or "").strip()
    # 0.95.2 — “sem resposta” é o que um `which` **bem-sucedido** devolve quando o
    # binário não existe (código 1, saída vazia). O `coletar` só guarda a chave
    # quando `codigo != 0 and not saida` for falso; como o `which` não achou nada,
    # a chave ficava de fora e a varredura anunciava “«which su»: sem resposta” —
    # um alarme onde o correto é **informação** (“não tem su”, que é bom).
    su_conferido = "which su" in saidas
    root_texto = (
        "Não há binário de `su` no PATH — não é alarme, é o normal num aparelho sem root."
        if su_conferido and not root
        else (f"`which su` respondeu: {root}." if root else "")
    )

    problemas: list[dict[str, Any]] = []
    otimizacoes: list[dict[str, Any]] = []
    secoes: list[dict[str, Any]] = []

    # ---- armazenamento
    dados = discos.get("/data") or discos.get("/storage/emulated") or {}
    if dados:
        secoes.append({
            "id": "armazenamento",
            "titulo": "Armazenamento",
            "itens": [
                {"rotulo": "Usado em /data", "valor": f"{dados['pct']:.0f}% ({_gb(dados['usado'])})"},
                {"rotulo": "Livre", "valor": _gb(dados["livre"])},
                {"rotulo": "Total", "valor": _gb(dados["total"])},
            ],
        })
        if dados["pct"] >= ARMAZENAMENTO_ALTO:
            problemas.append(_problema(
                "armazenamento-cheio",
                "alta",
                "O armazenamento está quase cheio",
                f"{dados['pct']:.0f}% de /data usado; restam {_gb(dados['livre'])}.",
                "Android fica lento quando falta espaço: o sistema gasta mais para reorganizar arquivos "
                "e os apps não conseguem gravar cache.",
                [
                    "Veja quem ocupa espaço: Ajustes → Armazenamento (a lista é por categoria e por app).",
                    "Apague vídeos baixados e downloads antigos: Ajustes → Armazenamento → Vídeos/Downloads.",
                    "Limpe o cache dos apps grandes: Ajustes → Apps → [app] → Armazenamento → Limpar cache.",
                    "Mova fotos para o PC ou para um cartão microSD (o JARVIS tem `resgatar-cartao.bat`).",
                    "Desinstale o que não usa — os instalados aparecem em “Aplicativos fora da loja do fabricante”.",
                ],
                "Apagar cache não devolve espaço de foto; e app do sistema não sai sem root.",
            ))
        elif dados["pct"] >= ARMAZENAMENTO_MEDIO:
            problemas.append(_problema(
                "armazenamento-apertado",
                "media",
                "O armazenamento está apertado",
                f"{dados['pct']:.0f}% usado; restam {_gb(dados['livre'])}.",
                "Ainda não trava, mas abaixo de ~10% livres o Android começa a ficar lento.",
                [
                    "Reserve uns 10 GB livres: é o que o sistema usa para atualizar app e gravar cache.",
                    "Comece pelos vídeos e pelos apps que você não abre há meses.",
                ],
                "Não é urgente — mas é o que estraga a sensação de velocidade primeiro.",
            ))

    # ---- memória
    total_mem = memoria.get("MemTotal", 0)
    disponivel = memoria.get("MemAvailable", 0)
    if total_mem:
        pct_livre = disponivel / total_mem * 100
        secoes.append({
            "id": "memoria",
            "titulo": "Memória",
            "itens": [
                {"rotulo": "Total", "valor": _gb(total_mem)},
                {"rotulo": "Disponível", "valor": f"{_gb(disponivel)} ({pct_livre:.0f}%)"},
                {"rotulo": "Swap/ZRAM", "valor": _gb(memoria.get("SwapTotal", 0)) if memoria.get("SwapTotal") else "sem"},
            ],
        })
        if pct_livre < MEMORIA_LIVRE_MINIMA:
            problemas.append(_problema(
                "memoria-baixa",
                "alta" if pct_livre < 6 else "media",
                "Sobrou pouca memória livre",
                f"{pct_livre:.1f}% da RAM disponível ({_gb(disponivel)} de {_gb(total_mem)}).".replace(".", ","),
                "Com pouca RAM livre, o Android fecha app em segundo plano e reabre do zero — é o "
                "“voltei no WhatsApp e ele carregou tudo de novo”.",
                [
                    "Reinicie o aparelho: é a única limpeza de memória que realmente funciona.",
                    "Veja os apps que mais ocupam memória na seção “Quem está usando a memória” e force a parada dos que não usa.",
                    "Desinstale os que você não abre — app instalado volta a subir sozinho.",
                ],
                "Nenhum “limpador de RAM” ajuda: app de limpeza costuma gastar mais memória do que libera.",
            ))

    # ---- processos pesados
    pesados = [p for p in processos if p["kb"] * 1024 >= APP_GASTANDO_MB * 1024 * 1024]
    if processos:
        secoes.append({
            "id": "processos",
            "titulo": "Quem está usando a memória",
            "itens": [
                {"rotulo": p["nome"], "valor": _mb(p["kb"] * 1024)} for p in processos[:8]
            ],
        })
        for processo in pesados[:3]:
            otimizacoes.append(_otimizacao(
                f"fechar-{processo['nome']}",
                f"Fechar {processo['nome']} quando não estiver usando",
                f"libera cerca de {_mb(processo['kb'] * 1024)} de memória",
                [
                    "Ajustes → Apps → " + processo["nome"] + " → Forçar parada.",
                    "Se ele volta sozinho, é porque tem permissão de segundo plano: Ajustes → Apps → "
                    + processo["nome"] + " → Bateria → Restringir.",
                ],
                "Forçar parada só limpa até o app abrir de novo. Restringir bateria pode atrasar notificação dele.",
                True,
            ))

    # ---- bateria
    saude = energia.get("health", "") or bateria.get("health", "")
    cheia = energia.get("charge_full", "")
    projeto = energia.get("charge_full_design", "")
    nivel = bateria.get("level", "")
    temperatura_bateria = bateria.get("temperature", "")
    ciclos = energia.get("cycle_count", "")
    itens_bateria: list[dict[str, str]] = []
    if nivel.isdigit():
        itens_bateria.append({"rotulo": "Carga", "valor": f"{nivel}%"})
    if saude:
        itens_bateria.append({"rotulo": "Saúde (do sistema)", "valor": anatomia.SAUDE_BATERIA.get(saude, saude)})
    if cheia.isdigit() and projeto.isdigit() and int(projeto) > 0:
        pct = int(cheia) / int(projeto) * 100
        itens_bateria.append({
            "rotulo": "Capacidade de fábrica",
            "valor": f"{pct:.0f}% ({int(cheia) // 1000} mAh de {int(projeto) // 1000} mAh)",
        })
    if ciclos.isdigit():
        itens_bateria.append({"rotulo": "Ciclos de carga", "valor": ciclos})
    if temperatura_bateria.lstrip("-").isdigit():
        itens_bateria.append({"rotulo": "Temperatura", "valor": anatomia._decimos_celsius(int(temperatura_bateria))})  # noqa: SLF001
    if itens_bateria:
        secoes.append({"id": "bateria", "titulo": "Bateria", "itens": itens_bateria})

    if cheia.isdigit() and projeto.isdigit() and int(projeto) > 0:
        pct_bateria = int(cheia) / int(projeto) * 100
        if pct_bateria < BATERIA_SAUDE_MINIMA:
            problemas.append(_problema(
                "bateria-gasta",
                "alta" if pct_bateria < 70 else "media",
                "A bateria já perdeu capacidade",
                f"Carrega até {pct_bateria:.0f}% do que carregava nova "
                f"({int(cheia) // 1000} mAh de {int(projeto) // 1000} mAh).",
                "Isso é desgaste químico normal: a célula perde capacidade a cada ciclo.",
                [
                    "A troca da bateria em assistência técnica é a única correção — nenhum app “recalibra” célula gasta.",
                    "Enquanto isso: reduza brilho, desligue 5G onde não usa e evite carregar até 100% todo dia.",
                ],
                "Ajuste de software melhora a autonomia em minutos, não devolve os mAh perdidos.",
            ))
    if saude and saude in {"3", "4", "5", "6", "7"}:
        problemas.append(_problema(
            "bateria-saude",
            "alta",
            "O sistema reporta problema na bateria",
            f"Estado informado pelo Android: {anatomia.SAUDE_BATERIA.get(saude, saude)}.",
            "Pode ser célula inchada, sensor descalibrado ou falha de carga — o Android marca pelo sensor de tensão/temperatura.",
            [
                "Leve a uma assistência: é o único caminho seguro.",
                "Não deixe carregando a noite toda até o diagnóstico.",
            ],
            "O JARVIS não mede a célula por dentro; só repete o que o sistema declarou.",
        ))
    if temperatura_bateria.lstrip("-").isdigit():
        temp = int(temperatura_bateria) / 10
        if temp >= TEMPERATURA_BATERIA_ALTA and bateria.get("status") == "2":
            problemas.append(_problema(
                "bateria-quente-carregando",
                "media",
                "A bateria está quente enquanto carrega",
                f"{anatomia._decimos_celsius(int(temperatura_bateria))} carregando o aparelho.".replace(".", ","),  # noqa: SLF001
                "Carga rápida com capa grossa ou aparelho no sol esquenta a célula — e calor é o que mais gasta bateria.",
                [
                    "Tire a capa ao carregar e não deixe o aparelho no sol ou sobre a cama.",
                    "Se esquentar sem carregar e sem app aberto, é achado de assistência.",
                ],
                "Esquentar um pouco carregando é normal; o limite aqui é 40 °C.",
            ))

    # ---- térmica
    if sensores:
        quente = [s for s in sensores if s["c"] >= TEMPERATURA_ZONA_ALTA]
        secoes.append({
            "id": "termica",
            "titulo": "Sensores térmicos",
            "itens": [{"rotulo": s["nome"], "valor": f"{s['c']:.1f} °C".replace(".", ",")} for s in sensores[:6]],
        })
        if quente:
            problemas.append(_problema(
                "aquecendo",
                "alta",
                "O aparelho está quente agora",
                f"{len(quente)} sensor(es) acima de {TEMPERATURA_ZONA_ALTA:.0f} °C — o maior em "
                f"{max(s['c'] for s in quente):.0f} °C.",
                "Acima disso o Android reduz a velocidade do processador (throttling) para não queimar: "
                "o travamento que você sente é proteção, não defeito.",
                [
                    "Feche o app que está aberto e deixe o aparelho esfriar fora da capa.",
                    "Veja se algum app está em segundo plano: Ajustes → Bateria → Uso por app.",
                    "Se esquenta parado, com a tela ligada e nada aberto, é caso de assistência.",
                ],
                "Resfriar com geladeira ou ventilador úmido estraga o aparelho — não faça.",
            ))

    # ---- sistema / segurança
    patch = props.get("ro.build.version.security_patch", "")
    dias_patch = _dias_desde(patch, quando)
    itens_sistema = [
        {"rotulo": "Versão do sistema", "valor": f"Android {props.get('ro.build.version.release', '?')} (API {props.get('ro.build.version.sdk', '?')})"},
        {"rotulo": "Patch de segurança", "valor": f"{patch or 'não informado'}" + (f" — {dias_patch} dias" if dias_patch is not None else "")},
    ]
    if uptime:
        itens_sistema.append({"rotulo": "Ligado há", "valor": f"{uptime / 86400:.1f} dias".replace(".", ",")})
    secoes.append({"id": "sistema", "titulo": "Sistema", "itens": itens_sistema})

    if dias_patch is not None and dias_patch >= PATCH_VELHO_DIAS:
        problemas.append(_problema(
            "patch-antigo",
            "media",
            "O sistema não recebe correção de segurança há meses",
            f"Último patch: {patch} ({dias_patch} dias atrás).",
            "Atualização de Android depende do fabricante e da operadora; o aparelho parado de receber é normal depois de alguns anos.",
            [
                "Ajustes → Atualização de software → Baixar e instalar.",
                "Se não aparecer nada, o fabricante encerrou o suporte deste modelo — não há como forçar por fora sem root.",
            ],
            "Isso não deixa o aparelho lento; é risco de segurança.",
        ))
    if uptime and uptime / 86400 >= UPTIME_DIAS:
        otimizacoes.append(_otimizacao(
            "reiniciar",
            "Reiniciar o aparelho",
            "devolve memória, encerra serviço travado e pode destravar a sensação de lentidão",
            [
                "Segure o botão de liga/desliga e toque em Reiniciar.",
                "Confira antes se tem algo não salvo no app que você está usando.",
            ],
            "Nada é perdido: reiniciar não apaga foto nem app. Só fecha o que estava aberto.",
            True,
        ))

    # ---- animação
    if animacao is not None and animacao >= ANIMACAO_CHEIA:
        otimizacoes.append(_otimizacao(
            "animacao",
            "Diminuir a animação do sistema",
            "deixa o aparelho com sensação de mais rápido (não muda desempenho medido)",
            [
                "Ligue as Opções do desenvolvedor: Ajustes → Sobre o telefone → Número da versão (7 toques).",
                "Em Opções do desenvolvedor, ponha Escala da animação de janela, de transição e de animação "
                "do Animator em 0,5x.",
            ],
            "Se algo parecer estranho, volte para 1x. Isso não ganha bateria nem velocidade real.",
            False,
        ))

    # ---- apps
    if apps:
        secoes.append({
            "id": "apps",
            "titulo": "Aplicativos fora da loja do fabricante",
            "itens": [
                {"rotulo": "Total instalado", "valor": str(len(apps))},
                # 0.95.2 — aqui saía a lista dos 12 primeiros pacotes, e ela
                # aparecia na tela **e no arquivo** que o dono manda para outra
                # pessoa. O nome do que ele instalou é vida privada; o número
                # não é. Quem precisa do detalhe vê em Ajustes → Apps.
                {"rotulo": "Onde ver quais", "valor": "Ajustes → Apps (ordene por tamanho)"},
            ],
        })
        if len(apps) >= RECOMENDACAO_APPS:
            otimizacoes.append(_otimizacao(
                "menos-apps",
                "Desinstalar os apps que você não abre",
                f"libera espaço e reduz processo em segundo plano — são {len(apps)} apps que você "
                "mesmo instalou (apps de fábrica não entram nesta conta)",
                [
                    "Ajustes → Apps: ordene por tamanho e veja quais não abre há meses.",
                    "Desinstale um por vez e veja se algo que você usa deixa de funcionar.",
                ],
                "Desinstalar é irreversível para os dados do app. Tire o backup do que importa antes.",
                True,
            ))

    # ---- travamentos
    if crashes:
        problemas.append(_problema(
            "app-travando",
            "media",
            "Há app fechando sozinho",
            "O sistema registrou travamento de: " + ", ".join(crashes[:4]) + ".",
            "Travamento de app é quase sempre dado corrompido, versão incompatível ou permissão negada.",
            [
                "Atualize o app na loja.",
                "Se continuar: Ajustes → Apps → [app] → Armazenamento → Limpar cache (não “Limpar dados”, "
                "que apaga sua conta e conversas).",
                "Como último recurso, desinstale e instale de novo.",
            ],
            "O log mostra qual app travou, não o motivo interno — para isso seria preciso o relatório completo.",
        ))

    # ---- destravado / build de teste
    if props.get("ro.build.tags", "").strip() == "test-keys":
        problemas.append(_problema(
            "build-de-teste",
            "media",
            "O sistema é assinado com chave de teste",
            "`ro.build.tags` = test-keys.",
            "Isso indica ROM modificada ou build de engenharia — não é o Android de fábrica.",
            [
                "Se você instalou uma ROM, foi isso. Se não instalou, alguém instalou antes de você.",
                "ROM modificada costuma vir sem as correções do fabricante e pode quebrar app de banco.",
            ],
            "Não é defeito por si só; é informação que muda a origem dos outros problemas.",
        ))
    if root:
        problemas.append(_problema(
            "root",
            "baixa",
            "O aparelho tem root",
            root_texto,
            "Acesso de superusuário instalado (Magisk ou similar).",
            [
                "Se você não instalou, é bom saber: root permite que qualquer app peça acesso total.",
                "App de banco e de pagamento podem recusar o aparelho por isso.",
            ],
            "O JARVIS nunca usa root: nem para ler, nem para “otimizar”.",
        ))

    # ---- tela: trava, frame lento, “se mexe sozinho” (0.92.4)
    #
    # O relato do dono, palavra por palavra: “as vezes minha tela trava ou ta
    # lenta o frame meio q fica lento do nada ou ele comeca a se mexer sozinho
    # so para quando desliga a tela e ligo de volta”.
    #
    # A sequência é a assinatura de uma causa só: o controlador de toque entrega
    # evento que ninguém pediu (fantasma), o Android espera o app responder
    # (ANR), a fila de desenho atrasa (frame lento) e o app reage a toques que
    # chegaram fora de hora (a tela “se mexe”). Desligar a tela desliga o
    # controlador de toque e esvazia a fila — e é por isso que só isso resolve.
    #
    # Aqui ficam TRÊS achados possíveis, e cada um exige medida própria. Se o
    # aparelho não publicou, a resposta não inventa: diz que não viu.
    tela = janela or ""
    if anrs:
        pior = anrs[0]
        motivos = "; ".join(sorted({a["motivo"] for a in anrs if a["motivo"]}))
        problemas.append(_problema(
            "app-nao-responde",
            "alta",
            "Um app parou de responder e travou a tela",
            f"ANR registrado em: {', '.join(a['pacote'] for a in anrs[:3])}"
            + (f" — motivo: {motivos}" if motivos else " (o sistema não escreveu o motivo)."),
            "ANR é o “não está respondendo” do Android. Enquanto a janela daquele app está presa, "
            "o toque é engolido ou entregue minutos depois — o que aparece como tela travada e, em "
            "seguida, como toque em lugar nenhum.",
            [
                f"Se o app do ANR é {pior['pacote']}: atualize na loja e, se repetir, "
                "Ajustes → Apps → [app] → Armazenamento → Limpar cache.",
                "Se o ANR repete em apps diferentes, o problema não é o app — é o sistema "
                "sobrecarregado: veja memória e armazenamento nos outros achados.",
                "Se o motivo citar “Input dispatching timed out”, o toque chegou e o app não "
                "terminou de desenhar: é a mesma cadeia do frame lento, abaixo.",
            ],
            "O ANR diz qual app travou e o motivo registrado; o motivo interno do travamento "
            "exigiria o relatório completo e root.",
        ))
    if gfx and gfx.get("quadros", 0) >= 300 and gfx.get("pct_travados", 0) >= 10:
        problemas.append(_problema(
            "frame-lento",
            "alta" if gfx["pct_travados"] >= 25 else "media",
            "Os quadros estão travando",
            f"{gfx['pacote']}: {gfx.get('travados', 0):,} de {gfx['quadros']:,} quadros travados "
            f"({gfx['pct_travados']:.0f}%).".replace(",", "."),
            "Quadro “travado” (janky) é o quadro que passou do tempo de 16 ms. Acima de ~10% o "
            "olho percebe como lentidão no rolar e no toque; acima de 25% a tela parece parar.",
            [
                f"No {gfx['pacote']}: Ajustes → Apps → Armazenamento → Limpar cache; se continuar, "
                "reinstale o app.",
                "Feche os apps que ficam em segundo plano — o frame também atrasa quando falta memória.",
                "Se a proporção é alta em QUALQUER app aberto, inclusive Ajustes, o problema é o "
                "sistema ou o hardware, não um app específico: os outros achados dizem qual.",
            ],
            "O número é do período que o Android guardou desde o último reinício; não mede "
            "o que aconteceu antes disso.",
        ))
    if sensores and max(s["c"] for s in sensores) >= 70:
        # Já existe o achado “aquecendo”; aqui a ligação com o sintoma, porque é
        # ela que explica “do nada”. Só entra quando o aparelho está quente.
        otimizacoes.append(_otimizacao(
            "esfriar-para-destravar",
            "Deixar o aparelho esfriar antes de julgar a lentidão",
            "o travamento por calor (throttling) some quando a temperatura cai",
            [
                "Tire a capa, feche o app pesado e deixe o aparelho longe do sol por 10 minutos.",
                "Use Ajustes → Bateria para ver qual app está gastando enquanto a tela está apagada.",
            ],
            "Não resfrie na geladeira nem com ventilador úmido: condensação estraga o aparelho.",
            True,
        ))
    if entrada.get("dispositivos"):
        secoes.append({
            "id": "toque",
            "titulo": "Entrada e toque",
            "itens": [
                {"rotulo": "Dispositivo de entrada", "valor": ", ".join(entrada["dispositivos"][:4])},
                {"rotulo": "Janela em foco", "valor": tela or "não publicada"},
            ],
        })
        # Toque fantasma: o sintoma clássico de controlador de toque com defeito ou
        # de carga/capa atrapalhando. O Android não publica “toque sem dedo”, então
        # o achado é de **pendência**, não de leitura: ele só aparece quando o
        # relato bate com a assinatura (frame lento OU ANR + janela em foco).
        if (anrs or (gfx and gfx.get("pct_travados", 0) >= 10)) and janela:
            problemas.append(_problema(
                "toque-fantasma",
                "media",
                "Padrão compatível com toque fantasma (a tela se mexendo sozinha)",
                f"Com {janela} em foco, o sistema registrou "
                + ("ANR de entrada" if anrs else f"{gfx.get('pct_travados', 0):.0f}% de quadros travados")
                + ". O toque não aparece como “sem dedo” em lugar nenhum — o Android não publica isso.",
                "Controlador de toque (o vidro, o flat e o conector) com mau contato, capa apertando a "
                "borda, película mal colada ou carregador sem aterramento injetam toque que ninguém fez. "
                "O app recebe, reage, e a tela parece ter vida própria — até a tela apagar e o "
                "controlador reiniciar.",
                [
                    "Tire a capa e a película e teste um dia inteiro: é a causa mais comum e a mais barata de eliminar.",
                    "Teste sem carregador e com outro carregador (de preferência o original, em tomada aterrada).",
                    "No próprio aparelho, abra o teste de toque: Ajustes → Suporte/Diagnóstico → Toque "
                    "(o nome muda por fabricante) — ou ligue as “Opções do desenvolvedor → Mostrar toques” "
                    "e veja se aparece bolinha sem você encostar.",
                    "Se aparecer toque sozinho no teste, com capa e película fora: é o vidro/controlador, "
                    "e o conserto é de assistência (troca do conjunto tela, não de software).",
                ],
                "O JARVIS mede a consequência (travamento, toque atrasado), não o dedo fantasma: o "
                "Android não expõe esse evento. Este achado é a leitura mais provável do conjunto — "
                "não um diagnóstico fechado de hardware.",
            ))

    # ---- ordenação: gravidade primeiro
    ordem = {"alta": 0, "media": 1, "baixa": 2}
    problemas.sort(key=lambda p: ordem.get(p["gravidade"], 3))

    titulo = " · ".join(
        p for p in (
            props.get("ro.product.model"),
            f"Android {props.get('ro.build.version.release', '')}".strip(),
        ) if p
    ) or "Android"

    if not problemas:
        veredito = "Nenhum problema medido nas áreas que o Android publica sem root."
    elif problemas[0]["gravidade"] == "alta":
        veredito = f"{len(problemas)} achado(s), e o principal é: {problemas[0]['titulo'].lower()}."
    else:
        veredito = f"{len(problemas)} achado(s), nenhum grave: o primeiro é {problemas[0]['titulo'].lower()}."

    limitacoes = list(dict.fromkeys(medido.get("falhas", [])))
    if not processos:
        limitacoes.append("A lista de processos não veio no formato esperado nesta versão do Android.")
    if not sensores:
        # 0.95.2 — a anatomia dizia a mesma coisa com outras palavras e as duas
        # apareciam juntas no relatório. Uma linha só, e `_limites_sem_repetir`
        # descarta a equivalente no fim.
        limitacoes.append(
            "Sem temperatura de CPU: este Android esconde `/sys/class/thermal` de quem não é root — "
            "o aquecimento fica sem número (a da bateria continua aparecendo)."
        )
    # 0.95.2 — “memória por app não vem” já é dito pela anatomia; repetir aqui
    # só enchia a lista de leituras que não responderam com a mesma ideia.

    return {
        "ok": True,
        "alvo": "android",
        "serial": medido.get("serial", ""),
        "titulo": titulo,
        "lido_em": quando.replace(microsecond=0).isoformat(),
        "veredito": veredito,
        "problemas": problemas,
        "otimizacoes": otimizacoes,
        "secoes": [s for s in secoes if s["itens"]],
        "limitacoes": limitacoes,
        "nao_faz": list(NAO_FAZ),
        "comandos": medido.get("comandos", []),
    }


def diagnosticar(
    alvo: str = "",
    *,
    rodar: Callable[[list[str]], tuple[int, str, str]] | None = None,
    agora: datetime | None = None,
) -> dict[str, Any]:
    """Lê o aparelho e devolve o diagnóstico — sem alterar nada nele."""
    medido = coletar(alvo, rodar=rodar)
    relatorio = analisar(medido, agora=agora)
    # 0.95.2 — o `--pacote` também vale para o scanner sozinho, e não só para a
    # varredura completa: é no scanner que aparecem o percentual de memória e o
    # nome do app que mais pesa, que é justamente o que o dono quer mostrar.
    relatorio["_saidas"] = dict(medido.get("saidas", {}))
    relatorio["_falhas"] = list(medido.get("falhas", []))
    return relatorio


# ---------------------------------------------------------------------------
# O relato do dono vira pergunta, e a pergunta vira ordem de suspeita (0.92.4)
# ---------------------------------------------------------------------------

SINTOMAS: dict[str, dict[str, str]] = {
    "tela-prende": {
        "titulo": "A tela prende e depois volta",
        "pergunta": "A tela congela por alguns segundos e depois volta a responder?",
    },
    "frame-lento": {
        "titulo": "O frame fica lento",
        "pergunta": "O rolar e o toque ficam lentos, como se o desenho estivesse atrasado?",
    },
    "se-mexe-sozinho": {
        "titulo": "A tela se mexe sozinha",
        "pergunta": "O aparelho toca, rola ou abre coisas sem você encostar?",
    },
    "so-para-apagar-tela": {
        "titulo": "Só para quando apaga e liga a tela",
        "pergunta": "Desligar a tela e ligar de volta é o que faz o problema passar?",
    },
    "esquenta": {
        "titulo": "Esquenta antes de ficar lento",
        "pergunta": "O aparelho esquenta logo antes de travar ou ficar lento?",
    },
}

# A matriz. Cada causa lista as evidências que a sustentam: se o relato tem a
# evidência, a causa sobe; se não tem, continua possível mas desce.
#
# A ordem não é opinião: o sintoma que o dono descreveu — frame lento, mexer
# sozinho e **só parar quando a tela apaga** — é a assinatura do controlador de
# toque, porque apagar a tela é exatamente o que desliga esse controlador e
# esvazia a fila de toque/desenho. Nenhuma outra causa tem esse “desliga e liga”.
CAUSAS: tuple[dict[str, Any], ...] = (
    {
        "id": "toque-fantasma",
        "titulo": "Toque fantasma no vidro (controlador de toque)",
        "forca": 4,
        "evidencias": {"se-mexe-sozinho": 3, "so-para-apagar-tela": 3, "frame-lento": 1, "tela-prende": 1},
        "porque": (
            "Apagar a tela desliga o controlador de toque e esvazia a fila de eventos. É a única "
            "causa em que esse gesto resolve na hora — e é a que combina com “se mexe sozinho”."
        ),
        "teste": [
            "Tire capa e película e use um dia inteiro.",
            "Teste sem carregador, e depois com outro carregador em tomada aterrada.",
            "Ligue “Opções do desenvolvedor → Mostrar toques” e veja se aparece bolinha sem você encostar.",
        ],
        "vira": "troca do conjunto tela em assistência, se o toque aparecer no teste com capa e película fora.",
    },
    {
        "id": "app-travado",
        "titulo": "Um app específico travando (ANR)",
        "forca": 3,
        "evidencias": {"tela-prende": 3, "frame-lento": 2},
        "porque": (
            "App que não responde prende a janela em foco: o toque é engolido e a tela parece "
            "travada. Mas o problema fica no app: trocar de app melhora, e apagar a tela não faz diferença."
        ),
        "teste": [
            "Anote em quais apps acontece. Se é sempre o mesmo, é ele.",
            "Atualize o app e limpe o cache (não os dados).",
        ],
        "vira": "desinstalar e reinstalar o app, ou abandonar o app.",
    },
    {
        "id": "calor",
        "titulo": "Calor reduzindo o processador (throttling)",
        "forca": 2,
        "evidencias": {"esquenta": 3, "frame-lento": 2, "tela-prende": 1},
        "porque": (
            "Acima de ~70 °C o Android baixa a frequência para não queimar. A lentidão vem "
            "depois de esquentar, e não faz a tela se mexer sozinha."
        ),
        "teste": [
            "Deixe esfriar 10 minutos e compare.",
            "Veja Ajustes → Bateria → uso por app enquanto a tela está apagada.",
        ],
        "vira": "ajuste de uso (capa, sol, carga) ou assistência se esquenta parado.",
    },
    {
        "id": "memoria",
        "titulo": "Memória cheia (apps fechando e reabrindo)",
        "forca": 2,
        "evidencias": {"tela-prende": 1, "frame-lento": 2},
        "porque": (
            "Com pouca RAM, o Android fecha app em segundo plano e reabre do zero. A tela "
            "“pula” entre apps, mas não se mexe sozinha dentro de um app."
        ),
        "teste": [
            "Reinicie o aparelho e compare nas primeiras horas.",
            "Force a parada dos dois apps que mais ocupam memória no relatório.",
        ],
        "vira": "desinstalar o que não usa.",
    },
    {
        "id": "armazenamento",
        "titulo": "Armazenamento quase cheio",
        "forca": 1,
        "evidencias": {"frame-lento": 1, "tela-prende": 1},
        "porque": (
            "Sem espaço livre o sistema gasta mais para gravar cache — deixa tudo lento, "
            "mas não cria toque que ninguém fez."
        ),
        "teste": ["Libere uns 10 GB e compare.", "Ajustes → Armazenamento mostra por categoria."],
        "vira": "apagar vídeos/downloads e mover fotos para o PC.",
    },
)

# O que sustenta cada causa **no aparelho** (não no relato). Sem isso, a causa é
# só hipótese — e a resposta diz isso.
# 0.95.2 — esta tabela estava **morta em três das cinco linhas**, e o efeito era
# o oposto do desenhado: toda suspeita saía “sem medida no aparelho”, mesmo num
# relatório com 25 leituras boas. Os ids de problema que o `analisar()` cria são
# `app-nao-responde`, `frame-lento`, `aquecendo`, `memoria-baixa` e
# `armazenamento-*`; a tabela pedia `app-travado`, que **nunca existe**. E
# `app-travando` (o travamento de um app no log) não estava ligado a nada.
#
# O conserto não é só trocar os nomes: um app que travou (`app-travando`) é
# evidência de app problemático, não de toque fantasma, e vai na linha do
# `app-travado`. E a lista é conferida por teste contra os ids reais.
EVIDENCIA_MEDIDA = {
    "toque-fantasma": ("app-nao-responde", "frame-lento"),
    "app-travado": ("app-nao-responde", "app-travando"),
    "calor": ("aquecendo", "bateria-quente-carregando"),
    "memoria": ("memoria-baixa",),
    "armazenamento": ("armazenamento-cheio", "armazenamento-apertado"),
}


def sintomas() -> list[dict[str, str]]:
    """A lista que a tela e o console mostram — e que a API aceita."""
    return [
        {"id": chave, "titulo": valor["titulo"], "pergunta": valor["pergunta"]}
        for chave, valor in SINTOMAS.items()
    ]


def cruzar(relatorio: dict[str, Any], marcados: list[str]) -> dict[str, Any]:
    """Ordena as causas pelo que o dono relatou **e** pelo que o aparelho mediu.

    Uma causa sobe por evidência de relato (a matriz `CAUSAS`) e desce quando o
    aparelho não mostra nada que a sustente. O resultado é uma fila de suspeitas
    com o teste de cada uma — não um diagnóstico fechado, porque toque fantasma
    não sai em `dumpsys` nenhum.
    """
    escolhidos = [s for s in dict.fromkeys(marcados) if s in SINTOMAS]
    ids_medidos = {p["id"] for p in relatorio.get("problemas", [])}
    fila: list[dict[str, Any]] = []
    for causa in CAUSAS:
        pontos = causa["forca"] if not escolhidos else 1
        for sintoma in escolhidos:
            pontos += causa["evidencias"].get(sintoma, 0)
        sustenta = [i for i in EVIDENCIA_MEDIDA.get(causa["id"], ()) if i in ids_medidos]
        if sustenta:
            pontos += 2
            # O relato é o que não pode ser medido; quando ele aponta a mesma
            # direção da medida, a causa é a primeira da fila.
            if "se-mexe-sozinho" in escolhidos and "so-para-apagar-tela" in escolhidos:
                pontos += 1 if causa["id"] == "toque-fantasma" else 0
        else:
            pontos -= 2
        fila.append({
            "id": causa["id"],
            "titulo": causa["titulo"],
            "pontos": pontos,
            "porque": causa["porque"],
            "teste": list(causa["teste"]),
            "o_que_confirma": causa["vira"],
            "medido_no_aparelho": sustenta,
        })
    fila.sort(key=lambda item: item["pontos"], reverse=True)
    primeira = fila[0] if fila else None
    if not escolhidos:
        veredito = (
            "Sem sintoma marcado, a ordem é a do que o aparelho mediu. Marque o que você vê para "
            "a ordem mudar."
        )
    elif primeira and primeira["pontos"] >= 5:
        veredito = (
            f"Pelo que você relatou e pelo que o aparelho mediu, a suspeita número um é: "
            f"{primeira['titulo'].lower()}."
        )
    elif primeira:
        veredito = (
            f"A suspeita número um é {primeira['titulo'].lower()}, mas o aparelho não mostrou "
            "medida que confirme — comece pelo teste mais barato."
        )
    else:
        veredito = "Nenhuma causa conhecida para os sintomas marcados."
    return {
        "sintomas_marcados": escolhidos,
        "fila": fila,
        "veredito": veredito,
        "como_ler": (
            "“Pontos” é só a ordem: relato soma, medida no aparelho soma mais, ausência de medida "
            "subtrai. Não é probabilidade e não substitui o teste."
        ),
    }


def diagnosticar_por_sintoma(
    sintomas_marcados: list[str],
    alvo: str = "",
    *,
    rodar: Callable[[list[str]], tuple[int, str, str]] | None = None,
    agora: datetime | None = None,
) -> dict[str, Any]:
    """Mede o aparelho e cruza com o relato do dono."""
    relatorio = diagnosticar(alvo, rodar=rodar, agora=agora)
    relatorio["sintomas"] = cruzar(relatorio, sintomas_marcados)
    return relatorio


def em_texto(relatorio: dict[str, Any]) -> str:
    """A versão para o console (`escanear-celular.bat`)."""
    linhas = [
        "",
        f"  {relatorio['titulo']}",
        f"  {relatorio['veredito']}",
        "",
    ]
    sintoma = relatorio.get("sintomas")
    if sintoma:
        linhas.append("  O QUE VOCÊ RELATOU — SUSPEITAS EM ORDEM")
        linhas.append(f"    {sintoma['veredito']}")
        for posicao, causa in enumerate(sintoma["fila"][:4], start=1):
            medida = ", ".join(causa["medido_no_aparelho"]) or "nada medido no aparelho"
            linhas.append(f"    {posicao}. {causa['titulo']}  (medido: {medida})")
            linhas.append(f"       por quê: {causa['porque']}")
            for passo in causa["teste"]:
                linhas.append(f"       teste: {passo}")
            linhas.append(f"       se confirmar: {causa['o_que_confirma']}")
        linhas.append(f"    {sintoma['como_ler']}")
        linhas.append("")
    for secao in relatorio["secoes"]:
        linhas.append(f"  {secao['titulo'].upper()}")
        for item in secao["itens"]:
            linhas.append(f"    {item['rotulo']:<28} {item['valor']}")
        linhas.append("")
    for problema in relatorio["problemas"]:
        linhas.append(f"  [{problema['gravidade'].upper()}] {problema['titulo']}")
        linhas.append(f"      medido: {problema['medido']}")
        linhas.append(f"      causa:  {problema['causa']}")
        for passo in problema["o_que_fazer"]:
            linhas.append(f"      -> {passo}")
        linhas.append(f"      limite: {problema['limite']}")
        linhas.append("")
    if relatorio["otimizacoes"]:
        linhas.append("  O QUE DÁ PARA MELHORAR")
        for otimizacao in relatorio["otimizacoes"]:
            linhas.append(f"    * {otimizacao['titulo']} — {otimizacao['ganho']}")
            for passo in otimizacao["como"]:
                linhas.append(f"        {passo}")
            linhas.append(f"        risco: {otimizacao['risco']}")
        linhas.append("")
    linhas.append("  O QUE ESTE SCANNER NÃO FAZ")
    for frase in relatorio["nao_faz"]:
        linhas.append(f"    - {frase}")
    if relatorio["limitacoes"]:
        linhas.append("")
        linhas.append("  LIMITES DESTA LEITURA")
        for frase in relatorio["limitacoes"]:
            linhas.append(f"    - {frase}")
    linhas.append("")
    return "\n".join(linhas)


def pasta_de_relatorios() -> "os.PathLike[str]":
    from . import dados

    return dados.raiz() / "diagnosticos"
