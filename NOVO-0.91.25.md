# JARVIS 0.91.25 — o Chrome não estava publicando a página

O `diagnostico-chave.bat` respondeu. E a resposta não era nenhuma das que eu
vinha tentando:

    auto        :   3 elementos — painel: não
    uia         :   3 elementos — painel: não
    uia_raw     :   3 elementos — painel: não
    uia_content :   3 elementos — painel: não
    msaa        :   2 elementos — painel: não

Com o painel **aberto na sua tela**. Não era a janela atrás. Não era a vista
errada. Era o **Chrome com a acessibilidade desligada** — não publicando a
página para ninguém, em nenhuma das cinco leituras.

## Por que o Chrome faz isso

O Chrome não publica a página para qualquer programa. Ele publica quando o
Windows diz que existe um **leitor de tela** na máquina. É uma configuração do
Windows (`SPI_SETSCREENREADER`) — a mesma que o NVDA liga quando abre. Sem esse
sinal, a janela responde só com a moldura: “Chrome Legacy Window”, o título da
aba, “Notifications”.

Na 0.91.17 ele leu 43 elementos porque, naquela sessão, alguma coisa tinha dado
esse sinal. Quando o Chrome desliga a acessibilidade de novo, tudo volta a ser
3 elementos.

## O que mudou

**1. O JARVIS dá o sinal.** Quando a leitura vem pobre, ele liga o modo leitor
de tela, pede a árvore de novo (`WM_GETOBJECT` na janela e nas filhas) e relê.

**2. E devolve como estava.** No fim do programa, a configuração volta ao que
era. É emprestado, não tomado.

**3. O diagnóstico mostra isso.** `diagnostico-chave.bat` agora imprime:

    Modo leitor de tela do Windows: desligado
       O Chrome só publica a página para quem parece um leitor de tela.
    Janelas filhas do Chrome: 1
       Chrome_RenderWidgetHostHWND  (handle 5150) — msaa=3, uia_raw=31

    ANTES de mexer em qualquer coisa:
      uia_raw     :    3 elementos — diálogo: não — nenhum campo do painel

    DEPOIS de ligar o modo leitor de tela:
      uia_raw     :   31 elementos — diálogo: SIM — campos: nome, expiração, limite, criar

Isso responde de uma vez se o sinal resolve — e, se não resolver, mostra se a
página está numa janela filha que eu não estava lendo.

**4. Um último recurso: `chrome-acessibilidade.bat`.** Se mesmo com o sinal o
Chrome continuar em 3 elementos, esse atalho fecha o Chrome e abre de novo com
`--force-renderer-accessibility`, que faz o Chrome publicar a árvore sempre.
**Ele fecha o Chrome** — as abas voltam, mas salve o que estiver escrevendo.

## O que fazer agora

1. Atualize para a 0.91.25.
2. Rode o `pegar-chave.bat` normalmente. Se der certo, acabou.
3. Se ainda falhar, rode o `diagnostico-chave.bat` **com o painel aberto** e me
   mande o `chave-leitura.txt`. Agora ele diz se o sinal foi dado, o que cada
   leitura viu antes e depois, e o que há em cada janela filha do Chrome.

## O que continua igual

- nada é criado sem `--autorizar`;
- **No expiration**, **No limit**, nome `jarvis-AAAA-MM-DD`;
- botão apagado não é clicado;
- cursor volta para o dono;
- sem chave, o `.env` não é tocado;
- o diagnóstico não cria chave e não clica em nada.

Suíte inteira: **3.785 testes passando** (7 pulados: dependem do Windows real).
