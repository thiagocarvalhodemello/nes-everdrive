@AGENTS.md

Notas extras para Claude Code:
- O mesmo conteúdo serve para qualquer agente; mantenha as regras em `AGENTS.md`, não aqui.
- Ao analisar o OS, use o emulador para decriptar (snippet em `docs/dev/ARQUITETURA.md`, seção
  "Decriptar para analisar") e o disassembler `py65` — não confie em leitura estática do `OS.BIN`
  criptografado.
- Scripts temporários de análise: guarde fora do repo e não os nomeie como módulos da stdlib
  (ex.: um `dis.py` no mesmo diretório quebra o `numpy`).
