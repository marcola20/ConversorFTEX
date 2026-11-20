# Conversor de Camisas PES 2021

Programa para Windows que transforma a textura de uma camisa (PNG, JPG ou WEBP) em **.ftex**, o formato que o PES 2021 usa, e já instala no time certo do **Kitserver do sider** (`content\kit-server`).

Foi feito para quem monta camisas no [PESMaster Kit Creator](https://www.pesmaster.com/kit-creator/) e quer colocar no jogo sem precisar de Photoshop, plugin de DDS ou ferramentas de linha de comando.

## Baixar

1. Vá em **[Releases](../../releases/latest)** e baixe o `ConversorFTEX.exe`.
2. Abra o arquivo. Não precisa instalar nada.

> O Windows pode mostrar "O Windows protegeu o computador" na primeira vez, porque o programa não é assinado. Clique em **Mais informações → Executar assim mesmo**.

O programa avisa sozinho quando sai uma versão nova e se atualiza com um clique.

## Como usar

### Trocar a camisa de um time

1. Aba **Instalar camisa no time**, botão **Escolher pasta...**: escolha a pasta do sider (onde fica o `sider.exe`), a pasta do jogo ou a própria `content\kit-server`.
2. Procure o time pelo nome e escolha o uniforme (`p1` = 1º uniforme, `p2` = 2º, `g1` = goleiro).
3. **Escolher imagem...**: a textura da camisa (PNG do PESMaster, JPG ou WEBP).
4. **Instalar no time**. A camisa antiga vai para a pasta `_backup_conversor` dentro do time; o botão **Desfazer última troca** coloca ela de volta.
5. Abra o jogo pelo sider (ou entre em outra partida) para ver.

Só a textura (`.ftex`) é trocada. Gola, cores do menu e fonte dos números continuam no `config.txt` do uniforme.

### Outras conversões (aba **Converter arquivo**)

- **Imagem → FTEX**: PNG, JPG ou WEBP para `.ftex`, salvando onde você quiser.
- **JPG / WEBP → PNG**: converte uma ou várias imagens para PNG, na mesma pasta.
- **FTEX → PNG**: exporta uma camisa ou fonte de número do jogo para ver ou editar.

### Linha de comando

```
ConversorFTEX.exe camisa.png  camisa.ftex  [--tamanho 2048|4096]
ConversorFTEX.exe camisa.webp camisa.ftex
ConversorFTEX.exe camisa.ftex camisa.png
ConversorFTEX.exe foto.jpg    foto.png
```

## Detalhes técnicos

- Grava FTEX versão 2.03 no formato **BC7** (formato 11), com todos os mipmaps, igual às camisas que o jogo já usa. Qualidade medida em ~53–55 dB de PSNR com texturas do PESMaster.
- Lê FTEX em BC7, DXT1, DXT3, DXT5 e RGBA.
- Tamanhos: mantém o da imagem (PESMaster exporta 4096×4096) ou reduz para 2048×2048. Imagem que não é quadrada é redimensionada.

## Para quem mantém o projeto

Rodar a partir do código (Python 3.10 ou mais novo):

```
pip install -r requirements.txt
python main.py
python -m unittest -v
```

Gerar o `.exe` localmente: `pip install pyinstaller` e depois `build.bat` (sai em `dist\ConversorFTEX.exe`).

### Publicar uma versão nova

1. Mude o número em `conversor_ftex/__init__.py` (ex.: `__version__ = "1.0.1"`).
2. Faça o commit e crie a tag com o **mesmo número**:
   ```
   git commit -am "Versão 1.0.1"
   git tag v1.0.1
   git push
   git push --tags
   ```
3. O GitHub Actions roda os testes, gera o `.exe` e cria o Release sozinho. Quem já usa o programa recebe o aviso de atualização na próxima vez que abrir.

O repositório precisa ser **público** para o aviso de atualização e o download funcionarem. O endereço que o programa consulta está em `conversor_ftex/atualizacao.py` (`REPOSITORIO = 'marcola20/ConversorFTEX'`): se criar o repositório com outro nome, mude ali.
