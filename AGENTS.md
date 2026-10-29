# Instruções para assistentes de IA

Este arquivo é para Claude Code, Codex, Cursor, Copilot e outros agentes que forem instalar, configurar ou modificar o VanishCam a pedido de alguém. O `CLAUDE.md` aponta para cá.

## O que é o projeto

App Python para macOS que lê a webcam, segmenta a pessoa com MediaPipe, reconhece gestos e aplica efeitos de desaparecimento (Normal, Naruto, Particles, Goku). O resultado aparece numa janela OpenCV (`Webcam - Preview`) e, opcionalmente, na câmera virtual do OBS via pyvirtualcam. Documentação para pessoas: `README.md`, `docs/OBS.md`, `docs/SOLUCAO_DE_PROBLEMAS.md` e `docs/PORTE_MACOS.md`.

## Instalar e verificar

Rode no diretório do repositório:

```bash
command -v uv || brew install uv
uv venv -p 3.12 .venv
uv pip install -p .venv/bin/python -r requirements.txt
.venv/bin/python -m unittest                     # não usa webcam nem câmera virtual
.venv/bin/python vanish_cam.py --self-test    # baixa os modelos para models/ e confere os assets
```

O `./VanishCam.command` faz a instalação sozinho, mas em seguida abre a janela e fica rodando. Para só preparar o ambiente, use os comandos acima.

Todos os testes precisam passar antes de qualquer commit.

## Configurar a câmera virtual (OBS)

Comandos que você pode rodar:

```bash
brew install --cask obs                                      # OBS 30+
systemextensionsctl list | grep -i obs                       # precisa terminar com [activated enabled]
system_profiler SPCameraDataType | grep "OBS Virtual Camera" # o sistema enxerga a câmera
```

Passos que **só a pessoa pode fazer**. Peça e espere a confirmação:

1. Abrir o OBS, clicar em **Iniciar câmera virtual**, aprovar a extensão em **Ajustes do Sistema > Geral > Itens de Início e Extensões > Extensões de Câmera** (macOS 15+) ou em **Privacidade e Segurança** (macOS 13 e 14), clicar em **Parar câmera virtual** e fechar o OBS.
2. Autorizar a câmera para o app de terminal na primeira execução.
3. Fechar com **Cmd+Q** e reabrir o navegador ou o app de videochamada que já estava aberto antes da extensão ser instalada.
4. Escolher **OBS Virtual Camera** no Meet, Zoom, Teams etc.

Detalhes e tabela de problemas em `docs/OBS.md`.

## Rodar o app

```bash
./VanishCam.command --virtual-camera --no-mirror   # para chamadas
./VanishCam.command --mode goku                    # pula o menu
```

- O app bloqueia o terminal enquanto estiver aberto. Se você rodar por uma ferramenta de shell, rode em segundo plano e acompanhe a saída.
- O menu só responde a clique ou às teclas `1` a `4` na janela. Sem interação humana, use `--mode`.
- Mensagens úteis na saída: `Saída virtual ativa: OBS Virtual Camera`, `Fundo pronto`, `[Goku] ...` e `A janela do vídeo tinha encolhido`.
- Encerrar: `Q`/`ESC` na janela, botão vermelho, **Encerrar** no Dock ou `SIGINT` no processo.

## Armadilhas conhecidas

- **Não use o Python 3.9 do sistema.** Use o `.venv` com Python 3.10+.
- **Não troque `mediapipe==1.2.0` pelo 1.0.1.** A 1.0.1 aborta no macOS com `Check failed: service_ Service is unavailable`.
- **Não instale `pygame` no macOS.** O SDL dele conflita com o do OpenCV. O som usa `afplay` (`vanish_sound.py`).
- **Não mande `osascript -e 'tell application "python" to quit'`.** O macOS pode abrir um diálogo "Onde está o python?" e o comando trava. Para testar o "Encerrar" do Dock, envie o Apple Event pelo PID com `NSAppleEventDescriptor`.
- **Janelas do OpenCV no Cocoa:** o `namedWindow` cria conteúdo com altura 0, o primeiro `imshow` redimensiona a janela para o tamanho da imagem (desfazendo `resizeWindow` anteriores), o mouse chega em coordenadas da imagem e `getWindowImageRect` devolve o tamanho da imagem, não da janela. Ajustes de janela ficam em `mac_window.py` e no-op fora do macOS.
- **Ordem das câmeras:** no OpenCV o índice 0 é a webcam embutida e a OBS Virtual Camera vem depois. No `ffmpeg -f avfoundation -list_devices true -i ""` a ordem é outra. Não use a lista do ffmpeg para escolher `--camera`.
- **Câmera virtual ocupada:** se o OBS estiver com a câmera virtual ligada, o pyvirtualcam falha. Ela precisa estar parada no OBS.
- **Fundo:** a pessoa precisa sair do quadro durante os 4 s de calibração. Não reintroduza a recusa automática de fundo com pessoa: cadeiras são segmentadas como pessoa e o fundo nunca é aceito.

## Arquivos que não vão para o Git

`.venv/`, `models/` (baixados na primeira execução), `__pycache__/` e `assets/instant_transmission.wav`. Esse último é um som com direitos autorais, de uso pessoal. Nunca faça commit dele nem de outro áudio ou imagem de terceiros. O modo Goku cai para `assets/teleport.wav`, gerado por `tools/make_teleport_sound.py`, quando ele não existe.

## Convenções de código

- Textos de interface, mensagens do terminal, comentários e documentação em português do Brasil.
- Frases sem ponto e vírgula. Separe com ponto ou vírgula.
- Mensagens do terminal com prefixo entre colchetes: `[Webcam]`, `[Vanish Lab]`, `[Goku]`.
- Nada de texto sobreposto ao vídeo. A prévia e a câmera virtual mostram só a imagem com o efeito.
- Cada efeito novo ganha seu módulo (`*_effect.py`), um item em `MODES` e em `menu_ui.ITEMS`, e testes que não dependem da webcam (veja `test_goku_particles.py` e `run_mock_video` em `test_video_output.py`).
- Commits e PRs descrevem o que muda e por quê, de forma impessoal.
