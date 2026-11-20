"""Ponto de entrada.

Sem argumentos abre a janela. Com argumentos converte direto (útil para converter vários de uma vez):
    ConversorFTEX.exe camisa.png camisa.ftex [--tamanho 2048|4096]
    ConversorFTEX.exe camisa.ftex camisa.png
    ConversorFTEX.exe foto.webp foto.png        (JPG/WEBP -> PNG)
Aceita PNG, JPG e WEBP como entrada para o FTEX.
Em caso de erro na linha de comando, grava ConversorFTEX_erro.txt ao lado do arquivo de saída.
"""
import argparse
import os
import sys
import traceback


def linha_de_comando(argv):
    from conversor_ftex import ftex
    from conversor_ftex.app import converter_para_png, preparar_imagem

    p = argparse.ArgumentParser(prog='ConversorFTEX', description='Converte PNG <-> FTEX (PES 2021).')
    p.add_argument('entrada')
    p.add_argument('saida')
    p.add_argument('--tamanho', type=int, choices=[0, 2048, 4096], default=0,
                   help='0 = manter o tamanho do PNG (padrão)')
    a = p.parse_args(argv)
    if a.entrada.lower().endswith('.ftex'):
        ftex.read_image(a.entrada).save(a.saida)
    elif a.saida.lower().endswith('.png'):
        converter_para_png(a.entrada, a.saida)
    else:
        ftex.write_image(preparar_imagem(a.entrada, a.tamanho), a.saida)
    return 0


def _registrar_erro(argv):
    destino = next((x for x in argv[1:] if not x.startswith('-')), argv[0]) if len(argv) > 1 else '.'
    pasta = os.path.dirname(os.path.abspath(destino))
    with open(os.path.join(pasta, 'ConversorFTEX_erro.txt'), 'w', encoding='utf-8') as f:
        f.write(traceback.format_exc())


if __name__ == '__main__':
    if len(sys.argv) > 1:
        try:
            sys.exit(linha_de_comando(sys.argv[1:]))
        except SystemExit:
            raise
        except Exception:  # noqa: BLE001
            _registrar_erro(sys.argv[1:])
            sys.exit(1)
    from conversor_ftex.app import main
    main()
