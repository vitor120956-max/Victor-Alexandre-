# JARVIS 0.62.7 — a USB acabou. O cartão continua funcionando.

O teste de pressão respondeu:

```
Em 60 segundos de pressao e inclinacao, NADA apareceu.
```

Com cabos que passam dados em outro aparelho. Isso **fecha a rota USB**: não é
driver (não há o que instalar), não é solda fria (não apareceu em ângulo
nenhum), é o caminho de dados do conector — ou o controlador USB na placa.

E aqui o limite honesto, sem enfeite: **sem dados na USB não existe `scrcpy`,
não existe `adb`, não existe MTP — e não existe driver que conserte pino.** O
`teclado-pelo-pc.bat` fica guardado para quando o conector voltar, mas hoje ele
não tem por onde falar com o aparelho.

## O que ainda funciona: o cartão

O microSD sai do celular e **não passa pelo conector**. E o leitor de cartão já
está ligado no seu PC — a própria sonda viu um Alcor (`058F`).

```
resgatar-cartao.bat
```

O que ele faz:

1. acha os discos removíveis (e os leitores que se disfarçam de disco local);
2. **mostra o plano antes de copiar** — pasta por pasta, quantidade e tamanho;
3. espera `Enter` para começar (ou você fecha no X);
4. confere espaço livre **antes** — falhar no meio de 8 GB é pior que falhar agora;
5. copia com progresso: `1234/5678  1.2 GB  3.4 MB/s  faltam ~2min`;
6. no fim: copiados, já existentes, erros, tempo e o caminho.

**O cartão é tratado como somente leitura.** Nada é apagado, movido ou renomeado
nele — o script nem tem `Remove-Item`/`Move-Item` (e há teste garantindo isso).

Rodar de novo **não duplica**: arquivo com mesmo nome e mesmo tamanho é pulado.

## O que vem e o que não vem

| vem do cartão | não vem |
| --- | --- |
| `DCIM`, `Pictures`, `Download`, `Movies`, `Music`, `Documents` | o que estava na **memória interna** |
| `WhatsApp` e `Android\media\com.whatsapp` (mídia) | o banco de mensagens do WhatsApp |
| `Samsung`, `Viber`, `Telegram`, `Instagram`, `Snapchat` | apps e configurações |

Se a câmera gravava no cartão, **as fotos estão lá**. Se gravava na memória
interna, elas continuam presas — e essa parte só sai com o conector funcionando,
ou por um backup em nuvem que já tenha acontecido.

## Duas verificações grátis, antes de qualquer conserto

1. **`photos.google.com`** — se o Google Fotos estava com backup ligado nesse
   aparelho, as fotos já estão na nuvem, sem cartão e sem conserto. Vale 2
   minutos.
2. **`findmymobile.samsung.com`** — se existe conta Samsung no aparelho, o
   "Desbloquear" remoto pode destravar a tela. Não liga a Depuração USB (não há
   entrada para navegar), mas destravar deixa o aparelho terminar backups
   pendentes.

## Sobre o conserto

No **Galaxy J7 Prime (SM-G610)**, a porta micro-USB é **peça de solda** — os
anúncios do próprio modelo dizem *"Charging Port Only ... (Soldering Required)"*.
Não é trocar um flex de encaixe: é solda em bancada (ou troca da sub-placa, se o
técnico preferir). A peça em si é barata; o serviço é o custo.

Depois do conserto, tudo que construímos volta a funcionar na ordem:

```
sonda-otg.bat      -> confere o driver
teclado-pelo-pc.bat-> PC vira teclado/mouse (destrava + liga Depuração USB)
celular.espelhar   -> a tela do celular vira janela do PC
celular.puxar      -> fotos e documentos pela USB
```

## Testes

- `pytest server/tests` → **2.861 passed** (`test_resgatar_cartao.py`: 15,
  `test_celular.py`: 169).
- Novos: o `.ps1` não contém `Remove-Item`/`Move-Item`/`Format-Volume`, confere
  espaço antes de copiar, mostra o plano e espera confirmação, progresso com
  contagem/velocidade/tempo restante, pula o que já existe, pega a mídia do
  WhatsApp em `Android\media`, ignora lixo de sistema do cartão, acha leitor que
  se disfarça de disco local, e diz que foto da memória interna precisa do
  conector.
- Skill nova `celular.cartao` (291 → **292 skills**).
- `vitest` → 124, `tsc -b` limpo, build embutido ok.

Achado de manutenção: o `read_text()` do Python traduz CRLF para LF, então todo
script de bump que passa por ele destruía o CRLF dos `.bat`/`.ps1`. O teste de
CRLF do repositório pegou os sete arquivos; agora a conversão é feita em bytes.
