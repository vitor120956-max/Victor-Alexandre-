"""Qual interface a API está servindo — e se ela é a mesma versão do servidor.

## O problema que este módulo resolve

Um relato real, com print da tela: *“já atualizei mas ainda não tem a parte para
botar as APIs”*. Na tela, o rodapé de Configurações dizia **VERSÃO 0.5.0** — um
número que só existe na interface antiga. O Python já estava novo; a **tela**
não. Três causas possíveis, e sem diagnóstico as três parecem iguais:

1. a atualização não foi aplicada **nesta pasta** (o `atualizar.bat` de outra
   cópia foi rodado, ou falhou e a janela fechou antes de alguém ler);
2. a API em execução é **antiga** e continua servindo o que carregou no start;
3. o navegador guardou o `index.html` velho em cache e nem pediu de novo.

Este módulo ataca (1) e (2) com fato, não palpite: cada build grava um
`versao.json` dentro da pasta da interface, e a API **compara** a versão que
está servindo com a sua. Se forem diferentes, `/api/health` diz, a tela avisa e
`conferir-versao.bat` explica em português. O (3) é tratado no `app.py`: o
`index.html` sai com `no-cache`, e `/assets/*` (nome com hash) sai com cache
longo — o que pode ser guardado é o que nunca muda de conteúdo.

## Por que não só a data do arquivo

A regra anterior escolhia a pasta mais **nova** pelo `mtime` do `index.html`.
Isso já consertou um caso real (`dist` velho escondendo `web-dist` novo), mas
depende de data de arquivo — e data mente em cópia por pendrive, em restauração
de backup e em pasta descompactada. Versão não mente: ela está escrita dentro do
arquivo.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ARQUIVO_VERSAO = "versao.json"
PASTAS = ("dist", "web-dist")
AMBIENTE_ESCOLHA = "JARVIS_INTERFACE"  # força `dist` ou `web-dist` (desenvolvimento)


def versao_da_pasta(pasta: Path) -> str | None:
    """A versão escrita no build daquela pasta, se ela declarar."""
    try:
        dados = json.loads((Path(pasta) / ARQUIVO_VERSAO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    versao = dados.get("versao") if isinstance(dados, dict) else None
    return str(versao).strip() if versao else None


def _numeros(versao: str) -> tuple[int, ...]:
    """“0.79.1” → (0, 79, 1). Comparar como texto erraria 0.9 < 0.10."""
    partes: list[int] = []
    for pedaco in versao.replace("-", ".").split("."):
        digitos = "".join(caractere for caractere in pedaco if caractere.isdigit())
        if not digitos:
            break
        partes.append(int(digitos))
    return tuple(partes) or (0,)


def mais_nova(versao: str, que: str | None) -> bool:
    """`versao` é mais nova que `que`? Sem “que”, qualquer versão ganha."""
    if not que:
        return True
    return _numeros(versao) > _numeros(que)


def candidatas(base: Path | None = None) -> list[dict[str, Any]]:
    """As pastas de interface que existem, com o que se sabe de cada uma."""
    raiz = Path(base) if base else _raiz()
    achadas: list[dict[str, Any]] = []
    for ordem, nome in enumerate(PASTAS):
        pasta = raiz / nome
        indice = pasta / "index.html"
        if not indice.is_file():
            continue
        try:
            quando = indice.stat().st_mtime
        except OSError:  # pragma: no cover - disco sem permissão
            quando = 0.0
        achadas.append(
            {
                "pasta": nome,
                "caminho": str(pasta),
                "versao": versao_da_pasta(pasta),
                "mtime": quando,
                "ordem": ordem,  # dist (0) ganha empate: é o build de quem desenvolve
            }
        )
    return achadas


def _raiz() -> Path:
    return Path(__file__).resolve().parents[1]


def escolher(base: Path | None = None) -> Path | None:
    """A pasta que a API vai servir.

    A ordem de decisão, do mais forte para o mais fraco:

    1. `JARVIS_INTERFACE=dist|web-dist` — quem desenvolve manda;
    2. **maior versão declarada** no `versao.json` — o fato;
    3. pasta **mais nova** pelo `mtime` do `index.html` — o palpite de antes;
    4. em empate, `dist`.
    """
    lista = candidatas(base)
    if not lista:
        return None

    forçada = (os.getenv(AMBIENTE_ESCOLHA) or "").strip().lower()
    if forçada in PASTAS:
        escolhida = next((item for item in lista if item["pasta"] == forçada), None)
        if escolhida is not None:
            return Path(escolhida["caminho"])

    com_versao = [item for item in lista if item["versao"]]
    if com_versao:
        # Versão conhecida vence versão desconhecida: um `dist` sem carimbo é
        # build local e não pode esconder a interface que veio na atualização.
        melhor = com_versao[0]
        for item in com_versao[1:]:
            if mais_nova(str(item["versao"]), str(melhor["versao"])):
                melhor = item
        return Path(melhor["caminho"])

    lista.sort(key=lambda item: (item["mtime"], -item["ordem"]), reverse=True)
    return Path(lista[0]["caminho"])


def estado(base: Path | None = None, versao_servidor: str = "", servida: Path | None = None) -> dict[str, Any]:
    """O quadro completo para a tela, para o `/api/health` e para o `.bat`.

    `desatualizada` só é `True` quando há dois números para comparar. Sem
    carimbo na pasta, a resposta é “não sei” — e dizer “não sei” é melhor do que
    alarmar sem motivo.
    """
    raiz = Path(base) if base else _raiz()
    lista = candidatas(raiz)
    escolhida = servida if servida is not None else escolher(raiz)
    nome = escolhida.name if escolhida else None
    versao = versao_da_pasta(escolhida) if escolhida else None
    desatualizada = bool(versao and versao_servidor and versao != versao_servidor)

    aviso = None
    if escolhida is None:
        aviso = "Não há interface compilada nesta pasta: rode `npm run build` ou use a `web-dist` que vem na atualização."
    elif desatualizada:
        aviso = (
            f"A tela que está sendo servida é a {versao} e o servidor é {versao_servidor}. "
            f"A atualização não chegou nesta pasta — rode `atualizar.bat` e abra `iniciar-jarvis.bat` de novo."
        )

    return {
        "servida": nome,
        "versao": versao,
        "versaoServidor": versao_servidor or None,
        "desatualizada": desatualizada,
        "aviso": aviso,
        "candidatas": [
            {
                "pasta": item["pasta"],
                "versao": item["versao"],
                # Sem carimbo a tela diz “sem carimbo”, não inventa número.
                "carimbo": bool(item["versao"]),
            }
            for item in lista
        ],
    }
