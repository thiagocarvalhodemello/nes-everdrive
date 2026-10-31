# EverDrive N8 (EDFC) - Tradução Completa em Português do Brasil (PT-BR)

[![GitHub Releases](https://img.shields.io/github/v/release/thiagocarvalhodemello/nes-everdrive?style=flat-square)](https://github.com/thiagocarvalhodemello/nes-everdrive/releases)
[![License](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)

Tradução completa para Português do Brasil (PT-BR) do Sistema Operacional do flashcart **EverDrive N8 / Famicom** (por Igor Golubovskiy / Krikzz), com suporte nativo tanto para placas originais quanto para clones de hardware baseados em Altera Cyclone II e MAX II CPLD (revisão `V3.1 2024.07`).

---

## 🎮 Versões Disponíveis nas Releases

Disponibilizamos versões pré-empacotadas prontas para uso direto no cartão MicroSD na aba [**Releases**](https://github.com/thiagocarvalhodemello/nes-everdrive/releases):

### 1. [Versão Clone Hardware (Recomendada para Placas V3.1 e Cyclone II)](https://github.com/thiagocarvalhodemello/nes-everdrive/releases)
* **Arquivo:** `EDFC-PTBR-v1.16-CloneHardware.zip`
* **Compatibilidade:** Cartuchos EverDrive N8 clone (ex: AliExpress `Drive-N8 V3.1 2024.07` com Cyclone II `EP2C5T144C8N` e CPLD MAX II `EPM240`).
* **Características:**
  * 100% livre de tela cinza ao iniciar jogos.
  * Barramento de CHR-RAM 100% sincronizado (sem linhas azuis ou pixels/tiles embaralhados).
  * Tradução integral de todos os menus, opções, Game Genie e mensagens de sistema.
  * Conjunto completo de **31 núcleos FPGA (.RBF)** e tabela `MAPROUT.BIN` (512 bytes).
  * 100% de compatibilidade testada com mais de 3.500 jogos da biblioteca de NES/Famicom.

### 2. [Versão Hardware Original (Base Oficial v1.26)](https://github.com/thiagocarvalhodemello/nes-everdrive/releases)
* **Arquivo:** `EDFC-PTBR-v1.26-OriginalHardware.zip`
* **Compatibilidade:** EverDrive N8 original da Krikzz.
* **Características:**
  * Base oficial mais recente **v1.26** com tradução integral em PT-BR.
  * Menu de Balanço de Áudio de expansão (FDS, VRC6, VRC7, Namco-163, MMC5, Sunsoft-5B).
  * Suporte a Save States e teclas de atalho.
  * Patches de centralização de texto e versão customizada.

### 3. [ROM de Teste Standalone para Emuladores](https://github.com/thiagocarvalhodemello/nes-everdrive/releases)
* **Arquivo:** `EDFC-PTBR-Standalone-TestROM.zip`
* **Compatibilidade:** Mesen, FCEUX, RetroArch, Nestopia e qualquer emulador de NES (Mapper 0).
* Permite navegar pelo sistema e testar a interface traduzida diretamente no computador.

---

## 🌟 Recursos da Tradução

* **Menus e Telas Traduzidos:**
  * **Menu Principal (`SELECT`):** Opções, Trapaças (Game Genie), Info Sistema, Sobre.
  * **Menu de Opções:** Balanço Áudio, ordenação alfabética, reset para o jogo, inversão dos botões A/B, teclas de Save State.
  * **Menu de Arquivos:** Navegação rápida com suporte a `.NES`, `.FDS`, `.SAV` e `.TXT`.
  * **Visualizador de Informações da ROM:** Mapper, Tamanho PRG/CHR, Memória (RAM/Bateria) e Tipo de Espelhamento (Vertical/Horizontal/4-Screen).
  * **Códigos Game Genie:** Adição, edição e alternância rápida de códigos de trapaça.
  * **Informações do Dispositivo (Info Sistema):** Exibição da versão do OS, versão da BIOS, CPLD, data e hora.
  * **Tela Sobre:** Créditos completos em português.
  * **Mensagens do Sistema e Erros:** Formato inválido, erros de leitura do cartão SD, inicialização e restauração de padrões.

* **Fonte Customizada com Acentuação Completa:**
  * Injetada no **Bank 0 (CHR)** com suporte completo a caracteres acentuados (`á`, `ã`, `â`, `é`, `ê`, `í`, `ó`, `õ`, `ô`, `ú`, `ç`, `Á`, `Ã`, `Ç`, `É`, `Í`, `Ó`, `Õ`, `Ú`), tanto para texto comum quanto destacado/selecionado.

---

## 📦 Estrutura de Arquivos no Cartão MicroSD

Basta descompactar o arquivo `.zip` da release desejada diretamente na raiz do seu cartão MicroSD (formatado em FAT16 ou FAT32):

```text
MicroSD (Raiz)/
└── EDFC/
    ├── OS.BIN              # Sistema Operacional traduzido em PT-BR
    ├── MAPROUT.BIN         # Tabela de roteamento de mappers (512 bytes)
    ├── mappers.png         # Tabela de referência dos mappers suportados
    ├── MAPS/               # 31 núcleos FPGA (.RBF) compatíveis
    └── SAVE/               # Diretório para armazenamento dos saves de bateria
```

---

## 🛠️ Como Compilar ou Modificar o `OS.BIN`

Requisitos: **Python 3.x**

Para recriar ou alterar os textos da tradução:
```bash
python translate_os_ptbr.py
```
O script processa a base do OS, injeta os glifos acentuados na fonte CHR, atualiza as tabelas de ponteiros no PRG-ROM e aplica os patches de compatibilidade e centralização, gerando `EDFC/OS.BIN` e a ROM `EDFC/OS_PTBR_TEST.nes`.

---

## 📄 Licença e Créditos
* Software original do EverDrive N8 por **Igor Golubovskiy (Krikzz)**.
* Tradução para Português do Brasil e patches de compatibilidade de hardware por **Thiago Carvalho de Mello**.
