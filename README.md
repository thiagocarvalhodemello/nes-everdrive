# EverDrive N8 (EDFC) - Tradução Completa em Português do Brasil (PT-BR)

[![GitHub Releases](https://img.shields.io/github/v/release/thiagocarvalhodemello/nes-everdrive?style=flat-square)](https://github.com/thiagocarvalhodemello/nes-everdrive/releases)
[![License](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)

Tradução completa para Português do Brasil (PT-BR) do Sistema Operacional do flashcart **EverDrive N8 / Famicom** (por Igor Golubovskiy / Krikzz), para placas clone baseadas em Altera Cyclone II e MAX II CPLD (revisão `V3.1 2024.07`), com **9 temas com banner**, **menu do jogo com capa**, **busca**, **favoritos**, **jogos recentes** e troca de tema por um botão.

![Menu do jogo com capas](docs/screenshots/art_grid.png)

---

## 🎮 Downloads (Releases)

Na aba [**Releases**](https://github.com/thiagocarvalhodemello/nes-everdrive/releases) (versão atual: **v1.8**) há dois arquivos. Escolha **um** e extraia na **raiz** do cartão MicroSD (FAT16/FAT32):

| Arquivo | Conteúdo |
| :--- | :--- |
| `EDFC-N8-PTBR-v1.8-com-capas.zip` | Sistema completo **+ 2.504 capas** (`EDFC/ARTS/`). |
| `EDFC-N8-PTBR-v1.8.zip` | Sistema completo, sem capas. |

As capas são identificadas pelo **conteúdo** da ROM (não pelo nome do arquivo), então funcionam com dumps padrão No-Intro/GoodNES. A versão para **hardware original Krikzz (base v1.26)** continua na [release v1.3](https://github.com/thiagocarvalhodemello/nes-everdrive/releases/tag/v1.3-ptbr).

---

## 📋 Menu Principal

Ao ligar, o console abre o **Menu Principal**; **START** no navegador abre de novo.

![Menu Principal](docs/screenshots/menu_principal.png)

**Lista de jogos** (fecha o menu e mostra a pasta) · **Busca** · **Favoritos** · **Recentes** · Opções · Trapaças · Info Sistema · Info Mappers · Sobre

---

## 🕹️ Controles no Navegador de Arquivos

| Botão | Ação |
| :--- | :--- |
| **A / B** (confirmar) | Abre a pasta, ou o **menu do jogo**: capa + `Carregar jogo` + `Info da ROM` + `Favoritar` |
| **SELECT** | Próximo tema (9 temas, em ciclo); o tema fica salvo e volta no próximo boot |
| **START** | **Menu Principal** |
| **ESQ / DIR** | Página anterior / próxima da lista; **dentro do menu do jogo**, jogo anterior / próximo |

O botão de confirmar segue a opção "inverter A/B" do menu Opções.

---

## 🖼️ Menu do Jogo e Capas

Ao confirmar um jogo abre o menu com a capa (64×96 px, 48 sprites 8×16, 12 cores) ao lado:

![Menu do jogo](docs/screenshots/art_2_legend_of_zelda_the_usa_rev_1.png)

* **Carregar jogo** inicia o jogo; **Info da ROM** mostra mapper, PRG/CHR, bateria e espelhamento (também com a capa).
* **ESQ / DIR** troca para o jogo anterior / próximo da pasta sem fechar o menu (pula pastas e arquivos que não são `.nes`/`.fds`, dá a volta no fim da lista); a capa e o nome no rodapé acompanham.
* **Identificação pelo conteúdo:** o console calcula o CRC-32 dos bytes 512–2559 da ROM e procura `EDFC/ARTS/<CRC>.BIN`. Traduções, revisões e a maioria dos hacks mostram a capa do jogo original.
* **Seguro:** a leitura usa a API de arquivos do próprio OS no laço principal, direto para a CHR-RAM; nada é gravado no cartão e nenhuma memória do OS é alterada.
* **Sem capa?** O menu funciona normalmente, só sem a imagem.

#### Gerar capas para a sua coleção (PC)
```bash
# baixa as capas do libretro-thumbnails + DAT No-Intro e converte para o formato NES
python tools/art_pack.py build                        # -> releases/EDFC-ARTPACK-NES.zip
# identifica cada ROM do cartão (CRC No-Intro, ou nome GoodNES/No-Intro) e grava EDFC/ARTS
python tools/art_pack.py install --sd E:\ --dry-run   # relatório
python tools/art_pack.py install --sd E:\
```
Capas: [libretro-thumbnails](https://github.com/libretro-thumbnails/Nintendo_-_Nintendo_Entertainment_System), direitos dos respectivos detentores.

---

## ⭐ Favoritos

| | |
| :---: | :---: |
| ![Favoritar no menu do jogo](docs/screenshots/favoritos_menu_jogo.png)<br>**Favoritar** no menu do jogo | ![Lista de favoritos](docs/screenshots/favoritos_lista.png)<br>**START → Favoritos** |

* Até **32 jogos**, mostrados pelo nome, na ordem em que foram adicionados.
* Na lista: **cima/baixo** escolhe, **confirmar** inicia o jogo, **SELECT** remove, **cancelar** volta.
* Ficam no arquivo `EDFC/FAVS.DAT` (16 KB, já vem no zip). O console só regrava setores dentro desse
  arquivo, conferindo uma assinatura antes de cada gravação — nunca cria arquivos nem mexe na FAT.
* **Ao atualizar o sistema**, não substitua o `FAVS.DAT` do cartão se quiser manter a sua lista.

---

## 🕘 Recentes

![Recentes](docs/screenshots/recentes.png)

* Os últimos **32 jogos** iniciados, do mais recente para o mais antigo. Vale para **Carregar jogo**,
  para os favoritos e para a própria lista.
* **Confirmar** inicia o jogo, e **SELECT** tira o jogo da lista.
* Ficam no `EDFC/RECENTS.DAT`, com a mesma proteção do `FAVS.DAT`: cada início de jogo regrava **um**
  setor desse arquivo. Ao atualizar, não substitua o arquivo do cartão.

---

## 🔍 Busca

| | | |
| :---: | :---: | :---: |
| ![Teclado da busca](docs/screenshots/busca_teclado.png)<br>**Menu Principal → Busca** | ![Progresso](docs/screenshots/busca_progresso.png)<br>**Buscando** | ![Resultados](docs/screenshots/busca_resultados.png)<br>**Resultados** |

* Teclado na tela: o **direcional** escolhe a letra, **confirmar** digita, **SELECT** apaga, **START** busca
  e **cancelar** volta.
* Procura o trecho digitado em **qualquer parte do nome**, sem diferenciar maiúsculas, em **todas as pastas**
  do cartão (até 10 níveis; a pasta `EDFC` fica de fora). Só entram jogos `.nes`/`.fds` (até 31 resultados).
* Enquanto busca, mostra **quantas pastas já leu de quantas achou** e quantos jogos encontrou;
  **cancelar** interrompe e mostra o que já achou.
* Ao confirmar um resultado, o navegador abre a pasta do jogo e para em cima dele; **cancelar** volta para as
  pastas de cima normalmente.
* Só lê o cartão.

---

## 🎨 Temas

9 temas com banner próprio, trocados com **SELECT** (capturas do emulador, `python tools/capture_theme_screenshots.py`):

| | | |
| :---: | :---: | :---: |
| ![RETROGAMER POA](docs/screenshots/theme0_retrogamer_poa.png)<br>**RETROGAMER POA** | ![PADRÃO](docs/screenshots/theme1_padrao.png)<br>**PADRÃO** | ![SYNTHWAVE](docs/screenshots/theme2_synthwave.png)<br>**SYNTHWAVE** |
| ![OUTRUN](docs/screenshots/theme3_outrun.png)<br>**OUTRUN** | ![16-BIT](docs/screenshots/theme4_16_bit.png)<br>**16-BIT** | ![RETROCHIMP](docs/screenshots/theme5_retrochimp.png)<br>**RETROCHIMP** |
| ![MADDRUGAMERS](docs/screenshots/theme6_maddrugamers.png)<br>**MADDRUGAMERS** | ![CYBERPUNK](docs/screenshots/theme7_cyberpunk.png)<br>**CYBERPUNK** | ![GAME BOY](docs/screenshots/theme8_game_boy.png)<br>**GAME BOY** |

Os banners são gerados por código (`tools/banner_art.py`, prévia em `docs/themes/banners/`). O tema escolhido é salvo na RAM do cartucho (banco 8, `$7FF8`) e restaurado ao reiniciar.

---

## 🌟 Recursos da Tradução

* **Menus e telas traduzidos:** Menu Principal, Opções (balanço de áudio, ordenação, reset para o jogo, inversão A/B, save states), menu do jogo, Info da ROM, Trapaças (Game Genie), Info Sistema, Info Mappers, Sobre e mensagens de erro.
* **Fonte com acentuação completa** (`á ã â é ê í ó õ ô ú ç Á Ã Ç É Í Ó Õ Ú`), em texto comum e destacado.
* **31 núcleos FPGA (.RBF)** e tabela `MAPROUT.BIN` compatíveis com as placas clone (sem tela cinza, sem tiles embaralhados).

---

## 📦 Estrutura no Cartão MicroSD

```text
MicroSD (Raiz)/
└── EDFC/
    ├── OS.BIN              # Sistema Operacional PT-BR (temas, menu do jogo, capas)
    ├── MAPROUT.BIN         # Tabela de roteamento de mappers (512 bytes)
    ├── OVL*.BIN            # Módulos do sistema (capas, favoritos, recentes, busca): copie junto com o OS.BIN
    ├── FAVS.DAT            # Favoritos (32 slots, 16 KB)
    ├── RECENTS.DAT         # Jogos recentes (32 slots, 16 KB)
    ├── mappers.png         # Tabela de referência dos mappers suportados
    ├── MAPS/               # 31 núcleos FPGA (.RBF)
    ├── SAVE/               # Saves de bateria (obrigatória)
    └── ARTS/               # Capas dos jogos (opcional)
```

---

## 🛠️ Como Compilar o `OS.BIN`

Requisitos: **Python 3.x** (+ Pillow e NumPy para as capas).

```bash
python translate_os_ptbr.py            # tradução sobre a base original
python tools/install_banner_theme.py   # OS.BIN + EDFC/OVL*.BIN (temas, menu, capas, listas, busca)
python tools/test_theme_safety.py      # testes no emulador do projeto
python tools/test_game_art.py
python tools/test_favorites.py         # favoritos e recentes
python tools/test_search.py
```

Guia para quem for manter o projeto (pessoas ou agentes de IA): [`AGENTS.md`](AGENTS.md), com arquitetura, receitas e histórico de bugs em [`docs/dev/`](docs/dev/).

---

## 📄 Licença e Créditos
* Software original do EverDrive N8 por **Igor Golubovskiy (Krikzz)**.
* Tradução para Português do Brasil e patches de compatibilidade de hardware por **Thiago Carvalho de Mello**.
