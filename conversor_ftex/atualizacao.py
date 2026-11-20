"""Verifica e instala novas versões publicadas nos Releases do GitHub."""
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

from . import __version__

REPOSITORIO = 'marcola20/ConversorFTEX'
PAGINA = f'https://github.com/{REPOSITORIO}'
API_ULTIMA = f'https://api.github.com/repos/{REPOSITORIO}/releases/latest'
NOME_EXE = 'ConversorFTEX.exe'


def _versao(texto):
    nums = []
    for parte in texto.strip().lstrip('vV').split('.'):
        digitos = ''.join(c for c in parte if c.isdigit())
        nums.append(int(digitos) if digitos else 0)
    return tuple(nums + [0] * (3 - len(nums)))


def verificar(timeout=6):
    """Devolve dict com a nova versão ou None se já está atualizado. Levanta exceção se falhar."""
    req = urllib.request.Request(API_ULTIMA, headers={'User-Agent': 'ConversorFTEX', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        rel = json.load(r)
    tag = rel.get('tag_name', '')
    if _versao(tag) <= _versao(__version__):
        return None
    exe = next((a for a in rel.get('assets', []) if a.get('name', '').lower().endswith('.exe')), None)
    return {'versao': tag.lstrip('vV'), 'pagina': rel.get('html_url', PAGINA + '/releases/latest'),
            'notas': rel.get('body') or '', 'url_exe': exe and exe.get('browser_download_url')}


def pode_autoatualizar():
    return getattr(sys, 'frozen', False) and sys.platform == 'win32'


def baixar_e_reiniciar(url_exe, progresso=None):
    """Baixa o novo .exe, troca pelo atual quando o programa fechar e abre de novo."""
    atual = sys.executable
    novo = atual + '.novo'
    req = urllib.request.Request(url_exe, headers={'User-Agent': 'ConversorFTEX'})
    with urllib.request.urlopen(req, timeout=30) as r, open(novo, 'wb') as f:
        total = int(r.headers.get('Content-Length') or 0)
        lido = 0
        while True:
            bloco = r.read(256 * 1024)
            if not bloco:
                break
            f.write(bloco)
            lido += len(bloco)
            if progresso and total:
                progresso(lido / total)
    if os.path.getsize(novo) < 1_000_000:
        os.remove(novo)
        raise RuntimeError('Download incompleto.')
    script = os.path.join(tempfile.gettempdir(), 'atualiza_conversorftex.cmd')
    with open(script, 'w', encoding='mbcs') as f:
        f.write('@echo off\r\n'
                f':espera\r\ntasklist /FI "PID eq {os.getpid()}" | find "{os.getpid()}" >nul && (timeout /t 1 >nul & goto espera)\r\n'
                f'move /Y "{novo}" "{atual}" >nul\r\n'
                f'start "" "{atual}"\r\n'
                'del "%~f0"\r\n')
    subprocess.Popen(['cmd', '/c', script], creationflags=0x08000000)  # CREATE_NO_WINDOW
