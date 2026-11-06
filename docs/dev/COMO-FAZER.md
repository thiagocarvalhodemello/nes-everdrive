# Como fazer (receitas)

Pré-requisitos: Python 3.12+, `pip install pillow numpy py65`, `gh` (só para releases).
Todos os comandos rodam na raiz do repositório.

## Build e testes (sempre)
```bash
python tools/install_banner_theme.py   # aplica tudo em EDFC/OS.BIN e gera EDFC/OVL*.BIN (idempotente)
python tools/test_theme_safety.py      # deve terminar em PASSED
python tools/test_game_art.py          # deve terminar em PASSED
python tools/test_favorites.py         # deve terminar em PASSED
python tools/test_search.py            # deve terminar em PASSED
```
`python tools/resident_runtime.py` mostra o tamanho do residente e de cada módulo.
Rodar o install duas vezes não muda nada; se `git diff EDFC/OS.BIN` mostrar diferença sem você ter
mudado código, algo está errado.

## Mudar um banner ou criar um tema
1. `tools/banner_art.py`: `THEMES` (id, nome, texto do banner, cores via `T(...)`), `DECOS` (decoração
   por tema, cores 1–3), `STYLES` (estilo do título) e `ICONS` (ícones nos cantos, x < 32 e x ≥ 224).
   A fonte 5×7 (`FONT5x7`) só tem os caracteres usados — acrescente os que faltarem.
   **Cada tema define uma paleta completa de 16 cores** (`palette16`), por papel:
   `bd` (fundo geral), `file` (nomes de arquivo), `bg` (**fundo da lista**), `folder` (pastas/seleção),
   `banner` (escura, média, clara), `icon` (3 cores dos ícones dos cantos, paleta 2) e
   `popup` (texto, fundo e item destacado das janelas e da barra de status).
   O build recusa combinações ilegíveis (`check_contrast`: ≥ 40 L*). Confira sempre uma pasta com
   **arquivos** (fonte normal), não só a raiz (pastas usam a fonte destacada).
2. `python tools/banner_art.py` mostra quantos tiles cada banner usa e grava prévias em
   `docs/themes/banners/`. Limite: `MAX_TILES = 39` por banner (slots livres da fonte).
3. Tema novo (10º): ajuste também `NUM_THEMES` em `tools/theme_runtime.py`. Confira o espaço: o
   `assert` "Theme data exceeds Bank 0x0B space" dispara se os pacotes passarem de `$6E60`.
4. Install + testes + `python tools/capture_theme_screenshots.py`.

## Adicionar uma opção ao menu do jogo ou ao Menu Principal
Estado atual (ver ARQUITETURA §5):
- **Menu do jogo**: tabela de itens na imagem DATA em `$FA9D` (3 ponteiros, banco 15 criptografado),
  quantidade em `$D579` (= 3: Carregar jogo, Info da ROM, Favoritar), despacho em `$D556`
  (0 → carregar; `CMP #$02` em `$D5BA` → `$D5BD` = Favoritar; resto → Info da ROM). Uma 4ª opção
  precisa de outra string (keystream novo em `theme_runtime.KEYSTREAM`), de um 4º ponteiro — a
  tabela DATA não tem espaço: mova-a para o banco 15 como foi feito com o Menu Principal — e de
  despacho novo. O menu genérico `$CA0D` comporta ~8 itens.
- **Menu Principal**: `resident_runtime.main_table_data()` (copiada para `$0280` pelo `START`;
  `$6E10` está cheio — para mais itens, mova os textos), quantidade `MAIN_ITEMS` (`$CB5D`), mapeamento
  dos resultados em `MMENU` (0–3 nossos, 4–8 → itens 0–4 do OS). O `MMENU` ajusta o espaçamento do
  `$CA0D` (1 linha) só durante o Menu Principal; cabem ~12 itens.

Código novo: **módulo de overlay** (o residente está quase cheio). Escreva o módulo em texto
(`asm_text`, como `find_runtime.module_find`), registre em `resident_runtime.OVL_FILES` e em
`build_all()`, e chame do residente com `LDA #id; JSR OVL; BCS erro; JSR OVL_BASE+4+3*k`. O módulo não
chama `SETUP` (o residente chama antes do `OVL`), usa o cache `$6FD0` e as variáveis `V_*` à vontade e
não pode carregar outro módulo (ele seria sobrescrito: devolva um código para o residente fazer o resto,
como os favoritos fazem com `LAUNCH_GO`). Um ponto novo no OS ainda precisa de um stub `H_X` no banco 15
(`LDA #id; JMP FAR`) e de um ramo na tabela `DJT` do `DISPATCH`; retorne por `JSR ZPOUT; JMP T_EXIT`.
Chamadas ao OS só via trampolim (`_call` = `JSR CALLI` + 3 bytes), pois o OS precisa do banco 8
mapeado. Textos que o OS vai ler precisam estar na RAM interna (`STRBUF`, via `PUTS`) ou no banco 15.
Registre os patches em `os_patches()` e acrescente teste.
Atenção: a capa fica visível enquanto o menu (`$CA0D`) roda e é escondida quando ele retorna.

## Favoritos e Recentes
- `EDFC/FAVS.DAT` e `EDFC/RECENTS.DAT` vêm de `fav_runtime.favs_dat()` (32 slots vazios) e vão nos zips;
  o install cria os que faltarem (nunca sobrescreve).
- Ao atualizar o sistema o usuário deve manter os `.DAT` dele (avise nas notas da release).
- Nunca grave no SD sem ler o mesmo setor antes e conferir slot + `EDFCFAV1` (ver `F_READ`/`F_WRITE`).

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
- Ligar: o Menu Principal abre sozinho; "Lista de jogos" e cancelar voltam ao navegador; START reabre.
- Banner inteiro na TV (não cortado no topo); rodapé visível.
- Telas de erro do OS (ex.: aviso A7 na primeira vez, cartão sem ROM) mostram só o código, sem linha de lixo.
- Busca num cartão grande (várias pastas, 100+ jogos): progresso andando, tempo aceitável, cancelar
  interrompe, resultado certo; escolher um jogo de subpasta abre a pasta dele e "voltar" sobe as pastas.
- ESQ/DIR no menu do jogo troca de jogo (capa e nome acompanham).
- Iniciar 2–3 jogos e abrir Recentes (mais recente primeiro).
- Confirmar num jogo com capa e num sem capa; "Info da ROM"; "Carregar jogo" inicia o jogo.
- Reiniciar: o tema volta.
- Favoritar 2–3 jogos, abrir START → Favoritos, iniciar um e remover outro com SELECT; depois
  conferir o cartão no PC (`chkdsk`/scandisk sem erros, `FAVS.DAT`/`RECENTS.DAT` continuam com 16 KB).
- Copiar arquivos para o cartão depois de usar o menu (nenhuma corrupção no PC).
