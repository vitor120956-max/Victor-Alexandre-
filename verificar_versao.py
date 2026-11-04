#!/usr/bin/env python3
"""Diz, em uma tela, **qual JARVIS está rodando e qual tela está aparecendo**.

O relato que gerou este arquivo, com print: *“já atualizei mas ainda não tem a
parte para botar as APIs”* — e o rodapé da tela dizia `VERSÃO 0.5.0`, um número
que só existe na interface antiga. Sem uma resposta automática, as três causas
possíveis parecem a mesma coisa:

1. a atualização não foi aplicada nesta pasta;
2. a API em execução é antiga (abadonou o código no start e não recarrega);
3. o navegador está com a página velha em cache.

Este script mede as três, em ordem, e termina com **um veredito** e **o que
fazer**. Nada é alterado: é leitura pura, sem internet.

Uso:
    conferir-versao.bat                  (duplo clique — é o caminho normal)
    .venv\\Scripts\\python verificar_versao.py
    .venv\\Scripts\\python verificar_versao.py --json
    .venv\\Scripts\\python verificar_versao.py --porta 8001
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from server import atualizacao, interface_web  # noqa: E402

TIMEOUT = 3.0


def _versao_do_arquivo() -> str:
    return atualizacao.VERSAO


def _api(potra: int) -> dict:
    """O que a API que está rodando agora responde. Sem API, dict vazio."""
    url = f"http://127.0.0.1:{potra}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resposta:  # noqa: S310 - endereço fixo, local
            return json.loads(resposta.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return {}


def _linha(rotulo: str, valor: str) -> str:
    return f"  {rotulo:<26}{valor}"


def diagnostico(porta: int = 8000) -> dict:
    versao_arquivo = _versao_do_arquivo()
    quadro = interface_web.estado(RAIZ, versao_servidor=versao_arquivo)
    api = _api(porta)
    versao_api = (api or {}).get("version")
    interface_api = (api or {}).get("interface")
    interface_versao_api = (api or {}).get("interfaceVersao")

    problemas: list[str] = []
    acoes: list[str] = []

    if not api:
        problemas.append(f"a API não respondeu em http://127.0.0.1:{porta}")
        acoes.append("abra o `iniciar-jarvis.bat` (a janela preta) e rode este conferidor de novo")
    elif versao_api != versao_arquivo:
        problemas.append(
            f"a API em execução é a {versao_api} e o código no disco é a {versao_arquivo}"
        )
        acoes.append("feche a janela preta no X e abra o `iniciar-jarvis.bat` — o processo velho não recarrega sozinho")

    if quadro.get("desatualizada"):
        problemas.append(
            f"a tela servida ({quadro['servida']}) é a {quadro['versao']}, mais velha que o servidor ({versao_arquivo})"
        )
        acoes.append("rode o `atualizar.bat` nesta mesma pasta")

    # Só a pasta **servida** importa: um `dist` local sem carimbo, quando há
    # `web-dist` carimbada, nem chega a ser usado.
    servida = quadro.get("servida")
    if servida and not quadro.get("versao"):
        problemas.append(
            f"a interface servida (`{servida}`) não tem carimbo de versão: "
            "ela é de antes da 0.79.1"
        )
        acoes.append("rode o `atualizar.bat` nesta mesma pasta para trazer a interface nova")

    if api and interface_api in (None, "ausente"):
        problemas.append("a API não achou nenhuma interface compilada para servir")

    pronto = not problemas
    if pronto:
        acoes.append("abra http://127.0.0.1:%d e aperte Ctrl+F5 uma vez" % porta)

    return {
        "pronto": pronto,
        "versaoArquivo": versao_arquivo,
        "versaoApi": versao_api,
        "porta": porta,
        "interface": quadro,
        "interfaceApi": interface_api,
        "interfaceVersaoApi": interface_versao_api,
        "problemas": problemas,
        "acoes": acoes,
    }


def relatorio(dados: dict) -> str:
    quadro = dados["interface"]
    linhas = [
        "JARVIS — conferir versão e tela",
        "=" * 46,
        "",
        "Arquivos neste computador",
        _linha("versão do servidor:", dados["versaoArquivo"]),
        _linha("pasta da interface:", str(quadro.get("servida") or "nenhuma")),
        _linha("versão da interface:", str(quadro.get("versao") or "sem carimbo (build antigo)")),
        "",
        f"API respondendo em http://127.0.0.1:{dados['porta']}",
        _linha("versão da API:", str(dados["versaoApi"] or "não respondeu")),
        _linha("interface que ela serve:", str(dados["interfaceApi"] or "—")),
        _linha("versão dessa interface:", str(dados["interfaceVersaoApi"] or "—")),
        "",
    ]
    for item in quadro["candidatas"]:
        estado = f"versão {item['versao']}" if item["carimbo"] else "sem carimbo (build antigo)"
        linhas.append(f"  · {item['pasta']:<10} {estado}")
    if quadro["candidatas"]:
        linhas.append("")

    if dados["pronto"]:
        linhas.append("VEREDITO: tudo certo.")
    else:
        linhas.append("VEREDITO: tem coisa fora de lugar.")
        for problema in dados["problemas"]:
            linhas.append(f"  - {problema}")
    linhas.append("")
    linhas.append("O que fazer (uma linha de cada vez):")
    for acao in dados["acoes"]:
        linhas.append(f"  {acao}")
    linhas.append("")
    linhas.append("Dica: se a tela continuar a antiga mesmo com tudo certo aqui,")
    linhas.append("      é o navegador. Aperte Ctrl+F5 na página do JARVIS.")
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diz qual versão do JARVIS está rodando e qual tela aparece.")
    parser.add_argument("--porta", type=int, default=8000, help="Porta da API (padrão: 8000).")
    parser.add_argument("--json", action="store_true", help="Dados crus, para conferir.")
    args = parser.parse_args(argv)

    dados = diagnostico(args.porta)
    if args.json:
        print(json.dumps(dados, ensure_ascii=False, indent=2))
    else:
        print(relatorio(dados))
    return 0 if dados["pronto"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
