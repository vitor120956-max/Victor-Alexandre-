"""Direção de arte estática inspirada em Leonxlnx/taste-skill (MIT, 2026).

Implementação própria e determinística. Nenhum skill, script Node, navegador,
plugin, CLI `npx skills`, marketplace ou aplicativo do upstream é instalado ou
executado. As skills leem o que você declara — briefing, argumento, código-fonte,
HTML e notas de júri — e devolvem candidatos com evidência, veredito e limites.

O recorte é o que sobrevive sem navegador: o sorteio determinístico de direções,
o argumento antes do desenho, o registro datado de tells, a medição estática da
moldura e a nota ponderada de júri com tetos.
"""
from __future__ import annotations

import hashlib
import random
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from .review import common, finalize, finding
from .studio import contrast_ratio

MAX_BRIEF_CHARS = 4_000
MAX_SECTIONS_CHARS = 2_000
MAX_CLAIMS_CHARS = 50_000
MAX_FILES_CHARS = 300_000
MAX_HTML_CHARS = 200_000
MAX_ENTRIES_CHARS = 50_000
MAX_FIELD_CHARS = 400
MAX_ROWS = 120
MAX_PROOF_LINES = 6

DEFAULT_WIDTHS = (1440, 768, 390)


class TasteError(ValueError):
    """Erro esperado da direção de arte, seguro para o usuário."""


# ------------------------------------------------------------------ vocabulário

SECTORS: dict[str, tuple[str, tuple[str, ...]]] = {
    "alimentacao": ("Alimentação", ("food", "restaurante", "cafe", "padaria", "bar")),
    "hospitalidade": ("Hospitalidade", ("hospitality", "hotel", "pousada", "hospedagem")),
    "software": ("Software", ("saas", "produto digital", "app", "plataforma")),
    "portfolio": ("Portfólio", ("portifolio", "estudio", "studio", "agencia", "freelance")),
    "evento": ("Evento", ("event", "festival", "show", "conferencia")),
    "varejo": ("Varejo", ("retail", "loja", "produto fisico", "marca")),
    "servico": ("Serviço", ("service", "consultoria", "clinica", "escritorio")),
    "cultura": ("Cultura", ("culture", "museu", "galeria", "teatro", "livro")),
    "saude": ("Saúde", ("health", "bem-estar", "terapia", "academia")),
    "imovel": ("Imóvel", ("imobiliaria", "arquitetura", "casa", "construcao")),
}
SECTOR_ALIASES = {alias: key for key, (_label, aliases) in SECTORS.items() for alias in aliases}
SECTOR_ALIASES.update({key: key for key in SECTORS})

TONES: dict[str, tuple[str, tuple[str, ...]]] = {
    "quieto": ("Quieto", ("quiet", "calmo", "discreto", "contido")),
    "ousado": ("Ousado", ("bold", "forte", "agressivo", "direto")),
    "quente": ("Quente", ("warm", "afetivo", "artesanal")),
    "tecnico": ("Técnico", ("technical", "preciso", "engenharia")),
    "ludico": ("Lúdico", ("playful", "divertido", "leve")),
    "luxo": ("Luxo", ("luxury", "premium", "sofisticado")),
    "editorial": ("Editorial", ("editorial", "revista", "jornal", "livro")),
}
TONE_ALIASES = {alias: key for key, (_label, aliases) in TONES.items() for alias in aliases}
TONE_ALIASES.update({key: key for key in TONES})

ASSETS: dict[str, tuple[str, tuple[str, ...]]] = {
    "fotografia": ("Fotografia", ("photo", "photography", "foto", "fotos")),
    "produto": ("Foto de produto", ("product-photo", "produto", "packshot")),
    "interface": ("Interface real", ("product-ui", "ui", "telas", "screenshots")),
    "ilustracao": ("Ilustração", ("illustration", "desenho", "arte")),
    "video": ("Vídeo", ("video", "filme", "footage", "clipe")),
}
ASSET_ALIASES = {alias: key for key, (_label, aliases) in ASSETS.items() for alias in aliases}
ASSET_ALIASES.update({key: key for key in ASSETS})

ROLES: dict[str, tuple[str, tuple[str, ...]]] = {
    "intro": ("Introdução", ("intro", "manifesto")),
    "sobre": ("Sobre", ("about", "historia", "quem-somos")),
    "trabalho": ("Trabalho", ("work", "projetos", "cases")),
    "galeria": ("Galeria", ("gallery", "fotos", "acervo")),
    "vitrine": ("Vitrine", ("showcase", "produtos", "cardapio", "menu")),
    "como-funciona": ("Como funciona", ("how-it-works", "processo", "etapas")),
    "recursos": ("Recursos", ("features", "funcionalidades")),
    "prova": ("Prova", ("proof", "depoimento", "testimonial", "clientes")),
    "numeros": ("Números", ("stats", "indicadores")),
    "preco": ("Preço", ("pricing", "planos", "valores")),
    "faq": ("Perguntas", ("faq", "duvidas", "perguntas")),
    "depoimento": ("Depoimento", ("quote", "citacao")),
    "contato": ("Contato", ("contact", "endereco", "localizacao")),
    "lista": ("Lista", ("list", "agenda", "programacao")),
    "cta": ("Ação final", ("call-to-action", "convite")),
    "rodape": ("Rodapé", ("footer", "creditos")),
}
ROLE_ALIASES = {alias: key for key, (_label, aliases) in ROLES.items() for alias in aliases}
ROLE_ALIASES.update({key: key for key in ROLES})
KEEP_SLOTS = {"palette": "paleta", "paleta": "palette", "type": "type", "tipografia": "type"}
REDRAW_SLOTS = {
    "hero", "type", "palette", "photos", "scenes", "direction",
    *(f"section:{role}" for role in ROLES),
}


def _direction(
    key: str,
    name: str,
    thesis: str,
    *,
    sectors: tuple[str, ...],
    tones: tuple[str, ...],
    needs: tuple[str, ...],
    hero: str,
    type_system: str,
    palette: tuple[str, str, str, str],
    imagery: str,
    motion: str,
    blueprint: dict[str, str],
    fallback: str,
    traps: tuple[str, ...],
    avoids: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "id": key,
        "name": name,
        "thesis": thesis,
        "sectors": frozenset(sectors),
        "tones": frozenset(tones),
        "needs": frozenset(needs),
        "hero": hero,
        "type": type_system,
        "palette": {"ground": palette[0], "ink": palette[1], "accent": palette[2], "field": palette[3]},
        "imagery": imagery,
        "motion": motion,
        "blueprint": blueprint,
        "fallback": fallback,
        "traps": traps,
        "avoids": avoids,
    }


DIRECTIONS: tuple[dict[str, Any], ...] = (
    _direction(
        "fachada", "A fachada",
        "O lugar aparece de frente, como quem chega na rua: a fachada desenhada ocupa a primeira tela e a página inteira é a visita.",
        sectors=("alimentacao", "varejo", "hospitalidade", "servico"),
        tones=("quente", "editorial", "ousado"),
        needs=("fotografia",),
        hero="Fachada desenhada em uma única linguagem chapada, de 55% a 70% da altura, com o nome do lugar grande sobre ou ao lado dela. Sem foto genérica de mesa posta.",
        type_system="Uma condensada para o letreiro (display em caixa alta, duas linhas no máximo) e uma grotesca quente para o texto. Tamanhos: display, corpo, pequeno.",
        palette=("pedra ou papel quente", "quase preto", "cor de esmalte do letreiro", "campo de cor para a seção de horários"),
        imagery="A rua, a placa, a porta, o balcão. Fotos do lugar real; o desenho da fachada cobre o que não existe em foto.",
        motion="A porta abre: o herói entra de opacidade 0 e escala 0.98 em 220 ms, ease-out forte; o resto entra em degraus de 70 ms.",
        blueprint={
            "vitrine": "Vitrine encostada na calçada: itens em uma faixa horizontal com preço ao lado, sem cartões.",
            "sobre": "Texto em duas colunas desiguais com uma foto do interior ocupando a coluna maior.",
            "lista": "Horários e endereço como uma placa: fundo de campo, duas colunas, tipo grande.",
            "contato": "Endereço em corpo de manchete, mapa desenhado ao lado, ação única.",
        },
        fallback="Uma faixa de cor com o conteúdo e uma imagem sangrada ao lado.",
        traps=(
            "Desenhar uma fachada genérica: sem toldo, sem número, sem a cor da rua, a ideia serve a qualquer padaria.",
            "Colocar o letreiro em cima de uma foto de banco de imagens.",
            "Encher a página de cartões de recurso depois de um herói forte.",
        ),
        avoids=("software sem endereço físico", "marca cujo produto é intangível"),
    ),
    _direction(
        "arquivo", "O arquivo",
        "Uma imagem de arquivo grande abre a página e o resto é o que ela documenta: pranchas, legendas e recortes com crédito.",
        sectors=("cultura", "portfolio", "imovel", "hospitalidade"),
        tones=("editorial", "quieto", "luxo"),
        needs=("fotografia",),
        hero="Fotografia de arquivo sangrada de 60% a 75% da tela, com uma legenda curta e o título em corpo de manchete sobre campo chapado ao lado ou abaixo.",
        type_system="Serifada de display para títulos e uma grotesca neutra para texto. Legendas no mesmo corpo do texto, nunca em mono.",
        palette=("papel envelhecido de baixa saturação", "tinta escura", "um vermelho de carimbo", "campo de cor para a seção de acervo"),
        imagery="Arquivo público com crédito visível: postal da rua, planta antiga, gravura do ofício, objeto de museu. Toda imagem tem legenda com fonte.",
        motion="A imagem abre: de 1.04 para 1.0 em 900 ms no scroll; legendas entram com 60 ms de atraso.",
        blueprint={
            "galeria": "Pranchas em grade irregular: uma grande, duas pequenas, sempre com legenda e crédito.",
            "sobre": "Coluna de texto estreita ao lado de um documento grande; nada centralizado.",
            "trabalho": "Índice de peças com ano e material, sem cartões.",
            "rodape": "Créditos das imagens em corpo pequeno e visível.",
        },
        fallback="Uma prancha de imagem com texto curto ao lado.",
        traps=(
            "Usar imagem de banco sem crédito ou fingir que é acervo do cliente.",
            "Decorar com molduras finas e numeração de prancha.",
            "Deixar o texto pequeno: a página vira uma exposição sem etiqueta legível.",
        ),
        avoids=("produto que precisa de packshot", "serviço sem acervo"),
    ),
    _direction(
        "campo", "O campo de cor",
        "Cada seção é um campo chapado de cor com o seu próprio texto, e a página muda de tom como quem vira a página de um livro.",
        sectors=("software", "evento", "varejo", "cultura"),
        tones=("ousado", "ludico", "editorial"),
        needs=(),
        hero="Um campo de cor de tela cheia, título grande em duas linhas no canto inferior esquerdo, uma única ação. Sem cartões e sem imagem obrigatória.",
        type_system="Uma display larga para títulos e uma grotesca para texto. Tamanhos: display, lead, corpo, pequeno — no máximo quatro.",
        palette=("primeiro campo de cor saturada", "tinta de contraste alto", "uma segunda cor para a ação", "campos alternados por seção"),
        imagery="Poucas imagens, recortadas dentro de campos; quando não houver foto honesta, tipografia e cor sozinhas sustentam a página.",
        motion="A troca de campo: cada seção entra com 12 px de deslocamento e o fundo muda por corte seco, nunca por gradiente.",
        blueprint={
            "recursos": "Um recurso por campo, frase curta e uma demonstração, sem ícone.",
            "preco": "O preço em corpo de manchete dentro do campo, com o que inclui em lista.",
            "prova": "Uma citação grande em campo escuro, atribuída a uma pessoa real.",
            "cta": "Campo final com uma ação e uma linha de contexto.",
        },
        fallback="Campo chapado com título e uma coluna de texto.",
        traps=(
            "Escolher cores pastel e chamar de campo: sem saturação, vira papel de parede.",
            "Misturar gradiente entre os campos.",
            "Deixar texto cinza sobre campo colorido.",
        ),
        avoids=("marca com paleta fixa de uma cor", "assunto que pede fotografia documental"),
    ),
    _direction(
        "carta", "A carta",
        "A página é uma carta ou um menu impresso: coluna estreita, cabeçalho com nome e data, listas com preço e uma assinatura no fim.",
        sectors=("alimentacao", "servico", "portfolio", "evento"),
        tones=("quente", "quieto", "editorial"),
        needs=(),
        hero="Cabeçalho de papel com o nome grande, uma linha de contexto e a data; abaixo, um sumário do que a pessoa encontra. Sem imagem obrigatória.",
        type_system="Uma serifada de texto para quase tudo e uma display da mesma família para o nome. Corpo generoso, entrelinha 1.6.",
        palette=("papel de baixa saturação", "tinta marrom-escura", "um verde ou vinho de assinatura", "sem campos: o papel é o fundo"),
        imagery="Poucas fotos, pequenas e dentro do texto, como ilustrações de um menu; o resto é tipografia.",
        motion="As linhas entram como texto datilografado: opacidade e 8 px, em degraus de 40 ms, uma vez.",
        blueprint={
            "vitrine": "Menu em lista: nome, descrição curta, preço alinhado à direita com tabular-nums.",
            "sobre": "Duas colunas de texto com uma foto pequena entre elas.",
            "contato": "Assinatura, endereço e horário em bloco de texto, sem ícones.",
            "faq": "Perguntas em lista, resposta logo abaixo, sem acordeão decorativo.",
        },
        fallback="Coluna de texto com um bloco de lista e uma imagem pequena.",
        traps=(
            "Imitar papel com textura, sombra e borda serrilhada.",
            "Usar capitular decorativa sem relação com o assunto.",
            "Fazer uma carta sem nada específico: sem nome, endereço ou preço, é um template.",
        ),
        avoids=("produto de software", "marca que depende de imagem grande"),
    ),
    _direction(
        "mapa", "O mapa",
        "Uma planta ou mapa desenhado vira o motivo e a navegação: cada seção é uma parada no território do assunto.",
        sectors=("hospitalidade", "imovel", "evento", "cultura"),
        tones=("tecnico", "editorial", "quente"),
        needs=("fotografia",),
        hero="Mapa ou planta desenhada em linha grossa ocupando a tela, com o título em corpo de manchete e uma parada destacada.",
        type_system="Uma grotesca condensada para títulos e uma grotesca neutra para texto. Rótulos do mapa em caixa alta com tracking apenas dentro do desenho.",
        palette=("papel ou concreto claro", "tinta escura", "uma cor de rota", "campo de cor na seção de paradas"),
        imagery="Fotos de cada parada, sempre associadas ao ponto no mapa; o desenho cobre o que não existe em foto.",
        motion="A rota se desenha: um traço SVG cresce em 1200 ms ao entrar na seção, uma vez.",
        blueprint={
            "como-funciona": "Paradas numeradas por posição no mapa, sem números decorativos no texto.",
            "galeria": "Cada foto ancorada ao seu ponto, com legenda de lugar.",
            "contato": "O endereço como ponto final da rota, mapa grande ao lado.",
            "lista": "Agenda em lista, com o lugar de cada item ao lado.",
        },
        fallback="Mapa pequeno ao lado de uma lista de paradas.",
        traps=(
            "Desenhar um mapa genérico de cidade inventada.",
            "Encher o mapa de alfinetes e legendas ilegíveis no celular.",
            "Usar linha fina: o mapa precisa de traço grosso.",
        ),
        avoids=("software sem território", "marca sem lugares reais"),
    ),
    _direction(
        "mostruario", "O mostruário",
        "Uma grade densa de objetos com títulos enormes e corpo pequeno: a página mostra o acervo inteiro e deixa o material falar.",
        sectors=("varejo", "portfolio", "cultura", "alimentacao"),
        tones=("editorial", "luxo", "ousado"),
        needs=("produto", "fotografia"),
        hero="Título enorme em uma linha e uma grade de três a cinco objetos que começa já na primeira tela, sem texto de apoio longo.",
        type_system="Uma display de peso médio para títulos e uma grotesca pequena para fichas. Corpo de ficha 14 px, nunca menor.",
        palette=("neutro claro", "quase preto", "uma cor de etiqueta", "sem campos: a grade é a estrutura"),
        imagery="Close-ups do material e do objeto, com a mesma luz e o mesmo enquadramento; fichas técnicas ao lado.",
        motion="A grade entra em cascata de 40 ms por item, uma vez, com 12 px de deslocamento.",
        blueprint={
            "vitrine": "Grade de objetos com nome, material e preço; filtros como texto, não como pílulas.",
            "trabalho": "Projetos em grade irregular, cada um com ano e material.",
            "sobre": "Texto curto ao lado de um close-up grande.",
            "preco": "Tabela simples: peça, tamanho, preço.",
        },
        fallback="Grade de três itens com título e ficha curta.",
        traps=(
            "Preencher a grade com imagens de banco de objetos que o cliente não vende.",
            "Transformar tudo em cartão com sombra.",
            "Deixar fichas em cinza claro sobre branco.",
        ),
        avoids=("serviço sem acervo", "software sem produto físico"),
    ),
    _direction(
        "cinema", "O cinema",
        "A página é uma sequência de planos: imagens sangradas, cortes secos e texto curto sobre uma área calma da imagem.",
        sectors=("evento", "hospitalidade", "portfolio", "cultura"),
        tones=("ousado", "luxo", "editorial"),
        needs=("fotografia", "video"),
        hero="Um plano sangrado de tela cheia, título em duas linhas sobre uma área calma, uma ação discreta. Nada de cartão sobre a imagem.",
        type_system="Uma grotesca de display em peso regular ou médio e a mesma família no texto. Títulos grandes, texto 17 px.",
        palette=("preto ou quase preto", "branco levemente quente", "uma cor de crédito", "sem campos: a imagem é o fundo"),
        imagery="Fotografia e vídeo do assunto real, com um tratamento único (tudo cru ou tudo em um grade definido). Nada de banco genérico.",
        motion="Corte e parallax: a imagem se move 6% mais devagar que o texto; a transição entre planos é seca, 200 ms.",
        blueprint={
            "galeria": "Planos em tela cheia com legenda curta no canto.",
            "sobre": "Texto em bloco estreito sobre campo escuro depois de um plano.",
            "programa": "Agenda em lista sobre imagem escurecida, com horário e lugar.",
            "cta": "Último plano com uma ação nomeada.",
        },
        fallback="Um plano grande com bloco de texto ao lado em campo escuro.",
        traps=(
            "Usar scrim em gradiente largo demais: só a área do texto pode escurecer.",
            "Empilhar dez animações de entrada.",
            "Texto sobre parte movimentada da imagem.",
        ),
        avoids=("marca sem imagem", "produto sem fotografia"),
    ),
    _direction(
        "oficina", "A oficina",
        "O processo aparece em close-ups e etapas fotografadas: a página prova como a coisa é feita em vez de dizer que é artesanal.",
        sectors=("varejo", "alimentacao", "servico", "portfolio"),
        tones=("quente", "tecnico", "editorial"),
        needs=("fotografia",),
        hero="Close-up de mão, material ou ferramenta em 60% da tela; título curto e uma linha de contexto ao lado, sem selo de artesanal.",
        type_system="Uma grotesca industrial para títulos e uma serifada de texto para o corpo; fichas técnicas em tabular-nums.",
        palette=("concreto ou metal claro", "tinta de óleo", "uma cor de marcação", "campo escuro para a seção de etapas"),
        imagery="Fotos do processo real: matéria-prima, ferramenta, etapa, resultado. Nada de banco de imagens de oficina.",
        motion="O compasso: cada etapa entra com 90 ms de atraso e uma barra de progresso desenhada avança uma vez.",
        blueprint={
            "como-funciona": "Etapas como faixas horizontais com foto e uma frase, sem ícone e sem número decorativo.",
            "vitrine": "Objetos acabados em grade com ficha de material e tempo.",
            "prova": "Números de produção com fonte e período declarados.",
            "sobre": "Retrato do ofício e uma frase sobre o método.",
        },
        fallback="Faixa com foto do processo ao lado de uma lista de etapas.",
        traps=(
            "Inventar números de produção.",
            "Usar 'feito à mão' como título sem mostrar a mão.",
            "Repetir o mesmo layout em todas as etapas.",
        ),
        avoids=("software", "serviço sem processo visível"),
    ),
    _direction(
        "vitrine", "A vitrine",
        "O produto aparece recortado em um campo chapado, grande, sem sombra e sem cenário: a página é a mesa onde ele é examinado.",
        sectors=("varejo", "software", "saude", "servico"),
        tones=("quieto", "luxo", "tecnico"),
        needs=("produto", "interface"),
        hero="O produto recortado ocupando 50% a 65% da tela sobre campo chapado, nome em duas linhas e preço ou função em corpo de lead.",
        type_system="Uma grotesca neutra para tudo, com display em peso médio; detalhes em tabular-nums. Uma família só.",
        palette=("campo chapado claro ou escuro", "tinta de contraste", "uma cor de detalhe", "campo de segunda cor para a ficha técnica"),
        imagery="Packshot ou interface real recortada. Se o produto é software, a tela é construída em HTML com dados que fecham.",
        motion="O objeto se ajusta: de 0.96 para 1.0 com opacidade em 240 ms; a ficha entra 80 ms depois.",
        blueprint={
            "vitrine": "Ficha técnica ao lado do objeto: medida, material, o que inclui.",
            "preco": "Preço grande com o que inclui em lista curta.",
            "recursos": "Um recurso por faixa, com recorte da interface real.",
            "faq": "Perguntas em lista, respostas curtas.",
        },
        fallback="Objeto grande com ficha e uma ação.",
        traps=(
            "Recortar um produto que não existe ou usar packshot de banco.",
            "Colocar sombra para 'dar profundidade'.",
            "Inventar números de desempenho.",
        ),
        avoids=("marca editorial", "assunto que não tem objeto"),
    ),
    _direction(
        "cartaz", "O cartaz",
        "Uma frase enorme, um campo de cor e um detalhe: a página é um cartaz que rola, e cada seção é uma afinação do mesmo gesto.",
        sectors=("evento", "cultura", "varejo", "software"),
        tones=("ousado", "ludico", "editorial"),
        needs=(),
        hero="Uma frase de até duas linhas em corpo de manchete, um campo de cor, um detalhe gráfico desenhado. Nada mais na primeira tela além de uma ação.",
        type_system="Uma display larga ou condensada, uma família só; corpo em 17 px. Tamanhos: display, lead, corpo.",
        palette=("campo de cor saturada", "tinta de contraste", "uma segunda cor chapada", "troca de campo por seção"),
        imagery="Imagens aparecem recortadas como parte do cartaz, nunca como fundo de texto.",
        motion="O cartaz se compõe: cada bloco entra com 16 px e opacidade, em 200 ms, uma vez.",
        blueprint={
            "programa": "Programação como bloco de cartaz: data grande, atração, horário.",
            "sobre": "Um parágrafo em corpo de lead dentro do campo.",
            "preco": "Ingresso com valor grande e o que inclui.",
            "cta": "Uma frase e uma ação.",
        },
        fallback="Frase grande e um bloco de texto curto em campo chapado.",
        traps=(
            "Escrever um parágrafo inteiro em corpo de cartaz.",
            "Usar três famílias para parecer editorial.",
            "Encher o cartaz de selos e emblemas.",
        ),
        avoids=("produto que exige demonstração", "serviço que precisa de prova extensa"),
    ),
    _direction(
        "boletim", "O boletim",
        "A página é um boletim ou uma agenda: duas colunas desiguais, datas, listas e títulos de jornal, com imagens pequenas e específicas.",
        sectors=("cultura", "evento", "servico", "portfolio"),
        tones=("editorial", "tecnico", "quieto"),
        needs=("fotografia",),
        hero="Título de jornal em duas linhas, uma linha de data e lugar, e a primeira matéria com foto pequena ao lado — sem imagem de fundo.",
        type_system="Uma serifada de jornal para títulos e texto, com uma grotesca para fichas e datas. Entrelinha apertada nos títulos.",
        palette=("papel claro", "tinta preta", "um vermelho de editoria", "sem campos"),
        imagery="Fotos pequenas e documentais, com legenda; a hierarquia vem do texto, não da imagem.",
        motion="A edição entra: blocos com 12 px e opacidade, 60 ms entre eles, uma vez.",
        blueprint={
            "lista": "Agenda com data à esquerda, título e lugar à direita.",
            "trabalho": "Matérias em duas colunas com fio de texto, não com cartões.",
            "sobre": "Texto em coluna estreita com uma foto e legenda.",
            "contato": "Bloco de serviço: endereço, horário, telefone.",
        },
        fallback="Duas colunas de texto com uma foto e uma lista.",
        traps=(
            "Desenhar fios finos e grade de jornal: a estrutura vem do espaço.",
            "Usar texto justificado e colunas longas demais.",
            "Inventar notícias ou números de tiragem.",
        ),
        avoids=("produto de consumo aspiracional", "marca visualmente silenciosa"),
    ),
    _direction(
        "passeio", "O passeio",
        "A página é um percurso: cada parada ocupa uma tela, a imagem muda e o texto acompanha; a pessoa avança como quem caminha.",
        sectors=("hospitalidade", "imovel", "evento", "cultura"),
        tones=("quieto", "luxo", "editorial"),
        needs=("fotografia", "video"),
        hero="Primeira parada com imagem de 70% da tela, título curto e uma linha que diz onde se está; a próxima parada é sugerida por um corte visível.",
        type_system="Uma família só, display em peso regular e texto 17 px; legendas de parada em corpo pequeno com tracking leve apenas dentro da cena.",
        palette=("tom natural da primeira parada", "tinta escura", "uma cor de sinalização", "campos por parada"),
        imagery="Uma imagem por parada, todas no mesmo tratamento, do mesmo lugar e no mesmo horário quando possível.",
        motion="A cena fixa: a imagem fica presa por 1.5 tela enquanto o texto avança; no celular, a cena vira empilhada.",
        blueprint={
            "galeria": "Uma parada por seção, com legenda e um detalhe do lugar.",
            "como-funciona": "O percurso em etapas, cada uma com a sua imagem.",
            "contato": "A última parada é a chegada: endereço e ação.",
            "prova": "Uma citação curta na parada mais silenciosa.",
        },
        fallback="Uma imagem por seção com texto ao lado.",
        traps=(
            "Prender três telas seguidas sem conteúdo.",
            "Usar imagens de lugares diferentes como se fossem o mesmo.",
            "Deixar a pessoa sem sinal de progresso.",
        ),
        avoids=("software", "marca sem lugar"),
    ),
)

DIRECTION_INDEX = {direction["id"]: direction for direction in DIRECTIONS}


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().split())


def _mode(mode: str) -> None:
    if mode not in {"lite", "full", "ultra"}:
        raise TasteError("Nível inválido: use lite, full ou ultra.")


def _lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _rows(text: str, expected: int, label: str, limit: int = MAX_ROWS) -> list[tuple[int, list[str]]]:
    if not text.strip():
        raise TasteError(f"Informe ao menos {label}.")
    rows: list[tuple[int, list[str]]] = []
    for number, raw in enumerate(_lines(text), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        cells = [cell.strip() for cell in stripped.split("|")]
        if len(cells) > expected:
            raise TasteError(f"Linha {number}: use no máximo {expected} campos separados por |.")
        if any(len(cell) > MAX_FIELD_CHARS for cell in cells):
            raise TasteError(f"Linha {number}: cada campo deve ter até {MAX_FIELD_CHARS} caracteres.")
        cells += [""] * (expected - len(cells))
        rows.append((number, cells))
    if not rows:
        raise TasteError(f"Informe ao menos {label}.")
    if len(rows) > limit:
        raise TasteError(f"A entrada tem {len(rows)} linhas; o limite é {limit}.")
    return rows


def _tokens(value: str, aliases: dict[str, str], label: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"[,|;]", value) if part.strip()]
    resolved: list[str] = []
    for part in parts:
        key = aliases.get(_norm(part))
        if key is None:
            raise TasteError(f"{label} desconhecido: {part}.")
        if key not in resolved:
            resolved.append(key)
    return resolved


def _seed_of(brief: str, sector: str, tone: str, sections: list[str]) -> str:
    material = "|".join([brief.strip().lower(), sector, tone, ",".join(sections)])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


def _num(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _option(direction: dict[str, Any], sector: str, tone: str, have: set[str], keep: set[str]) -> dict[str, Any]:
    fit: list[str] = []
    tension: list[str] = []
    if sector and sector in direction["sectors"]:
        fit.append(f"o setor {SECTORS[sector][0].lower()} aparece no estudo desta direção")
    if tone and tone in direction["tones"]:
        fit.append(f"o tom {TONES[tone][0].lower()} combina com a composição")
    covered = direction["needs"] & have
    if covered:
        fit.append("os ativos que você tem (" + ", ".join(sorted(covered)) + ") sustentam a direção")
    missing = direction["needs"] - have
    if missing:
        tension.append("vai pedir " + ", ".join(sorted(missing)) + " que você não declarou")
    if sector and sector not in direction["sectors"]:
        tension.append("o setor não é o habitat natural desta direção")
    if "palette" in keep:
        tension.append("a paleta é da marca: a direção entra só pela composição")
    if not fit:
        fit.append("é uma direção improvável aqui — só escolha se a ficha disser por quê")
    return {
        "id": direction["id"],
        "name": direction["name"],
        "thesis": direction["thesis"],
        "hero": direction["hero"],
        "needs": sorted(direction["needs"]),
        "fit": fit,
        "tension": tension,
    }


def _sheet(direction: dict[str, Any], sections: list[str], keep: set[str], seed: str) -> dict[str, Any]:
    palette = dict(direction["palette"])
    if "palette" in keep:
        palette = {
            "mode": "brand",
            "ground": "a cor de fundo da marca",
            "ink": "a cor de texto da marca",
            "accent": "o acento já definido",
            "field": "um segundo tom da marca para seções",
            "note": "A direção entra pela composição; as cores são as da marca, com a mesma proporção.",
        }
    else:
        palette = {**palette, "mode": "dealt", "proportion": "fundo 70–90% · tinta no texto · acento abaixo de 5% de cada tela · campos por seção"}

    type_system = direction["type"]
    if "type" in keep:
        type_system = "Tipografia da marca preservada. Use a escala da direção: display, lead quando existir, corpo e pequeno — no máximo quatro tamanhos."

    sheet_sections = [
        {"role": role, "label": ROLES[role][0], "layout": direction["blueprint"].get(role, direction["fallback"])}
        for role in sections
    ]
    return {
        "id": direction["id"],
        "name": direction["name"],
        "thesis": direction["thesis"],
        "seed": seed,
        "idea": (
            "Preencha com o inventário: nesta página, [algo que só este sujeito tem] vira "
            f"{direction['name'].lower()} — {direction['thesis'].split(':')[0].strip().lower()}."
        ),
        "hero": direction["hero"],
        "type": type_system,
        "palette": palette,
        "imagery": direction["imagery"],
        "motion": direction["motion"],
        "sections": sheet_sections,
        "traps": list(direction["traps"]),
        "avoids": list(direction["avoids"]),
        "slots": ["hero", "type", "palette", "photos", "scenes", "section:<papel>", "direction"],
    }


def deal_direction(
    *,
    brief: str,
    sector: str = "",
    sections: str = "",
    tone: str = "",
    have: str = "",
    keep: str = "",
    seed: str = "",
    direction: str = "",
    redraws: str = "",
    mode: str = "full",
) -> dict[str, Any]:
    _mode(mode)
    if not brief.strip():
        raise TasteError("Descreva o sujeito em uma linha antes de sortear uma direção.")
    if len(brief) > MAX_BRIEF_CHARS:
        raise TasteError(f"O briefing excede {MAX_BRIEF_CHARS:,} caracteres.".replace(",", "."))
    if len(sections) > MAX_SECTIONS_CHARS:
        raise TasteError(f"As seções excedem {MAX_SECTIONS_CHARS:,} caracteres.".replace(",", "."))

    findings: list[dict[str, Any]] = []

    def add(*args: str) -> None:
        findings.append(finding(*args))

    sector_key = ""
    if sector.strip():
        sector_key = SECTOR_ALIASES.get(_norm(sector), "")
        if not sector_key:
            valid = ", ".join(key for key in SECTORS)
            add("must", "unknown-sector", "Setor desconhecido", sector.strip()[:60],
                f"`{sector.strip()}` não está no vocabulário da direção.",
                "O setor decide quais direções fazem sentido; um valor livre desliga esse filtro.",
                f"Use um destes: {valid}.", "A ficha sai sem afinidade de setor.")

    tone_key = ""
    if tone.strip():
        tone_key = TONE_ALIASES.get(_norm(tone), "")
        if not tone_key:
            add("must", "unknown-tone", "Tom desconhecido", tone.strip()[:60],
                f"`{tone.strip()}` não está no vocabulário de tom.",
                "Tom é opcional, mas inventar um não muda o sorteio.",
                "Use " + ", ".join(key for key in TONES) + " ou deixe vazio.", "O tom é ignorado.")

    have_keys: set[str] = set()
    if have.strip():
        try:
            have_keys = set(_tokens(have, ASSET_ALIASES, "Ativo"))
        except TasteError as exc:
            add("must", "unknown-asset", "Ativo desconhecido", have.strip()[:60], str(exc),
                "A ficha só evita composições que dependem de ativos ausentes se souber o que existe.",
                "Use fotografia, produto, interface, ilustracao ou video.", "A ficha pode pedir foto que você não tem.")

    keep_keys: set[str] = set()
    raw_keep = [part.strip() for part in re.split(r"[,|]", keep) if part.strip()]
    for part in raw_keep:
        key = KEEP_SLOTS.get(_norm(part))
        if key is None:
            add("must", "unknown-keep", "Peça preservada desconhecida", part[:60],
                f"`{part}` não é uma peça que a direção saiba preservar.",
                "Só paleta e tipografia podem vir da marca; o resto é a direção.",
                "Use palette/paleta ou type/tipografia.", "A restrição é ignorada.")
            continue
        keep_keys.add(key)

    section_keys: list[str] = []
    if sections.strip():
        try:
            section_keys = _tokens(sections, ROLE_ALIASES, "Seção")
        except TasteError as exc:
            add("must", "unknown-section", "Seção desconhecida", sections.strip()[:80], str(exc),
                "Uma seção sem blueprint na biblioteca não pode ser composta.",
                "Use papéis como recursos, prova, preco, faq, contato.", "A seção cai no layout padrão da direção.")
        if len(section_keys) > 9:
            add("should", "many-sections", "Muitas seções", f"{len(section_keys)} seções",
                f"Você pediu {len(section_keys)} seções; a biblioteca compõe bem até 9.",
                "Página longa demais dilui o argumento e repete layouts.",
                "Corte as seções sem afirmação própria.", "A página vira uma sequência de blocos.")

    if not section_keys:
        add("must", "sections-missing", "Nenhuma seção declarada", "briefing",
            "O sorteio da ficha precisa da ordem do argumento.",
            "Sem seções, a direção não pode dizer o que cada tela mostra.",
            "Liste as seções na ordem em que o leitor deve encontrá-las.", "Só as três opções podem ser sorteadas.")

    seed_value = seed.strip().lower()
    if seed_value and not re.fullmatch(r"[a-z0-9-]{2,32}", seed_value):
        raise TasteError("A semente aceita de 2 a 32 caracteres: letras minúsculas, números e hífen.")
    if not seed_value:
        seed_value = _seed_of(brief, sector_key, tone_key, section_keys)

    chosen: dict[str, Any] | None = None
    if direction.strip():
        chosen = DIRECTION_INDEX.get(_norm(direction))
        if chosen is None:
            add("must", "unknown-direction", "Direção desconhecida", direction.strip()[:60],
                "Esta direção não está na biblioteca.",
                "Escolher uma direção inventada desliga a ficha e os seus limites.",
                "Use um id entre as três opções sorteadas.", "Nenhuma ficha é montada.")
            direction = ""

    redraw_items: list[dict[str, str]] = []
    if redraws.strip():
        try:
            for number, cells in _rows(redraws, 2, "redesenho"):
                slot, reason = cells
                if slot not in REDRAW_SLOTS:
                    add("must", "unknown-redraw-slot", "Peça de redesenho desconhecida", f"linha {number}",
                        f"`{slot}` não é uma peça redesenhável.",
                        "Redesenhar fora do contrato esconde a troca da direção inteira.",
                        "Use hero, type, palette, photos, scenes, direction ou section:<papel>.",
                        "O redesenho não é registrado.")
                    continue
                if len(reason.strip()) < 20:
                    add("must", "redraw-without-reason", "Redesenho sem motivo declarado", f"linha {number}",
                        f"Motivo com {len(reason.strip())} caractere(s).",
                        "A regra é redesenhar só por um motivo que você consiga dizer.",
                        "Declare o conflito de marca ou o ativo que não existe.", "A ficha é escolhida por conforto, não por adequação.")
                    continue
                redraw_items.append({"slot": slot, "reason": reason.strip()})
        except TasteError as exc:
            add("must", "redraw-invalid", "Redesenho inválido", "redraws", str(exc),
                "O formato é `peça | motivo`.", "Uma linha por redesenho.", "Nenhum redesenho é lido.")

    rng = random.Random(f"taste:{seed_value}")
    pool = list(DIRECTIONS)
    rng.shuffle(pool)
    if sector_key:
        pool.sort(key=lambda item: 0 if sector_key in item["sectors"] else 1)
    if tone_key:
        pool.sort(key=lambda item: 0 if (sector_key in item["sectors"], tone_key in item["tones"]) == (True, True) else 1)
    options = [_option(item, sector_key, tone_key, have_keys, keep_keys) for item in pool[:3]]

    low_brief = _norm(brief)
    generic_words = ("moderno", "moderna", "clean", "premium", "minimalista", "elegante", "profissional", "incrivel", "bonito")
    if len(brief.strip()) < 20:
        add("should", "vague-brief", "Briefing curto demais", "briefing",
            f"{len(brief.strip())} caractere(s) de descrição.",
            "Sem sujeito, lugar ou restrição, o sorteio não tem o que servir.",
            "Diga o que só este cliente tem: nome, endereço, material, número, rito.", "A direção vira decoração genérica.")
    elif any(word in low_brief for word in generic_words) and not re.search(r"\d", brief):
        add("should", "generic-brief", "Briefing de categoria", "briefing",
            "O texto usa adjetivos de categoria sem número, lugar ou material.",
            "O estudo mostra que as páginas fracas tinham uma ideia de categoria.",
            "Troque 'moderno e premium' pelo fato concreto que só este sujeito tem.", "A página poderia ser de qualquer concorrente.")

    if chosen is not None:
        missing_assets = chosen["needs"] - have_keys
        if missing_assets:
            add("should", "asset-gap", "A direção pede um ativo ausente", ", ".join(sorted(missing_assets)),
                "A ficha depende de ativos que você não declarou ter.",
                "Composição que precisa de foto honesta não se sustenta com desenho genérico.",
                "Declare o ativo, troque de direção ou aceite desenhar em código com honestidade.",
                "A seção fica vazia ou com placeholder.")
        for item in redraw_items:
            if item["slot"] == "direction":
                add("should", "direction-redraw", "Direção inteira redesenhada", "redraws",
                    "Você trocou a direção, não uma peça.",
                    "Trocar a direção inteira desfaz o estudo; é o caso mais caro.",
                    "Registre no relatório por que a ficha sorteada não servia.", "A escolha perde rastreabilidade.")

    sheet = _sheet(chosen, section_keys, keep_keys, seed_value) if chosen is not None else None
    questions = [
        "A ficha escolhida carrega um item do inventário deste cliente, e não uma ideia de categoria?",
        "Qual é a coisa viva da página: o que a pessoa faz ou o que muda a cada visita?",
        "Onde cada seção prova a sua afirmação, e não apenas ocupa espaço?",
    ]
    limitations = [
        "A biblioteca é própria e embutida: 12 direções em português, não as 20 do upstream.",
        "O sorteio é determinístico pela semente, mas não avalia o seu projeto real nem vê imagens.",
        "Nada é desenhado, compilado ou publicado: a ficha é um contrato para você executar.",
        "Nenhum script Node, navegador, plugin ou CLI do upstream é instalado.",
    ]
    summary = [
        f"**Semente:** `{seed_value}` · {len(options)} de {len(DIRECTIONS)} direções · setor `{sector_key or 'livre'}` · tom `{tone_key or 'livre'}`.",
        f"**Ativos declarados:** {', '.join(sorted(have_keys)) or 'nenhum'} · preservar: {', '.join(sorted(keep_keys)) or 'nada'}.",
    ]
    if sheet:
        summary.append(f"**Ficha:** {sheet['name']} com {len(sheet['sections'])} seção(ões) e {len(redraw_items)} redesenho(s) registrado(s).")
    findings, counts, verdict_text, questions = finalize(findings, mode, questions)
    rows = [
        {"id": option["id"], "name": option["name"], "thesis": option["thesis"], "needs": option["needs"]}
        for option in options
    ]
    extra: list[str] = ["", "## Direções sorteadas", "", "| Direção | Tese | Ativos |", "|---|---|---|"]
    extra += [f"| {row['name']} (`{row['id']}`) | {row['thesis'][:110]} | {', '.join(row['needs']) or '—'} |" for row in rows]
    if sheet:
        extra += [
            "", f"## Ficha · {sheet['name']}", "",
            f"**Ideia:** {sheet['idea']}", "",
            f"**Herói:** {sheet['hero']}", "",
            f"**Tipografia:** {sheet['type']}", "",
            f"**Paleta:** fundo {sheet['palette']['ground']} · tinta {sheet['palette']['ink']} · acento {sheet['palette']['accent']} · campo {sheet['palette']['field']}.", "",
            f"**Imagens:** {sheet['imagery']}", "",
            f"**Movimento:** {sheet['motion']}", "",
            "### Seções", "",
            "| Seção | Composição |", "|---|---|",
        ]
        extra += [f"| {item['label']} | {item['layout']} |" for item in sheet["sections"]]
        extra += ["", "### Armadilhas", ""]
        extra += [f"- {trap}" for trap in sheet["traps"]]
        if redraw_items:
            extra += ["", "### Redesenhos registrados", ""]
            extra += [f"- `{item['slot']}` — {item['reason']}" for item in redraw_items]
    return {
        **common(
            analysis="direction", mode=mode, title="Direção de arte", summary=summary,
            findings=findings, counts=counts, verdict=verdict_text, questions=questions, rows=rows,
            metrics={
                "directions": len(DIRECTIONS), "options": len(options), "sections": len(section_keys),
                "seed": seed_value, "assets": len(have_keys), "keep": len(keep_keys), "redraws": len(redraw_items),
            },
            limitations=limitations, extra_sections=extra,
        ),
        "seed": seed_value,
        "options": options,
        "sheet": sheet,
        "redraws": redraw_items,
    }


# ------------------------------------------------------------------- argumento

_ACTION_STOCK = (
    "saiba mais", "saber mais", "comece agora", "começar agora", "clique aqui", "leia mais",
    "descubra", "descubra mais", "explore", "explore agora", "get started", "learn more",
    "read more", "start now", "discover", "submit", "enviar",
)
_STOCK_PHRASES = (
    "desbloqueie", "eleve", "transforme", "revolucione", "potencialize", "superalimente",
    "sem esforço", "sem fricção", "à prova de futuro", "prova de futuro", "próximo nível",
    "solução completa", "tudo em um", "tudo-em-um", "líder de mercado", "corte de ponta",
    "estado da arte", "world-class", "cutting-edge", "all-in-one", "next-generation",
    "seamless", "effortless", "unlock", "supercharge", "elevate", "empower", "streamline",
    "revolutionize", "game-changer", "blazing fast", "reimagine", "leverage", "synergy",
)
_CORRECTION = re.compile(
    r"n[ãa]o\s+[ée]\s+(?:s[óo]|apenas|somente)\b[^.]{1,60}[,;—–-]\s*(?:[ée]|mas)\b"
    r"|more than just\b|n[ãa]o\s+[ée]\s+um\s+\w+[,;—–-]\s*[ée]\s+um",
    re.I,
)
_PROOF_NUMBER = re.compile(
    r"\b\d[\d.,]*\s*%(?=\s|$|[.,;:)])"
    r"|\b(?:\d+(?:[.,]\d+)?\s*(?:mil|milh[õo]es|k))\s+(?:clientes|usu[áa]rios|empresas|times|lojas|escolas)\b"
    r"|\b(?:5|cinco)\s*estrelas?\b|⭐"
    r"|\b(?:avalia[çc][õo]es|depoimentos|pr[êe]mios|logos?|cases?)\b",
    re.I,
)
_PROOF_SOURCE = re.compile(
    r"fonte|source|https?://|www\.|dados\s+de|pesquisa|segundo|relat[óo]rio|"
    r"\b(?:19|20)\d{2}\b|cliente\s+desde|case\s+real",
    re.I,
)


def audit_argument(
    *,
    brief: str,
    claims: str,
    headline: str = "",
    support: str = "",
    action: str = "",
    mode: str = "full",
) -> dict[str, Any]:
    _mode(mode)
    if not brief.strip():
        raise TasteError("Descreva o sujeito antes de montar o argumento.")
    if len(brief) > MAX_BRIEF_CHARS:
        raise TasteError(f"O briefing excede {MAX_BRIEF_CHARS:,} caracteres.".replace(",", "."))
    if len(claims) > MAX_CLAIMS_CHARS:
        raise TasteError(f"As afirmações excedem {MAX_CLAIMS_CHARS:,} caracteres.".replace(",", "."))
    rows = _rows(claims, 3, "afirmação")
    findings: list[dict[str, Any]] = []

    def add(*args: str) -> None:
        findings.append(finding(*args))

    sections: list[dict[str, Any]] = []
    seen_roles: set[str] = set()
    proofs = 0
    for number, cells in rows:
        raw_section, claim, proof = cells
        claim = " ".join(claim.split())
        proof = " ".join(proof.split())
        key = ROLE_ALIASES.get(_norm(raw_section))
        label = ROLES[key][0] if key else (raw_section or f"seção {number}")
        status = "ok"
        if not claim:
            status = "vazia"
            add("must", "empty-claim", f"Seção sem afirmação: {label}", f"linha {number}",
                "A linha declara a seção, mas não o que ela afirma.",
                "Seção sem afirmação é preenchimento: existe para ocupar espaço.",
                "Escreva a frase que a seção prova — ou apague a seção.",
                "A página vira a sequência padrão de hero, recursos e preço.")
        elif not proof:
            status = "sem prova"
            add("must", "claim-without-proof", f"Afirmação sem prova: {label}", f"linha {number}",
                f"Afirmação declarada: `{claim[:120]}`.",
                "Toda afirmação precisa de uma prova: a coisa, um número, um nome, uma demonstração.",
                "Diga o que mostra a afirmação: foto, preço, etapa, dado com fonte.",
                "A seção pede que o leitor acredite por educação.")
        else:
            proofs += 1
            if _PROOF_NUMBER.search(claim) and not _PROOF_SOURCE.search(f"{claim} {proof}"):
                status = "prova frágil"
                add("must", "invented-proof", f"Prova sem fonte: {label}", f"linha {number}",
                    f"Afirmação: `{claim[:100]}` · prova: `{proof[:100]}`.",
                    "Número, avaliação ou prêmio sem fonte é prova inventada — e um tell reconhecido.",
                    "Anexe a fonte, o ano e o recorte, ou troque por um fato que se prova por construção.",
                    "A peça vira alegação falsa e precisa ser retirada depois.")
        if key:
            if key in seen_roles:
                add("should", "duplicate-section", f"Seção repetida: {label}", f"linha {number}",
                    "O mesmo papel aparece mais de uma vez.",
                    "Repetir seção dilui o argumento e costuma repetir o layout.",
                    "Junte as duas ou dê papéis diferentes a elas.", "A página fica mais longa sem dizer mais.")
            seen_roles.add(key)
        sections.append({"line": number, "role": key or "", "label": label, "claim": claim, "proof": proof, "status": status})

    stock_sequence = ["recursos", "prova", "preco", "cta"]
    ordered = [item["role"] for item in sections if item["role"]]
    if len(ordered) >= 4:
        position = [stock_sequence.index(role) for role in ordered if role in stock_sequence]
        if position == sorted(position) and len(position) >= 3:
            add("should", "stock-order", "Ordem padrão de landing page", "afirmações",
                "A ordem é hero → recursos → prova → preço → ação.",
                "É a sequência que toda página gerada usa; ela não nasce da afirmação.",
                "Reordene pela força da prova: o que convence primeiro vem primeiro.",
                "A página parece um template, mesmo com bom conteúdo.")

    clean_headline = " ".join(headline.split())
    clean_support = " ".join(support.split())
    clean_action = " ".join(action.split())
    if not clean_headline:
        add("must", "missing-headline", "Sem título", "cabeçalho",
            "O argumento não declara o título da primeira tela.",
            "É o título que responde 'o que é isto' em cinco segundos.",
            "Escreva um título de até duas linhas, de quatro a seis palavras.", "A primeira tela vira decoração.")
    else:
        if len(clean_headline) > 42:
            add("must", "long-headline", "Título longo demais", f"{len(clean_headline)} caracteres",
                f"`{clean_headline[:90]}`.",
                "O orçamento que sobrevive a 390 px é de cerca de 32 caracteres; acima de 42 vira frase.",
                "Corte palavras até caber em duas linhas e leve o resto para a linha de apoio.",
                "No celular o título ocupa quatro linhas e perde a função.")
        elif len(clean_headline) > 32:
            add("should", "headline-tight", "Título no limite do orçamento", f"{len(clean_headline)} caracteres",
                f"`{clean_headline[:90]}`.",
                "Acima de 32 caracteres, o tamanho confortável no celular cai.",
                "Encurte para quatro a seis palavras ou aceite um corpo menor no celular.",
                "O título encolhe justamente onde precisa ser grande.")
        if len(clean_headline.split()) > 7:
            add("nice", "headline-words", "Muitas palavras no título", f"{len(clean_headline.split())} palavras",
                "A mediana dos heróis estudados é de cinco palavras.",
                "Título é olhado de relance; frase é lida.",
                "Deixe o título com quatro a seis palavras.", "O visitante lê o título como parágrafo.")
        if _CORRECTION.search(clean_headline):
            add("should", "correction-copy", "Título de correção", clean_headline[:80],
                "A fórmula 'não é X, é Y' é um dos títulos mais gerados.",
                "Ela explica por oposição em vez de dizer o que a coisa é.",
                "Troque pela afirmação direta.", "O título soa a anúncio de IA.")
        if clean_headline.count(":") == 1 and len(clean_headline.split(":")[0].split()) <= 2:
            add("nice", "colon-headline", "Título que depende dos dois-pontos", clean_headline[:80],
                "O nome antes dos dois-pontos já está na navegação.",
                "Título com dois-pontos costuma ser 'Marca: descrição'.",
                "Comece pela descrição.", "O título repete a marca sem dizer nada novo.")
        if clean_headline.rstrip().endswith("."):
            add("nice", "headline-period", "Ponto final no título", clean_headline[-30:],
                "O título termina em ponto final.",
                "A convenção é frase sem ponto, salvo quando a voz do projeto usa pontos em tudo.",
                "Remova o ponto ou assuma a pontuação em toda a página.", "O título parece legenda.")

    if not clean_support:
        add("must", "missing-support", "Sem linha de apoio", "cabeçalho",
            "Falta a frase que diz concretamente o que é a coisa e para quem.",
            "Quando o título é um nome ou uma figura de linguagem, é a linha de apoio que explica.",
            "Escreva uma frase de até 22 palavras logo abaixo do título.", "O visitante sabe o tom, não o produto.")
    else:
        if len(clean_support.split()) > 26:
            add("should", "long-support", "Linha de apoio longa", f"{len(clean_support.split())} palavras",
                "Acima de 22 palavras a linha de apoio vira parágrafo.",
                "O espaço dela é ao lado do título, não abaixo da dobra.",
                "Corte para uma frase.", "A linha some da primeira tela.")
        if clean_headline and set(_norm(clean_support).split()) & set(_norm(clean_headline).split()):
            overlap = set(_norm(clean_support).split()) & set(_norm(clean_headline).split())
            if len(overlap) >= max(3, len(set(_norm(clean_headline).split())) // 2):
                add("should", "support-repeats", "Linha de apoio repete o título", ", ".join(sorted(overlap))[:80],
                    "A linha de apoio repete palavras do título.",
                    "Ela existe para acrescentar o detalhe que o título cortou.",
                    "Diga o que é, para quem e o que custa, sem repetir o título.", "A primeira tela diz duas vezes a mesma coisa.")

    if not clean_action:
        add("must", "missing-action", "Sem ação principal", "cabeçalho",
            "Não há uma ação nomeada para a primeira tela.",
            "Página sem ação é leitura, não convite.",
            "Escolha uma ação e nomeie pelo que ela faz.", "O visitante não sabe o próximo passo.")
    elif _norm(clean_action) in {_norm(term) for term in _ACTION_STOCK}:
        add("should", "generic-action", "Ação genérica", clean_action[:60],
            f"`{clean_action}` não diz o que acontece ao clicar.",
            "Rótulo genérico é um dos tells de texto mais comuns.",
            "Nomeie a ação: 'Reservar mesa', 'Ver os planos', 'Baixar para Mac'.",
            "O botão some no meio de todos os outros botões.")
    elif len(clean_action.split()) > 4:
        add("nice", "action-long", "Ação longa", clean_action[:60],
            "A ação tem mais de quatro palavras.",
            "Botão é lido de relance e clicado no celular.",
            "Reduza a uma a três palavras.", "O botão quebra em duas linhas no celular.")

    combined = " ".join([clean_headline, clean_support, clean_action, *(item["claim"] for item in sections), *(item["proof"] for item in sections)])
    lowered = _norm(combined)
    stock_hits = [term for term in _STOCK_PHRASES if _norm(term) in lowered]
    if stock_hits:
        add("should", "stock-phrase", "Frase de prateleira", ", ".join(stock_hits[:5]),
            f"{len(stock_hits)} expressão(ões) de catálogo no texto.",
            "São as palavras que qualquer concorrente poderia imprimir sem mudar nada.",
            "Troque o adjetivo pelo fato: número, material, prazo, lugar.", "A página fala como um anúncio genérico.")
    if len(re.findall(r"—", combined)) > 3:
        add("should", "em-dash-budget", "Travessão em excesso", f"{len(re.findall('—', combined))} travessões",
            "O texto usa travessão como pontuação padrão.",
            "Um ou dois por página leem como escrita; dez leem como modelo.",
            "Troque por ponto final ou vírgula.", "O texto entrega que foi gerado.")
    if re.search(r"\b(?:bem-vindo|welcome)\b", lowered):
        add("should", "welcome-copy", "Boas-vindas genéricas", "texto",
            "O texto abre com boas-vindas.",
            "Ninguém procura boas-vindas; procura o que a página faz.",
            "Abra com a afirmação.", "A primeira linha desperdiça a atenção.")

    metrics = {
        "sections": len(sections), "proofs": proofs, "claims": sum(1 for item in sections if item["claim"]),
        "headlineChars": len(clean_headline), "headlineWords": len(clean_headline.split()),
        "supportWords": len(clean_support.split()), "stockPhrases": len(stock_hits),
        "actionWords": len(clean_action.split()),
    }
    questions = [
        "Qual afirmação desta página só este sujeito poderia fazer?",
        "Toda prova mostrada existe de verdade hoje, com fonte e data?",
        "Cada detalhe de amostra está listado para o cliente confirmar antes de publicar?",
    ]
    limitations = [
        "A skill valida o argumento declarado; não lê o HTML nem mede a linha de título no navegador.",
        "A detecção de prova inventada é lexical: número sem fonte vira candidato, com falso positivo possível.",
        "Detalhes de amostra não são separados automaticamente de prova; a lista para o cliente é manual.",
        "Nada é publicado e nenhum texto é enviado a um provedor externo.",
    ]
    summary = [
        f"**Seções:** {len(sections)} · {proofs} com prova · título {len(clean_headline)} caracteres · apoio {len(clean_support.split())} palavras.",
        f"**Ação:** `{clean_action or 'não declarada'}` · frases de prateleira: {len(stock_hits)}.",
    ]
    findings, counts, verdict_text, questions = finalize(findings, mode, questions)
    extra = ["", "## Seções e provas", "", "| Seção | Afirmação | Prova | Estado |", "|---|---|---|---|"]
    extra += [
        f"| {item['label']} | {item['claim'][:90] or '—'} | {item['proof'][:90] or '—'} | {item['status']} |"
        for item in sections
    ]
    return common(
        analysis="argument", mode=mode, title="Argumento antes do desenho", summary=summary,
        findings=findings, counts=counts, verdict=verdict_text, questions=questions, rows=sections,
        metrics=metrics, limitations=limitations, extra_sections=extra,
    )


# ------------------------------------------------------------------------ júri

JUDGE_DIMENSIONS: dict[str, tuple[str, int]] = {
    "design": ("Design", 40),
    "usabilidade": ("Usabilidade", 30),
    "criatividade": ("Criatividade", 20),
    "conteudo": ("Conteúdo", 10),
}
_DIM_ALIASES: dict[str, str] = {
    "design": "design", "visual": "design", "composicao": "design", "composição": "design",
    "usabilidade": "usabilidade", "usability": "usabilidade", "uso": "usabilidade", "funcao": "usabilidade",
    "criatividade": "criatividade", "creativity": "criatividade", "ideia": "criatividade", "inovacao": "criatividade",
    "conteudo": "conteudo", "conteúdo": "conteudo", "content": "conteudo", "copy": "conteudo", "texto": "conteudo",
}

JUDGE_BANDS: tuple[tuple[float, float, str, str], ...] = (
    (8.5, 10.0, "excepcional", "Referência: nada a corrigir antes de publicar."),
    (7.5, 8.4, "pronto", "Pode publicar; o que sobra é polimento."),
    (6.5, 7.4, "com ressalvas", "Publica, mas os tetos mostram o que ainda falta."),
    (6.0, 6.4, "abaixo", "Abaixo do padrão: corrija antes de liberar."),
    (0.0, 5.9, "não publicar", "Não publique: a peça ainda não sustenta a própria promessa."),
)

JUDGE_SIGNALS: dict[str, tuple[str, str, float, str]] = {
    "lint-fail": ("Falha no linter", "global", 6.0, "Uma regra obrigatória reprovou no linter."),
    "manchete-longa": ("Manchete em três linhas", "global", 6.5, "O título não cabe em duas linhas."),
    "manchete-problema": ("Problema na manchete", "global", 6.0, "O título é longo, de correção ou de molde."),
    "eyebrow": ("Sobrancelha", "global", 6.5, "A etiqueta acima do título é fantasia editorial."),
    "mono": ("Mono decorativa", "global", 6.5, "Mono aparece fora de código."),
    "numeracao": ("Numeração 01/02/03", "global", 6.5, "A seção usa número decorativo."),
    "gradiente": ("Gradiente", "global", 6.5, "Há gradiente decorativo na página."),
    "sombra": ("Sombra em repouso", "global", 6.5, "Cartões têm sombra sem elevação."),
    "fio": ("Fio de 1 px", "global", 6.5, "Blocos são separados por fios."),
    "margens-desiguais": ("Margens desiguais", "global", 6.5, "A moldura não fecha nas laterais."),
    "faixa-em-branco": ("Faixa em branco", "global", 5.0, "Uma seção inteira está vazia."),
    "sem-titulo": ("Sem título claro", "global", 6.0, "A primeira tela não tem título legível."),
    "serviria-a-qualquer-um": ("Serviria a qualquer um", "criatividade", 6.0, "A ideia não pertence a este sujeito."),
    "menos-de-4-fotos": ("Menos de quatro fotos", "design", 6.5, "O piso de imagens reais não foi cumprido."),
    "sem-coisa-viva": ("Sem coisa viva", "criatividade", 7.5, "Nada na página muda, responde ou respira."),
    "sem-botao-real": ("Sem botão real", "usabilidade", 7.0, "Não há uma ação que funcione de verdade."),
}
_SIGNAL_ALIASES: dict[str, str] = {
    "falha no linter": "lint-fail", "lint": "lint-fail", "fail": "lint-fail",
    "manchete longa": "manchete-longa", "manchete-longa": "manchete-longa", "titulo longo": "manchete-longa",
    "manchete": "manchete-problema", "problema na manchete": "manchete-problema",
    "sobrancelha": "eyebrow", "kicker": "eyebrow",
    "mono": "mono", "mono decorativa": "mono",
    "numeracao": "numeracao", "numeração": "numeracao", "numeros": "numeracao",
    "gradiente": "gradiente", "gradient": "gradiente",
    "sombra": "sombra", "shadow": "sombra",
    "fio": "fio", "hairline": "fio", "borda": "fio",
    "margens desiguais": "margens-desiguais", "margem": "margens-desiguais",
    "faixa em branco": "faixa-em-branco", "vazio": "faixa-em-branco",
    "sem titulo": "sem-titulo", "sem título": "sem-titulo",
    "serviria a qualquer um": "serviria-a-qualquer-um", "generico": "serviria-a-qualquer-um",
    "menos de 4 fotos": "menos-de-4-fotos", "poucas fotos": "menos-de-4-fotos", "fotos": "menos-de-4-fotos",
    "sem coisa viva": "sem-coisa-viva", "coisa viva": "sem-coisa-viva", "viva": "sem-coisa-viva",
    "sem botao real": "sem-botao-real", "sem botão real": "sem-botao-real", "botao": "sem-botao-real",
}
for _key in JUDGE_SIGNALS:
    _SIGNAL_ALIASES.setdefault(_key, _key)
_STATE_ON = {"sim", "s", "yes", "y", "true", "1", "verdadeiro", "presente", "tem"}
_STATE_OFF = {"não", "nao", "n", "no", "false", "0", "falso", "ausente", "na", "n/a", "—", "-"}

JUDGE_ORDER: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Ideia", "A frase que só este sujeito poderia dizer, antes de qualquer pixel.", ("criatividade",)),
    ("Hierarquia", "O primeiro olhar precisa cair no título e na ação.", ("design", "usabilidade")),
    ("Composição", "Margens iguais, seções com o mesmo respiro, nada flutuando.", ("design",)),
    ("Tipografia", "Até dois registros; display, corpo e pequeno sem buraco na escala.", ("design",)),
    ("Imagens", "Quatro imagens reais no mínimo, uma delas em movimento.", ("design",)),
    ("Cor", "Chão de 70 a 90%, acento abaixo de 5%, contraste medido.", ("design",)),
    ("Detalhe", "Aspas, números tabulares, foco visível, estado de erro.", ("design", "usabilidade")),
    ("Movimento", "Assinatura própria, entrada curta e alternativa reduzida.", ("usabilidade",)),
)


def _score(value: str, label: str) -> float:
    try:
        number = float(value.replace(",", "."))
    except ValueError as exc:
        raise TasteError(f"{label}: `{value}` não é uma nota numérica.") from exc
    if not 0 <= number <= 10:
        raise TasteError(f"{label}: a nota deve ficar entre 0 e 10.")
    return number


def _state(value: str) -> bool | None:
    key = _norm(value)
    if key in _STATE_ON:
        return True
    if key in _STATE_OFF:
        return False
    raise TasteError(f"Estado desconhecido: `{value}`. Use sim ou não.")


def _band(note: float) -> tuple[str, str]:
    for low, high, label, meaning in JUDGE_BANDS:
        if low <= note <= high:
            return label, meaning
    return JUDGE_BANDS[-1][2], JUDGE_BANDS[-1][3]


def judge_page(*, scores: str, signals: str = "", mode: str = "full") -> dict[str, Any]:
    """Nota ponderada de júri com tetos declarados, no formato de 14 passes."""
    _mode(mode)
    rows = _rows(scores, 3, "dimensão avaliada")
    findings: list[dict[str, Any]] = []

    def add(*args: str) -> None:
        findings.append(finding(*args))

    declared: dict[str, dict[str, Any]] = {}
    dimensions_rows: list[dict[str, Any]] = []
    for number, cells in rows:
        raw, score_text, evidence = cells
        key = _DIM_ALIASES.get(_norm(raw))
        label = JUDGE_DIMENSIONS[key][0] if key else (raw or f"dimensão {number}")
        if key is None:
            add("must", "unknown-dimension", "Dimensão desconhecida", f"linha {number}",
                f"`{raw}` não é uma das quatro dimensões do júri.",
                "Sem dimensão, a nota não entra na média ponderada.",
                "Use design, usabilidade, criatividade ou conteudo.", "A nota é ignorada.")
            continue
        if key in declared:
            add("should", "duplicate-dimension", "Dimensão repetida", label,
                "A mesma dimensão foi avaliada duas vezes.",
                "Duas notas para a mesma dimensão escondem qual delas vale.",
                "Deixe uma linha por dimensão.", "A média fica imprevisível.")
            continue
        if not evidence.strip():
            add("must", "missing-evidence", "Nota sem evidência", label,
                "A dimensão foi pontuada sem evidência.",
                "Nota sem referência é opinião, não crítica.",
                "Cite classe, seletor, arquivo, linha, página ou medida.", "A nota não pode ser conferida.")
            continue
        if len(evidence.strip()) < 12:
            add("should", "short-evidence", "Evidência curta demais", label,
                f"{len(evidence.strip())} caractere(s): `{evidence.strip()}`.",
                "Uma evidência precisa apontar o que existe e onde.",
                "Acrescente o seletor, a medida ou a página.", "A nota vira adjetivo.")
        note = _score(score_text, label)
        declared[key] = {"score": note, "evidence": evidence.strip(), "line": number}

    missing = [key for key in JUDGE_DIMENSIONS if key not in declared]
    for key in missing:
        add("must", "missing-dimension", f"Falta a dimensão {JUDGE_DIMENSIONS[key][0]}", "júri",
            "A revisão não cobre as quatro dimensões ponderadas.",
            "Sem as quatro notas, a média ponderada não existe.",
            "Avalie design, usabilidade, criatividade e conteúdo, cada uma com evidência.",
            "A nota final não é calculada.")

    active: list[dict[str, Any]] = []
    parsed_signals: dict[str, bool] = {}
    if signals.strip():
        try:
            for number, cells in _rows(signals, 2, "sinal"):
                raw, state_text = cells
                key = _SIGNAL_ALIASES.get(_norm(raw))
                if key is None:
                    add("must", "unknown-signal", "Sinal desconhecido", f"linha {number}",
                        f"`{raw}` não está na lista de sinais que aplicam teto.",
                        "Um sinal inventado não muda a nota e esconde o problema.",
                        "Use um dos sinais do quadro de tetos.", "O teto não é aplicado.")
                    continue
                if key in parsed_signals:
                    continue
                parsed_signals[key] = bool(_state(state_text))
        except TasteError as exc:
            add("must", "signals-invalid", "Sinais inválidos", "sinais",
                f"{exc} O formato é `sinal | sim` ou `sinal | não`.",
                "Sem estado legível, nenhum teto pode ser aplicado.",
                "Uma linha por sinal.", "A nota sai sem tetos.")

    for key, present in parsed_signals.items():
        if not present:
            continue
        label, target, cap, why = JUDGE_SIGNALS[key]
        active.append({"signal": key, "label": label, "target": target, "cap": cap, "why": why})

    weighted: float | None = None
    dim_notes: dict[str, float] = {}
    if not missing:
        dim_notes = {key: value["score"] for key, value in declared.items()}
        for item in active:
            if item["target"] != "global" and item["target"] in dim_notes:
                dim_notes[item["target"]] = min(dim_notes[item["target"]], item["cap"])
        raw_weighted = round(sum(declared[key]["score"] * JUDGE_DIMENSIONS[key][1] / 100 for key in JUDGE_DIMENSIONS), 2)
        weighted = round(sum(dim_notes[key] * JUDGE_DIMENSIONS[key][1] / 100 for key in JUDGE_DIMENSIONS), 2)
        global_caps = [item["cap"] for item in active if item["target"] == "global"]
        final = round(min([weighted, *global_caps]), 2) if global_caps else weighted
        weakest = min(JUDGE_DIMENSIONS, key=lambda key: (dim_notes[key], -JUDGE_DIMENSIONS[key][1]))
        band_label, band_meaning = _band(final)
        band_row = next(item for item in JUDGE_BANDS if item[0] <= final <= item[1])
        caps = ", ".join(f"{item['label']} ({_num(item['cap'])})" for item in active) or "nenhum"
        verdict_text = (
            f"Nota final **{_num(final)}/10** · {band_label}. {band_meaning} "
            f"Média ponderada {_num(weighted)}; tetos aplicados: {caps}."
        )
        metrics = {
            "weighted": weighted, "rawWeighted": raw_weighted, "final": final, "capLoss": round(raw_weighted - final, 2),
            "caps": len(active), "signals": len(parsed_signals), "band": band_label,
            "weakest": weakest, "dimensions": len(declared), "globalCaps": sum(1 for item in active if item["target"] == "global"),
        }
        for item in active:
            add("should", "cap-applied", f"Teto aplicado: {item['label']}", _num(item["cap"]),
                f"{item['why']} O teto de {item['cap']:.1f} vale para {('a nota final' if item['target'] == 'global' else 'a dimensão ' + JUDGE_DIMENSIONS[item['target']][0].lower())}.",
                "Um teto existe porque o defeito contamina a impressão inteira.",
                "Corrija o sinal antes de discutir a nota.",
                "A peça pode ser publicada parecendo melhor do que é.")
        order_rows = []
        for index, (step, action, keys) in enumerate(JUDGE_ORDER, start=1):
            triggered = any(dim_notes[key] < (7.5 if index <= 2 else 7.0) for key in keys)
            if index == 8 and "sem-coisa-viva" in parsed_signals and parsed_signals["sem-coisa-viva"]:
                triggered = True
            order_rows.append({"step": index, "label": step, "action": action, "active": False, "triggered": triggered})
        active_rows = [row for row in order_rows if row["triggered"]][:3]
        for row in active_rows:
            row["active"] = True
        top = [
            {"dimension": JUDGE_DIMENSIONS[key][0], "score": dim_notes[key], "evidence": declared[key]["evidence"]}
            for key in sorted(JUDGE_DIMENSIONS, key=lambda key: dim_notes[key])[:3]
        ]
    else:
        final = None
        weighted = None
        weakest = ""
        band_row = (0.0, 10.0, "incompleta", "A revisão não cobre as quatro dimensões, então não há nota.")
        band_label = "incompleta"
        band_meaning = "A revisão não cobre as quatro dimensões, então não há nota."
        verdict_text = f"Revisão incompleta: faltam {len(missing)} dimensão(ões). Não existe nota parcial."
        metrics = {
            "weighted": None, "final": None, "capLoss": None, "caps": len(active),
            "signals": len(parsed_signals), "band": band_label, "weakest": "",
            "dimensions": len(declared), "globalCaps": sum(1 for item in active if item["target"] == "global"),
        }
        order_rows = []
        top = []

    for key, value in declared.items():
        dimensions_rows.append({
            "key": key, "label": JUDGE_DIMENSIONS[key][0], "weight": JUDGE_DIMENSIONS[key][1],
            "score": value["score"], "evidence": value["evidence"], "line": value["line"],
            "capped": dim_notes.get(key, value["score"]) if not missing else value["score"],
        })

    questions = [
        "A nota de design sobreviveria se a página fosse impressa em preto e branco?",
        "Algum teto foi aplicado sem que o defeito existisse de verdade?",
        "O problema número um é de ideia, de hierarquia ou de detalhe — e nessa ordem?",
    ]
    limitations = [
        "As notas são declaradas por quem revisa; a skill pondera, aplica tetos e confere evidência, não vê a página.",
        "Sinais de teto são afirmações do júri: marcar `sim` sem evidência produz uma nota baixa que não se sustenta.",
        "A calibração 7,5–8,0 vem do upstream; a nota é comparável dentro deste projeto, não entre projetos.",
        "Nada é renderizado, medido no navegador ou publicado.",
    ]
    summary = [
        f"**Dimensões:** {len(declared)}/4 · tetos ativos: {len(active)} · banda: {band_label}.",
        f"**Ponderação:** design 40 · usabilidade 30 · criatividade 20 · conteúdo 10.",
    ]
    findings, counts, _auto_verdict, questions = finalize(findings, mode, questions)
    extra = ["", "## Quadro de notas", "", "| Dimensão | Peso | Nota | Com teto | Evidência |", "|---|---|---|---|---|"]
    extra += [
        f"| {row['label']} | {row['weight']}% | {_num(row['score'])} | {_num(row['capped'])} | {row['evidence'][:100]} |"
        for row in dimensions_rows
    ]
    if active:
        extra += ["", "## Tetos aplicados", "", "| Sinal | Alvo | Teto | Motivo |", "|---|---|---|---|"]
        extra += [
            f"| {item['label']} | {('final' if item['target'] == 'global' else JUDGE_DIMENSIONS[item['target']][0])} | {_num(item['cap'])} | {item['why']} |"
            for item in active
        ]
    if order_rows:
        extra += ["", "## Ordem de correção", ""]
        extra += [f"{row['step']}. **{row['label']}**{' ← comece aqui' if row in active_rows else ''} — {row['action']}" for row in order_rows]
    if top:
        extra += ["", "## Três problemas", ""]
        extra += [f"- **{item['dimension']} ({_num(item['score'])}):** {item['evidence']}" for item in top]
    extra += ["", "## Bandas", "", "| Faixa | Banda | Leitura |", "|---|---|---|"]
    extra += [f"| {_num(low)}–{_num(high)} | {label} | {meaning} |" for low, high, label, meaning in JUDGE_BANDS]
    return {
        **common(
            analysis="judge", mode=mode, title="Júri ponderado", summary=summary,
            findings=findings, counts=counts, verdict=verdict_text, questions=questions, rows=dimensions_rows,
            metrics=metrics, limitations=limitations, extra_sections=extra,
        ),
        "dimensions": dimensions_rows,
        "caps": active,
        "order": order_rows,
        "top": top,
        "band": {"label": band_label, "meaning": band_meaning, "low": band_row[0], "high": band_row[1]},
    }


# ------------------------------------------------------------------- biblioteca


def direction_reference() -> dict[str, Any]:
    """Vocabulário e limites usados pelas skills de direção de arte."""
    rows = [
        {"id": item["id"], "name": item["name"], "thesis": item["thesis"], "needs": sorted(item["needs"]),
         "sectors": [SECTORS[key][0] for key in item["sectors"]]}
        for item in DIRECTIONS
    ]
    waves = [
        {"wave": 1, "label": "Onda 1 · 2023", "hint": "vidro, gradiente roxo e ícone genérico"},
        {"wave": 2, "label": "Onda 2 · 2024–2025", "hint": "micro-rótulo, numeração, fio de 1 px e mobília editorial"},
        {"wave": 3, "label": "Onda 3 · 2026", "hint": "creme e terracota, serifa apertada e manchete-parágrafo"},
    ]
    metrics = {
        "directions": len(DIRECTIONS), "sectors": len(SECTORS), "tones": len(TONES),
        "roles": len(ROLES), "assets": len(ASSETS), "dimensions": len(JUDGE_DIMENSIONS),
        "signals": len(JUDGE_SIGNALS), "waves": len(waves),
    }
    summary = [
        f"**Direções:** {len(DIRECTIONS)} · setores: {len(SECTORS)} · tons: {len(TONES)} · papéis de seção: {len(ROLES)}.",
        f"**Júri:** {len(JUDGE_DIMENSIONS)} dimensões ponderadas · {len(JUDGE_SIGNALS)} sinais de teto.",
    ]
    findings: list[dict[str, Any]] = []
    _, counts, _auto_verdict, _ = finalize(findings, "full", [])
    verdict_text = (
        f"Referência completa: {len(DIRECTIONS)} direções, {len(ROLES)} papéis de seção, "
        f"{len(JUDGE_SIGNALS)} tetos e {len(waves)} ondas de tells."
    )
    extra = ["", "## Direções", "", "| Direção | Tese | Setores | Ativos |", "|---|---|---|---|"]
    extra += [
        f"| {item['name']} (`{item['id']}`) | {item['thesis'][:100]} | {', '.join(item['sectors'][:3])} | {', '.join(item['needs'])} |"
        for item in rows
    ]
    extra += ["", "## Setores", "", ", ".join(f"`{key}`" for key in SECTORS)]
    extra += ["", "## Tons", "", ", ".join(f"`{key}`" for key in TONES)]
    extra += ["", "## Papéis de seção", "", ", ".join(f"`{key}`" for key in ROLES)]
    extra += ["", "## Dimensões do júri", "", "| Dimensão | Peso |", "|---|---|"]
    extra += [f"| {label} | {weight}% |" for label, weight in JUDGE_DIMENSIONS.values()]
    extra += ["", "## Tetos", "", "| Sinal | Alvo | Teto |", "|---|---|---|"]
    extra += [
        f"| {label} | {('final' if target == 'global' else JUDGE_DIMENSIONS[target][0])} | {_num(cap)} |"
        for label, target, cap, _why in JUDGE_SIGNALS.values()
    ]
    extra += ["", "## Ondas de tells", ""]
    extra += [f"- **{wave['label']}** — {wave['hint']}." for wave in waves]
    return {
        **common(
            analysis="reference", mode="full", title="Biblioteca de direção", summary=summary,
            findings=[], counts=counts, verdict=verdict_text, questions=[], rows=rows,
            metrics=metrics, limitations=[
                "A biblioteca é própria e embutida; não é a do upstream e não desenha nada.",
                "Contagens e bandas valem para este projeto.",
                "Nenhum script Node, navegador ou plugin é executado.",
            ], extra_sections=extra,
        ),
        "directions": rows,
        "sectors": [{"id": key, "label": label, "aliases": list(aliases)} for key, (label, aliases) in SECTORS.items()],
        "tones": [{"id": key, "label": label, "aliases": list(aliases)} for key, (label, aliases) in TONES.items()],
        "roles": [{"id": key, "label": label, "aliases": list(aliases)} for key, (label, aliases) in ROLES.items()],
        "dimensions": [{"id": key, "label": label, "weight": weight} for key, (label, weight) in JUDGE_DIMENSIONS.items()],
        "caps": [{"id": key, "label": label, "target": target, "cap": cap, "why": why} for key, (label, target, cap, why) in JUDGE_SIGNALS.items()],
        "waves": waves,
    }
