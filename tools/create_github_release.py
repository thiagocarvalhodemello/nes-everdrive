#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de publicacao automatica de Releases no GitHub para o EverDrive N8 PT-BR.
Gerencia automaticamente o versionamento semantico (v1.0-ptbr -> v1.1-ptbr -> v1.2-ptbr...),
empacota os arquivos de release e faz upload de todos os assets no GitHub.
"""

import os
import sys
import json
import re
import argparse
import subprocess
import urllib.request

# Certifica que tools esta no path para importar package_releases
tools_dir = os.path.dirname(os.path.abspath(__file__))
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

from package_releases import package_all

def get_github_token():
    # Tenta obter token via git credential
    try:
        proc = subprocess.run(
            ['git', 'credential', 'fill'],
            input=b'protocol=https\nhost=github.com\n',
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        creds = dict(line.split('=', 1) for line in proc.stdout.decode().strip().splitlines() if '=' in line)
        if 'password' in creds:
            return creds['password']
    except Exception:
        pass
    
    # Fallback para variavel de ambiente
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if token:
        return token
        
    raise RuntimeError("Nao foi possivel obter o token do GitHub via 'git credential' nem via variavel de ambiente GITHUB_TOKEN.")

def get_existing_releases(owner, repo, token):
    req = urllib.request.Request(
        f'https://api.github.com/repos/{owner}/{repo}/releases',
        headers={
            'Authorization': f'Bearer {token}',
            'User-Agent': 'Python'
        }
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def calculate_next_version(releases):
    """Analisa as versoes existentes e determina o proximo incremento (ex: 1.0 -> 1.1 -> 1.2)."""
    versions = []
    for r in releases:
        tag = r.get('tag_name', '')
        m = re.match(r'v?(\d+)\.(\d+)(?:\.(\d+))?', tag)
        if m:
            major = int(m.group(1))
            minor = int(m.group(2))
            versions.append((major, minor))
            
    if not versions:
        return "1.0", "v1.0-ptbr"
        
    max_maj, max_min = max(versions)
    next_minor = max_min + 1
    version_str = f"{max_maj}.{next_minor}"
    tag_str = f"v{version_str}-ptbr"
    return version_str, tag_str

def ensure_git_tag(tag):
    """Cria a tag git localmente e envia para o repositorio remoto se necessario."""
    # Verifica se a tag ja existe no git local
    check_local = subprocess.run(['git', 'tag', '-l', tag], stdout=subprocess.PIPE, text=True)
    if tag not in check_local.stdout.splitlines():
        print(f"Criando tag git local: {tag}...")
        subprocess.run(['git', 'tag', '-a', tag, '-m', f"Release {tag}"], check=True)
    
    # Envia para origin
    print(f"Enviando tag {tag} para o repositorio remoto...")
    subprocess.run(['git', 'push', 'origin', tag], check=False)

def build_default_release_body(version_str):
    return f"""## 🎮 EverDrive N8 / Famicom - Tradução Completa PT-BR ({version_str})

Versão oficial atualizada da tradução completa do Sistema Operacional do flashcart **EverDrive N8 / Famicom** (EDFC) com **Banners Gráficos por Tema** (com banner padrão oficial **RETROGAMER POA** flame banner), **Seletor de Temas em Tempo Real** e **Persistência de Configuração na SRAM**!

---

### ✨ Novidades da Versão {version_str}:
* 🔥 **Banners Gráficos de Topo por Tema (Theme Headers):**
  * Banner padrão oficial: **RETROGAMER POA** flame banner (inspirado nos temas de referência do EverDrive MD customizado por opssemnik).
  * Cada um dos 9 temas possui seu banner gráfico dedicado de 256x16 pixels de alta fidelidade:
    1. **RETROGAMER POA** (Banner com chamas e logo flamejante)
    2. **PADRÃO** (Visual clássico EverDrive azul e branco)
    3. **SYNTHWAVE** (Grade retrô neon magenta e ciano)
    4. **OUTRUN** (Pôr do sol retrô anos 80 gradiente)
    5. **SEGA 16-BIT** (Estilo clássico arcade 16-bit)
    6. **RETROCHIMP** (Logo estilizado retrô)
    7. **MAD DRUGA** (Tema gamer verde e preto)
    8. **CYBERPUNK** (Visual futurista neon e sombras)
    9. **GAME BOY DMG** (Nostalgia clássica monocromática verde)
  * Espaço dedicado nas duas primeiras linhas da tela (16 pixels) com separação visual perfeita em relação à listagem de jogos (que se inicia na linha 3).
* 🎨 **Seletor de Temas Integrado em Tempo Real (In-System Hotkeys):**
  * Pressione **`SELECT` + `DIREITA`** a qualquer momento no menu para avançar para o próximo tema e banner.
  * Pressione **`SELECT` + `ESQUERDA`** para retornar ao tema anterior.
  * Troca instantânea na tela da sua TV sem reiniciar o console!
* 🛠️ **Arquitetura Glitch-Free e Sem Corrupção:**
  * Tiles dos banners alocados em slots CHR livres sem colidir com fontes, caracteres cirílicos ou mappers.
  * Atualização atômica direta de paleta PPU e CHR-RAM com sincronização de scanlines.
  * Margem de segurança de hardware estritamente abaixo do limite de $FC00 (CPLD MAX II BIOS safe boundary).
* 💾 **Persistência de Tema ao Reiniciar / Ligar (SRAM & CONFIG.DAT):**
  * O último tema e banner selecionado é gravado na SRAM do cartucho e restaurado automaticamente ao reiniciar o console!
  * Arquivo container `CONFIG.DAT` incluso para persistência contínua.
* 🕹️ **Aplicativo Interativo de Temas (`TEMAS.NES` / `EDFC/THEMES.NES`):**
  * ROM interativa de demonstração (Mapper 0 / NROM) inclusa para testes diretos no console ou emuladores.

---

### 📦 Arquivos Disponíveis para Download:

#### 1. `EDFC-PTBR-v1.16-CloneHardware.zip` (⭐ RECOMENDADO PARA CARTUCHOS CLONES)
* **Compatibilidade:** Cartuchos EverDrive N8 clone (incluindo revisões recentes do AliExpress como **`Drive-N8 V3.1 2024.07`** com Altera Cyclone II `EP2C5T144C8N` e CPLD MAX II `EPM240`).
* **Correções e recursos inclusos:**
  * Banners gráficos no topo da tela com o padrão RETROGAMER POA.
  * Seletor de temas integrado em tempo real (`SELECT + DIREITA` / `SELECT + ESQUERDA`).
  * Persistência de tema com restauração automática no boot.
  * Arquivo container `CONFIG.DAT` incluso.
  * ROM `TEMAS.NES` na raiz e `EDFC/THEMES.NES` inclusos.
  * Sem tela cinza ao iniciar jogos (núcleos FPGA `.RBF` compatíveis restaurados).
  * Sem embaralhamento de pixels ou faixas azuis (sincronização perfeita de CHR-RAM).
  * Tradução 100% de menus, opções, Game Genie e mensagens de sistema em português do Brasil.
  * Tabela `MAPROUT.BIN` e todos os 31 núcleos de mappers inclusos.
* **Como instalar:** Basta extrair o conteúdo do arquivo `.zip` diretamente na raiz do seu cartão MicroSD (deve ficar a pasta `EDFC` e os arquivos de inicialização na raiz).

---

#### 2. `EDFC-THEMES-AllVariants.zip` (🎨 PACOTE DE TEMAS E CORES)
* **Conteúdo:** 9 temas visuais completos prontos para uso com banners integrados e paletas personalizadas.
* Cada tema inclui seu `OS.BIN`, `CONFIG.DAT` e imagem de pré-visualização `preview.png`.
* Inclui a ROM `TEMAS.NES` e `CONFIG.DAT`.

---

#### 3. `EDFC-PTBR-v1.26-OriginalHardware.zip` (PARA HARDWARE ORIGINAL KRIKZZ)
* **Compatibilidade:** EverDrive N8 original da Krikzz.
* **Características:**
  * Base oficial mais recente **v1.26** com tradução integral em PT-BR.
  * Menu de Balanço de Áudio de expansão (FDS, VRC6, VRC7, Namco-163, MMC5, Sunsoft-5B).
  * Suporte a Save States e teclas de atalho.

---

#### 4. `EDFC-PTBR-Standalone-TestROM.zip` (PARA TESTES EM EMULADORES)
* Contém a ROM `OS_PTBR_TEST.nes`, `TEMAS.NES` e `CONFIG.DAT` para testes em emuladores de PC.
"""

def main():
    parser = argparse.ArgumentParser(description="Publicar Release no GitHub com versao incremental")
    parser.add_argument("--version", help="Versao exata da release (ex: 1.1)")
    parser.add_argument("--tag", help="Tag exata da release (ex: v1.1-ptbr)")
    parser.add_argument("--name", help="Titulo personalizado da release")
    parser.add_argument("--notes", help="Notas da versao / changelog personalizado")
    parser.add_argument("--skip-package", action="store_true", help="Nao empacotar novamente os arquivos .zip")
    args = parser.parse_args()

    owner = 'thiagocarvalhodemello'
    repo = 'nes-everdrive'

    print("Obtendo credenciais do GitHub...")
    token = get_github_token()

    print(f"Consultando releases existentes no repositorio {owner}/{repo}...")
    existing_releases = get_existing_releases(owner, repo, token)

    if args.version:
        version_str = args.version.lstrip("v").split("-")[0]
        tag_str = args.tag or f"v{version_str}-ptbr"
    elif args.tag:
        tag_str = args.tag
        m = re.match(r'v?(\d+\.\d+)', tag_str)
        version_str = m.group(1) if m else tag_str
    else:
        version_str, tag_str = calculate_next_version(existing_releases)

    release_title = args.name or f"EverDrive N8 - Tradução PT-BR Completa (v{version_str})"
    release_body = args.notes or build_default_release_body(version_str)

    print("=" * 65)
    print("  >>> PUBLICANDO NOVA RELEASE NO GITHUB")
    print(f"  Versao: {version_str}")
    print(f"  Tag:    {tag_str}")
    print(f"  Titulo: {release_title}")
    print("=" * 65)

    # 1. Empacotar arquivos de release se necessario
    if not args.skip_package:
        print("\nEmpacotando os 4 arquivos de release (.zip)...")
        package_all()

    # 2. Criar tag git e push
    try:
        ensure_git_tag(tag_str)
    except Exception as e:
        print(f"Aviso ao gerenciar tag git: {e}")

    # 3. Criar Release no GitHub
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'User-Agent': 'Python'
    }

    # Verifica se a tag ja existe em releases
    existing_rel = None
    for r in existing_releases:
        if r.get('tag_name') == tag_str:
            existing_rel = r
            break

    if existing_rel is not None:
        rel_id = existing_rel['id']
        print(f"\nAviso: Release com tag {tag_str} ja existe (ID: {rel_id}). Atualizando dados...")
        patch_data = {
            'name': release_title,
            'body': release_body,
            'target_commitish': 'main'
        }
        patch_req = urllib.request.Request(
            f"https://api.github.com/repos/{owner}/{repo}/releases/{rel_id}",
            data=json.dumps(patch_data).encode('utf-8'),
            headers=headers,
            method='PATCH'
        )
        with urllib.request.urlopen(patch_req) as resp:
            rel = json.loads(resp.read())
            print(f"Release atualizada com sucesso! ID: {rel['id']}")
    else:
        print(f"\nCriando nova Release no GitHub ({tag_str})...")
        create_data = {
            'tag_name': tag_str,
            'target_commitish': 'main',
            'name': release_title,
            'body': release_body,
            'draft': False,
            'prerelease': False
        }
        create_req = urllib.request.Request(
            f'https://api.github.com/repos/{owner}/{repo}/releases',
            data=json.dumps(create_data).encode('utf-8'),
            headers=headers
        )
        with urllib.request.urlopen(create_req) as resp:
            rel = json.loads(resp.read())
            print(f"Nova Release criada com sucesso! ID: {rel['id']}")

    print(f"URL da Release: {rel['html_url']}")
    upload_url = rel['upload_url'].split('{')[0]

    # 4. Upload dos assets
    assets = [
        ('releases/EDFC-PTBR-v1.16-CloneHardware.zip', 'EDFC-PTBR-v1.16-CloneHardware.zip', 'application/zip'),
        ('releases/EDFC-THEMES-AllVariants.zip', 'EDFC-THEMES-AllVariants.zip', 'application/zip'),
        ('releases/EDFC-PTBR-v1.26-OriginalHardware.zip', 'EDFC-PTBR-v1.26-OriginalHardware.zip', 'application/zip'),
        ('releases/EDFC-PTBR-Standalone-TestROM.zip', 'EDFC-PTBR-Standalone-TestROM.zip', 'application/zip'),
    ]

    # Deletar assets existentes se for atualizacao
    if existing_rel is not None:
        for old_asset in existing_rel.get('assets', []):
            old_name = old_asset['name']
            if any(name == old_name for _, name, _ in assets):
                old_id = old_asset['id']
                del_req = urllib.request.Request(
                    f"https://api.github.com/repos/{owner}/{repo}/releases/assets/{old_id}",
                    headers={'Authorization': f'Bearer {token}', 'User-Agent': 'Python'},
                    method='DELETE'
                )
                try:
                    with urllib.request.urlopen(del_req):
                        print(f"  Removido asset antigo: {old_name} (ID: {old_id})")
                except Exception as e:
                    print(f"  Erro ao remover asset {old_name}: {e}")

    print("\nFazendo upload dos novos assets...")
    for path, name, mime in assets:
        if not os.path.exists(path):
            print(f"  [ALERTA] Arquivo {path} nao encontrado, pulando...")
            continue
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
            print(f"  [OK] Upload concluido: {name} ({size} bytes)")

    print("\n" + "=" * 65)
    print("  [OK] RELEASE PUBLICADA COM SUCESSO!")
    print(f"  Versao: {version_str} ({tag_str})")
    print(f"  Link:   {rel['html_url']}")
    print("=" * 65)

if __name__ == "__main__":
    main()
