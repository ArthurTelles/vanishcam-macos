"""Ajustes das janelas do OpenCV no macOS: botão de fechar e "Encerrar" do Dock.

O OpenCV cria a janela sem o botão vermelho habilitado e não responde ao Apple
Event de encerrar que o Dock envia. Sem isto, a única saída é Q ou ESC.
"""

from __future__ import annotations

import sys

try:
    from AppKit import NSApp, NSWindowStyleMaskClosable
    from Foundation import NSAppleEventManager, NSObject
except ImportError:  # Fora do macOS, ou sem PyObjC: tudo vira no-op.
    NSApp = None


QUIT_REQUESTED = False
_quit_handler = None


if NSApp is not None:
    class _QuitHandler(NSObject):
        def handleQuit_withReply_(self, event, reply):
            global QUIT_REQUESTED
            QUIT_REQUESTED = True


def prepare_windows() -> None:
    """Habilita o botão de fechar e passa a atender o "Encerrar" do Dock.

    Chamar depois de cv2.namedWindow, quando a aplicação Cocoa já existe.
    """
    global _quit_handler
    if NSApp is None or sys.platform != "darwin":
        return
    app = NSApp()
    if app is None:
        return
    for window in app.windows():
        window.setStyleMask_(window.styleMask() | NSWindowStyleMaskClosable)
    if _quit_handler is None:
        _quit_handler = _QuitHandler.alloc().init()
        NSAppleEventManager.sharedAppleEventManager().setEventHandler_andSelector_forEventClass_andEventID_(
            _quit_handler, b"handleQuit:withReply:",
            int.from_bytes(b"aevt", "big"), int.from_bytes(b"quit", "big"),
        )


def quit_requested() -> bool:
    return QUIT_REQUESTED


def _window(title: str):
    if NSApp is None or sys.platform != "darwin" or NSApp() is None:
        return None
    for window in NSApp().windows():
        if window.title() == title:
            return window
    return None


def lock_window(title: str, width: int, height: int) -> None:
    """Impede que a janela seja arrastada até sumir e mantém a proporção da imagem.

    A janela do OpenCV nasce sem tamanho mínimo e pode ficar só com a barra de título.
    """
    window = _window(title)
    if window is not None:
        window.setContentMinSize_((width / 4, height / 4))
        window.setContentAspectRatio_((width, height))


def content_height(title: str) -> float | None:
    """Altura da área de vídeo da janela, em pontos, ou None fora do macOS."""
    window = _window(title)
    if window is None:
        return None
    return float(window.contentRectForFrameRect_(window.frame()).size.height)
