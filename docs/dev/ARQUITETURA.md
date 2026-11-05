# Arquitetura técnica

Tudo aqui foi levantado por engenharia reversa do OS decriptado (base oficial v1.26 traduzida), com o
emulador do projeto. Endereços de CPU em `$xxxx`; offsets de arquivo em `0x....`.

## 1. Layout do `OS.BIN` (57.344 bytes = 7 bancos de 8 KB)

| Offset no arquivo | Banco | Onde aparece | Conteúdo | Criptografado |
| :--- | :--- | :--- | :--- | :--- |
| `0x0000–0x1FFF` | `$09` | `$6000` (só no boot) | CHR da fonte; copiado inteiro para o PPU `$0000–$1FFF` no boot | não |
| `0x2000–0x3FFF` | `$0A` | — | dados do OS; decriptado no boot e **nunca mapeado depois** — não usar | sim |
| `0x4000–0x5FFF` | `$0B` | `$6000` sob demanda | **nosso**: pacotes de tema, paletas, loader, código das capas, tema e favoritos | não |
| `0x6000–0x7FFF` | `$0C` | `$8000–$9FFF` | código do OS | sim |
| `0x8000–0x9FFF` | `$0D` | `$A000–$BFFF` | código do OS | não |
| `0xA000–0xBFFF` | `$0E` | `$C000–$DFFF` | código do OS | não |
| `0xC000–0xDFFF` | `$0F` | `$E000–$FFFF` | código/strings/DATA do OS + **nossa região** `$FAE4–$FBFD` | sim |

Conversão para `$8000–$FFFF`: **offset = endereço − `$2000`**.
`$FC00–$FFF9` é coberto pela BIOS quando o registrador `$09` tem o bit 2 ligado (o OS liga) — não use.
Os bancos de PRG são RAM: código pode ser automodificável e variáveis podem morar no banco 15.

### Criptografia
Bancos 12, 15 (e 10) são XOR por posição: `cifrado = plano ^ keystream`. O keystream de qualquer byte é
`EDFC-ORIGINAL/OS.BIN[off] ^ (OS original decriptado)[off]`.
- Região `$FAE4–$FBFD`: o plano original é zero, então keystream = bytes do `EDFC-ORIGINAL`
  (`theme_runtime.patch_runtime` faz isso).
- Outros pontos: keystream fixo em `theme_runtime.KEYSTREAM` (hooks do boot/banner/NMI, tabela de
  itens `$FA9F`, string `$F66A`). Para um endereço novo, gere o keystream decriptando com o emulador
  (abaixo) e acrescente ao dicionário. Bancos 13/14: keystream zero.

### Decriptar para analisar
```python
import sys; sys.path.insert(0, "tools")
from edfc_emu import EverDriveN8Emu
emu = EverDriveN8Emu("EDFC-ORIGINAL/OS.BIN", ".")     # ou EDFC/OS.BIN
emu.run_frames(40)                                      # o decriptador roda no boot
plain = b"".join(bytes(emu.prg_ram[b]) for b in range(9, 16))   # mesmo layout do OS.BIN
```
Disassembly: `py65` (`from py65.disassembler import Disassembler`). Keystream de `off`:
`orig_enc[off] ^ plain_orig[off]`.

## 2. Mapper (registradores do EverDrive)
`$4400` = índice do registrador, `$4401` = dado. Os mais usados:
`$81` = banco em `$6000–$7FFF` (8 = RAM de trabalho do OS, 9 = CHR, `$0B` = nosso), `$80`, `$82–$8C`,
`$09`, `$0A`, `$87`, `$8A` = SD/FPGA/config. O OS escreve índice e dado em sequência, e às vezes faz
leitura-modifica-escrita no `$4401` — uma interrupção que mude o índice no meio corrompe essa sequência.

## 3. RAM

### Banco 8 em `$6000–$7FFF` (RAM de trabalho do OS)
- Heap bump: ponteiro em `$0450`, começa em `$6000`, após o boot = `$7BA5`; alocações em tempo de
  execução (12, 200, 256, 512 B) sobem até no máximo `$7F81`.
- `$6000–$63FF` sombra da nametable (tela), `$6400–$67FF` cópia para pop-ups (`$845E` salva, `$847C` restaura).
- `$7FF8–$7FFB` assinatura do tema salvo: `$ED $FC id ~id` (nosso; acima do teto do heap).

### RAM interna `$0000–$07FF`
| Faixa | Uso |
| :--- | :--- |
| `$00–$FF` | zero page do OS. `$28/$29` = ponteiro da pilha C (cc65), `$2A/$2B` = sreg, `$30/$31` = ptr temporário, `$9A–$9D` = temporários do upload de tela (`$8343`), `$9E/$A0/$A1` = NMI, `$A2` = "upload de VRAM em andamento" |
| `$0100–$01FF` | pilha do 6502; nunca desce de `$01DF` (medido também nos favoritos: `$01DB`) → **`$0100–$01AF` livre** (trampolim + variáveis, `art_runtime.T_LIMIT`) |
| `$0200–$02FF` | zerada no reset e nunca lida pelo OS → **livre** (capas: registro do arquivo + tabela OAM; favoritos: `$0200` linha de texto, `$0220–$0248` clusters, buffer, nome `FAVS    DAT` — ver `fav_runtime.py`) |
| `$0300–$03FF` | **DATA do OS (cc65)**: tabelas de menu (`$03B3`, `$03B9`, `$03C1`, `$03C9`, `$03D5`), variáveis (`$0350–$037F`), rotina copiada (`$03E0+`). **Proibido escrever.** Imagem de origem no banco 15 a partir de `$F9DA` |
| `$0400–$04DA` | BSS do OS (ponteiros globais, `$0484` = joypad, `$0486`/`$0487` = máscaras confirmar/cancelar, `$04D4` = redesenhar tela, `$046E` = cluster da pasta `/EDFC`) |
| `$0500–$07FF` | pilha C (cresce para baixo a partir de `$0800`) |

## 4. API do OS usada pelos patches
Convenção cc65: empilhe todos os argumentos com os helpers e chame com **A/X iguais ao último
argumento** (exatamente como o OS faz); quem é chamado desempilha. Helpers: `$F3B2` pusha,
`$F3C4` push0, `$F3C8` pushax, `$F1EC` pusheax (A/X + `$2A/$2B`), `$F3EF` pushwysp.

| Endereço | Função |
| :--- | :--- |
| `$83B0` | espera vblank (BIT `$2002`) |
| `$8343` | envia a sombra `$6000–$63FF` para o PPU (8 blocos, seta `$A2`) |
| `$83E2` | limpa a sombra (termina no nosso hook do banner, `$83F9`) |
| `$9F6C` | espera soltar e apertar botão (laço ocioso → `$ABBD`); devolve A = botões |
| `$ABBD` | poll de USB nos laços ociosos (nosso hook IDLE) |
| `$CA0D` | menu genérico com cursor (índice, tabela de itens, quantidade, início) |
| `$CB50` | Menu Principal (tabela de itens agora no banco 15, 6 itens; resultado em `(sp),0`, despacho `$CB76…$CBBD`) |
| `$A854` | começa tela de texto: limpa (banner entra pelo hook) e cursor x=2, y=1 (linha 3 da tela) |
| `$A864` | (str16) imprime linha e desce (`$048E` = y, máx. 24); `$9F = $7F` antes = linha destacada |
| `$847C` | restaura a tela salva por `$845E` (o `$CA0D` salva ao abrir o menu) |
| `$A451` / `$A476` | malloc(size16) / free(size16) — heap **LIFO** (o free só baixa `$0450`) |
| `$969A` | (cluster32) → LBA32 em A/X/`$2A/$2B` |
| `$C404` | (&cluster32) → próximo cluster no lugar; A = 0 se ok |
| `$AAD5` | (lba32, dst16, n8) lê setores; A = 0 se ok |
| `$AB0A` | (src16, n8, lba32) **grava** setores (invalida o cache de setor do OS); A = 0 se ok |
| `$BF16` | (índice8, `*$046A`) monta o registro "jogo atual" (271 B: cluster, …, LFN em +10, `$55AA` em +`$10B`); não grava no SD |
| `$B7AC` | inicia o jogo descrito pelo registro em `*$046A` (era o "repetir último jogo") |
| `$CBC0` | despacha o menu de arquivo pela extensão → `$D556` (.NES/.FDS), `$D782` (.SAV), `$D83F` (.TXT) |
| `$D556` | menu do jogo (resultado 0 = carregar → `$BF16` + `$B7AC`; 2 = Info da ROM `$CD1F`) |
| `$BC71` | lê o registro do arquivo pelo índice: `cluster32, …, nome(LFN)` e o **nome 8.3 em buf+`$100`** (11 bytes — buffer precisa de 267 B) |
| `$9541` | lê setores de um arquivo a partir do cluster; **destino < `$2000` vai para o PPU** |
| `$95C4` | continua lendo o arquivo aberto (o emulador não simula a continuação — leia tudo numa chamada) |
| `$AD3B` | acha subpasta — compara **exatamente 4 caracteres** (por isso `ARTS`, `EDFC`, `SAVE`, `MAPS`) |
| `$9DC7` | acha arquivo pelo nome 8.3 de 11 caracteres (`"XXXXXXXXBIN"`) |
| `$8DA9` | abre diretório (muda o diretório atual do FAT) — depois de buscar, **reabra `$8278`** (pasta do navegador) |
| `$D89E` | laço do navegador (redesenha se `$04D4`) |

## 5. Patches aplicados (fonte: `theme_runtime.os_patches`)
| Endereço | Original | Novo |
| :--- | :--- | :--- |
| `$828C` | `JSR $83B0` (boot) | `JSR BOOT` — lê a assinatura e pede o tema salvo |
| `$83F9` | fim da limpeza de tela | `JMP BANNER` — desenha o banner (linhas 0–1) + linha preta |
| `$ABBD` | `JSR $EF47` | `JSR IDLE` — aplica o tema pedido no boot |
| `$DBE7` | START = reiniciar último jogo | `JSR $CB50; JMP $D89E` (Menu Principal) |
| `$DBFC` | SELECT = Menu Principal | `JSR H_SEL` (próximo tema + redesenho, no banco `$0B`) |
| `$D579` | 3 itens | 3 itens: Carregar jogo, Info da ROM, Favoritar |
| `$D5BA` | `CMP #$01` | `CMP #$02` (resultado 1 cai em Info da ROM, 2 em `$D5BD`) |
| `$D5BD` | código do "Apenas Selec." | `JSR H_FAVADD; LDA #0; JMP $D5E5` (adiciona favorito) |
| `$D582` | `JSR $CA0D` | `JSR H_MENU` (capa + menu) |
| `$CFB2` | `JSR $9F6C` (Info da ROM) | `JSR H_INFO` (capa durante a espera) |
| `$FA9F`, `$FAA1` | ponteiros "Apenas Selec." / item 2 | ponteiros "Info da ROM" / "Favoritar" |
| `$F66A`, `$F679` | "Sel. e Iniciar", "Apenas Selec." | "Carregar jogo", "Favoritar" |
| `$CB56`, `$CB5D` | tabela `$03C9`, 5 itens | `MAIN_TABLE` no banco 15 (+ "Favoritos"), 6 itens |
| `$CBAF` | `LDY #0; LDA (sp),Y; BNE $CB55` | `JSR H_MAIN` (0 → Opções; 5 → tela de favoritos; resto → volta a `$CB55`) |
| `$8103` | (v1.4 tinha hook) | original `LDA $2002 / PLA / RTI` |
| `$F7B9–$F899` + 14 ponteiros em `$D1C7…$D251` | textos do "Sobre" | crédito do mod e controles atuais (`theme_runtime.ABOUT_LINES`, máx. 225 bytes) |
| `$63C0`, `$63C7` (sombra) | atributo `$05` | `$0A`: cantos do banner usam a paleta 2 (ícones) |

## 6. Nosso código
### Banco 15, região `$FAE4–$FBFD` (`theme_runtime.build_runtime`)
`$FAE4` id da chamada longa, `$FAE5` tema atual, `$FAE6` tema pedido (bit 7 = forçar). Rotinas:
`BANNER`/`BANNER_BODY`, `BOOT`, `APPLY` (paleta + tiles via loader do banco `$0B`, banner, assinatura),
`IDLE`, stubs `H_INFO`/`H_MENU`/`H_MAIN`/`H_SEL`/`H_FAVADD` (`LDA #id; JMP FAR`; `FAR` grava o id,
mapeia `$0B` e salta para `DISPATCH`), `MAIN_TABLE` (título + 6 itens do Menu Principal) e "Favoritos".

### Banco `$0B` (montado em `test_full_banner_system.build_bank11_image`)
| Endereço | Conteúdo |
| :--- | :--- |
| `$6000` | ponteiros dos 9 pacotes |
| `$6012…` | pacotes: nametable 64 B (linhas 0–1) + nº de tiles + (slot, 16 B) por tile |
| `$6E60` | paletas dos temas (9 × 16 cores, `banner_art.palette16`) |
| `$6F00` | loader (paleta + tiles; usa `$9A–$9D`), até `$6FBF` |
| `$6FC0` | variáveis dos favoritos (16 B, `fav_runtime.VARS_SRC`) |
| `$6FD0` | cache de nomes dos favoritos: 32 × 32 B (nome 28 + NUL, byte 31 = slot) |
| `$73D0` | código longo: `DISPATCH`, `SELT`, `MAIN`, `FAVADD`, tela de favoritos, capas, textos, imagem do trampolim (até ~`$7F49`) |
| `$7FE0` | rascunho: cópia de `$0300–$030F` durante `$BC71` |

### Capas (`art_runtime.py`)
Trampolim copiado para `$0100` (mapeia banco 8 só durante chamadas ao OS e volta para `$0B`).
Fluxo: registro → cluster → lê setores 0–4 da ROM para o PPU `$1000` → CRC-32 dos bytes 512–2559
(lidos de volta do PPU) → `EDFC/ARTS/<CRC>.BIN` → 4 setores para `$1000` → metadados em `$1600`
→ OAM em `$0200` + DMA → sprites 8×16 (`$2000=$A0`, `$2001=$1E`); ao sair `$2000=$80`, `$2001=$0A`.
Formato do arquivo: ver docstring de `nes_art.py`. A tabela de padrões `$1000` não é usada pelo OS.

### Favoritos (`fav_runtime.py`)
Arquivo `EDFC/FAVS.DAT` (16 KB) criado no PC e enviado no zip — o console **nunca cria, aumenta ou
renomeia arquivo** (sem escrita em FAT/diretório). Setor K = slot K: bytes 0–270 = cópia do registro
de `$BF16`; cluster 0 = vazio; byte 503 = K; 504–511 = `EDFCFAV1`. Antes de **toda** gravação o setor
é lido e o byte do slot + a assinatura conferidos (um LBA errado nunca grava em outro arquivo).
LBA do setor K: anda `K / spc` clusters com `$C404`, `$969A` e soma `K % spc`. Buffer de 512 B via
malloc do OS (recusa se `$0450` ≥ `$7C00`), liberado antes de voltar ao OS ou iniciar o jogo.
- **Favoritar** (menu do jogo): `$BF16` monta o registro, procura duplicado (mesmo cluster) e o primeiro
  slot livre, grava, mostra mensagem em tela cheia e pede redesenho (`$04D4`).
- **Favoritos** (Menu Principal): lista em ordem de slot; cima/baixo, confirmar copia o registro para
  `*$046A` e chama `$B7AC`; SELECT zera o cluster do slot; cancelar volta ao menu (`$847C` + `$CB55`).

### CHR e tela
Slots livres da fonte para tiles de banner: `$0B–$1E` e `$8B–$9F`; `$1F` = tile vazio (linha 2).
Atributos `$63C0–$63C7 = $05`: linhas 0–1 usam a paleta 1 (= cores do tema: sh, txt, hl).

## 7. Emulador (`tools/edfc_emu.py`) — limitações
- Roda o decriptador real (página tirada de `EDFC-ORIGINAL/OS.BIN`).
- BIOS/SD falsos: monta FAT16 com nomes longos a partir de uma pasta; `sdRead` recarrega o LBA
  inicial a cada chamada (não continua streams).
- Sem tempo de PPU real (espera de vblank é acelerada), sem decaimento de OAM, sem conflitos
  de escrita durante a renderização. **Bugs de timing não aparecem aqui.**
- Pastas ocultas, `releases/` e `sdcard/` são ignoradas ao montar o cartão a partir do repo.
- `tools/ppu_timing.py` (`TimedEmu`) é um modo com tempo aproximado (29.780 ciclos/quadro, vblank de
  2.273 ciclos, NMI real, leitura de `$2002` como no hardware, setor de SD = 16.000 ciclos) que lista
  escritas no PPU fora do vblank com a tela ligada (`emu.unsafe`). Segure botões ≥ 8 quadros nele: o OS
  só lê o controle depois de cada espera de vblank.
