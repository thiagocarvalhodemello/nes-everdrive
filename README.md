# EverDrive N8 (EDFC) - Tradução PT-BR

Tradução completa para Português do Brasil (PT-BR) do Sistema Operacional do flashcart **EverDrive N8 / Famicom** (versão EDFC v1.16/v1.2x por Igor Golubovskiy / Krikzz).

## 🎮 Recursos da Tradução

- **Menus e Telas Traduzidos:**
  - **Menu Principal (`SELECT`):** Opções, Trapaças, Info Sistema, Info Mappers, Sobre.
  - **Menu de Opções:** Áudio, ordenação, reset para o jogo, inversão dos botões A/B, teclas de Save State.
  - **Menu de Arquivos:** Suporte contextual para arquivos `.NES`, `.FDS`, `.SAV` e `.TXT`.
  - **Visualizador de Informações da ROM:** Mapper, Tamanho PRG/CHR, Memória (RAM/Bateria) e Espelhamento.
  - **Códigos Game Genie / Trapaças:** Gestão de códigos e alternância de ativação.
  - **Informações do Dispositivo & Lista de Mappers Suportados:** Exibição detalhada de mappers suportados.
  - **Mensagens do Sistema e Erros:** Mensagens de leitura do cartão SD, formato inválido, inicialização e reset de configurações.

- **Fonte Customizada com Acentos:**
  - Foi desenhada e injetada uma tabela de caracteres no **Bank 0 (CHR)** para suporte completo a caracteres acentuados (`á`, `ã`, `â`, `é`, `ê`, `í`, `ó`, `õ`, `ô`, `ú`, `ç`, `Á`, `Ã`, `Ç`, `É`, `Í`, `Ó`, `Õ`, `Ú`), tanto para texto normal quanto destacado.

- **Compatibilidade:**
  - Re-encriptado e compatível nativamente com o hardware do EverDrive N8 original.
  - Acompanha ROM de teste no formato iNES (Mapper 0) compatível com emuladores (Mesen, FCEUX, etc.).

---

## 📁 Estrutura de Arquivos

```text
nes-everdrive/
├── EDFC/
│   ├── OS.BIN              # Sistema operacional traduzido e pronto para o SD
│   ├── OS_PTBR_TEST.nes    # ROM independente para testes em emuladores
│   ├── MAPROUT.BIN         # Tabela de roteamento de mappers
│   ├── mappers.png         # Tabela de referência dos mappers
│   ├── MAPS/               # Arquivos de mappers FPGA (.RBF)
│   └── SAVE/               # Diretório de Saves
├── translate_os_ptbr.py    # Script gerador da tradução e re-encriptador
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
O script lê a cópia original (`OS.BIN.bak` ou `OS.BIN`), insere os novos caracteres acentuados na fonte CHR, atualiza as tabelas de ponteiros e realoca as strings nos blocos livres de memória, gerando o `EDFC/OS.BIN` e a ROM `EDFC/OS_PTBR_TEST.nes`.

---

## 💾 Instalação no Cartão SD do EverDrive N8

1. Copie a pasta `EDFC` para a raiz do seu cartão SD (formatado em FAT16 ou FAT32).
2. Insira o cartão no EverDrive N8 e ligue o seu Nintendo / Famicom.
3. O sistema carregará diretamente em português.

---

## 📜 Licença e Créditos
- Software do EverDrive N8 desenvolvido originalmente por **Igor Golubovskiy (Krikzz)**.
- Modificação e tradução para Português do Brasil por **Thiago Carvalho de Mello**.
