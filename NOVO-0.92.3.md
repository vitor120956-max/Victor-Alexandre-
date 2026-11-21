# 0.92.3 — o scanner do celular

> vou testar com o meu cll quero ver se considgo melhorar e otimizar e ver uns
> problemas q ele ta apresentando talvez passsando um escaner nele talvez
> consegimos resolver

## O que eu fiz

Transformei a leitura da 0.92.2 em **diagnóstico**. Agora o JARVIS não só diz o
que o aparelho é — ele diz **o que está errado, por que, e o que fazer**.

Duas portas, mesmo motor:

- **`escanear-celular.bat`** — duplo clique. Lê, imprime e salva o relatório em
  `storage/diagnosticos/`.
- **Aba Anatomia** → cartão do Android → **“Passar o scanner”**.
- No chat: “passa um scanner no meu celular”.

## Antes de rodar (no celular)

1. **Ajustes → Opções do desenvolvedor → Depuração USB: ligada.**
   (Se não existir: **Ajustes → Sobre o telefone → Número da versão**, 7 toques.)
2. Conecte o cabo — **de dados**, não só de carga.
3. Toque em **“Permitir”** no aviso que aparece na tela do celular.

Se o `adb` não estiver instalado, a mensagem manda para **Máquina → Preparar
celular** (baixa do site oficial do Google e confere o hash).

## O que ele mede

Armazenamento, memória livre, os apps que mais ocupam RAM, bateria (capacidade
real comparada com a de fábrica), temperatura, patch de segurança, tempo ligado,
apps que travaram e ajustes de animação.

**Cada achado vem com quatro coisas:**

| campo | o que é |
|---|---|
| **medido** | o número, com a origem — “93% de /data usado; restam 8,1 GB” |
| **causa** | por que aquilo deixa o aparelho ruim |
| **o que fazer** | o passo a passo, na tela do celular |
| **limite** | o que aquilo **não** resolve |

## A parte que importa: o ganho é medido?

Cada sugestão de melhoria diz se o ganho foi **medido** ou é **sensação**:

- “Fechar o Instagram quando não usa” → **medido**: libera 928 MB da RAM medida.
- “Reiniciar o aparelho” → **medido**.
- “Diminuir a animação para 0,5x” → **sensação, não número medido** — a tela
  marca isso na cara.

É a diferença entre o que funciona e a conversa de “limpador de RAM”.

## O que ele NÃO faz

Não desinstala, não limpa cache, não muda ajuste, não reinicia e não apaga nada.
Quem mexe no aparelho é você, na tela dele. O JARVIS mede e explica — e quando o
problema é hardware (bateria inflada, conector, tela), ele diz que é assistência.

## Medido

- **pytest 4 199** (0 falhas, 7 pulados) — **30 casos novos** no scanner.
- Todo comando da lista é de leitura — há teste que varre a lista procurando
  `install`, `push`, `rm`, `settings put`, `reboot` e `su`.
- API real na 8012, com um `adb` de teste servindo um SM-A346B: `/api/anatomia/android/scan`
  → **200**, 7 achados na ordem certa (armazenamento cheio → aquecendo → memória
  baixa → bateria gasta → bateria quente → patch antigo → app travando).
- `vitest` 243, `tsc` limpo, manifesto 661 arquivos em 0.92.3.

## Defeitos achados na primeira leitura de verdade

1. Vírgula sobrando: “42,8 °C carregando,”.
2. O texto mandava ver “a lista abaixo” quando a lista estava **acima**.
3. 11,8% de RAM aparecia como “12%” — parecia contradizer o próprio limiar.
4. `**negrito**` de markdown vazando no console do Windows.

## Como testar

1. `atualizar.bat` → `iniciar-jarvis.bat`.
2. No celular: Depuração USB, cabo de dados, “Permitir”.
3. **`escanear-celular.bat`** (duplo clique), ou Anatomia → “Passar o scanner”.
4. **Copie a tela e me mande.** Com o texto real do seu aparelho eu ajusto os
   limiares e o que cada achado recomenda — é a única parte que eu não consigo
   medir sem o seu celular na mão.
