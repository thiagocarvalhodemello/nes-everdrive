# EverDrive N8 (EDFC) - Tradução PT-BR (v1.26 PT-BR v1)

Tradução completa para Português do Brasil (PT-BR) do Sistema Operacional do flashcart **EverDrive N8 / Famicom** rebaseada na versão oficial mais recente **v1.26** (por Igor Golubovskiy / Krikzz).

## 🎮 Recursos da Tradução

- **Menus e Telas Traduzidos:**
  - **Menu Principal (`SELECT`):** Opções, Trapaças, Info Sistema, Sobre.
  - **Menu de Opções:** Balanço Áudio, ordenação, reset para o jogo, inversão dos botões A/B, teclas de Save State.
  - **Novo Menu Balanço Áudio (v1.26):** Ajuste de volume de áudio para chips de expansão (FDS, VRC6, VRC7, Namco-163, MMC5, Sunsoft-5B).
  - **Menu de Arquivos:** Suporte contextual para arquivos `.NES`, `.FDS`, `.SAV` e `.TXT`.
  - **Visualizador de Informações da ROM:** Mapper, Tamanho PRG/CHR, Memória (RAM/Bateria) e Espelhamento.
  - **Códigos Game Genie / Trapaças:** Gestão de códigos e alternância de ativação.
  - **Informações do Dispositivo (Info Sistema):** Exibição da versão customizada `OS: 1.26 PT-BR v1`, versão da BIOS, CPLD, data e hora.
  - **Tela Sobre:** Créditos completos em português com identificação da versão `EDN8 - 1.26 PT-BR v1`.
  - **Mensagens do Sistema e Erros:** Mensagens de leitura do cartão SD, formato inválido, inicialização e reset de configurações.

- **Fonte Customizada com Acentos:**
  - Desenhada e injetada no **Bank 0 (CHR)** com suporte completo a caracteres acentuados (`á`, `ã`, `â`, `é`, `ê`, `í`, `ó`, `õ`, `ô`, `ú`, `ç`, `Á`, `Ã`, `Ç`, `É`, `Í`, `Ó`, `Õ`, `Ú`), tanto para texto normal quanto destacado.

- **Compatibilidade:**
  - Base oficial **v1.26** (sem encriptação de banco, executável nativamente em clones e originais).
  - Mappers consolidados atualizados (17 núcleos `.RBF` da v1.26) com nova tabela `MAPROUT.BIN`.
  - Acompanha ROM de teste no formato iNES (Mapper 0) compatível com emuladores (Mesen, FCEUX, etc.).

---

## 📁 Estrutura de Arquivos

```text
nes-everdrive/
├── EDFC/
│   ├── OS.BIN              # Sistema operacional traduzido (v1.26 PT-BR v1)
│   ├── OS.BIN.orig         # Cópia original oficial v1.26 (Krikzz)
│   ├── OS_PTBR_TEST.nes    # ROM independente para testes em emuladores
│   ├── MAPROUT.BIN         # Tabela de roteamento de mappers v1.26
│   ├── mappers.png         # Tabela de referência dos mappers v1.26
│   ├── MAPS/               # 17 núcleos FPGA atualizados (.RBF)
│   └── SAVE/               # Diretório de Saves
├── translate_os_ptbr.py    # Script gerador da tradução e montador do OS.BIN
├── tools/                  # Emulador interno de testes e rotinas de validação
└── README.md
```

---

## 🛠️ Como Gerar o `OS.BIN` Traduzido

Requisitos: **Python 3.x**

Para recriar ou modificar as strings da tradução:
```bash
python translate_os_ptbr.py
```
O script lê a cópia original (`EDFC/OS.BIN.orig`), insere os novos caracteres acentuados na fonte CHR, atualiza as tabelas de ponteiros, realoca as strings nos blocos livres de memória e aplica os patches de centralização e versão, gerando o `EDFC/OS.BIN` e a ROM `EDFC/OS_PTBR_TEST.nes`.

---

## 💾 Instalação no Cartão SD do EverDrive N8

1. Copie a pasta `EDFC` para a raiz do seu cartão SD (formatado em FAT16 ou FAT32).
2. Insira o cartão no EverDrive N8 e ligue o seu Nintendo / Famicom.
3. O sistema carregará diretamente em português.

---

## 📜 Licença e Créditos
- Software do EverDrive N8 desenvolvido originalmente por **Igor Golubovskiy (Krikzz)**.
- Modificação e tradução para Português do Brasil por **Thiago Carvalho de Mello**.
