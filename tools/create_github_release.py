import urllib.request
import json
import subprocess
import os

proc = subprocess.run(['git', 'credential', 'fill'], input=b'protocol=https\nhost=github.com\n', stdout=subprocess.PIPE)
creds = dict(line.split('=', 1) for line in proc.stdout.decode().strip().splitlines() if '=' in line)
token = creds.get('password')

owner = 'thiagocarvalhodemello'
repo = 'nes-everdrive'
tag = 'v1.0.0-ptbr'

release_body = """## 🎮 EverDrive N8 / Famicom - Tradução Completa em Português do Brasil (PT-BR)

Primeira versão oficial da tradução completa do Sistema Operacional do flashcart **EverDrive N8 / Famicom** (EDFC).

---

### 📦 Arquivos Disponíveis para Download:

#### 1. `EDFC-PTBR-v1.16-CloneHardware.zip` (⭐ RECOMENDADO PARA CARTUCHOS CLONES)
* **Compatibilidade:** Cartuchos EverDrive N8 clone (incluindo revisões recentes do AliExpress como **`Drive-N8 V3.1 2024.07`** com Altera Cyclone II `EP2C5T144C8N` e CPLD MAX II `EPM240`).
* **Correções inclusas:**
  * Sem tela cinza ao iniciar jogos (núcleos FPGA `.RBF` compatíveis restaurados).
  * Sem embaralhamento de pixels ou faixas azuis (sincronização perfeita de CHR-RAM).
  * Tradução 100% de menus, opções, Game Genie e mensagens de sistema.
  * Tabela `MAPROUT.BIN` e todos os 31 núcleos de mappers inclusos.
* **Como instalar:** Basta extrair o conteúdo do arquivo `.zip` diretamente na raiz do seu cartão MicroSD (deve ficar uma pasta `EDFC` na raiz).

---

#### 2. `EDFC-PTBR-v1.26-OriginalHardware.zip` (PARA HARDWARE ORIGINAL KRIKZZ)
* **Compatibilidade:** EverDrive N8 original da Krikzz.
* **Características:**
  * Base oficial mais recente **v1.26** com tradução integral em PT-BR.
  * Menu de Balanço de Áudio de expansão (FDS, VRC6, VRC7, Namco-163, MMC5, Sunsoft-5B).
  * Suporte a Save States e teclas de atalho.
* **Como instalar:** Basta extrair o conteúdo do arquivo `.zip` diretamente na raiz do seu cartão MicroSD.

---

#### 3. `EDFC-PTBR-Standalone-TestROM.zip` (PARA TESTES EM EMULADORES)
* **Compatibilidade:** Mesen, FCEUX, RetroArch, Nestopia, etc.
* Contém a ROM `OS_PTBR_TEST.nes` no formato iNES (Mapper 0) para testar a interface traduzida diretamente no PC.
"""

data = {
    'tag_name': tag,
    'target_commitish': 'main',
    'name': 'EverDrive N8 - Tradução PT-BR Completa (v1.0.0)',
    'body': release_body,
    'draft': False,
    'prerelease': False
}

req = urllib.request.Request(
    f'https://api.github.com/repos/{owner}/{repo}/releases',
    data=json.dumps(data).encode('utf-8'),
    headers={
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'User-Agent': 'Python'
    }
)

with urllib.request.urlopen(req) as resp:
    rel = json.loads(resp.read())
    print('Release created successfully! ID:', rel['id'])
    print('URL:', rel['html_url'])
    upload_url = rel['upload_url'].split('{')[0]

assets = [
    ('releases/EDFC-PTBR-v1.16-CloneHardware.zip', 'EDFC-PTBR-v1.16-CloneHardware.zip', 'application/zip'),
    ('releases/EDFC-PTBR-v1.26-OriginalHardware.zip', 'EDFC-PTBR-v1.26-OriginalHardware.zip', 'application/zip'),
    ('releases/EDFC-PTBR-Standalone-TestROM.zip', 'EDFC-PTBR-Standalone-TestROM.zip', 'application/zip'),
]

for path, name, mime in assets:
    with open(path, 'rb') as f:
        content = f.read()
    up_req = urllib.request.Request(
        f'{upload_url}?name={name}',
        data=content,
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': mime,
            'User-Agent': 'Python'
        }
    )
    with urllib.request.urlopen(up_req) as up_resp:
        res_json = json.loads(up_resp.read())
        size = res_json['size']
        print(f'Uploaded asset: {name} ({size} bytes)')

print('All assets uploaded successfully!')
