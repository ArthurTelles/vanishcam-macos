# Solução de problemas

Os problemas da câmera virtual estão em [OBS.md](OBS.md#problemas-comuns). Aqui ficam os da instalação, da webcam, dos gestos e da janela.

Para diagnosticar, rode pelo Terminal, não pelo Finder, e leia as mensagens que começam com `[Webcam]`, `[Vanish Lab]`, `[Goku]` e `[Mãos]`.

## Instalação

**`Instale o Python 3.10 ou mais recente`**
O Python 3.9 do sistema não serve. Instale o uv (`brew install uv`), que baixa o Python 3.12 sozinho, ou o Python 3.12 (`brew install python@3.12`).

**A instalação das dependências falhou**
Apague o ambiente e tente de novo: `rm -rf .venv && ./VanishCam.command`. A primeira execução precisa de internet para baixar os pacotes e os modelos do MediaPipe.

**`Check failed: service_ Service is unavailable` ao abrir**
O `mediapipe` instalado é o 1.0.1, que aborta no macOS. O `requirements.txt` fixa o 1.2.0. Recrie o `.venv` como acima.

**Avisos `Class SDLApplication is implemented in both...`**
O `pygame` foi instalado no `.venv` do Mac. Ele traz uma cópia do SDL que conflita com a do OpenCV e pode derrubar o app. Remova com `.venv/bin/python -m pip uninstall pygame`. No macOS o som usa o `afplay` do sistema.

**Falha ao baixar os modelos**
Os modelos vão para `models/` na primeira execução. Atrás de proxy ou sem internet, baixe as URLs de `MODEL_URLS` em `vanish_cam.py` e salve com os mesmos nomes em `models/`.

## Webcam

**`Autorize o acesso à câmera` e nada acontece**
A permissão é pedida para o app de terminal (Terminal, iTerm, VS Code, Warp). Libere em **Ajustes do Sistema > Privacidade e Segurança > Câmera**, feche o terminal com **Cmd+Q** e abra de novo. Pelo Finder, quem pede a permissão é o Terminal.

**A prévia mostra o logo do OBS, ou a câmera errada**
A ordem das câmeras no OpenCV não é a mesma do `ffmpeg` nem a dos apps. Teste `--camera 0`, `--camera 1`, `--camera 2`. Em geral o `0` é a webcam embutida, e a OBS Virtual Camera e as câmeras externas vêm depois.

**Imagem escura ou lenta**
O AVFoundation entrega 1080p e o app reduz para 960 de largura. Se o processador estiver no limite, use `--width 640 --height 360`. Iluminação de frente ajuda a segmentação e os gestos.

## Fundo e efeito

**Eu não sumo, ou somem só partes de mim**
O fundo foi capturado com você no quadro. Aperte `ESPAÇO`, saia por completo por 4 segundos e só volte depois do sinal sonoro. Cabeça, ombro ou braço no canto já bastam para estragar o fundo.

**Depois do efeito a imagem fica parada**
É o esperado: a janela mostra o fundo capturado. Aperte `R` para reaparecer, ou repita o gesto no modo Goku.

**Se a câmera ou a luz mudar, aparecem manchas**
O fundo é uma foto fixa. Recapture com `ESPAÇO` sempre que mover a câmera, acender uma luz ou mudar algo no cenário.

**Uma cadeira ou um objeto aparece junto comigo**
O modelo de segmentação às vezes trata cadeiras gamer e encostos altos como parte da pessoa. Recapture o fundo com o objeto na mesma posição em que ele fica durante o uso.

## Gestos

Rode com `--gesture-debug` para ver no terminal o que o detector está vendo.

**O V não dispara (Normal e Particles)**
Mostre a palma para a câmera, com indicador e médio bem abertos e os outros dedos fechados. Mão inteira no quadro, a uns 50 cm a 1 m da câmera.

**As palmas não disparam (Naruto)**
Palmas encostadas, dedos lado a lado apontando para cima, sem entrelaçar, na altura do peito e de frente para a câmera.

**O Goku não teletransporta**
Indicador e médio esticados e juntos, encostados no meio da testa, por 1 segundo inteiro. O rosto precisa estar visível. O terminal mostra a contagem. Para voltar, baixe a mão antes de repetir o gesto, já que o app exige soltar a pose entre um teletransporte e outro.

## Janela

**Não consigo fechar a janela**
Use `Q` ou `ESC` com a janela em foco, o botão vermelho, **Encerrar** no Dock ou `Ctrl+C` no terminal. Se nada disso funcionar, o PyObjC não foi instalado. Recrie o `.venv`.

**A janela ficou só com a barra de título**
A janela do OpenCV nasce com altura 0. O app trava um tamanho mínimo e restaura o tamanho sozinho em até 1 segundo, avisando no terminal com `A janela do vídeo tinha encolhido`. Se continuar acontecendo, aperte `F` duas vezes para entrar e sair da tela cheia.

**O menu abre gigante ou desfocado**
O menu é desenhado em 2x para telas Retina e redimensionado depois do primeiro frame. Se aparecer grande por um instante, é normal.

**`Encerrar` no Dock mostra "Python" em vez de VanishCam**
O app roda dentro do Python do `.venv`, então o macOS mostra o nome e o ícone do Python. Isso é esperado.
