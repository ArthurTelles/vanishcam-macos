# Como foi feito o porte para o macOS

O [vanish_webcam](https://github.com/Nicovic17/vanish_webcam) original foi feito para Windows: lançadores `.bat`, executável gerado pelo PyInstaller, câmera aberta pelo DirectShow e som pelo `pygame`. Este documento lista cada obstáculo encontrado no macOS e a solução adotada, para quem quiser repetir o processo em outra máquina ou levar outro app OpenCV + MediaPipe para o Mac.

Ambiente de referência: MacBook Pro com Apple Silicon, macOS 27, Python 3.12 (via uv), OpenCV 5.0, MediaPipe 1.2.0, pyvirtualcam 0.15, OBS Studio 33.

## Resumo das mudanças

| Área | Original (Windows) | Este fork (macOS) |
| --- | --- | --- |
| Lançador | `AVVIA_LOCALE.bat`, `AVVIA_VIRTUAL.bat`, `AVVIA_OBS.bat` | `VanishCam.command` |
| Distribuição | `VanishCam.exe` via PyInstaller (`VanishCam.spec`, `BUILD_WINDOWS.bat`) | Ambiente `.venv` criado na primeira execução |
| Python | Instalado no Windows ou embutido no `.exe` | 3.10+ num `.venv`, o 3.9 do sistema não serve |
| MediaPipe | 1.0.1 | 1.2.0 |
| Câmera | `CAP_DSHOW` | `CAP_AVFOUNDATION`, com espera pela permissão |
| Som | `pygame` | `afplay` do sistema |
| Janela | OpenCV puro | OpenCV + ajustes via PyObjC (`mac_window.py`) |
| Câmera virtual | OBS ou Unity Capture | Só a extensão de câmera do OBS |
| Modos | Normal e Naruto no código. Particles e Goku só no README | Os quatro modos implementados |
| Menu | Desenhado com OpenCV | Estilo dos apps da Apple, com Pillow e a fonte SF (`menu_ui.py`) |
| Idioma | Italiano e inglês | Português |

Arquivos removidos por serem só do Windows ou sem uso: os `.bat`, `VanishCam.spec`, `assets/vanish_icon.ico`, `run3.py` (versão antiga do script principal) e `face_landmarker.task` (o código atual não usa). O `vanish_cam.py` ainda tem os caminhos de Windows (`CAP_DSHOW`, `pygame`), mas só o macOS é testado aqui. Para Windows, use o original.

## Obstáculos e soluções

### 1. MediaPipe 1.0.1 aborta no macOS

Ao criar qualquer detector, o processo morre com:

```
Check failed: service_ Service is unavailable
```

O erro vem da inicialização do Metal dentro do MediaPipe 1.0.1. A versão 1.2.0 corrige. O `requirements.txt` fixa `mediapipe==1.2.0`.

### 2. Python do sistema

O projeto usa sintaxe e dependências de Python 3.10+ e foi testado no 3.12. O macOS traz o 3.9, das Command Line Tools. O `VanishCam.command` usa o uv (`uv venv -p 3.12`) se ele estiver instalado. Senão, procura `python3.13` a `python3.10` no PATH.

### 3. Permissão da câmera

No macOS a permissão é dada ao app que abriu o processo (Terminal, iTerm, VS Code). Na primeira execução o `cv2.VideoCapture` falha na hora, enquanto o pedido de permissão ainda está na tela. O `open_camera` tenta de novo a cada segundo por até 30 segundos e explica onde liberar o acesso.

### 4. Resolução da câmera

O AVFoundation ignora `CAP_PROP_FRAME_WIDTH` e entrega 1080p na maioria das webcams do Mac. Processar 1080p com segmentação e mãos a cada frame deixa o vídeo lento. O `fit_frame` reduz cada frame para a largura de `--width` (960 por padrão) antes de qualquer processamento.

### 5. Som: pygame e OpenCV não convivem

O `pygame` e o `opencv-python` trazem cada um a sua cópia do SDL. No macOS isso gera `Class SDLApplication is implemented in both...` e pode derrubar o app. O `pygame` deixou de ser instalado no macOS (`sys_platform != "darwin"` no `requirements.txt`), e o `vanish_sound.py` toca os sons com `afplay`, que já vem com o sistema, num subprocesso que não bloqueia o vídeo.

### 6. A janela não fechava

O backend Cocoa do OpenCV cria a janela sem o botão vermelho habilitado e ignora o Apple Event de encerrar que o Dock envia. A única saída era `Q` ou `ESC`, e se o app travasse não havia como fechar. O `mac_window.prepare_windows()` usa PyObjC para:

- acrescentar `NSWindowStyleMaskClosable` às janelas, e o loop principal detecta o fechamento por `cv2.WND_PROP_VISIBLE`.
- registrar um handler para o Apple Event `aevt/quit`, que liga uma flag lida pelo loop principal.

### 7. A janela encolhia até sobrar só a barra de título

O `cv2.namedWindow` no Cocoa cria a janela com altura de conteúdo 0, e só o primeiro `imshow` dá a ela o tamanho da imagem. Depois disso nada impede que ela seja reduzida a 0 de altura, e o OpenCV não volta a ajustar. O app:

- chama `mac_window.lock_window()` depois do primeiro frame para fixar um tamanho mínimo de 1/4 da imagem e a proporção do vídeo.
- confere `mac_window.content_height()` a cada 30 frames e, se a área de vídeo tiver menos de 60 pontos, restaura o tamanho com `cv2.resizeWindow`.

### 8. Menu nítido em tela Retina

Desenhado com `cv2.putText`, o menu ficava serrilhado e com cara de app antigo. O `menu_ui.py` desenha o menu com Pillow em 2x, usando a fonte variável SF Pro (`/System/Library/Fonts/SFNS.ttf`, com os eixos de peso e tamanho óptico) e os emojis da Apple convertidos em silhuetas brancas sobre quadrados coloridos, como no app Ajustes. Cores do modo escuro do sistema, segundo as Human Interface Guidelines.

Duas pegadinhas do OpenCV no Cocoa:

- o primeiro `imshow` redimensiona a janela para o tamanho da imagem, desfazendo um `resizeWindow` anterior. O menu chama `resizeWindow` de novo depois do primeiro frame, para a imagem 2x caber em 520x440 pontos.
- as coordenadas do mouse chegam na escala da imagem, não da janela. O `hit_test` divide por `SCALE`.

### 9. Câmera virtual

No macOS o pyvirtualcam só suporta a extensão de câmera do OBS 30+, uma Camera Extension do sistema. O VanishCam escreve direto nela, sem precisar do OBS aberto. Os apps de videochamada só enxergam a extensão se forem abertos depois da instalação. Passo a passo em [OBS.md](OBS.md).

No OpenCV a OBS Virtual Camera também aparece como câmera de entrada, logo depois da webcam embutida. Por isso `--camera 0` é o padrão, e um índice errado faz a prévia mostrar o logo do OBS.

### 10. Fundo capturado com a pessoa

O efeito troca a pessoa pelo fundo capturado nos primeiros 4 segundos. Se a pessoa ainda estiver no quadro, ela fica gravada no fundo e "não some". No original o único aviso de que a captura terminou era uma linha no terminal, fácil de perder com o rosto longe do teclado. Agora a calibração mostra a contagem no terminal e toca um sinal sonoro (`Glass.aiff`) quando termina.

Durante o porte foi testada uma verificação automática que recusava o fundo se o segmentador visse uma pessoa nele. Ela foi descartada: uma cadeira gamer vazia era segmentada como pessoa, e até o detector de rosto via um rosto no encosto com 0,91 de confiança, então o fundo nunca era aceito.

### 11. Trocar de modo sem fechar

No original, trocar de modo exigia fechar e abrir o app. Agora `M` volta ao menu. O `run()` mantém o fundo capturado entre os modos e só recaptura se a resolução mudar.

### 12. Modos Particles e Goku

O README original descrevia os dois, mas o código publicado só tinha Normal e Naruto. Este fork implementa:

- **Particles** (`particles_effect.py`): captura a silhueta uma vez, divide em células de 5 px e lança cada célula com o vento, com renderização vetorizada no NumPy.
- **Goku** (`goku_effect.py`): o detector de rosto BlazeFace acha a testa e o `hand_landmarker.task` acha os dedos. A pose precisa durar 1 segundo e ser solta antes de valer de novo. O efeito usa linhas verticais estilo mangá e faixas que somem, e o retorno é o mesmo efeito ao contrário.

O som do Goku é `assets/teleport.wav`, gerado por `tools/make_teleport_sound.py`. O som original do Instant Transmission tem direitos autorais e não é distribuído. Quem tiver o arquivo pode colocá-lo em `assets/instant_transmission.wav`, que está no `.gitignore`.

## Testes

Os testes do original esperavam um número de tentativas antigo no reconhecimento de gestos (`MultiViewGestureRecognizer`) e falhavam. Eles foram atualizados para o comportamento atual: 3 vistas por tentativa. Foram acrescentados testes para o menu, os modos Particles e Goku, a troca de modo com `M` e o reaproveitamento do fundo.

```bash
.venv/bin/python -m unittest
```

## Para portar outro app OpenCV + MediaPipe para o Mac

1. Use Python 3.10+ num `.venv`, nunca o do sistema.
2. Use MediaPipe 1.2.0 ou mais recente.
3. Abra a câmera com `cv2.CAP_AVFOUNDATION` e repita a abertura enquanto a permissão é pedida.
4. Não instale `pygame` junto do OpenCV no Mac. Toque sons com `afplay`.
5. Para fechar pelo botão vermelho e pelo Dock, ajuste as janelas via PyObjC como em `mac_window.py`.
6. Fixe o tamanho mínimo das janelas depois do primeiro `imshow`.
7. Para câmera virtual, use o pyvirtualcam com o OBS 30+.
