#!/usr/bin/env python3
"""Sonda de leitura da árvore de acessibilidade — roda **fora** da API.

Por que um arquivo separado: ler a árvore significa chamar código de outro
programa por COM. Se esse programa travar, quem trava é este processo — que é
descartável — e não o JARVIS no meio da conversa.

Uso (Windows):

    py arvore_sonda.py                      # janela em foco, em texto
    py arvore_sonda.py --janelas            # o que está aberto
    py arvore_sonda.py --alvo chrome        # janela cujo título tem "chrome"
    py arvore_sonda.py --json --limite 200  # JSON para o JARVIS
    py arvore_sonda.py --fonte uia          # força uma das duas fontes
    py arvore_sonda.py --provados           # quais janelas abertas servem para agir
    py arvore_sonda.py --alvo notepad --escrever "oi, mundo"              # acha o campo e mostra o plano
    py arvore_sonda.py --alvo notepad --escrever "oi, mundo" --executar   # escreve de verdade
    py arvore_sonda.py --programa "bloco de notas" --escrever "oi" --executar  # abre se preciso

Só leitura: nada é clicado, digitado ou movido.

## 0.82.1 — duas correções que vieram da primeira medição no PC

1. **Não ler a si mesma.** O comando roda dentro de um `cmd.exe`, e a janela em
   foco é justamente esse `cmd`. A primeira medição devolveu o próprio terminal
   — “1 elemento, 0 acionável” — quando o usuário queria ver o programa aberto
   atrás. Agora, se o foco for o terminal, a sonda procura a janela anterior e
   diz que trocou.
2. **Segunda fonte.** O console não publica botões pela MSAA (é de 1996). Ele
   publica pela **UIAutomation**. A leitura agora tenta as duas e fica com a que
   mostrou mais elementos.

## 0.82.3 — a escolha da janela

Na 0.82.2, `--alvo chrome` leu **o terminal**: a busca procurava primeiro no
título, e o título do `cmd` é a linha de comando — que contém a palavra
“chrome”. A janela que roda a sonda é justamente a que sempre carrega o pedido
escrito nela. Agora ela é excluída das candidatas, e processo vence título.
"""
from __future__ import annotations

import argparse
import json
import sys


def _falhar(mensagem: str, codigo: int = 1, *, json_sim: bool = False) -> int:
    """Erro legível por gente; JSON só quando foi pedido JSON.

    O erro do ref saía como `{"erro": "..."}` numa linha só, e quem lê no
    terminal não merece JSON sem ter pedido. O `--json` continua instalando o
    formato de máquina.
    """
    if json_sim:
        print(json.dumps({"erro": mensagem}, ensure_ascii=False))
        return codigo
    print(f"  NÃO DEU: {mensagem}")
    return codigo


def _escolher(leitor, alvo: str) -> tuple[dict, str]:
    """Janela a ler + explicação de eventual troca.

    Quem decide o alvo é `arvore.escolher_janela` (a mesma da API): processo
    vence título, e a janela que roda a sonda fica de fora — foi ela que fez
    `--alvo chrome` ler o terminal na 0.82.2.

    Aqui só fica o caso `foco`: se quem está em foco é o terminal, pega a
    primeira janela de programa de verdade — é o que o usuário quis dizer.
    """
    from server import arvore

    pedido = (alvo or "foco").strip().lower()
    if pedido not in {"foco", "focused", ""}:
        return arvore.escolher_janela(alvo, janelas=leitor.janelas(), foco=None), ""

    foco = leitor.janela_em_foco()
    janela = arvore.escolher_janela(alvo, janelas=leitor.janelas(), foco=foco)
    if not arvore.e_terminal(janela):
        return janela, ""

    reais = getattr(leitor, "janelas_de_programas", leitor.janelas)
    candidatas = [
        item
        for item in reais()
        if not arvore.e_terminal(item) and not arvore.da_sonda(item) and item.get("titulo")
    ]
    if not candidatas:
        return janela, (
            "a janela em foco é este terminal e não achei outra aberta — abra o programa "
            "que quer examinar e rode de novo."
        )
    escolhida = candidatas[0]
    return escolhida, (
        f"o foco estava neste terminal; li “{escolhida.get('titulo')}” "
        f"({escolhida.get('processo') or '?'}) em vez dele."
    )


def _janelas_do_programa(leitor, args, mesa_ditar) -> int:
    """Todas as janelas do programa, com o que cada uma publica.

    Uma linha por janela: título, se está minimizada, quantos elementos e se
    tem lugar para escrever. É o bastante para saber se o problema é o
    programa, a janela minimizada ou uma janela velha sobrando.
    """
    from server import arvore

    try:
        info = mesa_ditar.pc.resolver(args.programa)
    except Exception as exc:  # noqa: BLE001
        return _falhar(str(exc), json_sim=args.json)
    janelas = mesa_ditar.janelas_do_programa(
        leitor.janelas(), info["executavel"], info["rotulo"]
    )
    itens: list[dict] = []
    for janela in janelas:
        item = {
            "handle": janela.get("handle"),
            "titulo": janela.get("titulo"),
            "pid": janela.get("pid"),
            "minimizada": bool(janela.get("minimizada")),
        }
        try:
            bruto = leitor.ler_janela(
                int(janela.get("handle") or 0),
                max(1, min(args.profundidade, 14)),
                max(1, min(args.limite, 3000)),
                fonte=args.fonte,
            )
            bruto.setdefault("janela", janela)
            montada = arvore.montar(bruto, max(1, min(args.profundidade, 14)), max(1, min(args.limite, 3000)), com_caminho=True)
            lido = montada.get("pronto") or arvore.prontidao(montada)
            campo = lido.get("onde_escrever") or {}
            item["elementos"] = int(montada.get("total") or 0)
            item["tem_campo"] = bool(campo.get("ref"))
            item["onde_escrever"] = campo.get("ref") or ""
        except Exception as exc:  # noqa: BLE001
            item["erro"] = f"{type(exc).__name__}: {exc}"
        itens.append(item)

    if args.json:
        print(json.dumps({"programa": info, "janelas": itens}, ensure_ascii=False))
        return 0
    caminho = ""
    try:
        caminho = mesa_ditar.pc.caminho_do_programa(info["executavel"])
    except Exception:  # noqa: BLE001
        caminho = ""
    if not itens:
        print(f"  O {info['rotulo']} ({info['executavel']}) não está aberto.")
        if caminho:
            print(f"  Instalado em: {caminho}")
        else:
            print(
                f"  E não achei {info['executavel']} no PATH, em %SystemRoot% nem no App Paths — "
                "o programa pode não estar instalado neste PC."
            )
        return 1
    if caminho:
        print(f"  programa: {caminho}")
    print(f"  {info['rotulo']} ({info['executavel']}) — {len(itens)} janela(s):")
    for item in itens:
        marcas = []
        if item.get("minimizada"):
            marcas.append("minimizada")
        if "erro" in item:
            marcas.append(f"não deu para ler ({item['erro']})")
        else:
            marcas.append(f"{item['elementos']} elemento(s)")
            marcas.append("tem campo " + str(item["onde_escrever"]) if item.get("tem_campo") else "sem campo")
        print(f"    {item['titulo']}  —  " + ", ".join(marcas))
    escreviveis = [item for item in itens if item.get("tem_campo")]
    print()
    if escreviveis:
        print(f"  {len(escreviveis)} aceita(m) escrita. Uma delas é a que o JARVIS usa.")
    else:
        print("  Nenhuma aceita escrita agora. Minimizada publica só moldura:")
        print("  restaure a janela e rode de novo.")
    return 0


def _provados(leitor, args) -> int:
    """Passa por todas as janelas abertas e diz em quais dá para trabalhar.

    Por que existe: a pergunta que decide a etapa 2 é “onde os elementos fazem
    sentido?”. Responder isso com uma rodada por programa custa uma mensagem
    do usuário por tentativa — e no Chrome ela já custou seis. Esta varredura
    responde tudo de uma vez, medindo com a leitura de verdade.
    """
    import time

    from server import arvore

    try:
        abertas = leitor.janelas_de_programas()
    except Exception as exc:  # noqa: BLE001
        return _falhar(f"não consegui listar as janelas ({type(exc).__name__}).")

    candidatas = [j for j in abertas if not arvore.da_sonda(j) and (j.get("titulo") or "").strip()]
    if not candidatas:
        return _falhar("nenhuma janela de programa aberta para medir.")

    linhas: list[dict] = []
    comeco = time.monotonic()
    # Teto de tempo: uma janela travada não pode transformar isto numa espera
    # sem fim. O que não foi medido é dito, não escondido.
    for janela in candidatas[:12]:
        if time.monotonic() - comeco > 60:
            break
        inicio = time.monotonic()
        item = {
            "processo": str(janela.get("processo") or "?"),
            "titulo": " ".join(str(janela.get("titulo") or "").split())[:44],
            "janela": janela,
        }
        try:
            bruto = leitor.ler_janela(int(janela["handle"]), 6, 300)
            montada = arvore.montar(bruto, 6, 300)
            item["lido"] = arvore.prontidao(montada)
            item["fonte"] = montada.get("fonte") or "?"
            item["acordou"] = bool(bruto.get("acordou"))
        except Exception as exc:  # noqa: BLE001 - COM de terceiros
            item["lido"] = {"pronto": False, "total": 0, "conteudo": False, "motivo": f"a leitura falhou ({type(exc).__name__})."}
            item["fonte"] = "?"
        item["segundos"] = round(time.monotonic() - inicio, 1)
        linhas.append(item)

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "processo": item["processo"],
                        "titulo": item["titulo"],
                        "pronto": item["lido"]["pronto"],
                        "total": item["lido"].get("total", 0),
                        "com_posicao": item["lido"].get("com_posicao", 0),
                        "conteudo": item["lido"].get("conteudo", False),
                        "motivo": item["lido"].get("motivo", ""),
                        "fonte": item["fonte"],
                        "acordou": item.get("acordou", False),
                        "onde_escrever": item["lido"].get("onde_escrever"),
                        "segundos": item["segundos"],
                    }
                    for item in linhas
                ],
                ensure_ascii=False,
            )
        )
        return 0

    print("  janela aberta                    elementos  posicoes  conteudo  serve?  fonte  seg")
    print("  " + "-" * 86)
    for item in linhas:
        lido = item["lido"]
        print(
            f"  {item['processo'][:14]:<14} {item['titulo'][:16]:<16} "
            f"{lido.get('total', 0):>9}  {lido.get('com_posicao', 0):>8}  "
            f"{'sim' if lido.get('conteudo') else 'nao':<8}  "
            f"{'SIM' if lido.get('pronto') else 'nao':<6}  {item['fonte'][:4]:<4}  {item['segundos']:>4}"
        )
    print()
    print("  'posicoes' = elementos que vieram com coordenada na tela. Saber onde")
    print("  a peca esta nao e o mesmo que saber o que ela e: moldura tem posicao")
    print("  e nao serve para trabalhar; conteudo e o que serve.")
    acordaram = [item for item in linhas if item.get("acordou")]
    if acordaram:
        print()
        print("  Acordaram na segunda leitura (o navegador liga a acessibilidade")
        print("  quando percebe alguem lendo — já vem lido, não precisa repetir):")
        for item in acordaram:
            campo = (item["lido"].get("onde_escrever") or {})
        onde = f" — escreve em {campo['caixa'][0]},{campo['caixa'][1]}" if campo else ""
        print(f"    - {item['processo']} — {item['titulo']}{onde}")

    prontas = [item for item in linhas if item["lido"]["pronto"]]
    print()
    if len(linhas) < len(candidatas):
        print(f"  medi {len(linhas)} de {len(candidatas)} janelas — parei pelo teto de 60 s.")
        print()
    if prontas:
        print(f"  {len(prontas)} de {len(linhas)} janela(s) servem para o JARVIS agir:")
        for item in prontas:
            print(f"    - {item['processo']} — {item['titulo']}")
        print()
        print("  A etapa 2 (clicar por `ref`) é medida nessas. Comece pela primeira:")
        print(f'    .venv\\Scripts\\python arvore_sonda.py --alvo "{prontas[0]["processo"]}"')
    else:
        print("  Nenhuma janela aberta publica conteúdo neste PC.")
        print("  Abra o Bloco de Notas ou uma pasta do Explorer e rode de novo.")

    # As que ficaram de fora: a razão, curta, para não parecer falha da leitura.
    mudas = [item for item in linhas if not item["lido"].get("conteudo")]
    if mudas:
        print()
        print("  Só moldura (não é falha nossa, é o programa):")
        for item in mudas:
            print(f"    - {item['processo']} — {item['lido'].get('motivo', '')[:70]}")
    return 0


def _mostrar_acao(feito: dict, args) -> int:
    """O plano (e o resultado) na tela — em texto, ou JSON se foi pedido."""
    if args.json:
        print(json.dumps(feito, ensure_ascii=False))
        return 0
    print(f"  {feito['resumo']}")
    plano = feito.get("plano")
    if not plano:
        if feito.get("como_autorizar"):
            print()
            print(f"  {feito['como_autorizar']}")
        return 0 if feito.get("ok") else 1
    print()
    print(f"  janela:  {plano['processo']} — {plano['janela']}")
    print(f"  alvo:    {plano['ref']}  {plano['papel']} “{plano['nome']}”")
    if plano.get("caixa"):
        caixa = plano["caixa"]
        print(f"  onde:    {caixa[0]},{caixa[1]} ({caixa[2]}x{caixa[3]})")
    print(f"  fonte:   {plano['fonte']}   leitura: {plano['leitura']}")
    if feito.get("como_autorizar"):
        print()
        print(f"  {feito['como_autorizar']}")
    resultado = feito.get("resultado") or {}
    if resultado.get("como"):
        print(f"  como:    {resultado['como']}")
    if resultado.get("motivo"):
        print(f"  motivo:  {resultado['motivo']}")
    if feito.get("caminho"):
        print(f"  abri:    {feito['caminho']}")
    if feito.get("restaurada"):
        print("  janela:  estava minimizada; eu restaurei (sem mouse).")
    if resultado.get("conferido") is True:
        print("  conferi: o texto está no campo.")
    elif resultado.get("conferido") is False:
        print("  atenção: digitei, mas o campo não mostrou o texto — confira na tela.")
    return 0 if feito.get("ok") else 1


def principal(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lê a árvore de acessibilidade de uma janela (somente leitura).")
    parser.add_argument("--alvo", default="foco", help="“foco” (padrão) ou parte do título do processo/janela.")
    parser.add_argument("--profundidade", type=int, default=6, help="Até onde descer (1 a 14).")
    parser.add_argument("--limite", type=int, default=600, help="Máximo de elementos lidos (1 a 3000).")
    parser.add_argument(
        "--fonte",
        default="auto",
        choices=("auto", "msaa", "uia"),
        help="auto (padrão): as duas, fica com a que mostrar mais. msaa ou uia: força uma.",
    )
    parser.add_argument("--json", action="store_true", help="Devolve JSON cru para o JARVIS.")
    parser.add_argument("--janelas", action="store_true", help="Só lista as janelas abertas.")
    parser.add_argument(
        "--diagnostico",
        action="store_true",
        help="Testa a UIAutomation passo a passo e mostra o retorno de cada chamada.",
    )
    parser.add_argument(
        "--provados",
        action="store_true",
        help="Mede todas as janelas abertas e diz em quais o JARVIS consegue trabalhar.",
    )
    parser.add_argument("--ref", default="", help="Ref do elemento (ex.: @4ab283d9:e11), vindo da leitura.")
    parser.add_argument(
        "--acao",
        default="clicar",
        choices=("clicar", "digitar", "escrever"),
        help="O que fazer com o ref. Padrão: clicar.",
    )
    parser.add_argument("--texto", default="", help="Texto a digitar (com --acao digitar).")
    parser.add_argument(
        "--escrever",
        default="",
        metavar="TEXTO",
        help="Acha o lugar de escrever na janela e digita ali — sem precisar copiar ref nenhum.",
    )
    parser.add_argument(
        "--executar",
        action="store_true",
        help="Faz de verdade. Sem esta opção, só mostra o plano e não toca em nada.",
    )
    parser.add_argument(
        "--programa",
        default="",
        metavar="NOME",
        help=(
            "Da lista fechada (bloco de notas, calculadora, paint, cmd…): abre o programa se ele "
            "não estiver aberto, espera a janela e escreve com --escrever. Sem --escrever, "
            "mostra as janelas dele e qual aceita escrita."
        ),
    )
    parser.add_argument(
        "--mouse",
        action="store_true",
        help=(
            "Último recurso: se o elemento não aceitar ação nem foco, clicar fisicamente no "
            "centro dele (move o ponteiro). Sem esta opção, o JARVIS não mexe no mouse."
        ),
    )
    parser.add_argument(
        "--acrescentar",
        action="store_true",
        help="Se o campo já tiver texto, escreve no fim dele em vez de recusar.",
    )
    args = parser.parse_args(argv)

    if sys.platform != "win32":
        return _falhar("a leitura da árvore só existe no Windows hoje.", json_sim=args.json)

    try:
        from server import arvore_windows as leitor
    except Exception as exc:  # noqa: BLE001 - qualquer falha de import é motivo de saída limpa
        return _falhar(
            f"não consegui carregar o leitor do Windows ({type(exc).__name__}).", json_sim=args.json
        )

    if args.programa and not args.escrever:
        # `--programa X` sozinho responde a pergunta que importa quando falha:
        # quantas janelas esse programa tem, e qual delas publica campo?
        from server import mesa_ditar

        return _janelas_do_programa(leitor, args, mesa_ditar)

    if args.programa:
        if not args.escrever:
            return _falhar("com --programa, informe o texto em --escrever \"texto\".", json_sim=args.json)
        from server import mesa_agir, mesa_ditar

        try:
            feito = mesa_ditar.ditar(
                programa=args.programa,
                texto=args.escrever,
                executar=args.executar,
                acrescentar=args.acrescentar,
                leitor=leitor,
                alvo=args.alvo,
                abrir=mesa_ditar.abrir_direto,
                profundidade=max(1, min(args.profundidade, 14)),
                limite=max(1, min(args.limite, 3000)),
                fonte=args.fonte,
            )
        except mesa_ditar.DitarError as exc:
            return _falhar(str(exc), json_sim=args.json)
        except mesa_agir.AgirError as exc:
            return _falhar(str(exc), json_sim=args.json)
        except Exception as exc:  # noqa: BLE001 - COM de terceiros
            return _falhar(f"a escrita falhou ({type(exc).__name__}).", json_sim=args.json)
        return _mostrar_acao(feito, args)

    if args.escrever or args.ref:
        from server import mesa_agir

        if args.escrever and not args.ref:
            try:
                feito = mesa_agir.escrever_na_janela(
                    texto=args.escrever,
                    executar=args.executar,
                    leitor=leitor,
                    alvo=args.alvo,
                    profundidade=max(1, min(args.profundidade, 14)),
                    limite=max(1, min(args.limite, 3000)),
                    fonte=args.fonte,
                    acrescentar=args.acrescentar,
                    mouse=args.mouse,
                )
            except mesa_agir.AgirError as exc:
                return _falhar(str(exc), json_sim=args.json)
            except Exception as exc:  # noqa: BLE001 - COM de terceiros
                return _falhar(f"a escrita falhou ({type(exc).__name__}).", json_sim=args.json)
            return _mostrar_acao(feito, args)

        try:
            feito = mesa_agir.agir(
                ref=args.ref,
                acao=args.acao,
                texto=args.texto,
                executar=args.executar,
                leitor=leitor,
                alvo=args.alvo,
                profundidade=max(1, min(args.profundidade, 14)),
                limite=max(1, min(args.limite, 3000)),
                fonte=args.fonte,
                acrescentar=args.acrescentar,
                mouse=args.mouse,
            )
        except mesa_agir.AgirError as exc:
            return _falhar(str(exc), json_sim=args.json)
        except Exception as exc:  # noqa: BLE001 - COM de terceiros
            return _falhar(f"a ação falhou ({type(exc).__name__}).", json_sim=args.json)

        return _mostrar_acao(feito, args)

    if args.provados:
        return _provados(leitor, args)

    if args.diagnostico:
        from server import arvore

        try:
            janela_diagnostico, _ = _escolher(leitor, args.alvo)
        except arvore.ArvoreError as exc:
            return _falhar(str(exc), json_sim=args.json)
        quadro = leitor.diagnostico(args.alvo, handle=janela_diagnostico["handle"])
        if args.json:
            print(json.dumps(quadro, ensure_ascii=False, indent=2))
            return 0 if quadro.get("ok") else 1

        # Dizer QUAL janela está sendo medida — a medição 6 mostrou a tabela do
        # terminal quando o pedido era o Chrome, e ninguém percebeu.
        alvo_medido = quadro.get("janela") or {}
        if alvo_medido:
            print(
                f"  medindo: {alvo_medido.get('processo') or '?'} — "
                f"{str(alvo_medido.get('titulo') or '')[:60]}"
            )
            print(f"  classe:  {alvo_medido.get('classe') or '?'}")
            print()

        for passo in quadro.get("passos", []):
            marca = "ok  " if passo.get("ok") else "FALHA"
            print(f"  [{marca}] {passo.get('passo')}  {passo.get('hex')}  {passo.get('detalhe') or ''}".rstrip())
        print()
        print(quadro.get("nota") or "")

        # A tabela que decide: quantos nós e se tem CONTEÚDO (não só moldura).
        varredura = quadro.get("varredura") or []
        if varredura:
            print()
            print("  janela                            msaa   uia   conteudo  processo")
            print("  " + "-" * 72)
            for linha in varredura:
                nome = ("  " if linha.get("filha") else "") + str(linha.get("classe"))[:30]
                conteudo = []
                if linha.get("msaa_conteudo"):
                    conteudo.append("msaa")
                if linha.get("uia_conteudo"):
                    conteudo.append("uia")
                print(
                    f"  {nome:<32}  {linha.get('msaa', 0):>4}  {linha.get('uia', 0):>4}   "
                    f"{', '.join(conteudo) or 'nenhum':<7}  {str(linha.get('processo') or '')[:16]}"
                )
            print()
            print("  As linhas indentadas sao janelas filhas: e nelas que a pagina")
            print("  do navegador costuma morar.")
            print("  A coluna 'processo' deve ser a do alvo pedido.")

            veredito = quadro.get("veredito") or {}
            if veredito:
                print()
                if veredito.get("conteudo"):
                    print(
                        f"  VEREDITO: a leitura vai funcionar — {veredito.get('total')} elemento(s) "
                        f"de conteudo, fonte {veredito.get('fonte') or '?'}."
                    )
                else:
                    print(
                        f"  VEREDITO: {veredito.get('total', 0)} elemento(s), nenhum de conteudo "
                        f"(fonte {veredito.get('fonte') or '?'})."
                    )
                if veredito.get("de_filha"):
                    print(f"  lido de dentro de: {veredito['de_filha']}")
        return 0 if quadro.get("ok") else 1

    if args.janelas:
        lista = leitor.janelas()
        if args.json:
            print(json.dumps({"janelas": lista}, ensure_ascii=False))
        else:
            for item in lista:
                print(f"{item.get('processo') or '?':24} {item.get('titulo') or '(sem título)'}")
        return 0

    from server import arvore

    try:
        janela, troca = _escolher(leitor, args.alvo)
    except arvore.ArvoreError as exc:
        return _falhar(str(exc), json_sim=args.json)

    try:
        bruto = leitor.ler_janela(
            janela["handle"],
            max(1, min(args.profundidade, arvore.PROFUNDIDADE_MAX)),
            max(1, min(args.limite, arvore.LIMITE_MAX)),
            fonte=args.fonte,
        )
    except Exception as exc:  # noqa: BLE001 - COM de terceiros: nunca vazar stack
        return _falhar(f"a leitura da janela falhou ({type(exc).__name__}).", json_sim=args.json)
    bruto.setdefault("janela", janela)
    if troca:
        bruto["nota_escolha"] = troca

    if args.json:
        print(json.dumps(bruto, ensure_ascii=False))
        return 0

    montada = arvore.montar(bruto, args.profundidade, args.limite)
    if troca:
        print(troca)
        print()
    print(arvore.resumo(montada))
    # A pergunta que importa depois do número: dá para agir aqui? Dizer “47
    # elementos” sem dizer isso foi o que manteve a etapa 2 parada por seis
    # versões — os 47 eram moldura.
    lido = montada.get("pronto") or arvore.prontidao(montada)
    print()
    print(("  SERVE para agir: " if lido["pronto"] else "  NAO SERVE para agir: ") + lido["motivo"])
    campo = lido.get("onde_escrever")
    if campo:
        print(
            f"  Onde escrever: {campo.get('ref') or '(sem ref)'} "
            f"em {campo['caixa'][0]},{campo['caixa'][1]} ({campo['caixa'][2]}x{campo['caixa'][3]})"
        )
    print()
    print(arvore.desenhar(montada.get("arvore")))
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
