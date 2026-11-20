import os
import struct
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw

from conversor_ftex import atualizacao, bc7, ftex, kitserver


def imagem_teste(lado=256):
    img = Image.new('RGBA', (lado, lado), (200, 16, 46, 255))
    d = ImageDraw.Draw(img)
    for x in range(0, lado, 32):
        d.rectangle([x, 0, x + 15, lado], fill=(245, 245, 245, 255))
    d.ellipse([lado // 4, lado // 4, lado * 3 // 4, lado * 3 // 4], fill=(0, 120, 60, 255))
    for y in range(lado):  # degradê
        d.line([(0, y), (lado // 8, y)], fill=(y % 256, 255 - y % 256, 128, 255))
    d.rectangle([lado - 40, 0, lado, 40], fill=(0, 0, 0, 0))  # canto transparente
    return img


def ler(caminho):
    with open(caminho, 'rb') as f:
        return f.read()


def psnr(a, b):
    a = np.asarray(a, np.float64)
    b = np.asarray(b, np.float64)
    mse = ((a - b) ** 2).mean()
    return 99.0 if mse == 0 else 10 * np.log10(255 ** 2 / mse)


class TestFtex(unittest.TestCase):
    def test_ida_e_volta(self):
        img = imagem_teste(256)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 't.ftex')
            ftex.write_image(img, p)
            info = ftex.read_info(p)
            self.assertEqual((info['formato'], info['largura'], info['altura'], info['mipmaps']), (11, 256, 256, 9))
            self.assertGreater(psnr(img, ftex.read_image(p)), 38)

    def test_mipmaps_validos(self):
        img = imagem_teste(64)
        dados = ftex.encode_image(img)
        n = dados[16]
        for m in range(n):
            off, size, csize, idx, _, nchunks = struct.unpack('<IIIBBH', dados[0x40 + m * 16: 0x50 + m * 16])
            self.assertEqual(idx, m)
            self.assertLessEqual(off + csize, len(dados))
            lado = max(1, 64 >> m)
            self.assertEqual(size, max(1, (lado + 3) // 4) ** 2 * 16)

    def test_bloco_transparente(self):
        dados = bc7.encode(np.zeros((4, 4, 4), np.uint8))
        self.assertEqual(len(dados), 16)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 't.ftex')
            ftex.write_image(Image.new('RGBA', (16, 16), (0, 0, 0, 0)), p)
            self.assertEqual(ftex.read_image(p).getchannel('A').getextrema(), (0, 0))


class TestFormatosDeEntrada(unittest.TestCase):
    def test_jpg_e_webp(self):
        from conversor_ftex.app import converter_para_png, preparar_imagem
        img = imagem_teste(128).convert('RGB')
        with tempfile.TemporaryDirectory() as d:
            for ext, opcoes in (('jpg', {'quality': 95}), ('webp', {'quality': 95})):
                origem = os.path.join(d, 'camisa.' + ext)
                img.save(origem, **opcoes)
                # direto para FTEX
                saida = os.path.join(d, f'camisa_{ext}.ftex')
                ftex.write_image(preparar_imagem(origem, 0), saida)
                self.assertEqual(ftex.read_info(saida)['largura'], 128)
                self.assertGreater(psnr(img.convert('RGBA'), ftex.read_image(saida)), 28)
                # para PNG, sem sobrescrever um PNG que já existe
                png1 = converter_para_png(origem)
                png2 = converter_para_png(origem)
                self.assertTrue(png1.endswith('camisa.png'))
                self.assertTrue(png2.endswith('camisa (2).png'))
                self.assertEqual(Image.open(png2).size, (128, 128))
                os.remove(png1)
                os.remove(png2)


class TestKitserver(unittest.TestCase):
    def test_times_kits_e_backup(self):
        with tempfile.TemporaryDirectory() as d:
            ks = os.path.join(d, 'content', 'kit-server')
            kit = os.path.join(ks, 'Liga', 'Time A', 'p1')
            os.makedirs(kit)
            with open(os.path.join(ks, 'map.txt'), 'w', encoding='utf-8-sig') as f:
                f.write('# comentario\n123,"Liga\\Time A"\n999,"Liga\\Nao Existe"\n')
            with open(os.path.join(kit, 'config.txt'), 'w', encoding='utf-8') as f:
                f.write('KitFile=u0123p1   ; textura\r\n')
            with open(os.path.join(ks, 'Liga', 'Time A', 'order.ini'), 'w', encoding='utf-8') as f:
                f.write('p1\n')
            self.assertEqual(kitserver.achar_kit_server(d), os.path.normpath(ks))
            times = kitserver.carregar_times(ks)
            self.assertEqual([t.id for t in times], [123])
            kits = kitserver.carregar_kits(times[0])
            self.assertEqual(kits[0].kit_file, 'u0123p1')
            self.assertTrue(kits[0].em_uso)
            ftex.write_image(imagem_teste(16), kits[0].ftex)
            original = ler(kits[0].ftex)
            self.assertIsNotNone(kitserver.fazer_backup(kits[0]))
            ftex.write_image(Image.new('RGBA', (16, 16), (1, 2, 3, 255)), kits[0].ftex)
            kitserver.restaurar_ultimo_backup(kits[0])
            self.assertEqual(ler(kits[0].ftex), original)


class TestVersao(unittest.TestCase):
    def test_comparacao(self):
        v = atualizacao._versao
        self.assertLess(v('1.0.0'), v('v1.0.1'))
        self.assertLess(v('1.9.0'), v('1.10.0'))
        self.assertEqual(v('v2'), (2, 0, 0))


if __name__ == '__main__':
    unittest.main()
