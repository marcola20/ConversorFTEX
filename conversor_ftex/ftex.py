"""Leitura e gravação de texturas FTEX (Fox Engine) usadas pelo PES 2021.

Estrutura (versão 2.03):
  0x00  'FTEX', float versão, u16 formato, u16 largura, u16 altura, u16 profundidade,
        u8 nº de mipmaps, ... (resto do cabeçalho copiado como o jogo grava)
  0x40  tabela de mipmaps, 16 bytes cada: u32 offset, u32 tamanho, u32 tamanho no arquivo,
        u8 índice, u8 0, u16 nº de pedaços
  dados de cada mip: tabela de pedaços (u16 comprimido, u16 original, u32 offset) + pedaços
        zlib de até 16 KB (pedaço guardado sem compressão quando comprimido == original).
Formatos: 0 = RGBA, 2 = DXT1, 3 = DXT3, 4 = DXT5, 11 = BC7.
"""
import io
import os
import struct
import zlib

import numpy as np
from PIL import Image

from . import bc7

FORMATS = {0: 'RGBA', 2: 'DXT1', 3: 'DXT3', 4: 'DXT5', 11: 'BC7'}
_FOURCC = {2: b'DXT1', 3: b'DXT3', 4: b'DXT5'}
_HEADER_TAIL = bytes.fromhex('0c021100000000000000000003000000') + bytes(32)
CHUNK = 16384


class FtexError(Exception):
    pass


def read_info(path):
    with open(path, 'rb') as f:
        b = f.read(0x40)
    if b[:4] != b'FTEX':
        raise FtexError('Não é um arquivo FTEX.')
    fmt, w, h, depth, mips = struct.unpack('<HHHHB', b[8:17])
    return {'formato': fmt, 'nome_formato': FORMATS.get(fmt, f'desconhecido ({fmt})'),
            'largura': w, 'altura': h, 'mipmaps': mips}


def _mip0_data(b):
    off, size, _, _, _, nchunks = struct.unpack('<IIIBBH', b[0x40:0x50])
    if nchunks == 0:
        return b[off:off + size]
    data = bytearray()
    for i in range(nchunks):
        cs, ds, co = struct.unpack('<HHI', b[off + i * 8: off + i * 8 + 8])
        raw = co & 0x80000000
        co &= 0x7FFFFFFF
        piece = b[off + co: off + co + cs]
        data += piece if raw or cs == ds else zlib.decompress(piece)
    return bytes(data)


def _dds(data, w, h, fmt):
    hdr = bytearray(128)
    hdr[0:4] = b'DDS '
    struct.pack_into('<IIIIIII', hdr, 4, 124, 0x1007 | 0x80000, h, w, len(data), 0, 1)
    struct.pack_into('<II', hdr, 76, 32, 4)
    struct.pack_into('<I', hdr, 108, 0x1000)
    if fmt == 11:
        hdr[84:88] = b'DX10'
        extra = struct.pack('<IIIII', 98, 3, 0, 1, 0)  # DXGI_FORMAT_BC7_UNORM
    else:
        hdr[84:88] = _FOURCC[fmt]
        extra = b''
    return Image.open(io.BytesIO(bytes(hdr) + extra + data))


def read_image(path):
    """Abre um .ftex e devolve uma imagem PIL RGBA (mip principal)."""
    with open(path, 'rb') as f:
        b = f.read()
    if b[:4] != b'FTEX':
        raise FtexError('Não é um arquivo FTEX.')
    fmt, w, h = struct.unpack('<HHH', b[8:14])
    data = _mip0_data(b)
    if fmt == 0:
        im = Image.frombytes('RGBA', (w, h), data[:w * h * 4], 'raw', 'BGRA')
    elif fmt in (2, 3, 4, 11):
        im = _dds(data, w, h, fmt)
    else:
        raise FtexError(f'Formato de textura {fmt} não suportado.')
    return im.convert('RGBA')


def _mip_count(w, h):
    n = 1
    while w > 1 or h > 1:
        w, h = max(1, w // 2), max(1, h // 2)
        n += 1
    return n


def encode_image(img, progress=None):
    """Converte uma imagem PIL em bytes de um .ftex BC7 com todos os mipmaps."""
    img = img.convert('RGBA')
    w, h = img.size
    if w > 65535 or h > 65535:
        raise FtexError('Imagem grande demais.')
    nmips = _mip_count(w, h)
    weights = [max(1, (w >> m)) * max(1, (h >> m)) for m in range(nmips)]
    total = float(sum(weights))
    done = 0.0

    mips = []
    current = img
    for m in range(nmips):
        mw, mh = max(1, w >> m), max(1, h >> m)
        if m:
            current = current.resize((mw, mh), Image.LANCZOS)

        def sub(p, base=done, part=weights[m] / total):
            if progress:
                progress(min(1.0, base + p * part))
        mips.append(bc7.encode(np.asarray(current), sub))
        done += weights[m] / total

    blobs = []
    for data in mips:
        pieces = []
        for o in range(0, len(data), CHUNK):
            raw = data[o:o + CHUNK]
            z = zlib.compress(raw, 6)
            pieces.append((z if len(z) < len(raw) else raw, len(raw)))
        table = bytearray()
        body = bytearray()
        pos = 8 * len(pieces)
        for p, ds in pieces:
            table += struct.pack('<HHI', len(p), ds, pos)
            body += p
            pos += len(p)
        blobs.append((bytes(table + body), len(data), len(pieces)))

    out = bytearray(b'FTEX' + struct.pack('<f', 2.03) + struct.pack('<HHHHB', 11, w, h, 1, nmips))
    out += _HEADER_TAIL[1:]  # completa 0x40 bytes (o 1º byte do resto já foi o nº de mips)
    assert len(out) == 0x40, len(out)
    out += bytes(16 * nmips)
    for m in reversed(range(nmips)):  # o jogo grava os mips menores primeiro
        blob, size, n = blobs[m]
        off = len(out)
        out += blob
        struct.pack_into('<IIIBBH', out, 0x40 + 16 * m, off, size, len(blob), m, 0, n)
    if progress:
        progress(1.0)
    return bytes(out)


def write_image(img, path, progress=None):
    data = encode_image(img, progress)
    tmp = str(path) + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)
