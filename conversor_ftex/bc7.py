"""Encoder BC7 vetorizado (numpy).

Para cada bloco 4x4 testa dois modos e fica com o de menor erro:
  - modo 6: RGBA na mesma reta, índices de 4 bits (bom para degradês)
  - modo 5: cor e alfa separados, índices de 2 bits (bom para bordas com transparência)
Processa a imagem em faixas para não estourar a memória em texturas 4096x4096.
"""
import numpy as np

_W16 = np.array([0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64], dtype=np.float32)
_W4 = np.array([0, 21, 43, 64], dtype=np.float32)

STRIP_BLOCK_ROWS = 64


class _Bits:
    """Escreve campos de bits (LSB primeiro) em N blocos de 128 bits ao mesmo tempo."""

    def __init__(self, n):
        self.lo = np.zeros(n, dtype=np.uint64)
        self.hi = np.zeros(n, dtype=np.uint64)
        self.pos = 0

    def put(self, values, nbits):
        v = np.asarray(values).astype(np.uint64) & np.uint64((1 << nbits) - 1)
        p = self.pos
        if p >= 64:
            self.hi |= v << np.uint64(p - 64)
        elif p + nbits <= 64:
            self.lo |= v << np.uint64(p)
        else:
            low_bits = 64 - p
            self.lo |= (v & np.uint64((1 << low_bits) - 1)) << np.uint64(p)
            self.hi |= v >> np.uint64(low_bits)
        self.pos += nbits

    def put_indices(self, idx, bits_each):
        """Índices de 16 pixels; o primeiro (âncora) usa um bit a menos."""
        self.put(idx[:, 0], bits_each - 1)
        for k in range(1, 16):
            self.put(idx[:, k], bits_each)


def _blocks(rgba):
    """(H, W, 4) -> (N, 16, 4) float32, completando bordas quando o mip é menor que 4x4."""
    h, w = rgba.shape[:2]
    bh, bw = max(1, (h + 3) // 4), max(1, (w + 3) // 4)
    if h % 4 or w % 4 or h < 4 or w < 4:
        pad = np.empty((bh * 4, bw * 4, 4), dtype=np.float32)
        pad[:h, :w] = rgba
        pad[:h, w:] = rgba[:, w - 1:w]
        pad[h:, :] = pad[h - 1:h, :]
        rgba = pad
    return rgba.reshape(bh, 4, bw, 4, 4).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 4).astype(np.float32)


def _mode6(blk):
    n = len(blk)
    mean = blk.mean(1)
    centered = blk - mean[:, None, :]
    cov = np.einsum('npi,npj->nij', centered, centered)
    axis = np.ones((n, 4), dtype=np.float32)
    for _ in range(8):
        axis = np.einsum('nij,nj->ni', cov, axis)
        norm = np.linalg.norm(axis, axis=1, keepdims=True)
        axis = np.where(norm > 1e-6, axis / np.maximum(norm, 1e-12), 0.5)
    proj = np.einsum('npi,ni->np', centered, axis)
    e0 = np.clip(mean + proj.min(1)[:, None] * axis, 0, 255)
    e1 = np.clip(mean + proj.max(1)[:, None] * axis, 0, 255)

    def quant(e):
        best_c = best_p = best_v = best_err = None
        for p in (0, 1):
            c = np.clip(np.round((e - p) / 2.0), 0, 127).astype(np.int64)
            v = ((c << 1) | p).astype(np.float32)
            err = ((v - e) ** 2).sum(1)
            if best_c is None:
                best_c, best_p, best_v, best_err = c, np.full(n, p), v, err
            else:
                m = err < best_err
                best_c[m], best_p[m], best_v[m], best_err[m] = c[m], p, v[m], err[m]
        return best_c, best_p, best_v

    c0, p0, v0 = quant(e0)
    c1, p1, v1 = quant(e1)
    d = v1 - v0
    dd = (d * d).sum(1)
    dd[dd == 0] = 1
    t = np.clip(((blk - v0[:, None, :]) * d[:, None, :]).sum(2) / dd[:, None], 0, 1)
    idx = np.abs(t[:, :, None] * 64 - _W16[None, None, :]).argmin(2)
    w = _W16[idx] / 64.0
    rec = np.round(v0[:, None, :] * (1 - w[:, :, None]) + v1[:, None, :] * w[:, :, None])
    err = ((rec - blk) ** 2).sum((1, 2))

    swap = idx[:, 0] >= 8
    c0[swap], c1[swap] = c1[swap].copy(), c0[swap].copy()
    p0[swap], p1[swap] = p1[swap].copy(), p0[swap].copy()
    idx[swap] = 15 - idx[swap]

    bits = _Bits(n)
    bits.put(np.full(n, 1 << 6), 7)
    for ch in range(4):
        bits.put(c0[:, ch], 7)
        bits.put(c1[:, ch], 7)
    bits.put(p0, 1)
    bits.put(p1, 1)
    bits.put_indices(idx, 4)
    assert bits.pos == 128
    return bits.lo, bits.hi, err


def _mode5(blk):
    n = len(blk)
    rgb, al = blk[:, :, :3], blk[:, :, 3]
    vis = al > 8
    anyv = vis.any(1)
    lo = np.where(vis[:, :, None], rgb, 1e9).min(1)
    hi = np.where(vis[:, :, None], rgb, -1e9).max(1)
    lo[~anyv] = rgb[~anyv].min(1)
    hi[~anyv] = rgb[~anyv].max(1)
    c0 = np.clip(np.round(lo / 255 * 127), 0, 127).astype(np.int64)
    c1 = np.clip(np.round(hi / 255 * 127), 0, 127).astype(np.int64)
    v0 = ((c0 << 1) | (c0 >> 6)).astype(np.float32)
    v1 = ((c1 << 1) | (c1 >> 6)).astype(np.float32)
    d = v1 - v0
    dd = (d * d).sum(1)
    dd[dd == 0] = 1
    t = np.clip(((rgb - v0[:, None, :]) * d[:, None, :]).sum(2) / dd[:, None], 0, 1)
    ci = np.abs(t[:, :, None] * 64 - _W4[None, None, :]).argmin(2)
    a0 = np.round(al.min(1)).astype(np.int64)
    a1 = np.round(al.max(1)).astype(np.int64)
    da = (a1 - a0).astype(np.float32)
    da[da == 0] = 1
    ta = np.clip((al - a0[:, None]) / da[:, None], 0, 1)
    ai = np.abs(ta[:, :, None] * 64 - _W4[None, None, :]).argmin(2)

    wc = _W4[ci] / 64.0
    rec_rgb = np.round(v0[:, None, :] * (1 - wc[:, :, None]) + v1[:, None, :] * wc[:, :, None])
    wa = _W4[ai] / 64.0
    rec_a = np.round(a0[:, None] * (1 - wa) + a1[:, None] * wa)
    err = ((rec_rgb - rgb) ** 2).sum((1, 2)) + ((rec_a - al) ** 2).sum(1)

    s = ci[:, 0] >= 2
    c0[s], c1[s] = c1[s].copy(), c0[s].copy()
    ci[s] = 3 - ci[s]
    s = ai[:, 0] >= 2
    a0[s], a1[s] = a1[s].copy(), a0[s].copy()
    ai[s] = 3 - ai[s]

    bits = _Bits(n)
    bits.put(np.full(n, 1 << 5), 6)
    bits.put(np.zeros(n), 2)  # rotação
    for ch in range(3):
        bits.put(c0[:, ch], 7)
        bits.put(c1[:, ch], 7)
    bits.put(a0, 8)
    bits.put(a1, 8)
    bits.put_indices(ci, 2)
    bits.put_indices(ai, 2)
    assert bits.pos == 128
    return bits.lo, bits.hi, err


def encode(rgba, progress=None):
    """rgba: array numpy (H, W, 4) uint8. Retorna os bytes BC7 (blocos em ordem de linha)."""
    rgba = np.asarray(rgba)
    h, w = rgba.shape[:2]
    bw = max(1, (w + 3) // 4)
    bh = max(1, (h + 3) // 4)
    out = []
    for by in range(0, bh, STRIP_BLOCK_ROWS):
        y0, y1 = by * 4, min(h, (by + STRIP_BLOCK_ROWS) * 4)
        blk = _blocks(rgba[y0:y1].astype(np.float32))
        lo6, hi6, e6 = _mode6(blk)
        lo5, hi5, e5 = _mode5(blk)
        use5 = e5 < e6
        lo = np.where(use5, lo5, lo6)
        hi = np.where(use5, hi5, hi6)
        packed = np.empty((len(blk), 2), dtype='<u8')
        packed[:, 0], packed[:, 1] = lo, hi
        out.append(packed.tobytes())
        if progress:
            progress(min(1.0, (by + STRIP_BLOCK_ROWS) / bh))
    data = b''.join(out)
    assert len(data) == bw * bh * 16
    return data
