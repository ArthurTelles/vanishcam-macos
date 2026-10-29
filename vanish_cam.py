"""Webcam local com efeitos de desaparecimento ativados por gestos."""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from contextlib import ExitStack
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

import mac_window
import menu_ui
from goku_effect import GokuPoseDetector, GokuTeleport
from naruto_effect import (
    EFFECT_SECONDS, joined_hands_from_landmarks, landed_log_anchor,
    load_log, overlay_log, render_substitution, substitution_anchor,
)
from particles_effect import PARTICLE_SECONDS, ParticleBurst
from vanish_sound import SOUND_PATH, TELEPORT_SOUND_PATH, VanishSound


APP_DIR = Path(__file__).resolve().parent
MODEL_DIR = APP_DIR / "models"
WINDOW_NAME = "Webcam - Preview"
MODES = ("normal", "naruto", "particles", "goku")
MENU_TITLE = "VanishCam"

SEGMENTER_MODEL = MODEL_DIR / "selfie_segmenter_landscape.tflite"
GESTURE_MODEL = MODEL_DIR / "gesture_recognizer.task"
FACE_MODEL = MODEL_DIR / "blaze_face_short_range.tflite"
HAND_MODEL = APP_DIR / "hand_landmarker.task"

MODEL_URLS = {
    SEGMENTER_MODEL: (
        "https://storage.googleapis.com/mediapipe-models/image_segmenter/"
        "selfie_segmenter_landscape/float16/latest/"
        "selfie_segmenter_landscape.tflite"
    ),
    GESTURE_MODEL: (
        "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/"
        "gesture_recognizer/float16/1/gesture_recognizer.task"
    ),
    FACE_MODEL: (
        "https://storage.googleapis.com/mediapipe-models/face_detector/"
        "blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
    ),
}
MODE_MODELS = {
    "normal": (SEGMENTER_MODEL, GESTURE_MODEL),
    "particles": (SEGMENTER_MODEL, GESTURE_MODEL),
    "naruto": (SEGMENTER_MODEL,),
    "goku": (SEGMENTER_MODEL, FACE_MODEL),
}

CALIBRATION_SECONDS = 4.0
BACKGROUND_SAMPLE_SECONDS = 0.55
VANISH_SECONDS = 3.6
GESTURE_INTERVAL_SECONDS = 0.14
CAMERA_PERMISSION_SECONDS = 30.0
READY_SOUND_PATH = Path("/System/Library/Sounds/Glass.aiff")


@dataclass
class AppState:
    phase: str = "calibrating"
    calibration_started: float = 0.0
    vanish_started: float | None = None
    last_gesture_check: float = 0.0
    fullscreen: bool = False


def positive_fps(value: str) -> float:
    fps = float(value)
    if not np.isfinite(fps) or not 1 <= fps <= 120:
        raise argparse.ArgumentTypeError("O FPS precisa estar entre 1 e 120.")
    return fps


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Escolha Normal Vanish, Naruto Vanish, Particles ou Goku para a webcam."
    )
    parser.add_argument("--camera", type=int, default=0, help="Índice da webcam")
    parser.add_argument("--width", type=int, default=960, help="Largura do vídeo")
    parser.add_argument("--height", type=int, default=540, help="Altura do vídeo")
    parser.add_argument(
        "--fullscreen", action="store_true", help="Abre em tela cheia"
    )
    parser.add_argument(
        "--no-mirror", action="store_true", help="Não espelha a webcam"
    )
    parser.add_argument("--fps", type=positive_fps, default=30.0, help="FPS máximo da saída virtual (padrão: 30)")
    parser.add_argument(
        "--virtual-camera", action=argparse.BooleanOptionalAction, default=None,
        help="Exige a câmera virtual. Por padrão ela é usada se estiver disponível. --no-virtual-camera desativa",
    )
    parser.add_argument(
        "--virtual-backend", choices=("obs", "unitycapture", "v4l2loopback"),
        help="Driver da câmera virtual (no macOS só existe obs)",
    )
    parser.add_argument("--virtual-device", help="Nome do dispositivo virtual")
    parser.add_argument(
        "--mode", choices=MODES,
        help="Pula o menu inicial e abre direto o modo escolhido",
    )
    parser.add_argument(
        "--gesture-debug", action="store_true",
        help="Mostra no terminal o estado do reconhecimento (sem texto no vídeo)",
    )
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def choose_mode() -> str | None:
    """Menu de teclado e mouse antes do vídeo limpo.

    Depois da escolha o menu fica aberto mostrando "Abrindo a câmera" até o
    primeiro frame aparecer. Quem chama fecha com close_menu().
    """
    state = {"hovered": None, "selected": None}

    def on_mouse(event, x, y, flags, userdata):
        state["hovered"] = menu_ui.hit_test(x, y)
        if event == cv2.EVENT_LBUTTONUP and state["hovered"] is not None:
            state["selected"] = state["hovered"]

    # A imagem tem o dobro da resolução e a janela o tamanho em pontos: texto nítido no Retina.
    cv2.namedWindow(MENU_TITLE, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(MENU_TITLE, menu_ui.WIDTH, menu_ui.HEIGHT)
    mac_window.prepare_windows()
    cv2.setMouseCallback(MENU_TITLE, on_mouse)
    sized = False
    while state["selected"] is None:
        cv2.imshow(MENU_TITLE, menu_ui.render(state["hovered"]))
        key = cv2.waitKey(30) & 0xFF
        if not sized:
            # O primeiro imshow ajusta a janela ao tamanho da imagem (2x). Volta ao tamanho em pontos.
            cv2.resizeWindow(MENU_TITLE, menu_ui.WIDTH, menu_ui.HEIGHT)
            mac_window.lock_window(MENU_TITLE, menu_ui.WIDTH, menu_ui.HEIGHT)
            sized = True
        if ord("1") <= key <= ord("4"):
            state["selected"] = MODES[key - ord("1")]
        elif key in (ord("q"), 27) or mac_window.quit_requested() or (
            cv2.getWindowProperty(MENU_TITLE, cv2.WND_PROP_VISIBLE) < 1
        ):
            close_menu()
            return None

    mode = state["selected"]
    print(f"[Webcam] Modo escolhido: {mode}. Carregando os modelos e abrindo a câmera...")
    cv2.imshow(MENU_TITLE, menu_ui.render(chosen=mode))
    # O macOS só pinta a janela quando o loop de eventos roda. Dá a ele alguns
    # ciclos antes do carregamento, que bloqueia a interface por alguns segundos.
    for _ in range(3):
        cv2.waitKey(10)
    return mode


def close_menu() -> None:
    cv2.destroyWindow(MENU_TITLE)
    cv2.waitKey(1)  # No macOS a janela só some quando o loop de eventos roda.


def open_virtual_camera(args: argparse.Namespace, width: int, height: int):
    if args.virtual_camera is False:
        return None
    try:
        import pyvirtualcam

        camera = pyvirtualcam.Camera(
            width=width, height=height, fps=args.fps,
            fmt=pyvirtualcam.PixelFormat.BGR,
            backend=args.virtual_backend, device=args.virtual_device,
        )
    except (ImportError, RuntimeError, OSError, ValueError) as error:
        if platform.system() == "Darwin":
            hint = (
                "Instale o OBS Studio 30 ou mais recente, clique uma vez em "
                "'Iniciar câmera virtual' para instalar a extensão do sistema "
                "(aprove em Ajustes do Sistema) e depois pare a câmera virtual no OBS."
            )
        else:
            hint = (
                "Instale o OBS Studio (com o driver OBS Virtual Camera) ou o Unity Capture. "
                "Se usar o OBS, pare a câmera virtual dele."
            )
        message = f"Câmera virtual indisponível. {hint} Detalhe: {error}"
        if args.virtual_camera is True or args.virtual_backend or args.virtual_device:
            raise RuntimeError(message) from error
        print(f"[Webcam] {message}\n[Webcam] Seguindo só com a prévia local.")
        return None
    print(f"[Webcam] Saída virtual ativa: {camera.device} ({width}x{height}, até {args.fps:g} FPS)")
    return camera


def send_virtual_frame(camera, frame: np.ndarray) -> None:
    if frame.shape[:2] != (camera.height, camera.width):
        frame = cv2.resize(frame, (camera.width, camera.height), interpolation=cv2.INTER_LINEAR)
    camera.send(np.ascontiguousarray(frame))


def download_models(mode: str | None = None) -> None:
    """Baixa os modelos do modo escolhido, ou todos quando mode é None."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    needed = MODE_MODELS[mode] if mode else tuple(MODEL_URLS)
    for destination in needed:
        url = MODEL_URLS[destination]
        if destination.exists() and destination.stat().st_size > 100_000:
            continue

        temporary = destination.with_suffix(destination.suffix + ".part")
        print(f"[Vanish Lab] Baixando {destination.name}...")
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "Vanish-Lab/1.0"}
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                total = int(response.headers.get("Content-Length", 0))
                received = 0
                with temporary.open("wb") as output:
                    while chunk := response.read(1024 * 256):
                        output.write(chunk)
                        received += len(chunk)
                        if total:
                            percent = int(received * 100 / total)
                            print(f"\r  {percent:3d}%", end="", flush=True)
            print()
            os.replace(temporary, destination)
        except (OSError, urllib.error.URLError) as error:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(
                "Não foi possível baixar os modelos do MediaPipe. "
                "Confira a conexão com a internet e tente de novo."
            ) from error


def _open_capture(index: int) -> cv2.VideoCapture:
    system = platform.system()
    if system == "Windows":
        capture = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not capture.isOpened():
            capture.release()
            capture = cv2.VideoCapture(index)
        return capture
    if system == "Darwin":
        return cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
    return cv2.VideoCapture(index)


def open_camera(index: int, width: int, height: int) -> cv2.VideoCapture:
    capture = _open_capture(index)
    if not capture.isOpened() and platform.system() == "Darwin":
        # Na primeira vez o macOS pede permissão e a abertura falha até a
        # pessoa responder. Tenta de novo enquanto o pedido estiver na tela.
        print("[Webcam] Autorize o acesso à câmera na janela do macOS "
              "(Ajustes do Sistema > Privacidade e Segurança > Câmera).")
        deadline = time.monotonic() + CAMERA_PERMISSION_SECONDS
        while not capture.isOpened() and time.monotonic() < deadline:
            capture.release()
            time.sleep(1.0)
            capture = _open_capture(index)

    if not capture.isOpened():
        hint = (
            " No macOS, libere o app do Terminal em Ajustes do Sistema > "
            "Privacidade e Segurança > Câmera e abra o Terminal de novo."
            if platform.system() == "Darwin" else ""
        )
        raise RuntimeError(
            f"Webcam {index} indisponível. Feche outros apps que usam a câmera ou tente --camera 1.{hint}"
        )

    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return capture


def fit_frame(frame: np.ndarray, width: int) -> np.ndarray:
    """O AVFoundation costuma ignorar a resolução pedida e entregar 1080p.
    Reduz para a largura escolhida, mantendo a proporção, para não pesar no efeito."""
    frame_height, frame_width = frame.shape[:2]
    if frame_width <= width * 1.05:
        return frame
    new_height = round(frame_height * width / frame_width)
    return cv2.resize(frame, (width, new_height), interpolation=cv2.INTER_AREA)


def create_tasks(mode: str = "normal"):
    segmenter_options = vision.ImageSegmenterOptions(
        base_options=python.BaseOptions(model_asset_path=str(SEGMENTER_MODEL)),
        running_mode=vision.RunningMode.VIDEO,
        output_confidence_masks=True,
        output_category_mask=False,
    )
    if mode in ("naruto", "goku") and not HAND_MODEL.is_file():
        raise RuntimeError(f"Modelo das mãos não encontrado: {HAND_MODEL}")

    if mode == "goku":
        hand_options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(HAND_MODEL)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.35,
            min_hand_presence_confidence=0.35,
            min_tracking_confidence=0.45,
        )
        face_options = vision.FaceDetectorOptions(
            base_options=python.BaseOptions(model_asset_path=str(FACE_MODEL)),
            running_mode=vision.RunningMode.VIDEO,
            min_detection_confidence=0.5,
        )
        segmenter = vision.ImageSegmenter.create_from_options(segmenter_options)
        try:
            hands = vision.HandLandmarker.create_from_options(hand_options)
            try:
                faces = vision.FaceDetector.create_from_options(face_options)
            except Exception:
                hands.close()
                raise
        except Exception:
            segmenter.close()
            raise
        return segmenter, GokuPoseDetector(hands, faces)

    if mode == "naruto":
        options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(HAND_MODEL)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.35,
            min_hand_presence_confidence=0.35,
            min_tracking_confidence=0.45,
        )
        task_class = vision.HandLandmarker
        wrapper_class = MultiViewHandLandmarker
    else:
        classifier_options = mp.tasks.components.processors.ClassifierOptions(
            score_threshold=0.55,
            category_allowlist=["Victory"],
        )
        options = vision.GestureRecognizerOptions(
            base_options=python.BaseOptions(model_asset_path=str(GESTURE_MODEL)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.35,
            min_hand_presence_confidence=0.35,
            min_tracking_confidence=0.5,
            canned_gesture_classifier_options=classifier_options,
        )
        task_class = vision.GestureRecognizer
        wrapper_class = MultiViewGestureRecognizer

    segmenter = vision.ImageSegmenter.create_from_options(segmenter_options)
    try:
        primary = task_class.create_from_options(options)
        try:
            alternate = task_class.create_from_options(
                replace(options, running_mode=vision.RunningMode.IMAGE)
            )
        except Exception:
            primary.close()
            raise
    except Exception:
        segmenter.close()
        raise
    return segmenter, wrapper_class(primary, alternate)


def smoothstep(edge0: float, edge1: float, values: np.ndarray) -> np.ndarray:
    values = np.clip((values - edge0) / max(edge1 - edge0, 1e-6), 0.0, 1.0)
    return values * values * (3.0 - 2.0 * values)


def ease_in_out_cubic(value: float) -> float:
    if value < 0.5:
        return 4.0 * value * value * value
    return 1.0 - ((-2.0 * value + 2.0) ** 3) / 2.0


def make_dissolve_fields(height: int, width: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(7391)
    y, x = np.mgrid[0:height, 0:width]
    y_normal = y.astype(np.float32) / max(height - 1, 1)
    x_normal = x.astype(np.float32) / max(width - 1, 1)
    low_noise = rng.random((max(2, height // 10), max(2, width // 10)), dtype=np.float32)
    low_noise = cv2.resize(low_noise, (width, height), interpolation=cv2.INTER_CUBIC)
    fine_noise = rng.random((height, width), dtype=np.float32)
    field = (
        (1.0 - y_normal) * 0.72
        + low_noise * 0.17
        + fine_noise * 0.08
        + np.sin(x_normal * 18.0) * 0.025
    )
    return np.clip(field, 0.0, 1.0), fine_noise


def person_mask(
    segmenter: vision.ImageSegmenter,
    image: mp.Image,
    timestamp_ms: int,
    width: int,
    height: int,
) -> np.ndarray:
    result = segmenter.segment_for_video(image, timestamp_ms)
    if not result.confidence_masks:
        return np.zeros((height, width), dtype=np.float32)
    raw = np.squeeze(result.confidence_masks[0].numpy_view()).astype(np.float32)
    resized = cv2.resize(raw, (width, height), interpolation=cv2.INTER_LINEAR)
    resized = cv2.GaussianBlur(resized, (0, 0), sigmaX=2.2, sigmaY=2.2)
    return np.clip((resized - 0.12) / 0.68, 0.0, 1.0)


def notify_background_ready() -> None:
    """Toca um aviso curto: quem saiu do enquadramento não está vendo o terminal."""
    if sys.platform == "darwin" and READY_SOUND_PATH.is_file():
        subprocess.Popen(["afplay", str(READY_SOUND_PATH)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        print("\a", end="", flush=True)


def alpha_composite(person: np.ndarray, background: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    alpha_3 = alpha[:, :, None]
    return (
        person.astype(np.float32) * alpha_3
        + background.astype(np.float32) * (1.0 - alpha_3)
    ).astype(np.uint8)


def apply_dissolve(
    frame: np.ndarray,
    background: np.ndarray,
    mask: np.ndarray,
    progress: float,
    field: np.ndarray,
    sparkle_noise: np.ndarray,
) -> np.ndarray:
    if progress <= 0.002:
        return alpha_composite(frame, background, mask)
    if progress >= 0.999:
        return background.copy()

    points = cv2.findNonZero((mask > 0.01).astype(np.uint8))
    if points is None:
        return background.copy()
    x, y, width, height = cv2.boundingRect(points)
    left, top = max(0, x - 18), max(0, y - 18)
    right = min(mask.shape[1], x + width + 18)
    bottom = min(mask.shape[0], y + height + 18)
    area = np.s_[top:bottom, left:right]
    mask = mask[area]
    field = field[area]
    sparkle_noise = sparkle_noise[area]
    eased = ease_in_out_cubic(progress)
    survival = smoothstep(eased - 0.055, eased + 0.055, field)
    alpha = mask * survival
    output = alpha_composite(frame[area], background[area], alpha)
    edge = (
        (np.abs(field - eased) < 0.018)
        & (mask > 0.48)
        & (sparkle_noise > 0.54)
    ).astype(np.float32)
    glow = cv2.GaussianBlur(edge, (0, 0), sigmaX=5.0, sigmaY=5.0)
    glow = np.clip(glow * 5.0 + edge, 0.0, 1.0)[:, :, None]
    cyan = np.full_like(output, (255, 228, 92), dtype=np.uint8)
    result = np.clip(
        output.astype(np.float32) * (1.0 - glow * 0.8)
        + cyan.astype(np.float32) * glow * 0.8,
        0,
        255,
    ).astype(np.uint8)
    canvas = background.copy()
    canvas[area] = result
    return canvas


def victory_landmark_score(points: np.ndarray) -> float:
    """Reconhece indicador e médio esticados usando distâncias 3D, não a orientação."""
    if points.shape != (21, 3) or not np.isfinite(points).all():
        return 0.0

    straightness = []
    extended = []
    folded = []
    lengths = []
    # MCP, PIP, DIP e ponta: indicador, médio, anelar e mínimo.
    for index, base in enumerate((5, 9, 13, 17)):
        finger = points[base : base + 4]
        length = float(np.linalg.norm(np.diff(finger, axis=0), axis=1).sum())
        if length < 1e-6:
            if index < 2:
                return 0.0
            straightness.append(0.0)
            lengths.append(0.0)
            extended.append(False)
            folded.append(True)
            continue
        ratio = float(np.linalg.norm(finger[3] - finger[0])) / length
        tip_distance = float(np.linalg.norm(finger[3] - points[0]))
        joint_distance = float(np.linalg.norm(finger[1] - points[0]))
        straightness.append(ratio)
        lengths.append(length)
        extended.append(ratio >= 0.82 and tip_distance > joint_distance * 1.10)
        folded.append(ratio < 0.78 or tip_distance <= joint_distance * 1.05)

    # De lado, os dedos dobrados podem parecer retos mas muito curtos.
    # Não exige articulações bem visíveis para anelar e mínimo.
    reference_length = min(lengths[:2])
    for index, base in ((2, 13), (3, 17)):
        reach = float(np.linalg.norm(points[base + 3] - points[base]))
        folded[index] = folded[index] or reach < reference_length * 0.65
    if not (extended[0] and extended[1] and folded[2] and folded[3]):
        return 0.0
    # As duas pontas precisam estar separadas. O polegar pode ficar escondido.
    separation = float(np.linalg.norm(points[8] - points[12]))
    if separation < min(lengths[:2]) * 0.20:
        return 0.0
    # Qualidade geométrica dos dedos esticados, não a probabilidade do classificador.
    return float(np.clip(min(straightness[:2]), 0.0, 1.0))


def classify_gesture_result(
    result: vision.GestureRecognizerResult,
    image: mp.Image,
) -> tuple[str, float]:
    # Os landmarks chegam mesmo quando o classificador não reconhece
    # "Victory" (por exemplo, com as costas da mão viradas para a webcam).
    for landmarks in result.hand_world_landmarks:
        points = np.array([(point.x, point.y, point.z) for point in landmarks])
        score = victory_landmark_score(points)
        if score:
            return "Victory", score
    # Confere SEMPRE também a geometria visível: a profundidade estimada
    # pode ser imprecisa quando a palma e os dedos dobrados ficam escondidos.
    for landmarks in result.hand_landmarks:
        points = np.array([(point.x * image.width, point.y * image.height, 0.0)
                           for point in landmarks])
        score = victory_landmark_score(points)
        if score:
            return "Victory", score
    for categories in result.gestures:
        for category in categories:
            if category.category_name == "Victory" and category.score >= 0.62:
                return "Victory", float(category.score)
    if result.hand_landmarks or result.hand_world_landmarks:
        return "Hand_Detected", 0.0
    return "No_Hand", 0.0


class MultiViewGestureRecognizer:
    """Tenta de novo em frames girados sem atrapalhar o tracking."""

    def __init__(self, primary, alternate):
        self.primary = primary
        self.alternate = alternate
        self.preferred_rotation: int | None = None
        self.preferred_crop: str | None = None
        self.next_retry_ms = 0
        self.retry_cursor = 0

    def recognize_gesture(self, image: mp.Image, timestamp_ms: int) -> tuple[str, float]:
        result = self.primary.recognize_for_video(image, timestamp_ms)
        best = classify_gesture_result(result, image)
        if best[0] == "Victory":
            self.preferred_rotation = None
            self.preferred_crop = None
            return best
        if timestamp_ms < self.next_retry_ms:
            return best

        # IMAGE força uma nova detecção. O modelo VIDEO fica no frame original
        # e evita timestamps e tracking incoerentes entre rotações diferentes.
        rgb = image.numpy_view()
        height, width = rgb.shape[:2]
        # Na pose lateral a palma costuma ficar pequena demais no frame inteiro.
        # Os dois recortes inferiores se sobrepõem e cobrem as duas mãos,
        # mesmo com a imagem espelhada.
        crops = {
            "full": rgb,
            "lower_left": rgb[int(height * 0.28):, :int(width * 0.78)],
            "lower_right": rgb[int(height * 0.28):, int(width * 0.22):],
        }
        views = [("full", rotation) for rotation in (0, 1, 3, 2)]
        views += [(crop, rotation) for crop in ("lower_left", "lower_right")
                  for rotation in (0, 1, 3)]
        preferred = (self.preferred_crop, self.preferred_rotation)
        selected = []
        if preferred in views:
            selected.append(preferred)
        # Distribui as tentativas caras em IMAGE entre frames seguidos.
        while len(selected) < 3:
            view = views[self.retry_cursor % len(views)]
            self.retry_cursor += 1
            if view not in selected:
                selected.append(view)
        for crop, rotation in selected:
            rotated = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=np.ascontiguousarray(np.rot90(crops[crop], rotation)),
            )
            result = self.alternate.recognize(rotated)
            candidate = classify_gesture_result(result, rotated)
            if candidate[0] == "Victory":
                self.preferred_rotation = rotation
                self.preferred_crop = crop
                self.next_retry_ms = timestamp_ms + int(GESTURE_INTERVAL_SECONDS * 1000)
                return candidate
            if candidate[0] == "Hand_Detected":
                best = candidate
        self.preferred_rotation = None
        self.preferred_crop = None
        self.next_retry_ms = timestamp_ms + int(GESTURE_INTERVAL_SECONDS * 1000)
        return best

    def close(self) -> None:
        try:
            self.primary.close()
        finally:
            self.alternate.close()


class MultiViewHandLandmarker:
    """Acompanha duas mãos no vídeo e tenta de novo as vistas difíceis."""

    def __init__(self, primary, alternate):
        self.primary = primary
        self.alternate = alternate
        self.preferred_view: tuple[str, int] | None = None
        self.next_retry_ms = 0
        self.last_hand_count = 0
        self.retry_cursor = 0

    def recognize_joined_hands(self, image: mp.Image, timestamp_ms: int) -> bool:
        result = self.primary.detect_for_video(image, timestamp_ms)
        self.last_hand_count = len(result.hand_landmarks)
        if joined_hands_from_landmarks(result.hand_landmarks, image.width, image.height):
            self.preferred_view = None
            return True
        if timestamp_ms < self.next_retry_ms:
            return False

        rgb = image.numpy_view()
        height, width = rgb.shape[:2]
        views = {
            "full": rgb,
            "center": rgb[int(height * 0.18):, int(width * 0.12):int(width * 0.88)],
            "lower_left": rgb[int(height * 0.22):, :int(width * 0.78)],
            "lower_right": rgb[int(height * 0.22):, int(width * 0.22):],
        }
        attempts = [("full", rotation) for rotation in (1, 3, 2)]
        attempts += [("center", rotation) for rotation in (0, 1, 3)]
        attempts += [("lower_left", 0), ("lower_right", 0)]
        selected = []
        if self.preferred_view in attempts:
            selected.append(self.preferred_view)
        while len(selected) < 2:
            view = attempts[self.retry_cursor % len(attempts)]
            self.retry_cursor += 1
            if view not in selected:
                selected.append(view)
        for crop, rotation in selected:
            rotated = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=np.ascontiguousarray(np.rot90(views[crop], rotation)),
            )
            result = self.alternate.detect(rotated)
            self.last_hand_count = max(self.last_hand_count, len(result.hand_landmarks))
            if joined_hands_from_landmarks(result.hand_landmarks, rotated.width, rotated.height):
                self.preferred_view = (crop, rotation)
                self.next_retry_ms = timestamp_ms + 90
                return True
        self.preferred_view = None
        self.next_retry_ms = timestamp_ms + 80
        return False

    def close(self) -> None:
        try:
            self.primary.close()
        finally:
            self.alternate.close()


def recognize_gesture(
    recognizer: MultiViewGestureRecognizer,
    image: mp.Image,
    timestamp_ms: int,
) -> tuple[str, float]:
    if isinstance(recognizer, MultiViewGestureRecognizer):
        return recognizer.recognize_gesture(image, timestamp_ms)
    return classify_gesture_result(recognizer.recognize_for_video(image, timestamp_ms), image)


def start_vanish_on_gesture(state: AppState, name: str, score: float, now: float,
                            phase: str = "vanishing") -> bool:
    """Começa o efeito no primeiro reconhecimento confiável do V."""
    if state.phase == "ready" and name == "Victory" and score >= 0.62:
        state.phase = phase
        state.vanish_started = now
        return True
    return False


def start_naruto_on_join(state: AppState, joined: bool, now: float) -> bool:
    if state.phase == "ready" and joined:
        state.phase = "naruto_vanishing"
        state.vanish_started = now
        return True
    return False


def set_fullscreen(enabled: bool) -> None:
    mode = cv2.WINDOW_FULLSCREEN if enabled else cv2.WINDOW_NORMAL
    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, mode)
    mac_window.prepare_windows()  # O botão de fechar pode sumir ao trocar de modo.


def self_test() -> int:
    """Confere recursos e modelos sem abrir a webcam."""
    download_models()
    required = (SEGMENTER_MODEL, GESTURE_MODEL, FACE_MODEL, HAND_MODEL,
                SOUND_PATH, TELEPORT_SOUND_PATH)
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"Recursos ausentes: {', '.join(missing)}")
    load_log()
    for path in (SOUND_PATH, TELEPORT_SOUND_PATH):
        VanishSound(path).close()
    for mode in MODES:
        segmenter, recognizer = create_tasks(mode)
        try:
            recognizer.close()
        finally:
            segmenter.close()
    print("[Webcam] Autoteste concluído: modelos, imagens e áudio presentes.")
    return 0


def run() -> int:
    args = parse_args()
    if getattr(args, "self_test", False):
        return self_test()
    mode = args.mode or choose_mode()
    menu_open = args.mode is None
    background = None
    while mode is not None:
        with ExitStack() as resources:
            switch, background = run_camera(args, resources, mode, menu_open, background)
        if not switch:
            break
        # Volta ao menu. O fundo capturado vale para o próximo modo.
        mode = choose_mode()
        menu_open = True
    return 0


def run_camera(args: argparse.Namespace, resources: ExitStack, mode: str,
               menu_open: bool = False, background: np.ndarray | None = None,
               ) -> tuple[bool, np.ndarray | None]:
    """Roda o vídeo de um modo. Devolve (voltar ao menu?, fundo capturado)."""
    download_models(mode)
    capture = open_camera(args.camera, args.width, args.height)
    resources.callback(capture.release)
    capture.set(cv2.CAP_PROP_FPS, args.fps)
    segmenter, recognizer = create_tasks(mode)
    resources.callback(segmenter.close)
    resources.callback(recognizer.close)
    log_sprite = load_log() if mode == "naruto" else None
    sound_path = {"naruto": SOUND_PATH, "goku": TELEPORT_SOUND_PATH}.get(mode)
    vanish_sound = VanishSound(sound_path) if sound_path is not None else None
    if vanish_sound is not None:
        resources.callback(vanish_sound.close)
    teleport = (GokuTeleport(recognizer, vanish_sound, args.gesture_debug)
                if mode == "goku" else None)
    gesture_mode = mode in ("normal", "particles")
    resources.callback(cv2.destroyAllWindows)
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, args.width, args.height)
    mac_window.prepare_windows()

    state = AppState(
        phase="calibrating" if background is None else "ready",
        calibration_started=time.perf_counter(), fullscreen=args.fullscreen,
    )
    if state.fullscreen:
        set_fullscreen(True)

    switch_mode = False
    background_samples: list[np.ndarray] = []
    last_mask: np.ndarray | None = None
    last_mask_at = float("-inf")
    dissolve_field: np.ndarray | None = None
    sparkle_noise: np.ndarray | None = None
    log_anchor: tuple[int, int, int] | None = None
    log_cache: dict[int, np.ndarray] = {}
    burst: ParticleBurst | None = None
    vanished_frame: np.ndarray | None = None
    virtual_camera = None
    virtual_camera_initialized = False
    calibration_remaining = None
    last_gesture_report = 0.0
    started = time.perf_counter()
    frames_shown = 0
    if background is None:
        print("[Webcam] Saia do enquadramento por 4 segundos: capturando o fundo.")
    else:
        print("[Webcam] Usando o fundo já capturado. Aperte ESPAÇO para capturar outro.")
    if mode == "goku":
        print("[Webcam] Comandos na janela: ESPAÇO novo fundo, M trocar de modo, F tela cheia, "
              "Q sair. No modo Goku, V e R ficam desativados.")
    else:
        print("[Webcam] Comandos na janela: ESPAÇO novo fundo, R reaparecer, V sumir, "
              "M trocar de modo, F tela cheia, Q sair.")
    print("[Webcam] Também dá para sair pelo botão vermelho da janela, pelo Dock ou com Ctrl+C aqui.")

    try:
        while True:
            ok, camera_frame = capture.read()
            if not ok:
                raise RuntimeError("A webcam parou de enviar imagens.")

            camera_frame = fit_frame(camera_frame, args.width)
            if not args.no_mirror:
                camera_frame = cv2.flip(camera_frame, 1)

            height, width = camera_frame.shape[:2]
            if background is not None and background.shape != camera_frame.shape:
                background = None  # Resolução mudou: o fundo antigo não serve mais.
            if not virtual_camera_initialized:
                virtual_camera = open_virtual_camera(args, width, height)
                virtual_camera_initialized = True
                if virtual_camera is not None:
                    resources.callback(virtual_camera.close)
            if mode == "normal" and (dissolve_field is None or dissolve_field.shape != (height, width)):
                dissolve_field, sparkle_noise = make_dissolve_fields(height, width)
            now = time.perf_counter()

            elapsed_ms = int((now - started) * 1000)
            mp_image = None

            if state.phase == "calibrating":
                elapsed = now - state.calibration_started
                remaining = max(0, int(np.ceil(CALIBRATION_SECONDS - elapsed)))
                if remaining != calibration_remaining:
                    print(f"[Webcam] Capturando o fundo: {remaining} segundos.")
                    calibration_remaining = remaining
                if elapsed >= CALIBRATION_SECONDS - BACKGROUND_SAMPLE_SECONDS:
                    background_samples.append(camera_frame.copy())
                if elapsed >= CALIBRATION_SECONDS:
                    if background_samples:
                        stack = np.stack(background_samples[-18:], axis=0)
                        background = np.median(stack, axis=0).astype(np.uint8)
                    else:
                        background = camera_frame.copy()
                    background_samples.clear()
                    state.phase = "ready"
                    notify_background_ready()
                    print("[Webcam] Fundo pronto (sinal sonoro). Pode voltar para o enquadramento.")
                    if mode == "goku":
                        print("[Goku] Encoste indicador e médio juntos na testa por 1 segundo.")
                display = camera_frame

            elif background is None:
                state.phase = "calibrating"
                state.calibration_started = now
                print("[Webcam] Saia do enquadramento por 4 segundos: capturando o fundo.")
                display = camera_frame

            elif mode == "goku":
                rgb = cv2.cvtColor(camera_frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                display = teleport.update(
                    camera_frame, background, mp_image, elapsed_ms, now,
                    lambda: person_mask(segmenter, mp_image, elapsed_ms, width, height),
                )

            elif state.phase == "vanished":
                if vanished_frame is None:
                    vanished_frame = background.copy()
                    if mode == "naruto" and log_anchor is not None:
                        overlay_log(vanished_frame, log_sprite, landed_log_anchor(log_anchor, height),
                                    cache=log_cache)
                display = vanished_frame

            else:
                mask = last_mask
                if (
                    state.phase == "ready"
                    and now - state.last_gesture_check >=
                    (0.08 if mode == "naruto" else GESTURE_INTERVAL_SECONDS)
                ):
                    state.last_gesture_check = now
                    rgb = cv2.cvtColor(camera_frame, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    if gesture_mode:
                        name, score = recognize_gesture(recognizer, mp_image, elapsed_ms)
                        if args.gesture_debug and now - last_gesture_report >= 1.0:
                            print(
                                f"[Gesto] {name}, valor={score:.2f}, "
                                f"recorte={recognizer.preferred_crop or 'full'}, "
                                f"rotação={recognizer.preferred_rotation or 0}"
                            )
                            last_gesture_report = now
                        start_vanish_on_gesture(
                            state, name, score, now,
                            "particles_vanishing" if mode == "particles" else "vanishing",
                        )
                    else:
                        joined = recognizer.recognize_joined_hands(mp_image, elapsed_ms)
                        if args.gesture_debug and now - last_gesture_report >= 1.0:
                            print(f"[Mãos] detectadas={recognizer.last_hand_count}, "
                                  f"unidas={joined}, vista={recognizer.preferred_view or 'full'}")
                            last_gesture_report = now
                        if start_naruto_on_join(state, joined, time.perf_counter()):
                            vanish_sound.play()

                if state.phase in ("vanishing", "naruto_vanishing", "particles_vanishing"):
                    # O Normal acompanha a silhueta a 20 Hz. O Naruto só precisa
                    # dela enquanto a pessoa ainda aparece. O Particles a captura uma vez.
                    needs_mask = (
                        (mode == "normal" and (mask is None or now - last_mask_at >= 0.05))
                        or (mode == "naruto" and (log_anchor is None or now - state.vanish_started < 0.13))
                        or (mode == "particles" and burst is None)
                    )
                    if needs_mask:
                        if mp_image is None:
                            rgb = cv2.cvtColor(camera_frame, cv2.COLOR_BGR2RGB)
                            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                        mask = person_mask(segmenter, mp_image, elapsed_ms, width, height)
                        last_mask = mask
                        last_mask_at = now
                    if mode == "naruto" and log_anchor is None:
                        log_anchor = substitution_anchor(mask)
                    if mode == "particles" and burst is None:
                        burst = ParticleBurst(camera_frame, mask)

                if mode == "naruto" and state.phase == "naruto_vanishing":
                    age = max(0.04, time.perf_counter() - state.vanish_started)
                    display = render_substitution(
                        camera_frame, background, mask, log_sprite, log_anchor, age, log_cache
                    )
                    if age >= EFFECT_SECONDS:
                        state.phase = "vanished"
                        vanished_frame = display
                elif mode == "particles" and state.phase == "particles_vanishing":
                    age = time.perf_counter() - state.vanish_started
                    display = burst.render(background, age)
                    if age >= PARTICLE_SECONDS:
                        state.phase = "vanished"
                        vanished_frame = background.copy()
                        display = vanished_frame
                elif state.phase == "ready":
                    display = camera_frame
                else:
                    progress = 0.0
                    if state.phase == "vanishing" and state.vanish_started is not None:
                        progress = min(
                            1.0, (time.perf_counter() - state.vanish_started) / VANISH_SECONDS
                        )
                        if progress >= 1.0:
                            state.phase = "vanished"
                    display = apply_dissolve(
                        camera_frame, background, mask, progress, dissolve_field, sparkle_noise
                    )
                    if state.phase == "vanished":
                        vanished_frame = display

            if virtual_camera is not None:
                send_virtual_frame(virtual_camera, display)
            cv2.imshow(WINDOW_NAME, display)
            frames_shown += 1
            if frames_shown == 1:
                mac_window.lock_window(WINDOW_NAME, width, height)
            elif frames_shown % 30 == 0 and not state.fullscreen:
                video_height = mac_window.content_height(WINDOW_NAME)
                if video_height is not None and video_height < 60:
                    cv2.resizeWindow(WINDOW_NAME, width, height)
                    print("[Webcam] A janela do vídeo tinha encolhido. Tamanho restaurado.")
            if menu_open:
                close_menu()  # Só agora: até aqui o menu mostrava "Abrindo a câmera".
                menu_open = False

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27) or mac_window.quit_requested():
                break
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                break  # Janela fechada pelo botão vermelho.
            if key == ord("m"):
                switch_mode = True
                print("[Webcam] Voltando ao menu para trocar de modo.")
                break
            if key == ord(" "):
                state.phase = "calibrating"
                state.calibration_started = now
                state.vanish_started = None
                log_anchor = None
                burst = None
                last_mask = None
                last_mask_at = float("-inf")
                vanished_frame = None
                background_samples.clear()
                calibration_remaining = None
                if teleport is not None:
                    teleport.reset()
                print("[Webcam] Saia do enquadramento por 4 segundos: capturando o novo fundo.")
            elif mode == "goku":
                pass  # V e R ficam desativados: só o gesto faz sumir e voltar.
            elif key == ord("r"):
                if background is not None:
                    state.phase = "ready"
                    state.vanish_started = None
                    vanished_frame = None
                    log_anchor = None
                    burst = None
                    last_mask = None
                    last_mask_at = float("-inf")
            elif key == ord("v") and background is not None:
                state.phase = {
                    "naruto": "naruto_vanishing", "particles": "particles_vanishing",
                }.get(mode, "vanishing")
                state.vanish_started = time.perf_counter()
                if mode == "naruto":
                    vanish_sound.play()
                    log_anchor = None
                burst = None
                vanished_frame = None
            if key == ord("f"):
                state.fullscreen = not state.fullscreen
                set_fullscreen(state.fullscreen)
            if virtual_camera is not None:
                virtual_camera.sleep_until_next_frame()
    finally:
        resources.close()

    return switch_mode, background


def main() -> int:
    try:
        return run()
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        print(f"\n[Vanish Lab] ERRO: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
