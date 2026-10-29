# VanishCam para macOS

Efeitos de desaparecimento na webcam ativados por gestos, rodando no macOS e saindo como câmera no Meet, Zoom, Teams e afins pela câmera virtual do OBS.

Este repositório é um fork do [vanish_webcam](https://github.com/Nicovic17/vanish_webcam), feito para Windows, adaptado para o macOS. Os detalhes técnicos da adaptação estão em [docs/PORTE_MACOS.md](docs/PORTE_MACOS.md).

O vídeo é processado no seu computador, sem gravação e sem envio a servidores. A prévia e a câmera virtual mostram só o vídeo com o efeito, sem menus nem textos por cima.

| Modo | Gesto | Efeito |
| --- | --- | --- |
| 1. Normal Vanish | V com indicador e médio | Você se dissolve no fundo em cerca de 3,6 s |
| 2. Naruto Vanish | Palmas juntas, dedos lado a lado | Nuvem de fumaça e um tronco cai no seu lugar |
| 3. Particles | V com indicador e médio | A silhueta vira fragmentos levados pelo vento |
| 4. Goku | Indicador e médio juntos na testa por 1 s | Teletransporte com linhas estilo mangá. Repita o gesto para voltar |

## Documentação

- [Guia rápido](#guia-rápido): do zero até a prévia aberta.
- [docs/OBS.md](docs/OBS.md): câmera virtual do OBS no Meet, Zoom, Teams, Slack e FaceTime.
- [docs/SOLUCAO_DE_PROBLEMAS.md](docs/SOLUCAO_DE_PROBLEMAS.md): erros conhecidos e como resolver.
- [docs/PORTE_MACOS.md](docs/PORTE_MACOS.md): o que mudou em relação ao original e por quê.
- [AGENTS.md](AGENTS.md): instruções para assistentes de IA (Claude Code, Codex, Cursor e outros) instalarem, configurarem e modificarem o projeto.

## Requisitos

- Mac com Apple Silicon. Testado no macOS 27 em arm64.
- [Homebrew](https://brew.sh).
- [uv](https://docs.astral.sh/uv/) (`brew install uv`) ou Python 3.10+ (`brew install python@3.12`). O Python 3.9 que vem com o macOS não serve.
- Webcam (a embutida do Mac ou uma USB).
- Opcional, para videochamadas: [OBS Studio](https://obsproject.com/) 30 ou mais recente (`brew install --cask obs`).

## Guia rápido

```bash
brew install uv
git clone https://github.com/ArthurTelles/vanishcam-macos.git
cd vanishcam-macos
./VanishCam.command
```

Também dá para clicar duas vezes em `VanishCam.command` no Finder. Na primeira vez o script cria o ambiente em `.venv`, instala as dependências de `requirements.txt` e baixa os modelos do MediaPipe para `models/`. A internet só é necessária nessa primeira execução.

1. **Permissão da câmera:** o macOS pede acesso à câmera para o app de terminal (Terminal, iTerm, VS Code...). Autorize. O app espera até 30 segundos pela resposta. Se você negou sem querer, libere em **Ajustes do Sistema > Privacidade e Segurança > Câmera** e abra o terminal de novo.
2. **Menu:** escolha o modo com o mouse ou com as teclas `1` a `4`.
3. **Fundo:** saia do enquadramento por 4 segundos enquanto o fundo é capturado. Saia por completo, sem cabeça, ombro ou braço aparecendo. O efeito troca você por esse fundo, e se você estiver nele vai continuar aparecendo. Um sinal sonoro avisa quando você pode voltar.
4. **Gesto:** volte e faça o gesto do modo escolhido.

Para usar como câmera numa videochamada, siga [docs/OBS.md](docs/OBS.md). Em resumo: instale o OBS, ative a câmera virtual dele uma vez, feche o OBS, abra o VanishCam com `./VanishCam.command --virtual-camera --no-mirror` e escolha **OBS Virtual Camera** no app da chamada.

## Modos em detalhe

**1. Normal Vanish:** faça um V com indicador e médio. A dissolução começa assim que o gesto é reconhecido e dura cerca de 3,6 segundos.

**2. Naruto Vanish:** junte as palmas na frente da webcam, com os dedos lado a lado, sem entrelaçar. Você some numa nuvem de fumaça e um tronco de madeira cai e fica no lugar até você apertar `R`. Toca `assets/vanish.MP3`.

**3. Particles:** o mesmo V do Normal. A silhueta se desfaz em pequenos fragmentos levados pelo vento para o lado. Dura cerca de 2,1 segundos. A silhueta é capturada uma vez no início para manter o vídeo fluido.

**4. Goku:** encoste indicador e médio juntos e esticados na testa por 1 segundo. Linhas verticais estilo mangá correm pela sua silhueta, você some em faixas verticais e as linhas ficam um instante no ar. Para reaparecer, baixe a mão e repita o gesto por mais 1 segundo. O retorno é o mesmo efeito ao contrário. Se você quebrar a pose, a contagem recomeça, e o terminal mostra a contagem. Neste modo, `V` e `R` ficam desativados.

O modo Goku toca `assets/teleport.wav`, um som sintetizado pelo próprio projeto. Se quiser o som original do Instant Transmission, veja [Som do modo Goku](#som-do-modo-goku).

Para abrir um modo direto, sem menu:

```bash
./VanishCam.command --mode goku
./VanishCam.command --mode particles
./VanishCam.command --mode naruto
./VanishCam.command --mode normal
```

## Comandos

Com a janela de prévia em foco:

| Tecla | Ação |
| --- | --- |
| `ESPAÇO` | Captura um novo fundo |
| `R` | Faz a pessoa reaparecer |
| `V` | Dispara o efeito manualmente |
| `M` | Volta ao menu para trocar de modo, reaproveitando o fundo já capturado |
| `F` | Alterna tela cheia |
| `Q` ou `ESC` | Sai e libera as câmeras |

O botão vermelho da janela, **Encerrar** no Dock e `Ctrl+C` no terminal também fecham o app.

Depois que o efeito termina, a janela mostra só o fundo capturado, parado. Isso é esperado. Aperte `R`, ou repita o gesto no modo Goku, para reaparecer.

## Opções de linha de comando

| Opção | Padrão | Descrição |
| --- | --- | --- |
| `--mode {normal,naruto,particles,goku}` | menu | Pula o menu e abre o modo |
| `--camera N` | `0` | Índice da webcam. Use `1`, `2`... para câmeras externas ou o iPhone (Câmera de Continuidade) |
| `--width` / `--height` | `960` / `540` | Tamanho do vídeo processado e enviado à câmera virtual |
| `--fps` | `30` | FPS máximo da câmera virtual |
| `--no-mirror` | espelhado | Não espelha a imagem. Recomendado em chamadas |
| `--fullscreen` | janela | Abre em tela cheia |
| `--virtual-camera` | automático | Exige a câmera virtual e para com erro se ela não estiver disponível |
| `--no-virtual-camera` | automático | Usa só a prévia local |
| `--virtual-device NOME` | automático | Nome do dispositivo virtual. No macOS só existe `OBS Virtual Camera` |
| `--gesture-debug` | desligado | Mostra no terminal o estado do reconhecimento de gestos |

Sem `--virtual-camera` nem `--no-virtual-camera`, o app usa a câmera virtual se ela estiver disponível e segue só com a prévia se não estiver.

O AVFoundation costuma ignorar a resolução pedida e entregar 1080p. O app reduz o frame para a largura de `--width` para manter o efeito leve.

## Som do modo Goku

O som original do Instant Transmission tem direitos autorais e não faz parte deste repositório. O arquivo `assets/instant_transmission.wav` está no `.gitignore`. Se ele existir, o modo Goku toca esse arquivo no lugar do `teleport.wav` sintetizado.

Para usar um som seu, para uso pessoal, coloque qualquer WAV curto, de preferência com menos de 1 segundo e sem silêncio no começo, em `assets/instant_transmission.wav`. Para cortar o silêncio inicial de um arquivo que você já tem:

```bash
ffmpeg -i seu_audio.wav \
  -af "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.01" \
  -ar 44100 -ac 2 assets/instant_transmission.wav
```

Os sons tocam só nos alto-falantes do Mac. A câmera virtual leva apenas vídeo, então quem está na chamada não ouve o efeito. Veja [docs/OBS.md](docs/OBS.md#e-o-som-do-efeito) para alternativas.

## Testes

```bash
.venv/bin/python -m unittest
.venv/bin/python vanish_cam.py --self-test   # carrega todos os modelos e assets, sem abrir a webcam
```

Os testes não usam a webcam nem a câmera virtual.

## Estrutura

| Arquivo | Conteúdo |
| --- | --- |
| `VanishCam.command` | Lançador. Cria o `.venv`, instala dependências e abre o app |
| `vanish_cam.py` | App principal: menu, câmera, calibração do fundo, gestos, modos Normal e Naruto, câmera virtual |
| `menu_ui.py` | Menu inicial no estilo dos apps da Apple, desenhado com Pillow e a fonte SF |
| `mac_window.py` | Ajustes das janelas do OpenCV no macOS via PyObjC |
| `goku_effect.py` | Detecção da pose e efeito do modo Goku |
| `particles_effect.py` | Efeito do modo Particles |
| `naruto_effect.py` | Fumaça e tronco do modo Naruto |
| `vanish_sound.py` | Sons sem travar o vídeo (`afplay` no macOS) |
| `tools/make_teleport_sound.py` | Gera `assets/teleport.wav` |
| `hand_landmarker.task` | Modelo de mãos do MediaPipe, versionado como no original |
| `models/` | Demais modelos, baixados na primeira execução (fora do Git) |

## Créditos

- App original, efeitos Normal e Naruto, sprite do tronco e `assets/vanish.MP3`: [vanish_webcam](https://github.com/Nicovic17/vanish_webcam).
- Modelos de segmentação, gestos, mãos e rosto: [MediaPipe](https://ai.google.dev/edge/mediapipe/solutions/guide), do Google.
- Câmera virtual: [pyvirtualcam](https://github.com/letmaik/pyvirtualcam) com a extensão de câmera do [OBS Studio](https://obsproject.com/).

O repositório original não declara licença. Este fork mantém o histórico e o crédito do original, e as mudanças feitas aqui seguem os mesmos termos.
