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

release_body = """## 🎮 EverDrive N8 / Famicom - Tradução Completa em Português do Brasil (PT-BR) + Seletor de Temas

Primeira versão oficial da tradução completa do Sistema Operacional do flashcart **EverDrive N8 / Famicom** (EDFC), agora com **Seletor de Temas em Tempo Real** no próprio console!

---

### ✨ Novidades da Atualização:
* 🎨 **Seletor de Temas Integrado em Tempo Real (In-System Hotkeys):**
  * Pressione **`SELECT` + `DIREITA`** a qualquer momento no menu para avançar para o próximo tema.
  * Pressione **`SELECT` + `ESQUERDA`** para retornar ao tema anterior.
  * Troca instantânea na tela da sua TV sem reiniciar o console!
* 🛠️ **Correção Definitiva de Gráficos ao Trocar de Tema:**
  * Rotina de carregamento atômico de paleta PPU que elimina qualquer corrupção de tiles/fontes ou necessidade de reiniciar o console.
* 💾 **Persistência de Tema ao Reiniciar / Ligar (SRAM & CONFIG.DAT):**
  * O último tema selecionado é memorizado na SRAM do cartucho e restaurado automaticamente ao reiniciar o console!
  * Arquivo container `CONFIG.DAT` (512 bytes) incluso para persistência contínua.
* 🕹️ **Aplicativo Interativo de Temas (`TEMAS.NES` / `EDFC/THEMES.NES`):**
  * ROM interativa de demonstração (Mapper 0 / NROM) pronta para ser executada diretamente do cartão SD.

---

### 📦 Arquivos Disponíveis para Download:

#### 1. `EDFC-PTBR-v1.16-CloneHardware.zip` (⭐ RECOMENDADO PARA CARTUCHOS CLONES)
* **Compatibilidade:** Cartuchos EverDrive N8 clone (incluindo revisões recentes do AliExpress como **`Drive-N8 V3.1 2024.07`** com Altera Cyclone II `EP2C5T144C8N` e CPLD MAX II `EPM240`).
* **Correções e recursos inclusos:**
  * Seletor de temas integrado em tempo real (`SELECT + DIREITA` / `SELECT + ESQUERDA`).
  * Aplicativo `TEMAS.NES` e `EDFC/THEMES.NES` inclusos para demonstração.
  * Sem tela cinza ao iniciar jogos (núcleos FPGA `.RBF` compatíveis restaurados).
  * Sem embaralhamento de pixels ou faixas azuis (sincronização perfeita de CHR-RAM).
  * Tradução 100% de menus, opções, Game Genie e mensagens de sistema.
  * Tabela `MAPROUT.BIN` e todos os 31 núcleos de mappers inclusos.
* **Como instalar:** Basta extrair o conteúdo do arquivo `.zip` diretamente na raiz do seu cartão MicroSD (deve ficar uma pasta `EDFC` na raiz).

---

#### 2. `EDFC-THEMES-AllVariants.zip` (🎨 PACOTE DE TEMAS E CORES)
* **Conteúdo:** 9 temas visuais completos prontos para uso (Clássico, Matrix, Cyberpunk 2077, Game Boy DMG, Âmbar Retrô CRT, Midnight Dark OLED, Crimson Famicom, Deep Ocean e Synthwave Sunset).
* Cada tema inclui seu `OS.BIN` pré-configurado e imagem de pré-visualização `preview.png`.
* Inclui a ROM `TEMAS.NES`.
* **Como usar:** Basta copiar o `OS.BIN` do tema desejado para a pasta `EDFC/` do seu cartão MicroSD caso queira deixá-lo como tema padrão ao ligar.

---

#### 3. `EDFC-PTBR-v1.26-OriginalHardware.zip` (PARA HARDWARE ORIGINAL KRIKZZ)
* **Compatibilidade:** EverDrive N8 original da Krikzz.
* **Características:**
  * Base oficial mais recente **v1.26** com tradução integral em PT-BR.
  * Menu de Balanço de Áudio de expansão (FDS, VRC6, VRC7, Namco-163, MMC5, Sunsoft-5B).
  * Suporte a Save States e teclas de atalho.
* **Como instalar:** Basta extrair o conteúdo do arquivo `.zip` diretamente na raiz do seu cartão MicroSD.

---

#### 4. `EDFC-PTBR-Standalone-TestROM.zip` (PARA TESTES EM EMULADORES)
* **Compatibilidade:** Mesen, FCEUX, RetroArch, Nestopia, etc.
* Contém a ROM `OS_PTBR_TEST.nes` e `TEMAS.NES` no formato iNES (Mapper 0) para testar a interface traduzida diretamente no PC.
"""

data = {
    'tag_name': tag,
    'target_commitish': 'main',
    'name': 'EverDrive N8 - Tradução PT-BR Completa + Seletor de Temas (v1.0.0)',
    'body': release_body,
    'draft': False,
    'prerelease': False
}

headers = {
    'Authorization': f'Bearer {token}',
    'Content-Type': 'application/json',
    'User-Agent': 'Python'
}

# Check if release exists
get_req = urllib.request.Request(
    f'https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}',
    headers={'Authorization': f'Bearer {token}', 'User-Agent': 'Python'}
)

rel = None
try:
    with urllib.request.urlopen(get_req) as resp:
        rel = json.loads(resp.read())
        print('Existing release found! ID:', rel['id'])
except Exception:
    pass

if rel is None:
    # Create release
    req = urllib.request.Request(
        f'https://api.github.com/repos/{owner}/{repo}/releases',
        data=json.dumps(data).encode('utf-8'),
        headers=headers
    )
    with urllib.request.urlopen(req) as resp:
        rel = json.loads(resp.read())
        print('Release created successfully! ID:', rel['id'])
else:
    # Update release
    patch_req = urllib.request.Request(
        f"https://api.github.com/repos/{owner}/{repo}/releases/{rel['id']}",
        data=json.dumps(data).encode('utf-8'),
        headers=headers,
        method='PATCH'
    )
    with urllib.request.urlopen(patch_req) as resp:
        rel = json.loads(resp.read())
        print('Release updated successfully! ID:', rel['id'])

upload_url = rel['upload_url'].split('{')[0]

# List of assets to upload
assets = [
    ('releases/EDFC-PTBR-v1.16-CloneHardware.zip', 'EDFC-PTBR-v1.16-CloneHardware.zip', 'application/zip'),
    ('releases/EDFC-THEMES-AllVariants.zip', 'EDFC-THEMES-AllVariants.zip', 'application/zip'),
    ('releases/EDFC-PTBR-v1.26-OriginalHardware.zip', 'EDFC-PTBR-v1.26-OriginalHardware.zip', 'application/zip'),
    ('releases/EDFC-PTBR-Standalone-TestROM.zip', 'EDFC-PTBR-Standalone-TestROM.zip', 'application/zip'),
]

# Delete old assets that will be re-uploaded
for existing_asset in rel.get('assets', []):
    asset_name = existing_asset['name']
    if any(name == asset_name for _, name, _ in assets):
        asset_id = existing_asset['id']
        del_req = urllib.request.Request(
            f"https://api.github.com/repos/{owner}/{repo}/releases/assets/{asset_id}",
            headers={'Authorization': f'Bearer {token}', 'User-Agent': 'Python'},
            method='DELETE'
        )
        try:
            with urllib.request.urlopen(del_req) as del_resp:
                print(f'Deleted old asset: {asset_name} (ID: {asset_id})')
        except Exception as e:
            print(f'Error deleting asset {asset_name}: {e}')

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
