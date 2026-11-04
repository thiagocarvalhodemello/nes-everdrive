# Histórico de bugs (e o que eles ensinam)

| Versão | Sintoma | Causa | Correção | Lição |
| :--- | :--- | :--- | :--- | :--- |
| v1.3 | Trocar tema às vezes corrompia o cartão SD (precisava formatar) | Tema aplicado **dentro da NMI**: mudava `$4400/$4401` sem restaurar (no meio de sequências de SD/banco do OS) e gravava em `$7BA6`/`$7C00`, dentro do **heap** do OS (buffers de setor) | v1.4: NMI só detectava o atalho; aplicação no laço ocioso; assinatura em `$7FF8` | Nada de trabalho na NMI; nunca escrever no heap (banco 8 `$6000–$7FF7`) |
| v1.3 | Tema salvo não voltava direito | No boot o hook rodava com o banco `$0A` mapeado e gravava a assinatura nele | Mapear banco 8 explicitamente no `BOOT` | Nunca assuma qual banco está em `$6000` |
| v1.4 | Lista de jogos corrompida até reiniciar | Trampolim das capas em `$0300` = **DATA do OS** (tabelas e variáveis da listagem) | v1.5: trampolim em `$0100`, scratch em `$0200` | Medir uso real de RAM antes de chamar de "livre"; "zerado no reset" não significa "sem uso" |
| v1.5 (dev) | Página 3 ainda mudava ao abrir o menu do jogo | `$BC71` grava o nome 8.3 em **buffer+`$100`** (11 bytes): buffer de 256 B transborda | Salvar/restaurar `$0300–$030F` em volta da chamada | Funções do OS podem escrever além do que o buffer "parece" ter; teste com verificação de RAM |
| v1.4 (dev) | Lista mostrava arquivos da pasta `ARTS` após ver uma capa | Buscas `$AD3B/$9DC7` mudam o diretório atual do FAT | Reabrir `$8278` (pasta do navegador) com `$8DA9` | Restaurar todo estado global que as chamadas do OS alteram |
| v1.4 (dev) | Pasta `ART` nunca encontrada | `$AD3B` compara exatamente 4 caracteres | Pasta `ARTS` | Ler a rotina antes de assumir semântica de nomes |
| v1.4 (dev) | Segunda leitura de setores recomeçava do início (no emulador) | O SD falso do emulador recarrega o LBA a cada chamada | Ler tudo numa única chamada `$9541` | Separar limitação do emulador de comportamento do hardware |
| v1.5 (dev) | Emulador mostrava lista lixo | Construtor FAT do emulador estourava diretórios grandes (`.artcache` com 13 mil nomes) | Diretórios dimensionados pelo nº de entradas; ignorar pastas ocultas | Quando o teste falha de forma estranha, desconfie primeiro do emulador |

Pendências conhecidas
- As correções de timing/PPU não são verificáveis no emulador; confirmar no hardware a cada release.
- Ao abrir o menu do jogo a tela fica apagada ~0,3 s (leitura + CRC de 2 KB via PPU).
- A janela do menu do jogo ainda se chama "Menu Arquivo" (string compartilhada com os menus de `.SAV`/`.TXT`).
