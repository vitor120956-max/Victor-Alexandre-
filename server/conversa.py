"""Conversa, filosofia e psicologia — conselho honesto, sem truque (0.92.0).

O pedido (19/11):

    adicione filosofia, psicologo, psicologia, como responder uma mulher por
    msg/presencialmente, como se comportar, dicas e ideias, como começar uma
    conversa, como ir levando a garota para que ela queira ou dê vontade de
    sair comigo ou que se apaixone por quem eu sou

Isso pede uma linha clara, e ela é esta: **este módulo ensina a conversar
melhor e a ser mais interessante de perto — não a fabricar sentimento.** Ninguém
faz outra pessoa se apaixonar; o que existe é aproximação honesta, curiosidade
real, respeito ao “não” e tempo. Técnica usada para **produzir** atração sem
consentimento não é charme: é manipulação, e o JARVIS não escreve isso.

O que ele faz:

- `abrir` — como começar, por contexto (app, festa, academia, trabalho, curso);
- `manter` — como a conversa não morrer: pergunta aberta, troca, ritmo, sair
  de cena na hora certa;
- `convidar` — como chamar para sair com convite concreto, leve e com saída
  fácil; o que fazer com um “não”;
- `ler` — sinais de interesse **e** de desconforto, com o aviso de que sinal é
  ambíguo e que consentimento é palavra, não dedução;
- `revisar` — a mensagem que você ia mandar, com o que ela tem de pressão,
  tamanho, excesso de pergunta ou falta de assunto;
- `filosofia` — oito perspectivas para pensar a própria vida (e o medo de
  chegar), cada uma com uma prática concreta;
- `psicologia` — conceitos com base (escuta ativa, comunicação não violenta,
  apego, rejeição, ansiedade social), com o que a pesquisa sustenta e o que não.

O que ele **recusa**, de propósito, e diz por quê: neg, insistência depois do
não, chantagem emocional, personagem falso, “técnicas” de sedução que dependem
de confundir a outra pessoa, e qualquer coisa que envolva vigiar, chantagear ou
expor alguém.

Isto não é terapia. Quando o texto traz sofrimento sério, o módulo **para** e
aponta ajuda de verdade (no Brasil: CVV 188, gratuito, 24 h).
"""
from __future__ import annotations

import re
from typing import Any

MAX_TEXTO = 4_000

AVISO = (
    "Isto é conversa e educação, não terapia nem diagnóstico. Ninguém aqui pode "
    "saber o que a outra pessoa sente — sinal se lê com cautela e se confirma com palavra."
)

CRISE = (
    "Se você está pensando em se machucar, isso é maior do que uma dica de conversa. "
    "Ligue para o CVV — 188, gratuito, 24 horas, sigiloso — ou procure o CAPS/UBS mais perto. "
    "Se houver risco imediato, 190. Falar com alguém agora importa mais do que qualquer texto meu."
)

SINAIS_DE_CRISE = re.compile(
    r"\b(me matar|suic[ií]dio|suicida|n[aã]o quero mais viver|acabar com tudo|"
    r"me cortar|automutila|n[aã]o vejo sa[ií]da)\b",
    re.IGNORECASE,
)
SINAIS_DE_VIOLENCIA = re.compile(
    r"\b(me bater|me agrediu|me amea[cç]ou|viol[eê]ncia dom[eé]stica|me persegue|stalker|"
    r"n[aã]o sai de perto|tem medo dele|tem medo dela)\b",
    re.IGNORECASE,
)


class ConversaError(ValueError):
    """Pedido fora do que este módulo faz — com a frase do porquê."""


# ---------------------------------------------------------------------------
# Os limites, escritos para aparecerem no resultado (não só no código)
# ---------------------------------------------------------------------------

RECUSADOS = [
    ("negar/“negging”", "diminuir a autoestima dela para ela buscar sua aprovação. Isso é abuso emocional, não sedução."),
    ("insistir depois do não", "“ela disse não mas quis dizer sim” é o roteiro mais comum de assédio. Não é."),
    ("chantagem emocional", "“se você gostasse de mim, você faria…” troca afeto por dívida."),
    ("personagem falso", "inventar gostos, renda, rotina ou sentimentos. A mentira tem prazo e a conta chega."),
    ("técnicas de confundir", "frieza calculada, ciúme provocado, sumiço programado. Isso produz ansiedade, não vínculo."),
    ("vigiar ou invadir", "ler conversa, rastrear localização, criar perfil falso. É crime ou beira."),
]


def _limite(texto: str | None, campo: str = "texto") -> str:
    limpo = (texto or "").strip()
    if len(limpo) > MAX_TEXTO:
        raise ConversaError(f"O {campo} passa de {MAX_TEXTO:,} caracteres.")
    return limpo


def _com_aviso(resultado: dict[str, Any], texto: str, campo: str = "texto") -> dict[str, Any]:
    """Toda resposta passa por aqui: crise primeiro, aviso sempre."""
    if SINAIS_DE_CRISE.search(texto or ""):
        return {
            "parou": True,
            "motivo": "sofrimento sério",
            "texto": CRISE,
            "o_que_fazer": "Falar com uma pessoa agora (CVV 188). Depois, se quiser, a gente volta à conversa.",
        }
    if SINAIS_DE_VIOLENCIA.search(texto or ""):
        return {
            "parou": True,
            "motivo": "risco ou violência",
            "texto": (
                "O que você descreveu é segurança, não paquera. No Brasil: 180 (Central de Atendimento "
                "à Mulher), 190 (emergência). Se for você que está sendo ameaçado, 190; se for alguém "
                "que você conhece, ofereça o 180 e não confronte a pessoa sozinho."
            ),
            "o_que_fazer": "Procurar ajuda agora. Nenhuma dica de conversa se aplica a um contexto de risco.",
        }
    resultado.setdefault("aviso", AVISO)
    return resultado


# ---------------------------------------------------------------------------
# Como começar
# ---------------------------------------------------------------------------

CONTEXTOS: dict[str, dict[str, Any]] = {
    "app": {
        "nome": "aplicativo de relacionamento",
        "aberturas": [
            "Comente **uma coisa específica** do perfil dela e faça uma pergunta que só ela poderia responder. "
            "Ex.: “Você foi no show do Criolo? Fiquei na dúvida entre ir e ficar em casa — valeu a pena?”",
            "Prefira uma pergunta que abre história a uma que fecha em sim/não. “Qual foi o último lugar que te "
            "surpreendeu?” rende mais que “você gosta de viajar?”.",
            "Se o perfil tem uma foto com algo incomum (um livro, um instrumento, um lugar), comece por ali: é o "
            "assunto que ela escolheu mostrar.",
        ],
        "evite": [
            "“oi”, “tudo bem?” sozinho — não dá o que responder.",
            "elogio ao corpo antes de qualquer conversa: sinaliza o que você está olhando.",
            "texto gigante na primeira mensagem: parece formulário.",
        ],
    },
    "festa": {
        "nome": "festa, bar ou rolê",
        "aberturas": [
            "Comente o ambiente, não a pessoa: “esse lugar é sempre assim ou hoje tá fora do normal?” — é leve e "
            "dá margem para ela responder ou só sorrir e virar.",
            "Se estão na mesma roda, entre pela conversa que já existe: escute 30 segundos e faça uma pergunta "
            "sobre o que foi dito. Isso é o oposto de chegar falando de si.",
            "Se ela está claramente ocupada (no celular, conversando sério, de saída), não é o momento. Voltar "
            "depois é permitido; insistir não.",
        ],
        "evite": [
            "chegar por trás ou encostar para chamar atenção.",
            "“posso te pagar uma bebida?” como abertura — troca a conversa por dívida.",
            "ficar parado olhando de longe: aproximação com frase é melhor que encarada.",
        ],
    },
    "academia": {
        "nome": "academia, parque, aula",
        "aberturas": [
            "Contexto compartilhado é o melhor assunto: horário, aula, equipamento, professor. “Você faz essa aula "
            "sempre? Tô na segunda e ainda não decorei nada.”",
            "Fale no intervalo, não no meio da série: ninguém conversa ofegante.",
            "Se ela está de fone, espere o momento em que ele sai. Fone é “não estou disponível” na prática.",
        ],
        "evite": [
            "comentar o corpo dela. Ali, mais que em qualquer lugar.",
            "seguir de aparelho em aparelho para “dar match” de horário.",
        ],
    },
    "trabalho": {
        "nome": "trabalho ou estudo",
        "aberturas": [
            "Comece pelo que é de todo mundo: um projeto, um professor, um café ruim, uma reunião longa.",
            "Converse em espaço comum (copa, corredor, intervalo), não na mesa dela com gente em volta.",
            "Convide para algo de grupo primeiro (almoço, café com o time). Isso dá contexto e saída para os dois.",
        ],
        "evite": [
            "constranger quem não pode sair da situação (é chefe, é orientadora, é cliente).",
            "usar o chat da empresa para paquera — fica registrado e expõe a pessoa.",
        ],
    },
    "rua": {
        "nome": "fila, loja, rua",
        "aberturas": [
            "Só quando há contexto real e tempo para uma resposta (fila parada, espera longa). “Você sabe se essa "
            "fila anda? Tô aqui há vinte minutos e já fiz amizade com o extintor.”",
            "Se ela responde curto e volta ao celular, acabou. Não tem segunda tentativa na mesma esquina.",
            "Abordagem na rua é o contexto em que a pessoa tem menos controle — seja breve e aceite o não sem "
            "negociar.",
        ],
        "evite": [
            "acompanhar andando ao lado.",
            "bloquear caminho ou ficar entre ela e a saída.",
        ],
    },
    "curso": {
        "nome": "curso, igreja, grupo, voluntariado",
        "aberturas": [
            "Vocês já têm um interesse em comum — use isso. “Você já tinha feito esse curso antes? A parte de "
            "hoje me pegou.”",
            "Ofereça algo pequeno e útil: anotação, resumo, carona até o ponto (se for natural).",
            "Grupo é melhor que individual no começo: conversa sem plateia e sem pressão.",
        ],
        "evite": [
            "transformar o grupo em busca individual e ignorar as outras pessoas.",
            "usar informação do grupo (lista de telefone) sem ela ter dado o número para você.",
        ],
    },
}


def abrir(*, contexto: str = "app", interesse: str = "") -> dict[str, Any]:
    """Como começar a conversa no contexto pedido — com o que não fazer."""
    chave = (contexto or "app").strip().lower()
    if chave not in CONTEXTOS:
        opcoes = ", ".join(sorted(CONTEXTOS))
        raise ConversaError(f"Contexto “{contexto}” não está na lista: {opcoes}.")
    dados = CONTEXTOS[chave]
    assunto = _limite(interesse, "interesse")
    resultado = {
        "contexto": dados["nome"],
        "aberturas": list(dados["aberturas"]),
        "evite": list(dados["evite"]),
        "principio": (
            "A melhor abertura é sobre o mundo, não sobre ela nem sobre você. Ela dá uma porta; "
            "a conversa é que decide se alguém entra."
        ),
    }
    if assunto:
        resultado["com_o_seu_assunto"] = (
            f"Você disse que o interesse é “{assunto}”. Comece por uma pergunta que só quem vive isso responde: "
            "“como você começou com isso?” rende mais que “você gosta de X?”. Depois conte **uma** coisa sua — "
            "troca, não entrevista."
        )
    return _com_aviso(resultado, assunto)


# ---------------------------------------------------------------------------
# Como manter
# ---------------------------------------------------------------------------

def manter(*, mensagem: str = "", objetivo: str = "conhecer") -> dict[str, Any]:
    """O que fazer para a conversa não morrer — e quando encerrar bem."""
    texto = _limite(mensagem, "mensagem")
    principios = [
        ("Pergunta aberta + sua parte", "Pergunte e **responda também**. Sequência de perguntas sem nada seu vira entrevista."),
        ("Escuta ativa", "Repita com suas palavras o que ela disse antes de acrescentar: “então você saiu do curso porque…”. "
                         "Isso mostra que você ouviu, não que estava esperando a vez."),
        ("Ritmo", "Mensagem longa pede mensagem longa; resposta curta pede resposta curta. Espelhar o tamanho é o "
                  "jeito mais simples de não parecer afobado."),
        ("Assunto que rende", "Prefira o que tem história (uma escolha, uma viagem, um medo bobo) ao que tem catálogo "
                              "(série, comida, time)."),
        ("Encerrar no alto", "Saia da conversa num momento bom, com uma frase que deixa assunto para amanhã. Conversa "
                             "que só acaba quando não tem mais nada é conversa que não recomeça."),
        ("Próximo passo", "Se a conversa está boa há um tempo, proponha algo concreto. Conversa que nunca vira encontro "
                          "vira hábito."),
    ]
    exemplo = (
        "Ela: “tô cansada, foi semana difícil no trabalho”.\n"
        "Ruim: “nossa, que pena” (fecha).\n"
        "Ruim também: “eu também, a minha foi pior porque…” (rouba o assunto).\n"
        "Bom: “foi difícil como? foi volume ou foi gente?” — e, depois que ela contar, uma frase sua do mesmo tamanho."
    )
    resultado = {
        "principios": [{"titulo": titulo, "como": como} for titulo, como in principios],
        "exemplo": exemplo,
        "regra_de_ouro": "Conversa boa é troca: ela fala, você fala, ninguém está se apresentando para uma banca.",
    }
    if texto:
        achados = _analisar_mensagem(texto)
        resultado["sua_mensagem"] = achados
    return _com_aviso(resultado, texto)


# ---------------------------------------------------------------------------
# Como convidar
# ---------------------------------------------------------------------------

def convidar(*, plano: str = "", tempo_conhecendo: str = "") -> dict[str, Any]:
    """Convite concreto, leve e com saída fácil — e o que fazer com o não."""
    ideia = _limite(plano, "plano")
    resultado = {
        "estrutura": [
            "1. Diga o que é (lugar e atividade específicos). “Tem uma feira de vinil no sábado na Praça…”",
            "2. Diga quando (dia e hora). “Sábado às 15h.” — convite sem hora é convite que não acontece.",
            "3. Diga por que com ela. “Lembrei de você quando vi o disco do Cartola.”",
            "4. Dê a saída fácil. “Se não der, sem problema — a gente se fala.”",
        ],
        "exemplos": [
            "“Sábado tem feira de vinil na Praça XV, 15h. Lembrei de você quando vi o disco do Cartola. "
            "Topa? Se não der, tranquilo.”",
            "“Quinta eu vou naquele café novo da Osmar Cunha depois do trabalho, umas 18h30. Quer ir junto?”",
            "“Vou no cinema domingo à tarde ver o novo do Kleber Mendonça. Se você gostar do tipo, bora — "
            "se não, eu conto depois se presta.”",
        ],
        "o_que_nao_fazer": [
            "“a gente devia sair qualquer dia” — sem data, não é convite, é desejo.",
            "convite em cima de insistência: se ela já disse não uma vez, não reformule três vezes.",
            "convite com cobrança embutida (“eu pago”, “só uma hora”, “você me deve essa”).",
            "convite por áudio de cinco minutos ou por textão: aumenta o peso de dizer não.",
        ],
        "com_o_nao": (
            "“Sem problema, obrigado por falar.” E siga. Não pergunte por quê, não peça outra chance na hora, "
            "não desapareça como castigo. Um não é uma resposta completa — e quem recebe bem um não é lembrado "
            "como alguém seguro."
        ),
        "com_o_sim": (
            "Confirme um dia antes, chegue no horário, tenha um plano B se chover. O encontro é para os dois "
            "conversarem, não para você executar um roteiro."
        ),
    }
    if ideia:
        resultado["seu_plano"] = (
            f"Você pensou em “{ideia}”. Deixe assim no convite: o que é, quando, por que com ela, e a saída. "
            "Se for caro ou longe, simplifique — encontro caro cria pressão nos dois."
        )
    if (tempo_conhecendo or "").strip():
        resultado["tempo"] = (
            "Tempo de conversa não é regra, é termômetro: se vocês já falam há dias com boa troca, convidar cedo "
            "é natural; se a conversa ainda é de “oi, tudo bem”, o convite chega antes de haver assunto."
        )
    return _com_aviso(resultado, ideia)


# ---------------------------------------------------------------------------
# Como ler sinais (e quando parar)
# ---------------------------------------------------------------------------

def ler() -> dict[str, Any]:
    """Sinais de interesse, sinais de desconforto e a regra que vale mais que todos."""
    return {
        "interesse": [
            "Ela puxa assunto de volta, ou começa conversa sem você pedir.",
            "Pergunta sobre você e lembra do que você contou.",
            "Responde com frases, não com monossílabos, e mantém o ritmo.",
            "Aceita um convite concreto ou propõe outro horário quando o seu não dá.",
            "Procura contato depois (mensagem, story, “cheguei bem”).",
        ],
        "desconforto": [
            "Respostas curtas e cada vez mais espaçadas, sem assunto novo.",
            "Ela não pergunta nada de volta.",
            "Muda de assunto quando o papo fica pessoal.",
            "Corpo virado para o lado, passos para trás, olhar para a saída.",
            "Diz “não”, “agora não”, “tô meio sem tempo” — e não oferece alternativa.",
        ],
        "regra": (
            "Sinal é ambíguo; palavra não é. Interesse se confirma perguntando, não deduzindo. "
            "E “não”, “agora não” e “deixa” são respostas completas: pare, agradeça e siga."
        ),
        "consentimento": (
            "Consentimento é entusiástico, específico e pode ser retirado a qualquer momento — inclusive no meio. "
            "Silêncio não é sim; estar ali não é sim; ter beijado antes não é sim para o resto."
        ),
        "se_ela_sumir": (
            "Se ela parou de responder, o próximo passo é **nenhum**. Uma mensagem leve depois de dias é aceitável "
            "se havia conversa; três é perseguição. Ocupar-se é melhor que reaquecer por insistência."
        ),
    }


# ---------------------------------------------------------------------------
# Revisar a mensagem (o que dá para dizer sem saber o que ela pensa)
# ---------------------------------------------------------------------------

_PESO = {
    "pressao": re.compile(r"\b(me responde|por que n[aã]o respondeu|t[aá] me ignorando|responde logo|"
                          r"eu mere[cç]o uma chance|depois de tudo que eu fiz)\b", re.IGNORECASE),
    "cobran[cç]a": re.compile(r"\b(voc[eê] me deve|eu paguei|eu fiz tudo|se voc[eê] gostasse)\b", re.IGNORECASE),
    "elogio_ao_corpo": re.compile(r"\b(seu corpo|seus peitos|sua bunda|gostosa|del[ií]cia de corpo)\b", re.IGNORECASE),
    "apelido_forcado": re.compile(r"\b(linda|gatinha|princesa|amor|meu bem)\b", re.IGNORECASE),
}


def _analisar_mensagem(texto: str) -> dict[str, Any]:
    problemas: list[str] = []
    sugestoes: list[str] = []

    if len(texto) > 600:
        problemas.append("A mensagem é longa demais para uma conversa em andamento: parece um comunicado.")
        sugestoes.append("Corte para 2 ou 3 frases e deixe o resto para a resposta dela.")

    perguntas = len(re.findall(r"\?+", texto))  # “??” é uma pergunta com ênfase, não duas
    if perguntas >= 3:
        problemas.append(f"São {perguntas} perguntas numa mensagem só — vira entrevista e cansa.")
        sugestoes.append("Escolha a melhor pergunta e responda você também.")

    if not perguntas and len(texto) < 200:
        sugestoes.append("Falta uma pergunta ou um gancho: sem isso, a conversa morre no “haha”.")

    for nome, padrao in _PESO.items():
        if padrao.search(texto):
            problemas.append(f"Tem cara de {nome.replace('[cç]', 'ç')}: isso cria dívida em vez de vontade.")
    if _PESO["pressao"].search(texto):
        sugestoes.append(
            "Se ela não respondeu, a mensagem certa é nenhuma por um tempo. Cobrança transforma interesse em obrigação."
        )

    caixa_alta = sum(1 for letra in texto if letra.isupper()) / max(1, sum(1 for letra in texto if letra.isalpha()))
    if caixa_alta > 0.6 and len(texto) > 12:
        problemas.append("Quase tudo em maiúscula lê como grito.")

    if re.search(r"[\U0001F600-\U0001FAFF]{3,}", texto):
        sugestoes.append("Muitos emojis seguidos tiram o peso do que você escreveu. Um ou dois bastam.")

    if not problemas:
        problemas = []  # lista vazia é resposta: nada de inventar defeito
    return {
        "caracteres": len(texto),
        "perguntas": perguntas,
        "problemas": problemas,
        "sugestoes": sugestoes[:5] or ["Está bom: curto, claro e sem cobrança. Mande."],
        "lembrete": "Eu não sei o que ela vai responder. Isto é sobre a sua mensagem, não sobre a cabeça dela.",
    }


def revisar(*, mensagem: str) -> dict[str, Any]:
    """Analisa a mensagem que você ia mandar — sem adivinhar a reação dela."""
    texto = _limite(mensagem, "mensagem")
    if not texto:
        raise ConversaError("Cole a mensagem que você ia mandar.")
    resultado = _analisar_mensagem(texto)
    # O texto **da mensagem** vai para o detector: até a 0.92.0 ele ia vazio e,
    # com isso, violência no rascunho passava sem aviso (achado pelo teste).
    return _com_aviso(resultado, texto)


# ---------------------------------------------------------------------------
# Filosofia
# ---------------------------------------------------------------------------

FILOSOFIAS: dict[str, dict[str, str]] = {
    "estoicismo": {
        "ideia": "Só o que depende de você é seu: o que você tenta, como trata as pessoas, o que faz com o que sente. "
                 "O resto — resposta do outro, resultado, opinião alheia — não está sob seu controle.",
        "pergunta": "O que aqui depende de mim, e o que eu estou tentando controlar sem poder?",
        "pratica": "Antes de mandar a mensagem ou de chegar na pessoa, separe numa frase: “eu faço X; o que ela "
                   "responder não é meu”. Isso não tira o nervosismo — tira o peso de ter que dar certo.",
        "limite": "Não é engolir sentimento nem fingir que nada dói: é não entregar a decisão da sua vida a quem não "
                  "foi consultado.",
    },
    "existencialismo": {
        "ideia": "Você não tem uma essência pronta para descobrir; você se faz nas escolhas. Angústia é o preço da "
                 "liberdade, não um defeito.",
        "pergunta": "Que pessoa eu estou me tornando com o que faço hoje — inclusive com o que evito?",
        "pratica": "Troque “eu sou tímido” por “eu tenho evitado conversar”. A segunda frase tem porta; a primeira, não.",
        "limite": "Liberdade não é fazer o que quer com os outros: o outro também é sujeito, não cenário.",
    },
    "virtude": {
        "ideia": "Aristóteles: a boa vida é a vida em que você exercita bem o que é seu — coragem, temperança, justiça, "
                 "amizade —, no meio entre o excesso e a falta.",
        "pergunta": "Qual é o meio-termo aqui entre não tentar nada e atropelar a pessoa?",
        "pratica": "Coragem não é não sentir medo; é agir bem **com** medo. Aproximar-se com uma frase honesta é coragem; "
                   "insistir é o excesso; não falar nunca é a falta.",
        "limite": "Virtude não é regra de etiqueta: é hábito construído por repetição, e se erra.",
    },
    "pragmatismo": {
        "ideia": "O valor de uma ideia está no que ela muda na prática. “Ela pode gostar de mim” não muda nada; "
                 "“vou mandar uma pergunta sobre o que ela postou” muda.",
        "pergunta": "O que eu faço amanhã por causa disso?",
        "pratica": "Uma ação pequena e verificável por dia: uma mensagem, um convite, uma caminhada. Sem ação, a "
                   "reflexão vira fuga bem escrita.",
        "limite": "Nem tudo é medido por resultado: conversa que não virou nada ainda pode ter sido boa.",
    },
    "fenomenologia": {
        "ideia": "Experiência vem antes da teoria. Em vez de julgar a situação pela expectativa, olhe o que está "
                 "de fato acontecendo: o que ela disse, como respondeu, o que você sentiu no corpo.",
        "pergunta": "O que aconteceu de verdade, sem a história que eu já contei sobre isso?",
        "pratica": "Depois de um encontro, escreva três fatos e três interpretações. “Ela olhou o celular” é fato; "
                   "“ela me achou chato” é interpretação.",
        "limite": "Olhar para a experiência não substitui perguntar: você vê de um lugar só.",
    },
    "camus": {
        "ideia": "O absurdo é a distância entre a nossa sede de sentido e o silêncio do mundo. A resposta de Camus não é "
                 "desistir: é viver com intensidade e revolta lúcida.",
        "pergunta": "Se nada garante que vai dar certo, o que ainda vale a pena tentar?",
        "pratica": "Trate o encontro como o encontro em si — não como investimento com retorno garantido. "
                   "Ir porque a conversa vale é diferente de ir para provar algo.",
        "limite": "Absurdo não é niilismo: não dá licença para desrespeitar ninguém.",
    },
    "taoismo": {
        "ideia": "Agir sem forçar (wu wei): a água não briga com a pedra, ela contorna. Há um tempo das coisas que não "
                 "obedece à pressa.",
        "pergunta": "Onde eu estou empurrando uma porta que abre para o outro lado?",
        "pratica": "Se a conversa esfriou, não aqueça por insistência. Deixe espaço e volte quando houver assunto novo.",
        "limite": "Não é passividade: contornar pedra é movimento, não ficar parado.",
    },
    "etica_do_cuidado": {
        "ideia": "A pergunta moral não é só “o que é justo?”, é “quem aqui é vulnerável e o que a minha ação faz com "
                 "essa pessoa?”. Cuidado é atenção ao outro concreto.",
        "pergunta": "Como esta situação está sendo para ela, não só para mim?",
        "pratica": "Antes de qualquer aproximação, pergunte-se o que ela ganha com isso se não quiser nada com você. "
                   "Se a resposta for “nada, só desconforto”, não é o momento.",
        "limite": "Cuidar não é decidir por ela nem transformar gentileza em crédito.",
    },
}


def filosofia(*, pergunta: str = "", escola: str = "") -> dict[str, Any]:
    """Uma escola por vez — ou a pergunta passada por várias, para comparar."""
    texto = _limite(pergunta, "pergunta")
    pedida = (escola or "").strip().lower()
    if pedida and pedida not in FILOSOFIAS:
        raise ConversaError(f"Escola “{escola}” não está na lista: {', '.join(sorted(FILOSOFIAS))}.")
    if pedida:
        dados = dict(FILOSOFIAS[pedida])
        dados.pop("idea_key", None)
        if texto:
            dados["aplicado"] = (
                f"Sua pergunta: “{texto}”. Por esta escola: {dados['pergunta']} "
                f"Prática: {dados['pratica']}"
            )
        return _com_aviso({"escola": pedida, **dados}, texto)

    itens = []
    for nome, dados in FILOSOFIAS.items():
        item = dict(dados)
        item.pop("idea_key", None)
        itens.append({"escola": nome, **item})
    return _com_aviso(
        {
            "pergunta": texto or "nenhuma — só o panorama",
            "escolas": itens,
            "como_usar": "Escolha a que faz a pergunta mais incômoda, não a que dá a resposta mais confortável.",
        },
        texto,
    )


# ---------------------------------------------------------------------------
# Psicologia
# ---------------------------------------------------------------------------

CONCEITOS: dict[str, dict[str, Any]] = {
    "escuta_ativa": {
        "o_que_e": "Ouvir para entender, não para responder: parafrasear, perguntar o detalhe, não completar a frase "
                   "do outro com a sua história.",
        "base": "É técnica central de entrevista motivacional e de terapia centrada na pessoa (Rogers). Em conversa "
                "comum, o efeito medido é de maior sensação de vínculo e menos mal-entendido.",
        "pratica": "Uma vez por conversa: “deixa eu ver se entendi — você quis dizer que…?”.",
        "cuidado": "Não é repetir como papagaio nem virar terapeuta de quem não pediu.",
    },
    "comunicacao_nao_violenta": {
        "o_que_e": "Quatro passos (Rosenberg): observação sem julgamento, sentimento, necessidade, pedido concreto.",
        "base": "Muito usada em mediação de conflito. A evidência é boa para reduzir escalada em conflito; para "
                "conquista amorosa, não é método de sedução — é forma de não ferir.",
        "pratica": "“Quando você não respondeu (observação), eu fiquei inseguro (sentimento); eu preciso de clareza "
                   "(necessidade). Você pode me dizer se prefere que eu pare de puxar assunto? (pedido)”",
        "cuidado": "Pedido não é ordem disfarçada: ela pode dizer não.",
    },
    "apego": {
        "o_que_e": "Modelos de vínculo (seguro, ansioso, evitativo) descrevem tendências em relações próximas — não "
                   "rótulos de personalidade.",
        "base": "A teoria do apego adulto tem apoio em pesquisa, mas estilo não é destino nem diagnóstico, e "
                "questionário de revista não mede isso.",
        "pratica": "Se você tende a ansiedade, note a vontade de mandar a terceira mensagem seguida e espere. Se tende "
                   "a evitar, note a vontade de sumir quando a conversa fica próxima.",
        "cuidado": "Não use “ela é evitativa” para explicar um não. O não é sobre o que ela quer, não sobre o seu rótulo.",
    },
    "rejeicao": {
        "o_que_e": "Dor de rejeição social ativa áreas ligadas à dor física; por isso dói de verdade e dá vontade de "
                  "insistir ou de sumir.",
        "base": "Estudos de neuroimagem (Eisenberger e outros) mostram sobreposição com circuitos de dor; a leitura "
                "popular costuma exagerar o tamanho do efeito.",
        "pratica": "Depois de um não: nomeie (“doeu”), não decida nada nas primeiras 24 h, e faça uma coisa que não "
                   "dependa dela.",
        "cuidado": "Dor não transforma o não em injustiça. Sentir muito não cria direito sobre ninguém.",
    },
    "ansiedade_social": {
        "o_que_e": "Medo intenso de julgamento em situações sociais, com evitação e sintomas físicos.",
        "base": "É condição tratável (TCC tem boa evidência). Não se diagnostica por texto nem por um dia ruim.",
        "pratica": "Exposição gradual: uma conversa curta por dia, com objetivo de fazer, não de agradar.",
        "cuidado": "Se atrapalha trabalho, estudo ou sono por semanas, procure profissional — isto aqui não substitui.",
    },
    "reciprocidade": {
        "o_que_e": "Gostar de quem demonstra gostar da gente, e revelar um pouco de si para o outro revelar também.",
        "base": "Efeito de reciprocidade é bem documentado em psicologia social; auto-revelação gradual aumenta "
                "proximidade em estudos com desconhecidos (Aron).",
        "pratica": "Troca: cada coisa sua vem depois de uma dela, no mesmo tamanho.",
        "cuidado": "Reciprocidade não é contabilidade: se está pesando quem falou mais, a conversa já não está boa.",
    },
    "atracao": {
        "o_que_e": "Atração tem componentes de proximidade, familiaridade, semelhança percebida e reciprocidade — "
                   "e uma parte grande que ninguém controla.",
        "base": "Proximidade e familiaridade têm efeito medido; “técnicas” de sedução têm efeito pequeno, de curto "
                "prazo e às vezes negativo.",
        "pratica": "O que está ao seu alcance: estar presente, ser interessante de conversar, cuidar de si e ser claro "
                   "sobre o que quer.",
        "cuidado": "Não existe método que faça alguém se apaixonar por você. Quem promete isso está vendendo outra coisa.",
    },
}


def psicologia(*, conceito: str = "") -> dict[str, Any]:
    """Conceitos com o que a pesquisa sustenta — e com o que ela não sustenta."""
    pedido = (conceito or "").strip().lower()
    if pedido and pedido not in CONCEITOS:
        raise ConversaError(f"Conceito “{conceito}” não está na lista: {', '.join(sorted(CONCEITOS))}.")
    if pedido:
        return _com_aviso({"conceito": pedido, **CONCEITOS[pedido]}, "")
    return _com_aviso(
        {
            "conceitos": [{"conceito": nome, **dados} for nome, dados in CONCEITOS.items()],
            "como_usar": "Comece pelos que doem: rejeição, ansiedade social ou apego.",
        },
        "",
    )


# ---------------------------------------------------------------------------
# O que este módulo não faz
# ---------------------------------------------------------------------------

def catalogo() -> dict[str, Any]:
    """Tudo o que a aba precisa saber sem perguntar nada: contextos, escolas,
    conceitos e a lista de recusas. Uma chamada, sem conteúdo de conversa."""
    return {
        "contextos": [
            {"id": nome, "nome": dados.get("nome", nome), "aberturas": list(dados.get("aberturas", []))}
            for nome, dados in CONTEXTOS.items()
        ],
        "escolas": [
            {"id": nome, "ideia": dados.get("ideia", ""), "pergunta": dados.get("pergunta", "")}
            for nome, dados in FILOSOFIAS.items()
        ],
        "conceitos": [
            {"id": nome, "o_que_e": dados.get("o_que_e", "")} for nome, dados in CONCEITOS.items()
        ],
        "recusados": [tecnica for tecnica, _motivo in RECUSADOS],
        "no_lugar": limites()["no_lugar"],
        "nao_e_terapia": AVISO,
        "ajuda": "CVV 188 (24 h, gratuito) · Centro de Valorização da Vida: cvv.org.br",
    }


def limites() -> dict[str, Any]:
    """A lista do que o JARVIS não escreve — com o motivo de cada um."""
    return {
        "recusados": [{"tecnica": tecnica, "porque": motivo} for tecnica, motivo in RECUSADOS],
        "porque": (
            "Atração construída com informação falsa ou pressão não é vínculo: é alguém sendo convencido. "
            "Além de ser errado, costuma terminar mal — e a pessoa machucada é ela."
        ),
        "no_lugar": (
            "O que funciona é mais chato e mais durável: estar presente, escutar, ser claro sobre o que quer, "
            "aceitar o não e continuar sendo você."
        ),
        "nao_e_terapia": AVISO,
        "ajuda": "CVV 188 (24 h, gratuito) · Centro de Valorização da Vida: cvv.org.br",
    }
