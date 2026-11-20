"""Janela do Conversor de Camisas (tkinter)."""
import json
import os
import queue
import sys
import threading
import traceback
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from . import __version__, atualizacao, ftex, kitserver

TITULO = 'Conversor de Camisas PES 2021'
PREVIEW = 280
TIPOS_IMAGEM = [('Imagens (PNG, JPG, WEBP)', '*.png *.jpg *.jpeg *.webp *.bmp *.tga'), ('Todos', '*.*')]
TAMANHOS = [('Manter o tamanho do PNG', 0), ('2048 x 2048 (arquivo menor)', 2048), ('4096 x 4096 (mais nítido)', 4096)]


def _pasta_config():
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    p = os.path.join(base, 'ConversorFTEX')
    os.makedirs(p, exist_ok=True)
    return p


def carregar_preferencias():
    try:
        with open(os.path.join(_pasta_config(), 'config.json'), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def salvar_preferencias(prefs):
    try:
        with open(os.path.join(_pasta_config(), 'config.json'), 'w', encoding='utf-8') as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def preparar_imagem(caminho_png, tamanho):
    img = Image.open(caminho_png).convert('RGBA')
    w, h = img.size
    if tamanho:
        if (w, h) != (tamanho, tamanho):
            img = img.resize((tamanho, tamanho), Image.LANCZOS)
    elif w != h or w & (w - 1):
        lado = 4096 if max(w, h) > 2048 else 2048
        img = img.resize((lado, lado), Image.LANCZOS)
    return img


def converter_para_png(origem, destino=None):
    """Salva a imagem como PNG (na mesma pasta, sem sobrescrever outro arquivo). Devolve o caminho."""
    img = Image.open(origem)
    img.load()
    img = img.convert('RGBA' if 'A' in img.getbands() or img.mode == 'P' else 'RGB')
    if destino is None:
        base = os.path.splitext(origem)[0]
        destino = base + '.png'
        n = 2
        while os.path.exists(destino):
            destino = f'{base} ({n}).png'
            n += 1
    img.save(destino)
    return destino


def miniatura(img, lado=PREVIEW):
    fundo = Image.new('RGBA', img.size, (60, 60, 60, 255))
    fundo.alpha_composite(img.convert('RGBA'))
    fundo.thumbnail((lado, lado), Image.LANCZOS)
    return ImageTk.PhotoImage(fundo.convert('RGB'))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f'{TITULO}  v{__version__}')
        self.minsize(900, 640)
        self.prefs = carregar_preferencias()
        self.fila = queue.Queue()
        self.ocupado = False
        self.times = []
        self.times_filtrados = []
        self.kit_server = None
        self._fotos = {}
        self._icone()
        self._montar()
        self.after(100, self._processar_fila)
        pasta = self.prefs.get('kit_server')
        if pasta and kitserver.achar_kit_server(pasta):
            self._usar_kit_server(kitserver.achar_kit_server(pasta))
        self.after(800, lambda: self._verificar_atualizacao(silencioso=True))

    # ---------- montagem da tela ----------
    def _icone(self):
        base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ico = os.path.join(base, 'assets', 'icone.ico')
        if os.path.isfile(ico):
            try:
                self.iconbitmap(ico)
            except tk.TclError:
                pass

    def _montar(self):
        estilo = ttk.Style(self)
        if 'vista' in estilo.theme_names():
            estilo.theme_use('vista')
        estilo.configure('Aviso.TLabel', foreground='#0b5394', font=('Segoe UI', 10, 'bold'))
        estilo.configure('Titulo.TLabel', font=('Segoe UI', 10, 'bold'))

        self.barra_atualizacao = ttk.Frame(self, padding=(10, 6))
        self.lbl_atualizacao = ttk.Label(self.barra_atualizacao, style='Aviso.TLabel')
        self.lbl_atualizacao.pack(side='left')
        self.btn_atualizar = ttk.Button(self.barra_atualizacao, text='Atualizar agora', command=self._atualizar)
        self.btn_atualizar.pack(side='right')

        abas = self.abas = ttk.Notebook(self)
        abas.pack(fill='both', expand=True, padx=10, pady=(6, 0))
        self.aba_instalar = ttk.Frame(abas, padding=10)
        self.aba_converter = ttk.Frame(abas, padding=10)
        self.aba_sobre = ttk.Frame(abas, padding=10)
        abas.add(self.aba_instalar, text='Instalar camisa no time')
        abas.add(self.aba_converter, text='Converter arquivo')
        abas.add(self.aba_sobre, text='Sobre')
        self._montar_instalar()
        self._montar_converter()
        self._montar_sobre()

        rodape = ttk.Frame(self, padding=(10, 6))
        rodape.pack(fill='x', side='bottom')
        self.progresso = ttk.Progressbar(rodape, maximum=1.0, length=260)
        self.progresso.pack(side='right')
        self.status = ttk.Label(rodape, text='Pronto.')
        self.status.pack(side='left', fill='x', expand=True)

    def _montar_instalar(self):
        f = self.aba_instalar
        f.columnconfigure(1, weight=1)

        ttk.Label(f, text='Pasta do kit-server:', style='Titulo.TLabel').grid(row=0, column=0, sticky='w')
        self.var_pasta = tk.StringVar(value='(escolha a pasta do sider ou do jogo)')
        ttk.Label(f, textvariable=self.var_pasta).grid(row=0, column=1, sticky='w', padx=6)
        ttk.Button(f, text='Escolher pasta...', command=self._escolher_pasta).grid(row=0, column=2, sticky='e')

        esquerda = ttk.Frame(f)
        esquerda.grid(row=1, column=0, sticky='nsew', pady=(10, 0))
        f.rowconfigure(1, weight=1)
        ttk.Label(esquerda, text='Time:', style='Titulo.TLabel').pack(anchor='w')
        self.var_busca = tk.StringVar()
        self.var_busca.trace_add('write', lambda *_: self._filtrar_times())
        busca = ttk.Entry(esquerda, textvariable=self.var_busca, width=34)
        busca.pack(fill='x', pady=(2, 4))
        ttk.Label(esquerda, text='digite para buscar', foreground='#777').pack(anchor='w')
        caixa = ttk.Frame(esquerda)
        caixa.pack(fill='both', expand=True, pady=(4, 0))
        self.lista_times = tk.Listbox(caixa, width=38, exportselection=False, activestyle='none')
        rolagem = ttk.Scrollbar(caixa, orient='vertical', command=self.lista_times.yview)
        self.lista_times.configure(yscrollcommand=rolagem.set)
        self.lista_times.pack(side='left', fill='both', expand=True)
        rolagem.pack(side='right', fill='y')
        self.lista_times.bind('<<ListboxSelect>>', lambda e: self._time_escolhido())

        direita = ttk.Frame(f)
        direita.grid(row=1, column=1, columnspan=2, sticky='nsew', padx=(12, 0), pady=(10, 0))
        direita.columnconfigure(0, weight=1)
        direita.columnconfigure(1, weight=1)

        ttk.Label(direita, text='Uniforme:', style='Titulo.TLabel').grid(row=0, column=0, columnspan=2, sticky='w')
        self.combo_kits = ttk.Combobox(direita, state='readonly')
        self.combo_kits.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(2, 8))
        self.combo_kits.bind('<<ComboboxSelected>>', lambda e: self._kit_escolhido())

        ttk.Label(direita, text='Nova camisa (PNG, JPG ou WEBP):', style='Titulo.TLabel').grid(row=2, column=0, columnspan=2, sticky='w')
        linha_png = ttk.Frame(direita)
        linha_png.grid(row=3, column=0, columnspan=2, sticky='ew', pady=(2, 8))
        self.var_png = tk.StringVar()
        ttk.Entry(linha_png, textvariable=self.var_png, state='readonly').pack(side='left', fill='x', expand=True)
        ttk.Button(linha_png, text='Escolher imagem...', command=self._escolher_png).pack(side='left', padx=(6, 0))

        ttk.Label(direita, text='Tamanho da textura:', style='Titulo.TLabel').grid(row=4, column=0, columnspan=2, sticky='w')
        self.var_tamanho = tk.IntVar(value=int(self.prefs.get('tamanho', 0)))
        linha_tam = ttk.Frame(direita)
        linha_tam.grid(row=5, column=0, columnspan=2, sticky='w', pady=(2, 8))
        for texto, valor in TAMANHOS:
            ttk.Radiobutton(linha_tam, text=texto, value=valor, variable=self.var_tamanho).pack(side='left', padx=(0, 12))

        ttk.Label(direita, text='Camisa atual', style='Titulo.TLabel').grid(row=6, column=0)
        ttk.Label(direita, text='Nova camisa', style='Titulo.TLabel').grid(row=6, column=1)
        self.prev_atual = ttk.Label(direita, text='—', anchor='center', relief='solid', width=40)
        self.prev_nova = ttk.Label(direita, text='—', anchor='center', relief='solid', width=40)
        self.prev_atual.grid(row=7, column=0, padx=4, pady=4, sticky='n')
        self.prev_nova.grid(row=7, column=1, padx=4, pady=4, sticky='n')

        botoes = ttk.Frame(direita)
        botoes.grid(row=8, column=0, columnspan=2, pady=(10, 0))
        self.btn_instalar = ttk.Button(botoes, text='Instalar no time', command=self._instalar)
        self.btn_instalar.pack(side='left', padx=6)
        self.btn_desfazer = ttk.Button(botoes, text='Desfazer última troca', command=self._desfazer)
        self.btn_desfazer.pack(side='left', padx=6)
        ttk.Button(botoes, text='Abrir pasta do uniforme', command=self._abrir_pasta_kit).pack(side='left', padx=6)

    def _montar_converter(self):
        f = self.aba_converter
        ttk.Label(f, text='Imagem (PNG, JPG ou WEBP)  →  FTEX', style='Titulo.TLabel').pack(anchor='w')
        ttk.Label(f, text='Converte a textura da camisa (ex.: baixada do PESMaster) em .ftex para usar no jogo.\n'
                          'O tamanho segue a opção escolhida na aba "Instalar camisa no time".').pack(anchor='w', pady=(2, 6))
        ttk.Button(f, text='Escolher imagem e converter...', command=self._converter_png).pack(anchor='w')
        ttk.Separator(f).pack(fill='x', pady=16)
        ttk.Label(f, text='JPG / WEBP  →  PNG', style='Titulo.TLabel').pack(anchor='w')
        ttk.Label(f, text='Transforma uma ou várias imagens em PNG. O PNG é salvo na mesma pasta, com o mesmo nome.').pack(anchor='w', pady=(2, 6))
        ttk.Button(f, text='Escolher imagens e converter para PNG...', command=self._para_png).pack(anchor='w')
        ttk.Separator(f).pack(fill='x', pady=16)
        ttk.Label(f, text='FTEX  →  PNG', style='Titulo.TLabel').pack(anchor='w')
        ttk.Label(f, text='Exporta uma camisa (ou fonte de número) do jogo para PNG, para ver ou editar.').pack(anchor='w', pady=(2, 6))
        ttk.Button(f, text='Escolher FTEX e exportar...', command=self._exportar_ftex).pack(anchor='w')

    def _montar_sobre(self):
        f = self.aba_sobre
        ttk.Label(f, text=TITULO, style='Titulo.TLabel').pack(anchor='w')
        ttk.Label(f, text=f'Versão {__version__}').pack(anchor='w', pady=(2, 10))
        ttk.Label(f, text='Converte texturas PNG em FTEX (formato BC7) e instala direto nas pastas\n'
                          'do Kitserver do sider (content\\kit-server). Antes de trocar, a camisa antiga\n'
                          'é guardada na pasta "_backup_conversor" dentro do time.').pack(anchor='w')
        ttk.Button(f, text='Procurar atualização', command=lambda: self._verificar_atualizacao(False)).pack(anchor='w', pady=(14, 4))
        ttk.Button(f, text='Abrir página do projeto', command=lambda: webbrowser.open(atualizacao.PAGINA)).pack(anchor='w')

    # ---------- kit-server / times ----------
    def _escolher_pasta(self):
        pasta = filedialog.askdirectory(title='Escolha a pasta do sider (ou do jogo, ou o próprio kit-server)')
        if not pasta:
            return
        ks = kitserver.achar_kit_server(pasta)
        if not ks:
            messagebox.showerror(TITULO, 'Não achei a pasta content\\kit-server (com o map.txt) aí dentro.\n\n'
                                         'Escolha a pasta do sider (onde fica o sider.exe) ou a própria pasta kit-server.')
            return
        self._usar_kit_server(ks)

    def _usar_kit_server(self, ks):
        try:
            self.times = kitserver.carregar_times(ks)
        except OSError as e:
            messagebox.showerror(TITULO, f'Erro ao ler o map.txt:\n{e}')
            return
        self.kit_server = ks
        self.var_pasta.set(ks)
        self.prefs['kit_server'] = ks
        salvar_preferencias(self.prefs)
        self._filtrar_times()
        self._status(f'{len(self.times)} times encontrados no kit-server.')

    def _filtrar_times(self):
        termo = self.var_busca.get().strip().lower()
        self.times_filtrados = [t for t in self.times if termo in t.caminho_rel.lower()]
        self.lista_times.delete(0, 'end')
        for t in self.times_filtrados:
            self.lista_times.insert('end', f'{t.nome}   ·   {t.liga}')

    def _time_atual(self):
        sel = self.lista_times.curselection()
        return self.times_filtrados[sel[0]] if sel else None

    def _time_escolhido(self):
        t = self._time_atual()
        if not t:
            return
        try:
            kits = kitserver.carregar_kits(t)
        except OSError as e:
            messagebox.showerror(TITULO, str(e))
            return
        self.combo_kits['values'] = [k.rotulo for k in kits]
        if kits:
            self.combo_kits.current(0)
            self._kit_escolhido()
        else:
            self.combo_kits.set('')
            self._mostrar(self.prev_atual, None, 'atual', 'Nenhum uniforme com config.txt')

    def _kit_atual(self):
        t = self._time_atual()
        i = self.combo_kits.current()
        return t.kits[i] if t and 0 <= i < len(t.kits) else None

    def _kit_escolhido(self):
        kit = self._kit_atual()
        if not kit:
            return
        if not os.path.isfile(kit.ftex):
            self._mostrar(self.prev_atual, None, 'atual', f'{kit.kit_file}.ftex\nnão existe nesta pasta')
            return
        self._rodar(lambda prog: ftex.read_image(kit.ftex),
                    lambda img: self._mostrar(self.prev_atual, img, 'atual'),
                    'Lendo camisa atual...')

    def _mostrar(self, rotulo, img, chave, texto='—'):
        if img is None:
            self._fotos.pop(chave, None)
            rotulo.configure(image='', text=texto)
            return
        foto = miniatura(img)
        self._fotos[chave] = foto
        rotulo.configure(image=foto, text='')

    # ---------- PNG ----------
    def _escolher_png(self):
        caminho = filedialog.askopenfilename(title='Escolha a textura da camisa',
                                             initialdir=self.prefs.get('pasta_png') or None,
                                             filetypes=TIPOS_IMAGEM)
        if not caminho:
            return
        self.prefs['pasta_png'] = os.path.dirname(caminho)
        salvar_preferencias(self.prefs)
        try:
            img = Image.open(caminho)
            img.load()
        except Exception as e:
            messagebox.showerror(TITULO, f'Não consegui abrir a imagem:\n{e}')
            return
        self.var_png.set(caminho)
        w, h = img.size
        self._mostrar(self.prev_nova, img, 'nova')
        aviso = '' if w == h and not (w & (w - 1)) else '  (não é quadrada/potência de 2: vou redimensionar)'
        self._status(f'PNG {w} x {h}{aviso}')

    # ---------- instalar ----------
    def _instalar(self):
        kit = self._kit_atual()
        png = self.var_png.get()
        if not self.kit_server:
            return messagebox.showwarning(TITULO, 'Escolha primeiro a pasta do kit-server.')
        if not kit:
            return messagebox.showwarning(TITULO, 'Escolha o time e o uniforme.')
        if not png:
            return messagebox.showwarning(TITULO, 'Escolha o PNG da nova camisa.')
        t = self._time_atual()
        if not messagebox.askyesno(TITULO, f'Trocar a camisa de {t.nome} ({kit.pasta})?\n\n'
                                           f'Arquivo: {kit.ftex}\n\nA camisa atual vai para a pasta de backup.\n'
                                           'Deixe o PES fechado (ou troque de partida) para ver a mudança.'):
            return
        tamanho = self.var_tamanho.get()
        self.prefs['tamanho'] = tamanho
        salvar_preferencias(self.prefs)

        def trabalho(prog):
            img = preparar_imagem(png, tamanho)
            backup = kitserver.fazer_backup(kit)
            ftex.write_image(img, kit.ftex, prog)
            return img, backup

        def pronto(res):
            img, backup = res
            self._mostrar(self.prev_atual, img, 'atual')
            msg = f'Camisa instalada em {t.nome} ({kit.pasta}), {img.size[0]}x{img.size[1]}.'
            self._status(msg)
            messagebox.showinfo(TITULO, msg + (f'\n\nBackup da antiga:\n{backup}' if backup else ''))

        self._rodar(trabalho, pronto, 'Convertendo e instalando...')

    def _desfazer(self):
        kit = self._kit_atual()
        if not kit:
            return
        backups = kitserver.listar_backups(kit)
        if not backups:
            return messagebox.showinfo(TITULO, 'Não há backup deste uniforme feito pelo conversor.')
        if not messagebox.askyesno(TITULO, f'Voltar a camisa anterior?\n\n{os.path.basename(backups[-1])}'):
            return
        kitserver.restaurar_ultimo_backup(kit)
        self._kit_escolhido()
        self._status('Camisa anterior restaurada.')

    def _abrir_pasta_kit(self):
        kit = self._kit_atual()
        if kit:
            os.startfile(kit.caminho)

    # ---------- aba converter ----------
    def _converter_png(self):
        png = filedialog.askopenfilename(title='Imagem para converter', filetypes=TIPOS_IMAGEM)
        if not png:
            return
        destino = filedialog.asksaveasfilename(title='Salvar .ftex como', defaultextension='.ftex',
                                               initialfile=os.path.splitext(os.path.basename(png))[0] + '.ftex',
                                               filetypes=[('Textura FTEX', '*.ftex')])
        if not destino:
            return
        tamanho = self.var_tamanho.get()

        def trabalho(prog):
            img = preparar_imagem(png, tamanho)
            ftex.write_image(img, destino, prog)
            return img

        self._rodar(trabalho, lambda img: self._status(f'Salvo: {destino} ({img.size[0]}x{img.size[1]})'), 'Convertendo...')

    def _para_png(self):
        origens = filedialog.askopenfilenames(title='Imagens para converter em PNG',
                                              filetypes=[('JPG, WEBP e outras', '*.jpg *.jpeg *.webp *.bmp *.tga *.gif'), ('Todos', '*.*')])
        if not origens:
            return

        def trabalho(prog):
            feitos = []
            for i, origem in enumerate(origens):
                feitos.append(converter_para_png(origem))
                prog((i + 1) / len(origens))
            return feitos

        def pronto(feitos):
            self._status(f'{len(feitos)} imagem(ns) convertida(s) para PNG.')
            messagebox.showinfo(TITULO, 'Convertido para PNG:\n\n' + '\n'.join(feitos[:15]) + ('\n...' if len(feitos) > 15 else ''))

        self._rodar(trabalho, pronto, 'Convertendo para PNG...')

    def _exportar_ftex(self):
        origem = filedialog.askopenfilename(title='FTEX para exportar', filetypes=[('Textura FTEX', '*.ftex'), ('Todos', '*.*')])
        if not origem:
            return
        destino = filedialog.asksaveasfilename(title='Salvar PNG como', defaultextension='.png',
                                               initialfile=os.path.splitext(os.path.basename(origem))[0] + '.png',
                                               filetypes=[('PNG', '*.png')])
        if not destino:
            return

        def trabalho(prog):
            img = ftex.read_image(origem)
            img.save(destino)
            return img

        self._rodar(trabalho, lambda img: self._status(f'Exportado: {destino} ({img.size[0]}x{img.size[1]})'), 'Exportando...')

    # ---------- atualização ----------
    def _verificar_atualizacao(self, silencioso):
        def pronto(info):
            self.info_atualizacao = info
            if info:
                self.lbl_atualizacao.configure(text=f'Nova versão {info["versao"]} disponível (você tem a {__version__}).')
                self.btn_atualizar.configure(text='Atualizar agora' if atualizacao.pode_autoatualizar() and info['url_exe'] else 'Baixar')
                self.barra_atualizacao.pack(fill='x', side='top', before=self.abas)
            elif not silencioso:
                messagebox.showinfo(TITULO, f'Você já está na versão mais nova ({__version__}).')

        def erro(e):
            if not silencioso:
                messagebox.showwarning(TITULO, f'Não consegui verificar atualizações:\n{e}')

        threading.Thread(target=self._em_thread, args=(atualizacao.verificar, pronto, erro), daemon=True).start()

    def _atualizar(self):
        info = getattr(self, 'info_atualizacao', None)
        if not info:
            return
        if not (atualizacao.pode_autoatualizar() and info['url_exe']):
            webbrowser.open(info['pagina'])
            return
        if not messagebox.askyesno(TITULO, f'Baixar a versão {info["versao"]} e reiniciar o programa?'):
            return

        def trabalho(prog):
            atualizacao.baixar_e_reiniciar(info['url_exe'], prog)

        self._rodar(trabalho, lambda _: self.destroy(), 'Baixando atualização...')

    # ---------- execução em segundo plano ----------
    def _em_thread(self, func, ok, falha):
        try:
            res = func()
        except Exception as e:  # noqa: BLE001
            self.fila.put(('erro_silencioso', falha, e))
        else:
            self.fila.put(('ok', ok, res))

    def _rodar(self, trabalho, ao_terminar, texto):
        if self.ocupado:
            return
        self.ocupado = True
        self.btn_instalar.state(['disabled'])
        self.progresso['value'] = 0
        self._status(texto)

        def prog(p):
            self.fila.put(('progresso', None, p))

        def alvo():
            try:
                res = trabalho(prog)
            except Exception as e:  # noqa: BLE001
                self.fila.put(('erro', None, (e, traceback.format_exc())))
            else:
                self.fila.put(('fim', ao_terminar, res))

        threading.Thread(target=alvo, daemon=True).start()

    def _processar_fila(self):
        try:
            while True:
                tipo, func, valor = self.fila.get_nowait()
                if tipo == 'progresso':
                    self.progresso['value'] = valor
                elif tipo in ('fim', 'erro'):
                    self.ocupado = False
                    self.btn_instalar.state(['!disabled'])
                    self.progresso['value'] = 1.0 if tipo == 'fim' else 0
                    if tipo == 'fim':
                        func(valor)
                    else:
                        e, tb = valor
                        self._status(f'Erro: {e}')
                        messagebox.showerror(TITULO, f'{e}\n\n{tb[-1500:]}')
                elif tipo == 'ok':
                    func(valor)
                elif tipo == 'erro_silencioso':
                    func(valor)
        except queue.Empty:
            pass
        self.after(100, self._processar_fila)

    def _status(self, texto):
        self.status.configure(text=texto)


def main():
    App().mainloop()
