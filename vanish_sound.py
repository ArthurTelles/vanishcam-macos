"""Toca os efeitos sonoros sem bloquear os frames de vídeo."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ASSETS_DIR = Path(__file__).resolve().parent / "assets"
SOUND_PATH = ASSETS_DIR / "vanish.MP3"
# Som oficial do Instant Transmission, de uso pessoal: fica fora do controle de versão.
# Sem ele, o modo Goku usa o "zip" sintetizado por tools/make_teleport_sound.py.
INSTANT_TRANSMISSION_PATH = ASSETS_DIR / "instant_transmission.wav"
TELEPORT_SOUND_PATH = (INSTANT_TRANSMISSION_PATH if INSTANT_TRANSMISSION_PATH.is_file()
                       else ASSETS_DIR / "teleport.wav")


class VanishSound:
    def __init__(self, path: Path = SOUND_PATH):
        if not path.is_file():
            raise RuntimeError(f"Áudio não encontrado: {path}")
        self.path = path
        self.process = None
        self.command = None

        # No macOS o afplay já vem com o sistema. O pygame traz uma cópia do SDL
        # que conflita com a do OpenCV e pode derrubar o app.
        if sys.platform == "darwin" and shutil.which("afplay"):
            self.command = [shutil.which("afplay"), str(path)]
            return

        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        try:
            from pygame import mixer
        except ImportError:
            ffplay = shutil.which("ffplay")
            if ffplay is None:
                raise RuntimeError(f"Para tocar {path.name} instale pygame ou ffplay.")
            self.command = [ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet", "-i", str(path)]
            return

        self.mixer = mixer
        self.owns_mixer = mixer.get_init() is None
        try:
            if self.owns_mixer:
                mixer.init(frequency=44100, size=-16, channels=2, buffer=256)
            self.sound = mixer.Sound(str(path))  # Decodifica uma vez, antes de abrir a webcam.
        except Exception as error:
            if self.owns_mixer:
                mixer.quit()
            raise RuntimeError(f"Não foi possível abrir o áudio: {error}") from error

    def play(self) -> None:
        if self.command is not None:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
            try:
                self.process = subprocess.Popen(
                    self.command,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except OSError as error:
                raise RuntimeError(f"Não foi possível tocar o áudio: {error}") from error
            return
        self.sound.stop()
        if self.sound.play() is None:
            raise RuntimeError("Não foi possível tocar o áudio: nenhum canal livre.")

    def close(self) -> None:
        if self.command is not None:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
            return
        if self.owns_mixer:
            self.mixer.quit()
            self.owns_mixer = False
