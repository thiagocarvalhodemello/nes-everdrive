# Arquitetura técnica

Tudo aqui foi levantado por engenharia reversa do OS decriptado (OS de fábrica da placa clone Drive-N8 V3.1 2024.07, que se identifica como "OS ver 13"; a base oficial v1.26 da Krikzz só vale para a release v1.3), com o
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
| `$0200–$02FF` | zerada no reset e nunca lida pelo OS → **livre** (capas: registro do arquivo + tabela OAM; listas: `$0200` linha de texto, `$0220–$024B` clusters, buffer, nome, contador; busca: `$0200–$023F` linhas do progresso, `$0240` cluster lido, `$0244` fila de pastas, `$0250–$027F` nome comparado; **`$0280–$02BF` tabela do Menu Principal** enquanto ele está aberto — ver `fav_runtime.py`/`find_runtime.py`) |
| `$0300–$03FF` | **DATA do OS (cc65)**: tabelas de menu (`$03B3`, `$03B9`, `$03C1`, `$03C9`, `$03D5`), variáveis (`$0350–$037F`), rotina copiada (`$03E0+`). **Proibido escrever.** Imagem de origem no banco 15 a partir de `$F9DA` |
| `$0400–$04DA` | BSS do OS (ponteiros globais, `$0464`/`$0466` = flags/ordem da lista, `$04B8` = nº de entradas, `$0484` = joypad, `$0486`/`$0487` = máscaras confirmar/cancelar, `$04D4` = redesenhar tela, `$046E` = cluster da pasta `/EDFC`) |
| `$0500–$06FF` | nunca usada pelo OS (a pilha C não desce de ~`$07A7`; na busca, `$07B1` medido) → **buffer de setor de diretório da busca** (`find_runtime.SBUF`); ao iniciar um favorito/recente: registro do jogo em `$0500–$060E` e o gancho do `$BC71` em `$0610` (`fav_runtime.RECB`/`HOOK`) |
| `$0700–$07FF` | pilha C (cresce para baixo a partir de `$0800`) |

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
| `$A854` | começa tela de texto: limpa (banner entra pelo hook) e cursor x=2, y=1 (linha 4 da tela: linha y = y + 3) |
| `$A864` | (str16) imprime linha e desce (`$048E` = y, máx. 24); `$9F = $7F` antes = linha destacada |
| `$847C` | restaura a tela salva por `$845E` (o `$CA0D` salva ao abrir o menu) |
| `$A451` / `$A476` | malloc(size16) / free(size16) — heap **LIFO** (o free só baixa `$0450`) |
| `$969A` | (cluster32) → LBA32 em A/X/`$2A/$2B` |
| `$C404` | (&cluster32) → próximo cluster no lugar; A = 0 se ok |
| `$AAD5` | (lba32, dst16, n8) lê setores; A = 0 se ok |
| `$AB0A` | (src16, n8, lba32) **grava** setores (invalida o cache de setor do OS); A = 0 se ok |
| `$BF16` | (índice8, `*$046A`) **seleciona o jogo**: se o jogo anterior (registro ainda em `*$046A`) tem bateria, grava a SRAM (banco 0) no arquivo dele em `EDFC/SAVE/<nome da ROM>` (`$A12A`); monta o registro novo com `$BC71` (em `$BFDA`; 271 B: cluster, …, LFN em +10, `$55AA` em +`$10B`) e carrega o save do jogo novo na SRAM (`$A245`). Todo início de jogo tem que passar por aqui, senão o save não é carregado |
| `$B7AC` | inicia o jogo descrito pelo registro em `*$046A` (era o "repetir último jogo") |
| `$CBC0` | despacha o menu de arquivo pela extensão → `$D556` (.NES/.FDS), `$D782` (.SAV), `$D83F` (.TXT) |
| `$D556` | menu do jogo (resultado 0 = carregar → `$BF16` + `$B7AC`; 2 = Info da ROM `$CD1F`) |
| `$BC71` | lê o registro do arquivo pelo índice: `cluster32, …, nome` em +10 (nome longo, ou `"NOME    EXT"` sem LFN); escreve além de 256 B (buffer de 267 B: salve `$0300–$030F` se o buffer for `$0200`). Não há nome 8.3 confiável em buf+`$100` (verificado) |
| `$C7E2` | (redesenhar8) desenha a lista e a barra de status para `$8276`; o laço do navegador chama com 0 |
| `$9541` | lê setores de um arquivo a partir do cluster; **destino < `$2000` vai para o PPU** |
| `$95C4` | continua lendo o arquivo aberto (o emulador não simula a continuação — leia tudo numa chamada) |
| `$AD3B` | acha subpasta — compara **exatamente 4 caracteres** (por isso `ARTS`, `EDFC`, `SAVE`, `MAPS`) |
| `$9DC7` | acha arquivo pelo nome (abre a pasta com `$8DA9` e compara entrada por entrada): **só enxerga as ~253 primeiras entradas** (índice de 8 bits). Para pastas grandes (`EDFC/ARTS`) use leitura própria dos setores (`art_runtime.AFIND`) |
| `$8DA9` | (cluster32; 0 = raiz) abre diretório: monta as tabelas por entrada (`*$0460/$0462/$0464`), a quantidade `$04B8` (< `$FE`), a pasta pai `$04BB` e `$04BA` (raiz). Ignora `.`/`..`/apagados. Depois de usar, **reabra `$8278`** (pasta do navegador) |
| `$923B` | (índice16, nome16*, cluster32* ou 0, 0) lê a entrada: nome longo em `*$0468` (banco 8), primeiro cluster no ponteiro; 0 = ok. Não lê o arquivo (o `$BC71` lê) |
| `$C67D` | depois do `$8DA9`: monta a tabela de ordem de exibição `*$0466` |
| `$8275`, `*$0456` | profundidade da pasta do navegador e a seleção salva por nível (64 B), usadas pelo "voltar" |
| `$D89E` | laço do navegador (redesenha se `$04D4`) |

## 5. Patches aplicados (fonte: `theme_runtime.os_patches`)
| Endereço | Original | Novo |
| :--- | :--- | :--- |
| `$828C` | `JSR $83B0` (boot) | `JSR BOOT` — lê a assinatura e pede o tema salvo (sem assinatura: tema 0), para o IDLE rodar uma vez |
| `$83F9` | fim da limpeza de tela | `JMP BANNER` — banner nas linhas 1–2, linhas 0 (fica sob a borda da TV) e 3 pretas |
| `$A56B`, `$A5A9` | `LDA #$40` (base `$6040` = linha 2 das rotinas de posição de texto `$A565`/`$A595`) | `#$60`: tudo que o OS escreve desce uma linha (lista nas linhas 4–24, telas de texto 4–27, menus) |
| `$83F6` (banco 12) | `LDA #$40` (ponteiro de texto após limpar) | `#$60` |
| `$840C`, `$8418` (banco 12) | upload parcial do cursor: coluna 1 das linhas 0–23 (`$6001`/PPU `$2001`) | coluna 0 das linhas 1–24 (`$6020`/`$2020`) |
| `$C95B` | linha do navegador: `$A660(">"/" ", x, y)` com x = variável local (= 1, a mesma do x da barra de status) | `LDA #0; JSR pusha; NOP NOP`: setinha na coluna 0 e nome na coluna 1 (a TV mostra a coluna 0; antes sobrava uma coluna vazia antes da setinha) |
| `$C995` | largura do nome na lista `$1D` (29) | `$1E` (30: colunas 1–30, como a barra) |
| `$ABBD` | `JSR $EF47` | `JSR IDLE` — aplica o tema pedido no boot |
| `$D91E` | `LDA $0484` (laço ocioso do navegador) | `JSR H_JOY` → `BJOY` (residente): na 1ª vez após ligar "aperta START" (`$0484 = $10`, `$A2 = 1` para a NMI não sobrescrever até o `START`) → Menu Principal; depois só devolve `$0484` |
| `$ECF1`, `$ECF8`, `$ECFF`, `$ED06`, `$ED23` | mensagens da tela de erro do OS (a tradução as tinha posto em `$FAEB…`, hoje nosso código: saíam como lixo) | `$FAE4` (string vazia): a tela mostra só o código, como o OS de fábrica |
| `$DBE7` | START = reiniciar último jogo | `JSR $DBED; JMP $D89E`; em `$DBED` (bytes mortos) o stub `H_START` (`LDA #5; JMP FAR`) |
| `$DBFC` | SELECT = Menu Principal | `JSR H_SEL` (próximo tema + redesenho, no banco `$0B`) |
| `$D579` | 3 itens | 3 itens: Carregar jogo, Info da ROM, Favoritar |
| `$D5BA` | `CMP #$01` | `CMP #$02` (resultado 1 cai em Info da ROM, 2 em `$D5BD`) |
| `$D5BD` | código do "Apenas Selec." | `JSR H_FAVADD; LDA #0; JMP $D5E5` (adiciona favorito) |
| `$D582` | `JSR $CA0D` | `JSR H_MENU` (capa + menu) |
| `$CFB2` | `JSR $9F6C` (Info da ROM) | `JSR H_INFO` (capa durante a espera) |
| `$FA9F`, `$FAA1` | ponteiros "Apenas Selec." / item 2 | ponteiros "Info da ROM" / "Favoritar" |
| `$F66A`, `$F679` | "Sel. e Iniciar", "Apenas Selec." | "Carregar jogo", "Favoritar" |
| `$CB56`, `$CB5D` | tabela `$03C9`, 5 itens | tabela em `$0280` (página 2, copiada por `START`), 9 itens |
| `$CB68` | `JSR $CA0D` | `JSR H_MMENU` (itens 0–3 nossos; 4–8 viram os itens 0–4 do OS) |
| `$CBAF` | `LDY #0; LDA (sp),Y; BNE $CB55` | original (a v1.6 tinha `JSR H_MAIN` aqui) |
| `$D5B1` | `JSR $B7AC` ("Carregar jogo") | `JSR H_LAUNCH` (grava em Recentes e então `$B7AC`) |
| `$CA41`, `$CAC1`, `$CAC2` (em tempo de execução) | 1ª linha `$0B - n`, linha `+= 2` | só durante o Menu Principal: `$0F - n` e `+= 1` (`LDY #2; TYA; LSR; ADC`) — 9 itens não cabem na caixa do `$CA0D`; o `MMENU` restaura os bytes logo depois |
| `$C81F`, `$C833` | atributos da barra de status: linha 6 = `$FF` (linhas 24–27) | linha 7 = `$0F` (linhas 28–29, fim da tela, 2 linhas de altura) |
| `$C8BF`, `$C8C7`, `$C8DF`, `$C941` | nome selecionado nas linhas `$17`/`$18` (tela 25/26) | `$19`/`$1A` (tela 28/29) |
| `$8442`, `$8449` (banco 12) | upload parcial ao mover o cursor: PPU `$2320` ← `$6320` | PPU `$2380` ← `$6380` |
| `$CB34` | `JMP $CA40` (laço do menu sem confirmar/cancelar) | `JMP $D5C5`: no menu do jogo (tabela `$03C1`, único byte baixo `$C1`) ESQ/DIR saem com `$FE`/`$FD` |
| `$D5C5–$D5DD` | código morto do "Apenas Selec." | `theme_runtime.menu_lr_code` (25 bytes) |
| `$8103` | (v1.4 tinha hook) | original `LDA $2002 / PLA / RTI` |
| `$F7B9–$F899` + 14 ponteiros em `$D1C7…$D251` | textos do "Sobre" | crédito do mod e controles atuais (`theme_runtime.ABOUT_LINES`, máx. 225 bytes) |
| `$63C0–$63C7` (sombra) | atributo `$05` | `$55` (linhas 0–3 na paleta 1); cantos `$63C0`/`$63C7` = `$AA` (paleta 2, ícones) |

## 6. Nosso código
### Banco 15, região `$FAE4–$FBFD` (`theme_runtime.build_runtime`)
`$FAE4` fica sempre 0 (string vazia das mensagens de erro), `$FAE5` tema atual, `$FAE6` tema pedido
(bit 7 = forçar), `$FAE7` id da chamada longa. Rotinas:
`BANNER`/`BANNER_BODY`, `BOOT`, `APPLY` (paleta + tiles via loader do banco `$0B`, banner, assinatura),
`IDLE`, stubs `H_INFO`/`H_MENU`/`H_MMENU`/`H_SEL`/`H_JOY`/`H_LAUNCH`/`H_FAVADD` (`LDA #id; JMP FAR`; `FAR` grava o id,
mapeia `$0B` e salta para `DISPATCH`). Ids: 0 INFO, 1 MENU, 2 MMENU, 3 SEL, 4 FAVADD, 5 START (stub em `$DBED`),
6 LAUNCH, 7 JOY. Usado: 278/282 bytes.

### Banco `$0B` (montado em `test_full_banner_system.build_bank11_image`)
| Endereço | Conteúdo |
| :--- | :--- |
| `$6000` | ponteiros dos 9 pacotes |
| `$6012…` | pacotes: nametable 64 B (banner, desenhado nas linhas 1–2) + nº de tiles + (slot, 16 B) por tile (até `$6E10`) |
| `$6E10` | tabela + textos do Menu Principal (origem da cópia para `$0280`) e "Falta EDFC/OVL*.BIN" (80 B, cheio) |
| `$6E60` | paletas dos temas (9 × 16 cores, `banner_art.palette16`) |
| `$6F00` | loader (paleta + tiles; usa `$9A–$9D`), até `$6FB3` |
| `$6FB8` | `OVL_CUR` (overlay carregado; 0 no boot), `V_MSEL` (item do Menu Principal), `OVL_WANT` |
| `$6FC0` | variáveis das listas (16 B, `fav_runtime.VARS_SRC`; `V_DIR` = ESQ/DIR do menu do jogo) |
| `$6FD0` | cache das listas/resultados: 32 × 32 B (listas: nome 27 + NUL, contador 28–30, slot 31; busca: nome 26 + NUL, profundidade 27, cluster da pasta 28–30, índice 31; entrada 31 = texto digitado) |
| `$73D0` | **residente** (`resident_runtime.py`): `DISPATCH`, `SELT`, `R_INFO`/`R_MENU`/`R_FAVADD`, `LAUNCH`, `START`, `MMENU`, `OVL`, `CALLI`, `SETUP`…, `SHOWMSG`/`PUTS`, `ENTRY`, imagem do trampolim (até ~`$7850`) |
| `OVL_BASE` (~`$78AE`) | **área de overlay** (até `$7FDF`; a busca vai até `$7FFF`): o módulo carregado do SD (`OVL_BASE` = fim do residente; o loader copia exatamente `OVL_BASE–$7FFF`) |
| `$7FE0` | rascunho: cópia de `$0300–$030F` durante `$BC71` (módulo ART) |

### Overlays (`resident_runtime.py`)
O banco `$0B` não comporta tudo, então capas, favoritos, recentes e busca são **módulos** em arquivos
`EDFC/OVLART.BIN`, `OVLFAV.BIN`, `OVLREC.BIN`, `OVLFIND.BIN`, `OVLSCAN.BIN`, montados para `OVL_BASE` e gerados por
`install_banner_theme.py` junto com o `OS.BIN`. Cabeçalho: `'O'`, id, build id (2 bytes, hash dos
símbolos do residente — um arquivo de outra build é recusado), depois a tabela de `JMP`s.
`OVL(id)`: se `OVL_CUR` ≠ id, acha o arquivo em `/EDFC` (`$9DC7`), desliga a renderização, lê os setores
com `$9541` para a CHR `$1000` (não usada pelo OS), copia do PPU para o banco `$0B`, confere o cabeçalho,
religa a tela e reabre a pasta do navegador. Sem o arquivo: capas e ESQ/DIR somem (menu normal do OS);
as listas/busca mostram "Falta EDFC/OVL*.BIN". Os módulos não chamam `SETUP` (o residente chama antes de
`OVL`); chamadas ao OS usam `JSR CALLI` + 3 bytes (destino, A), que preserva X/Y.

### Menu Principal, Recentes e Busca
- **Boot**: `BOOT` sempre pede um tema e o primeiro `IDLE` o aplica. A primeira passada do laço ocioso do
  navegador após ligar ou reset (`$D91E` → `BJOY`: trampolim ausente em `$0100` ou marcador `$01AF` ≠ `$A5`) grava START em `$0484` e trava a leitura da NMI
  (`$A2 = 1`); o laço trata como START → `START` (libera `$A2`) copia a tabela para `$0280` e chama `$CB50`.
  (Antes o `IDLE` gravava o START: ele roda primeiro numa espera de botão do boot (`$9F82`), então o START
  fechava o aviso A7 "configurações recriadas" ou era sobrescrito pela NMI/OS.)
- **`MMENU`** (no `$CB68`): restaura o cursor (`V_MSEL`), ajusta o espaçamento do `$CA0D`, chama;
  0 Lista de jogos e cancelar → `$FF` (fecha); 1 Busca, 2 Favoritos, 3 Recentes → módulo, depois `$847C`,
  empilha de novo os argumentos e reabre; 4–8 → devolve 0–4 para o despacho original do OS.
- **Recentes** (`OVLREC`): `RECENTS.DAT` no mesmo formato do `FAVS.DAT` + contador de 24 bits nos bytes
  271–273. `RECADD` (antes de todo início de jogo: `$D5B1`, favoritos, a própria lista) grava no slot do mesmo
  jogo, senão no primeiro vazio, senão no de menor contador, com contador = maior + 1 (uma gravação por
  início). A tela ordena o cache pelo contador (bolha).
- **Favoritos** (`OVLFAV`): confirmar devolve C=1 com o registro em `*$046A`; o residente (`LAUNCH_GO`)
  carrega `OVLREC`, grava em Recentes e inicia.
- **Busca**: dois módulos encadeados pelo `MMENU`: `OVLFIND` E0 (teclado novo) → `OVLSCAN` E0 (varredura)
  → `OVLFIND` E1 (resultados; voltar → E2, teclado com a consulta). Teclado 10×4, consulta até 18
  caracteres; consulta, tamanho e cursor ficam na entrada 31 do cache (sobrevivem à troca de módulo).
  Varre **todas as pastas em largura** a partir da raiz: fila (anel de 128 × 4 B: cluster 24 bits +
  profundidade) num buffer de 512 B do heap do OS (malloc/free), cada pasta lida uma única vez.
  A **raiz** vai pelo OS (`$8DA9` + `$923B` por entrada: ele conhece a raiz fixa do FAT16). As
  **subpastas** são lidas direto: cadeia de clusters (`$969A`, `$C404`, fim de cadeia FAT16/FAT32),
  setores com `$AAD5` para `$0500` e entradas de 32 B analisadas no módulo (nome longo = byte baixo dos
  caracteres LFN; sem LFN, os 11 caracteres "NOME    EXT" como o OS mostra), com o mesmo filtro e índice do
  `$8DA9` (sem `$E5`, `.`, oculto/rótulo; para em `$FE`). É ~10× mais rápido que `$923B`, que relê e remonta
  cada entrada. Extensão conferida no nome 8.3 da entrada (`NES`/`FDS`) antes de comparar; a comparação
  procura a 1ª letra da consulta e só então compara o resto. **Ponteiros passados ao OS** (o cluster do
  `$C404`, `find_runtime.W_CL` = `$024A`) têm de estar na RAM interna: o OS roda com o banco 8 mapeado.
  Medido no emulador com 5.000 nomes do cartão real: ~4,8 milhões de instruções (~11 s de CPU) + ~1.550
  setores. Só `.nes`/`.fds`, primeiros 47 caracteres, sem diferenciar maiúsculas; `EDFC` e níveis abaixo
  de 10 ficam de fora; até 31 resultados (nome 26 + NUL, profundidade, cluster da pasta, índice).
  Progresso ("Pastas lidas: X de Y", achados): 2 linhas (64 B) escritas direto no PPU no vblank, como a barra
  de status do OS (`$A2 = 1` durante a cópia), uma vez por pasta e por achado; cancelar (`$0484`) interrompe.
  Escolher um resultado: `$8278` = pasta, `$8DA9` + `$C67D` (como o navegador), `$8275` = profundidade com
  as seleções dos níveis de cima zeradas (`*$0456`, para o "voltar"); confere com `$923B` se o índice tem o
  mesmo nome (senão procura o nome na pasta), posição em `*$0466` → `$8276`, redesenho (`$04D4`), fecha.

### Capas (`art_runtime.py`, módulo ART)
Trampolim copiado para `$0100` (mapeia banco 8 só durante chamadas ao OS e volta para `$0B`).
Fluxo: registro → cluster → lê setores 0–4 da ROM para o PPU `$1000` → CRC-32 dos bytes 512–2559
(lidos de volta do PPU) → `EDFC/ARTS/<CRC>.BIN` → 4 setores para `$1000` → metadados em `$1600`
→ OAM em `$0200` + DMA → sprites 8×16 (`$2000=$A0`, `$2001=$1E`); ao sair `$2000=$80`, `$2001=$0A`.
Formato do arquivo: ver docstring de `nes_art.py`. A tabela de padrões `$1000` não é usada pelo OS.

### Favoritos (`fav_runtime.py`, módulos FAV/REC)
Arquivo `EDFC/FAVS.DAT` (16 KB) criado no PC e enviado no zip — o console **nunca cria, aumenta ou
renomeia arquivo** (sem escrita em FAT/diretório). Setor K = slot K: bytes 0–270 = cópia do registro
de `$BF16`; cluster 0 = vazio; byte 503 = K; 504–511 = `EDFCFAV1`. Antes de **toda** gravação o setor
é lido e o byte do slot + a assinatura conferidos (um LBA errado nunca grava em outro arquivo).
LBA do setor K: anda `K / spc` clusters com `$C404`, `$969A` e soma `K % spc`. Buffer de 512 B via
malloc do OS (recusa se `$0450` ≥ `$7C00`), liberado antes de voltar ao OS ou iniciar o jogo.
- **Favoritar** (menu do jogo): `$BF16` monta o registro, procura duplicado (mesmo cluster) e o primeiro
  slot livre, grava, mostra mensagem em tela cheia e pede redesenho (`$04D4`).
- **ESQ/DIR no menu do jogo** (`art_runtime` `STEP`): o `$CA0D` devolve `$FE`/`$FD`; o código anda `$8276`
  (dá a volta em `$04B8`), pula pastas (`*$0464`[índice] bit 7) e nomes que não terminam em `ES`/`DS`, grava o
  novo índice em `(sp),0` (o `$D556` usa esse valor para carregar/Info/Favoritar), chama `$C7E2(0)`, empilha de
  novo os argumentos do menu (`$03C1`, 3, 0) e reabre capa + menu.
- **Favoritos** (Menu Principal): lista em ordem de slot; cima/baixo, confirmar inicia o jogo (o residente grava
  em Recentes + `$B7AC`); SELECT zera o cluster do slot; cancelar volta ao menu.
- **Iniciar um favorito/recente** (`SELREC`): o registro do slot vai para `$0500` e o jogo é selecionado pelo
  próprio `$BF16` (save do jogo anterior gravado, save deste carregado), como no navegador. Só a chamada
  `JSR $BC71` em `$BFDA` (registro pelo índice da pasta aberta, que aqui não existe) é apontada, em tempo de
  execução e só para essa chamada, para um gancho em `$0610` que copia `$0500` para o registro, desempilha os
  3 bytes de argumento e devolve 0; o gancho e o `SELREC` restauram `$BC71` (v1.8.3 e antes chamavam `$B7AC`
  direto: o save não carregava).

### CHR e tela
Slots livres da fonte para tiles de banner: `$0B–$1E` e `$8B–$9F`; `$1F` = tile sólido da cor 1 (a cor
da faixa do banner; linhas 0 e 3 e células vazias do banner). A cor universal (`$3F00`) é o **fundo da
lista**, porque o NES também pinta a borda da TV com ela (antes ficava uma faixa escura nas laterais);
`banner_art._band_remap` move a cor da faixa para a cor 1 das paletas 1/2 abrindo mão da cor do banner
que menos aparece. Atributos `$63C0–$63C7 = $55`: linhas 0–3 usam a paleta 1 (= cores do tema:
sh, txt, hl); o banner fica nas linhas 1–2 porque a linha 0 some sob a borda de muitas TVs.

## 7. Emulador (`tools/edfc_emu.py`) — limitações
- Roda o decriptador real (página tirada de `EDFC-ORIGINAL/OS.BIN`).
- BIOS/SD falsos: monta FAT16 com nomes longos a partir de uma pasta; `sdRead` recarrega o LBA
  inicial a cada chamada (não continua streams).
- Sem tempo de PPU real (espera de vblank é acelerada), sem decaimento de OAM, sem conflitos
  de escrita durante a renderização. **Bugs de timing não aparecem aqui.**
- Pastas ocultas, `releases/` e `sdcard/` são ignoradas ao montar o cartão a partir do repo.
- RAM do cartucho zerada: o OS recria as configurações e mostra o aviso **A7** esperando um botão (no
  console isso só acontece quando as configurações se perdem). `boot_to_main_menu()` confirma o aviso.
- `tools/ppu_timing.py` (`TimedEmu`) é um modo com tempo aproximado (29.780/29.781 ciclos/quadro alternados
  — com um valor fixo a espera `BIT $2002` do OS fica presa em fase com a leitura de `$2002` da NMI —, vblank de
  2.273 ciclos, NMI real, leitura de `$2002` como no hardware, setor de SD = 16.000 ciclos) que lista
  escritas no PPU fora do vblank com a tela ligada (`emu.unsafe`). Segure botões ≥ 8 quadros nele: o OS
  só lê o controle depois de cada espera de vblank.
