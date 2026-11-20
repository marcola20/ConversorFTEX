"""Acesso à pasta content\\kit-server do Kitserver (sider) do PES 2021."""
import os
import re
import shutil
import time
from dataclasses import dataclass, field

BACKUP_DIR = '_backup_conversor'


@dataclass
class Kit:
    pasta: str          # nome da subpasta (p1, p2, g1, ...)
    caminho: str        # caminho completo da subpasta
    kit_file: str       # valor de KitFile no config.txt
    em_uso: bool        # listado em order.ini / gk_order.ini

    @property
    def ftex(self):
        return os.path.join(self.caminho, self.kit_file + '.ftex')

    @property
    def rotulo(self):
        tipo = 'goleiro' if self.pasta.lower().startswith('g') else 'jogador'
        extra = '' if self.em_uso else ' (fora do order.ini)'
        return f'{self.pasta}  —  {self.kit_file}.ftex  ({tipo}){extra}'


@dataclass
class Time:
    id: int
    caminho_rel: str
    caminho: str
    kits: list = field(default_factory=list)

    @property
    def nome(self):
        return os.path.basename(self.caminho_rel)

    @property
    def liga(self):
        return os.path.dirname(self.caminho_rel)


def achar_kit_server(pasta):
    """Aceita a pasta do kit-server, a do sider ou a do jogo; devolve o caminho do kit-server ou None."""
    if not pasta or not os.path.isdir(pasta):
        return None
    candidatos = [pasta, os.path.join(pasta, 'kit-server'), os.path.join(pasta, 'content', 'kit-server')]
    try:
        for sub in os.listdir(pasta):
            candidatos.append(os.path.join(pasta, sub, 'content', 'kit-server'))
    except OSError:
        pass
    for c in candidatos:
        if os.path.isfile(os.path.join(c, 'map.txt')):
            return os.path.normpath(c)
    return None


def _ler_texto(caminho):
    with open(caminho, 'rb') as f:
        raw = f.read()
    for enc in ('utf-8-sig', 'cp1252'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode('utf-8', errors='replace')


def ler_config(caminho_config):
    cfg = {}
    for linha in _ler_texto(caminho_config).splitlines():
        linha = linha.split(';', 1)[0].strip()
        if '=' in linha:
            k, v = linha.split('=', 1)
            cfg[k.strip()] = v.strip()
    return cfg


def _ler_lista(caminho):
    if not os.path.isfile(caminho):
        return []
    return [l.strip() for l in _ler_texto(caminho).splitlines() if l.strip() and not l.strip().startswith(';')]


def carregar_kits(t):
    em_uso = set(_ler_lista(os.path.join(t.caminho, 'order.ini')) + _ler_lista(os.path.join(t.caminho, 'gk_order.ini')))
    kits = []
    for sub in sorted(os.listdir(t.caminho)):
        d = os.path.join(t.caminho, sub)
        cfg_path = os.path.join(d, 'config.txt')
        if sub == BACKUP_DIR or not os.path.isfile(cfg_path):
            continue
        kit_file = ler_config(cfg_path).get('KitFile', '').strip()
        if not kit_file:
            continue
        kits.append(Kit(sub, d, kit_file, sub in em_uso))
    kits.sort(key=lambda k: (not k.em_uso, k.pasta.lower().startswith('g'), k.pasta.lower()))
    t.kits = kits
    return kits


def carregar_times(kit_server):
    times = []
    vistos = set()
    for linha in _ler_texto(os.path.join(kit_server, 'map.txt')).splitlines():
        m = re.match(r'\s*(\d+)\s*,\s*"(.+?)"', linha)
        if not m:
            continue
        rel = m.group(2).replace('/', '\\')
        caminho = os.path.join(kit_server, *rel.split('\\'))
        if os.path.isdir(caminho) and rel.lower() not in vistos:
            vistos.add(rel.lower())
            times.append(Time(int(m.group(1)), rel, caminho))
    times.sort(key=lambda t: (t.liga.lower(), t.nome.lower()))
    return times


def fazer_backup(kit):
    """Copia o .ftex atual para a pasta de backup do time. Devolve o caminho ou None se não existia."""
    if not os.path.isfile(kit.ftex):
        return None
    pasta = os.path.join(os.path.dirname(kit.caminho), BACKUP_DIR, kit.pasta)
    os.makedirs(pasta, exist_ok=True)
    destino = os.path.join(pasta, f'{kit.kit_file}_{time.strftime("%Y%m%d-%H%M%S")}.ftex')
    shutil.copy2(kit.ftex, destino)
    return destino


def listar_backups(kit):
    pasta = os.path.join(os.path.dirname(kit.caminho), BACKUP_DIR, kit.pasta)
    if not os.path.isdir(pasta):
        return []
    arqs = [os.path.join(pasta, f) for f in os.listdir(pasta)
            if f.startswith(kit.kit_file + '_') and f.endswith('.ftex')]
    return sorted(arqs)


def restaurar_ultimo_backup(kit):
    backups = listar_backups(kit)
    if not backups:
        return None
    ultimo = backups[-1]
    shutil.copy2(ultimo, kit.ftex)
    os.remove(ultimo)
    return ultimo
