# Guia para agentes de IA (e humanos) — nes-everdrive

Mod em PT-BR do sistema operacional (`EDFC/OS.BIN`) do flashcart **EverDrive N8** (placas clone
`Drive-N8 V3.1 2024.07`). Não há código-fonte do OS: tudo é **patch binário** em 6502, montado por
scripts Python em `tools/` e verificado num emulador próprio (`tools/edfc_emu.py`).

Leia antes de mexer:
1. **Este arquivo** (regras e fluxo).
2. [`docs/dev/ARQUITETURA.md`](docs/dev/ARQUITETURA.md) — mapa de memória, criptografia, API do OS, hooks.
3. [`docs/dev/COMO-FAZER.md`](docs/dev/COMO-FAZER.md) — receitas (tema novo, opção de menu, capas, release).
4. [`docs/dev/HISTORICO-DE-BUGS.md`](docs/dev/HISTORICO-DE-BUGS.md) — bugs que já aconteceram e por quê.

---

## Regras de ouro (cada uma já custou um bug real)

1. **Nada de trabalho dentro da NMI.** A NMI é a original do OS (`$80D1`, termina em `$8103`). Trocar
   banco do mapper, escrever no PPU ou na RAM do OS dentro dela corrompeu o cartão SD (v1.3).
2. **Registradores do mapper (`$4400` índice / `$4401` dado) só no laço principal**, sempre escrevendo
   `$4400` antes de `$4401`, e devolvendo o **banco 8** mapeado em `$6000` ao voltar para o OS.
3. **Não escreva no heap do OS** (banco 8, `$6000–$7FF7`). O alocador começa em `$6000`, termina o boot
   em `$7BA5` e entrega buffers (até 512 B, buffer de setor) acima disso. Exceções conhecidas e seguras:
   sombra da nametable linhas 0–3 (`$6000–$607F`, cópia `$6400–$647F`), atributos `$63C0–$63C7` e a
   assinatura do tema `$7FF8–$7FFB`.
4. **A página `$0300–$03FF` da RAM interna é dado do OS** (segmento DATA do cc65: tabelas de menu e
   variáveis da listagem). Nunca escreva lá (v1.4 escrevia e corrompia a lista até reiniciar).
   Áreas livres: `$0100–$01AF` (pilha nunca desce de `$01D9`), `$0200–$02FF` (`$0280–$02BF` = tabela
   do Menu Principal enquanto ele está aberto) e `$0500–$06FF` (buffer de setor da busca; a pilha C não
   desce de ~`$07A7` — `test_search.py` mede).
5. **Espaço é escasso e tem orçamento**: banco 15 `$FAE5–$FBFD` (282 B, usado 278; `$FAE4` tem que ficar 0:
   é a string vazia das telas de erro do OS), banco `$0B`
   (dados de tema ≤ `$6E10`, tabela do menu `$6E10–$6E5F` (cheio), paletas `$6E60–$6EEF`, loader ≤ `$6FB8`,
   variáveis `$6FB8–$6FCF`, cache `$6FD0–$73CF`, **residente** `$73D0–OVL_BASE`, **overlay** `OVL_BASE–$7FDF` (busca: até `$7FFF`)),
   trampolim ≤ `$01B0`. Código novo grande vai para um **módulo de overlay** (`resident_runtime.py`):
   cada módulo cabe na área de overlay (~1840 B; `python tools/resident_runtime.py` mostra) e roda sozinho
   (não chame um módulo de dentro de outro: devolva ao residente, como a busca faz com FIND → SCAN → FIND).
   Banco 14 livre: `$D5DE–$D5E0`, `$DBF2–$DBF4`. Os scripts têm `assert` — não os remova.
6. **Banco 12 e 15 são criptografados** (XOR por posição). Patch = `plano ^ keystream`. Bancos 13/14 não.
   Veja a seção "Criptografia" em ARQUITETURA.md antes de alterar qualquer byte fora da região livre.
7. **`EDFC/OS.BIN` commitado é a fonte da verdade.** `tools/install_banner_theme.py` aplica todos os
   patches sobre ele e é **idempotente**. **Não rode `translate_os_ptbr.py`** para "reconstruir": ele
   gera uma base diferente (verificado: 39.516 bytes de diferença) e desfaz a tradução atual.
8. **Testes do emulador precisam passar** antes de commitar: `tools/test_theme_safety.py`,
   `tools/test_game_art.py`, `tools/test_favorites.py` (favoritos + recentes) e `tools/test_search.py`. O emulador **não** simula tempo real de PPU; bugs de timing só aparecem no
   hardware — descreva isso honestamente ao usuário.
9. **O console só grava no SD dentro do `EDFC/FAVS.DAT` e do `EDFC/RECENTS.DAT`**, que já existem com
   tamanho fixo (sem mexer em FAT/diretório) e só depois de ler o setor e conferir slot + assinatura.
   Não crie outro caminho de escrita sem a mesma proteção.
10. **`EDFC/OVL*.BIN` e `EDFC/OS.BIN` andam juntos**: os módulos levam o build id do residente e são
   recusados se não baterem. Sempre gere os dois com `install_banner_theme.py` e commite/empacote juntos.

---

## Fluxo padrão de uma mudança

```bash
# 1. editar tools/theme_runtime.py, tools/art_runtime.py, tools/banner_art.py, ...
python tools/install_banner_theme.py      # aplica tudo em EDFC/OS.BIN (idempotente)
python tools/test_theme_safety.py         # temas, SELECT/START, NMI, assinatura, reboot
python tools/test_game_art.py             # menu do jogo, capas, página 3 intacta, "Carregar jogo"
python tools/test_favorites.py            # favoritos e recentes; só FAVS.DAT/RECENTS.DAT são gravados
python tools/test_search.py               # Menu Principal no boot, busca em todas as pastas, resultados
# 2. se a tela mudou: atualizar capturas
python tools/capture_theme_screenshots.py
python tools/capture_art_screenshots.py --arts <pasta com EDFC/ARTS> <roms...>
python tools/capture_menu_screenshots.py  # Menu Principal, busca (teclado, progresso, resultados), recentes
# 3. commitar código + EDFC/OS.BIN + EDFC/OVL*.BIN juntos
```

Commits: mensagens em português, estilo `tipo(escopo): resumo` (ex.: `fix(art): ...`).
Releases só quando pedido — ver COMO-FAZER.md.

---

## Mapa dos arquivos

| Caminho | Papel |
| :--- | :--- |
| `EDFC/OS.BIN` | **Produto final** (o que vai no cartão). Commitado. |
| `EDFC-ORIGINAL/OS.BIN` | OS original de fábrica: fonte do **keystream** de criptografia e da página do decriptador do emulador. **Nunca altere.** |
| `EDFC/OS.BIN.orig` | Base usada por `translate_os_ptbr.py` (histórico; não use no fluxo normal). |
| `EDFC/MAPS/*.RBF`, `EDFC/MAPROUT.BIN` | Núcleos FPGA e roteamento de mappers compatíveis com as placas clone. |
| `tools/theme_runtime.py` | Assembler 6502 + código do banco 15 (temas, SELECT, boot, hooks) + **lista de todos os patches no OS** (`os_patches`). |
| `tools/resident_runtime.py` | **Residente** do banco `$0B` (despacho, tema, Menu Principal, loader de overlay) e montagem dos módulos `EDFC/OVL*.BIN`. |
| `tools/art_runtime.py` | Trampolim (`$0100`) e módulo ART (capas + ESQ/DIR no menu do jogo). |
| `tools/fav_runtime.py` | Front end de assembly (`asm_text`, `_call`…) e módulos FAV/REC (favoritos, recentes); gera os `.DAT` vazios. |
| `tools/find_runtime.py` | Módulos da busca: `OVLFIND` (teclado, resultados) e `OVLSCAN` (varredura de todas as pastas com progresso; leitor de diretório próprio). |
| `EDFC/OVL*.BIN` | Módulos gerados (precisam bater com o `OS.BIN`). |
| `EDFC/FAVS.DAT`, `EDFC/RECENTS.DAT` | Listas vazias (32 slots) que vão nos zips. |
| `tools/test_full_banner_system.py` | Monta a imagem do banco `$0B` (pacotes de tema, paletas, loader, capas). Nome histórico. |
| `tools/banner_art.py` | Temas (nomes, paletas) e geração dos banners 256×16 por código. |
| `tools/install_banner_theme.py` | Aplica banco 9 (tiles do tema 0), banco `$0B` e banco 15/hooks em `EDFC/OS.BIN`. |
| `tools/nes_art.py` | Formato do arquivo de capa (2 KB), conversão PNG→NES, fingerprint (CRC). |
| `tools/art_pack.py` | PC: baixa/converte capas do libretro (`build`) e instala no cartão (`install`). |
| `tools/edfc_emu.py` | Emulador 6502 + PPU simplificado + BIOS/SD falsos (imagem FAT16 com LFN gerada de uma pasta). |
| `tools/test_theme_safety.py`, `tools/test_game_art.py`, `tools/test_favorites.py`, `tools/test_search.py` | Testes de regressão (rodar sempre). |
| `tools/capture_*_screenshots.py` | Capturas para README/release. |
| `tools/package_releases.py`, `tools/create_github_release.py` | Empacotar (2 zips) e publicar release via `gh`. |
| `translate_os_ptbr.py`, `tools/patch_font_and_strings.py` | Pipeline histórico da tradução (ver regra 7). |
| `docs/release-notes/vX.md` | Notas de cada release (usadas pelo publicador). |
| `docs/screenshots/`, `docs/themes/banners/` | Imagens do README/release. |

`releases/`, `.artcache/` e `sdcard/` são ignorados pelo git (pacotes gerados, cache de capas, cartão de teste).
