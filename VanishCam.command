#!/bin/bash
# Abre o VanishCam no macOS. Dá para clicar duas vezes no Finder ou rodar no Terminal.
set -euo pipefail
cd "$(dirname "$0")"

VENV_DIR=".venv"
VENV_PY="$VENV_DIR/bin/python"

fail() {
  echo
  echo "Não foi possível abrir o VanishCam. $1"
  exit 1
}

if [ ! -x "$VENV_PY" ]; then
  echo "[Vanish Lab] Criando o ambiente Python local..."
  if command -v uv >/dev/null 2>&1; then
    uv venv -q -p 3.12 "$VENV_DIR" || fail "O uv não conseguiu criar o ambiente."
  else
    PYTHON=""
    for candidate in python3.13 python3.12 python3.11 python3.10; do
      if command -v "$candidate" >/dev/null 2>&1; then PYTHON="$candidate"; break; fi
    done
    [ -n "$PYTHON" ] || fail "Instale o Python 3.10 ou mais recente: brew install python@3.12 (ou brew install uv)."
    "$PYTHON" -m venv "$VENV_DIR" || fail "O Python não conseguiu criar o ambiente."
  fi
fi

if ! "$VENV_PY" -c "import cv2, mediapipe, numpy, pyvirtualcam, AppKit" >/dev/null 2>&1; then
  echo "[Vanish Lab] Instalando os componentes. A internet só é necessária desta vez..."
  if command -v uv >/dev/null 2>&1; then
    uv pip install -q -p "$VENV_PY" -r requirements.txt || fail "A instalação das dependências falhou."
  else
    "$VENV_PY" -m pip install -q --upgrade pip && "$VENV_PY" -m pip install -q -r requirements.txt \
      || fail "A instalação das dependências falhou."
  fi
fi

echo "[Vanish Lab] Abrindo a webcam..."
PYTHONUNBUFFERED=1 exec "$VENV_PY" vanish_cam.py "$@"
