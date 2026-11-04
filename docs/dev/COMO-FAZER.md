# Como fazer (receitas)

Pré-requisitos: Python 3.12+, `pip install pillow numpy py65`, `gh` (só para releases).
Todos os comandos rodam na raiz do repositório.

## Build e testes (sempre)
```bash
python tools/install_banner_theme.py   # aplica tudo em EDFC/OS.BIN (idempotente)
python tools/test_theme_safety.py      # deve terminar em PASSED
python tools/test_game_art.py          # deve terminar em PASSED
```
Rodar o install duas vezes não muda nada; se `git diff EDFC/OS.BIN` mostrar diferença sem você ter
mudado código, algo está errado.

## Mudar um banner ou criar um tema
1. `tools/banner_art.py`: `THEMES` (id, nome, texto do banner, `pal0 = (bd, txt, hl, sh)` em cores NES)
   e `DECOS` (função de decoração por tema, desenha com as cores 0–3). A fonte 5×7 (`FONT5x7`) só tem
   os caracteres usados — acrescente os que faltarem.
2. `python tools/banner_art.py` mostra quantos tiles cada banner usa e grava prévias em
   `docs/themes/banners/`. Limite: `MAX_TILES = 39` por banner (slots livres da fonte).
3. Tema novo (10º): ajuste também `NUM_THEMES` em `tools/theme_runtime.py`. Confira o espaço: o
   `assert` "Theme data exceeds Bank 0x0B space" dispara se os pacotes passarem de `$7A40`.
4. Install + testes + `python tools/capture_theme_screenshots.py`.

## Adicionar uma opção ao menu do jogo
Estado atual (ver ARQUITETURA §5): tabela de itens na imagem DATA em `$FA9D` (3 ponteiros de 2 bytes,
banco 15 criptografado), quantidade em `$D579` (hoje 2), despacho em `$D556`:
`resultado 0` → carregar; `CMP` em `$D5B9/$D5BA` → caminho do antigo "Apenas Selec." (`$D5BD`,
seleciona a ROM sem iniciar); qualquer outro → Info da ROM (`$D5E1`).
Para uma 3ª opção:
1. String: reaproveite o espaço da string antiga (`"Apenas Selec."` em `$F679`, 13 chars + NUL) ou
   use bytes livres da região do banco 15. Strings do banco 15 são criptografadas — gere o keystream
   (ARQUITETURA §1) e acrescente em `theme_runtime.KEYSTREAM`.
2. Ponteiro: 3º slot da tabela (`$FAA1–$FAA2`, também criptografado) e quantidade `$D579 = 3`.
3. Despacho: ajuste o `CMP` de `$D5BA` para o índice da nova opção e aponte o desvio para o código
   novo (no banco 15 se couber, ou no banco `$0B` via stub como as capas).
4. Registre tudo em `os_patches()` (nunca edite `EDFC/OS.BIN` à mão) e acrescente um teste em
   `tools/test_game_art.py` que abre o menu e escolhe a opção.
Atenção: a capa fica visível enquanto o menu (`$CA0D`) roda e é escondida quando ele retorna.

## Capas
- **Formato e chave**: `tools/nes_art.py` (2 KB, CRC-32 dos bytes 512–2559 da ROM).
- **Pacote completo** (13.422 capas do libretro, ~4 min com paralelismo, cache em `.artcache/`):
  `python tools/art_pack.py build`.
- **Instalar num cartão/coleção**: `python tools/art_pack.py install --sd E:\ [--roms pasta] [--dry-run] [-v]`.
  Casa por CRC No-Intro (sem header) e depois por nome (GoodNES/No-Intro); uma capa por fingerprint,
  preferindo EUA > Mundo > Europa > Japão.
- **Qualidade da conversão**: `nes_art.convert` (pesos em `L_WEIGHT`, busca exaustiva de paletas).
  Confira com `nes_art.render(arquivo)` antes de regerar tudo.
- As capas da release saem da coleção de ROMs do mantenedor (pasta `sdcard/` fora do git):
  `python tools/art_pack.py install --sd <tmp> --roms <coleção>` gera `<tmp>/EDFC/ARTS`.

## Release (só quando o usuário pedir)
1. Escreva `docs/release-notes/v<versão>.md` (as imagens usam URLs `raw.githubusercontent.com/.../v<versão>-ptbr/...`).
2. Commit + push do `main`.
3. Tag anotada (a máquina pode não ter identidade git configurada):
   `git -c user.name=... -c user.email=... tag -a v<versão>-ptbr -m "Release v<versão>-ptbr"`.
4. `python tools/create_github_release.py --version <versão> --arts <tmp com EDFC/ARTS>`
   → gera e publica **2 zips**: `EDFC-N8-PTBR-v<versão>.zip` e `...-com-capas.zip`.
5. Confira que as imagens das notas abrem (HTTP 200) e que a release ficou como Latest.

## Investigar o OS
- Decriptar: snippet em ARQUITETURA §1. Disassembly: `py65`.
- Rastrear no emulador: substitua `emu.step` / `emu.write` / `emu.read` por wrappers que registram
  `emu.PC`, endereços e `emu.reg_data[0x81]` (banco mapeado). Os testes em `tools/test_*.py` têm exemplos
  (`Probe`, `Watch`).
- Achar quem usa um texto: procure a string no binário decriptado e depois `LDA #<lo / LDX #>hi`.
- Antes de usar qualquer RAM "livre", meça no emulador quem lê/escreve nela durante vários fluxos.

## Checklist de teste no hardware (o emulador não pega timing)
- Trocar tema várias vezes com SELECT; a lista e o banner continuam corretos.
- START → Menu Principal; fechar volta ao navegador.
- Confirmar num jogo com capa e num sem capa; "Info da ROM"; "Carregar jogo" inicia o jogo.
- Reiniciar: o tema volta.
- Copiar arquivos para o cartão depois de usar o menu (nenhuma corrupção no PC).
