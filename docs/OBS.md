# Câmera virtual com OBS (Meet, Zoom, Teams e afins)

O VanishCam processa a webcam e entrega o vídeo com o efeito para uma câmera virtual chamada **OBS Virtual Camera**. Qualquer app que aceite escolher a câmera passa a ver o VanishCam no lugar da webcam.

No macOS o [pyvirtualcam](https://github.com/letmaik/pyvirtualcam) só tem um driver: a extensão de câmera do OBS Studio. O OBS precisa estar instalado, mas **não precisa ficar aberto**. O VanishCam escreve direto na extensão.

```
webcam ──> VanishCam (efeito) ──> OBS Virtual Camera ──> Meet / Zoom / Teams
                 │
                 └──> janela "Webcam - Preview" (prévia local)
```

## 1. Instalar o OBS Studio

Precisa ser a versão 30 ou mais recente. Pelo Homebrew:

```bash
brew install --cask obs
```

Ou baixe em [obsproject.com](https://obsproject.com/) e arraste o OBS para Aplicativos.

## 2. Ativar a extensão de câmera (uma vez só)

1. Abra o OBS. Se aparecer o assistente de configuração, pode cancelar.
2. No painel **Controles**, à direita, clique em **Iniciar câmera virtual**.
3. O macOS avisa que o OBS quer instalar uma extensão de câmera. Aprove:
   - **macOS 15 ou mais recente:** **Ajustes do Sistema > Geral > Itens de Início e Extensões**. Na lista **Por Categoria**, abra **Extensões de Câmera** e ligue o **OBS Virtual Camera**.
   - **macOS 13 e 14:** **Ajustes do Sistema > Privacidade e Segurança**. Perto do fim da página aparece um aviso sobre o software do sistema do OBS. Clique em **Permitir** e digite a senha.
4. Volte ao OBS e clique em **Parar câmera virtual**.
5. Feche o OBS com **Cmd+Q**.

O passo 4 importa. Enquanto o OBS estiver enviando a câmera virtual dele, o VanishCam não consegue usá-la.

Confira no Terminal se a extensão está ativa:

```bash
systemextensionsctl list | grep -i obs
```

O resultado precisa terminar com `[activated enabled]`. Para ver a câmera como o sistema enxerga:

```bash
system_profiler SPCameraDataType | grep -A2 "OBS Virtual Camera"
```

## 3. Abrir o VanishCam com a câmera virtual

```bash
./VanishCam.command --virtual-camera --no-mirror
```

- `--virtual-camera` faz o app parar com uma mensagem clara se a câmera virtual não estiver disponível, em vez de seguir só com a prévia.
- `--no-mirror` envia a imagem sem espelhar. Em chamada é o recomendado: o Meet e o Zoom já espelham a sua própria miniatura, e quem está do outro lado vê você do jeito certo, com textos legíveis.

Escolha um modo no menu. O terminal deve mostrar:

```
[Webcam] Saída virtual ativa: OBS Virtual Camera (960x540, até 30 FPS)
```

A câmera virtual só recebe imagem depois que um modo é escolhido. Antes disso, e depois que o VanishCam fecha, os apps mostram o logo do OBS ou uma tela preta.

## 4. Escolher a câmera no app da chamada

**Importante:** apps que já estavam abertos quando a extensão foi instalada não enxergam a câmera nova. Feche-os com **Cmd+Q**, não só a janela, e abra de novo. Isso vale principalmente para o Chrome, o Arc, o Edge e outros navegadores.

| App | Onde escolher |
| --- | --- |
| Google Meet (Chrome, Arc, Edge, Safari) | Na tela de entrada ou durante a chamada: **⋮ > Configurações > Vídeo > Câmera** |
| Zoom | **zoom.us > Configurações > Vídeo > Câmera**, ou a setinha ao lado de **Iniciar vídeo** |
| Microsoft Teams | Foto de perfil > **Configurações > Dispositivos > Câmera** |
| Slack (huddle) | Durante o huddle, a setinha ao lado do ícone de câmera |
| Discord | **Configurações de usuário > Voz e vídeo > Câmera** |
| FaceTime | Menu **Vídeo** na barra de menus, durante a chamada |
| Photo Booth | Menu **Câmera** |

No navegador, o site também precisa de permissão para a câmera. Se o Meet não listar câmera nenhuma, confira **Ajustes do Sistema > Privacidade e Segurança > Câmera** e libere o navegador.

## Dicas para usar em chamada

- Abra o VanishCam e capture o fundo **antes** de entrar na chamada, assim ninguém vê a calibração.
- Mantenha a janela **Webcam - Preview** aberta. Ela pode ficar atrás de outras janelas, mas fechar a janela fecha o app e a câmera virtual volta para o logo do OBS.
- Para trocar de modo no meio da chamada, aperte `M` na prévia. O fundo capturado é reaproveitado e a câmera virtual volta assim que você escolhe o próximo modo.
- O padrão é 960x540 a 30 FPS, suficiente para chamadas e leve para o processador. Para mais qualidade, use `--width 1280 --height 720`. O efeito fica mais pesado.

## E o som do efeito?

A câmera virtual leva só vídeo. Os sons do VanishCam tocam nos alto-falantes do Mac, e o microfone pode ou não captar, dependendo do volume e do cancelamento de eco do app da chamada. Para enviar o som de forma limpa você precisa de um áudio virtual, como o [BlackHole](https://github.com/ExistentialAudio/BlackHole) ou o Loopback, misturando o microfone com a saída do Mac. Isso não é configurado por este projeto.

## Alternativa: captura de janela pelo OBS

Útil se você quer compor o VanishCam com outras fontes no OBS (texto, overlay, cena com slides):

1. Abra o VanishCam com `./VanishCam.command --no-virtual-camera`.
2. No OBS, em **Fontes**, adicione **Captura de Janela (macOS 13+)** e escolha a janela **Webcam - Preview**.
3. Ajuste o recorte para tirar a barra de título.
4. Clique em **Iniciar câmera virtual** no OBS.

O OBS precisa da permissão **Gravação de Tela e Áudio do Sistema** em **Ajustes do Sistema > Privacidade e Segurança**. Nesse modo a qualidade depende do tamanho da janela, e a latência é um pouco maior.

## Problemas comuns

| Sintoma | Causa provável e solução |
| --- | --- |
| O Meet não lista a OBS Virtual Camera | O navegador foi aberto antes da extensão ser instalada. Feche com **Cmd+Q** e abra de novo |
| O app da chamada mostra o logo do OBS | O VanishCam não está rodando ou ainda está no menu. Escolha um modo |
| `Câmera virtual indisponível` no terminal | OBS ausente, versão anterior à 30, extensão não aprovada ou câmera virtual ligada no próprio OBS. Refaça o passo 2 |
| A imagem chega espelhada para os outros | Abra com `--no-mirror` |
| A prévia do VanishCam mostra o logo do OBS | O app abriu a OBS Virtual Camera como entrada. Use `--camera 0` ou teste outros índices |
| Imagem travada na chamada | A janela de prévia foi fechada ou o app travou. Abra o VanishCam de novo. Se a imagem não voltar, troque para outra câmera no app da chamada e volte para a OBS Virtual Camera |

Mais casos em [SOLUCAO_DE_PROBLEMAS.md](SOLUCAO_DE_PROBLEMAS.md).

## Remover a extensão

Para desinstalar a câmera virtual, abra o OBS, inicie e pare a câmera virtual e, em seguida, desligue o **OBS Virtual Camera** em **Ajustes do Sistema > Geral > Itens de Início e Extensões > Extensões de Câmera**. Apagar o OBS da pasta Aplicativos também remove a extensão.
