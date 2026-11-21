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
        raise DiagnosticoError(
            "Nenhum Android apareceu. Confira o cabo (tem de ser de dados, não só de carga), "
            "ligue a Depuração USB em Opções do desenvolvedor e aceite o aviso na tela."
        )
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
    root = (saidas.get("which su", "") or "").strip()

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
                {"rotulo": "Amostra", "valor": ", ".join(apps[:12])},
            ],
        })
        if len(apps) >= RECOMENDACAO_APPS:
            otimizacoes.append(_otimizacao(
                "menos-apps",
                "Desinstalar os apps que você não abre",
                f"libera espaço e reduz processo em segundo plano ({len(apps)} instalados)",
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
            f"`which su` respondeu: {root}.",
            "Acesso de superusuário instalado (Magisk ou similar).",
            [
                "Se você não instalou, é bom saber: root permite que qualquer app peça acesso total.",
                "App de banco e de pagamento podem recusar o aparelho por isso.",
            ],
            "O JARVIS nunca usa root: nem para ler, nem para “otimizar”.",
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
        limitacoes.append("Este aparelho não expõe sensores térmicos sem root — o aquecimento fica sem número.")
    limitacoes.append(
        "O scanner lê o que o Android publica para `adb` sem root: memória por app em detalhe e "
        "saúde de célula não estão nessa lista."
    )

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
    return analisar(coletar(alvo, rodar=rodar), agora=agora)


def em_texto(relatorio: dict[str, Any]) -> str:
    """A versão para o console (`escanear-celular.bat`)."""
    linhas = [
        "",
        f"  {relatorio['titulo']}",
        f"  {relatorio['veredito']}",
        "",
    ]
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
