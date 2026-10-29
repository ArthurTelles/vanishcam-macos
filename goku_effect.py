"""Modo Goku: dois dedos na testa por 1 segundo e teletransporte com linhas verticais."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np


HOLD_SECONDS = 1.0
CHECK_INTERVAL_SECONDS = 0.08
MASK_INTERVAL_SECONDS = 0.05
LINES_SECONDS = 0.30  # As linhas surgem sobre a silhueta ainda visível.
STRIPES_SECONDS = 0.30  # A pessoa some em faixas verticais.
TELEPORT_SECONDS = 1.0  # Inclui o rastro que fica alguns instantes depois do sumiço.
FREEZE_SECONDS = LINES_SECONDS + STRIPES_SECONDS
STRIPE_WIDTH = 6
LINE_COUNT = 44


@dataclass(frozen=True)
class Face:
    left: float
    top: float
    width: float
    height: float
    eye_y: float


def two_fingers_together(points: np.ndarray) -> bool:
    """Indicador e médio esticados e encostados, anelar e mínimo dobrados."""
    if points.ndim != 2 or points.shape[0] != 21 or not np.isfinite(points).all():
        return False
    lengths, extended, folded = [], [], []
    # MCP, PIP, DIP e ponta: indicador, médio, anelar e mínimo.
    for base in (5, 9, 13, 17):
        finger = points[base:base + 4]
        length = float(np.linalg.norm(np.diff(finger, axis=0), axis=1).sum())
        lengths.append(length)
        if length < 1e-6:
            extended.append(False)
            folded.append(True)
            continue
        ratio = float(np.linalg.norm(finger[3] - finger[0])) / length
        tip_distance = float(np.linalg.norm(finger[3] - points[0]))
        joint_distance = float(np.linalg.norm(finger[1] - points[0]))
        extended.append(ratio >= 0.80 and tip_distance > joint_distance * 1.10)
        folded.append(ratio < 0.78 or tip_distance <= joint_distance * 1.05)
    reference = min(lengths[:2])
    if reference < 1e-6 or not (extended[0] and extended[1]):
        return False
    # Perto do rosto, anelar e mínimo dobrados aparecem curtos, mas às vezes retos.
    for index, base in ((2, 13), (3, 17)):
        reach = float(np.linalg.norm(points[base + 3] - points[base]))
        folded[index] = folded[index] or reach < reference * 0.65
    if not (folded[2] and folded[3]):
        return False
    return float(np.linalg.norm(points[8] - points[12])) < reference * 0.42


def forehead_box(face: Face) -> tuple[float, float, float, float]:
    """Área da testa: acima da linha dos olhos, com folga para cima e para os lados."""
    return (
        face.left - face.width * 0.15,
        face.top - face.height * 0.60,
        face.left + face.width * 1.15,
        face.eye_y + face.height * 0.08,
    )


def fingers_on_forehead(hands: list[tuple[np.ndarray, np.ndarray | None]],
                        faces: list[Face]) -> bool:
    """Recebe pares (pontos na imagem em pixels, pontos 3D do mundo ou None)."""
    for image_points, world_points in hands:
        if image_points.shape != (21, 3):
            continue
        shape_ok = two_fingers_together(image_points) or (
            world_points is not None and two_fingers_together(world_points)
        )
        if not shape_ok:
            continue
        tip_x, tip_y = (image_points[8, :2] + image_points[12, :2]) * 0.5
        for face in faces:
            left, top, right, bottom = forehead_box(face)
            if left <= tip_x <= right and top <= tip_y <= bottom:
                return True
    return False


def face_from_detection(detection, width: int, height: int) -> Face:
    box = detection.bounding_box
    eyes = list(detection.keypoints or [])[:2]
    if eyes:
        eye_y = float(np.mean([point.y for point in eyes])) * height
    else:
        eye_y = box.origin_y + box.height * 0.35
    return Face(float(box.origin_x), float(box.origin_y),
                float(box.width), float(box.height), eye_y)


class GokuPoseDetector:
    """Combina o modelo de mãos com o detector de rosto no mesmo frame."""

    def __init__(self, hands, faces):
        self.hands = hands
        self.faces = faces
        self.last_hand_count = 0
        self.last_face_count = 0

    def detect(self, image, timestamp_ms: int) -> bool:
        width, height = image.width, image.height
        hand_result = self.hands.detect_for_video(image, timestamp_ms)
        face_result = self.faces.detect_for_video(image, timestamp_ms)
        faces = [face_from_detection(item, width, height) for item in face_result.detections]
        hands = []
        world = list(hand_result.hand_world_landmarks or [])
        for index, landmarks in enumerate(hand_result.hand_landmarks):
            image_points = np.array([(p.x * width, p.y * height, 0.0) for p in landmarks])
            world_points = (np.array([(p.x, p.y, p.z) for p in world[index]])
                            if index < len(world) else None)
            hands.append((image_points, world_points))
        self.last_hand_count = len(hands)
        self.last_face_count = len(faces)
        return fingers_on_forehead(hands, faces)

    def close(self) -> None:
        try:
            self.hands.close()
        finally:
            self.faces.close()


@lru_cache(maxsize=4)
def column_rank(width: int) -> np.ndarray:
    """Ordem aleatória, mas fixa, em que as faixas verticais desaparecem."""
    stripes = np.random.default_rng(5150).random(width // STRIPE_WIDTH + 1, dtype=np.float32)
    return np.repeat(stripes, STRIPE_WIDTH)[:width]


def lines_intensity(timeline: float) -> float:
    if timeline < LINES_SECONDS:
        return timeline / LINES_SECONDS
    if timeline < FREEZE_SECONDS:
        return 1.0
    return max(0.0, 1.0 - (timeline - FREEZE_SECONDS) / (TELEPORT_SECONDS - FREEZE_SECONDS))


def draw_speed_lines(output: np.ndarray, mask: np.ndarray, timeline: float,
                     intensity: float) -> None:
    """Linhas verticais de mangá correndo para cima, presas à silhueta."""
    if intensity <= 0.01:
        return
    points = cv2.findNonZero((mask > 0.3).astype(np.uint8))
    if points is None:
        return
    x, y, width, height = cv2.boundingRect(points)
    pad = max(12, width // 6)
    left, top = max(0, x - pad), max(0, y - pad)
    right = min(mask.shape[1], x + width + pad)
    bottom = min(mask.shape[0], y + height + pad)
    region_width, region_height = right - left, bottom - top
    layer = np.zeros((region_height, region_width), np.float32)

    rng = np.random.default_rng(8001)
    xs = rng.uniform(0.04, 0.96, LINE_COUNT)
    lengths = rng.uniform(0.18, 0.60, LINE_COUNT)
    speeds = rng.uniform(1.8, 3.4, LINE_COUNT)
    phases = rng.random(LINE_COUNT)
    thickness = rng.integers(1, 4, LINE_COUNT)
    for index in range(LINE_COUNT):
        line_x = int(xs[index] * region_width)
        center = ((phases[index] - timeline * speeds[index]) % 1.0) * region_height * 1.4
        center -= region_height * 0.2
        half = lengths[index] * region_height * 0.5
        cv2.line(layer, (line_x, int(center - half)), (line_x, int(center + half)),
                 1.0, int(thickness[index]), cv2.LINE_AA)

    area = np.s_[top:bottom, left:right]
    weight = cv2.GaussianBlur(mask[area], (0, 0), sigmaX=9.0, sigmaY=9.0)
    weight = np.clip(weight * 1.8, 0.0, 1.0) * intensity
    halo = np.clip(cv2.GaussianBlur(layer, (0, 0), sigmaX=3.5, sigmaY=3.5) * 1.6, 0.0, 1.0)
    core = (layer * weight)[:, :, None]
    halo = (halo * weight * 0.7)[:, :, None]
    halo = np.minimum(halo, 1.0 - core)
    blue = np.array((255, 214, 140), np.float32)
    destination = output[area]
    destination[:] = np.clip(
        destination.astype(np.float32) * (1.0 - core - halo) + 255.0 * core + blue * halo,
        0, 255,
    ).astype(np.uint8)


def render_teleport(frame: np.ndarray, background: np.ndarray, mask: np.ndarray,
                    timeline: float) -> np.ndarray:
    """Linhas surgem, a silhueta some em faixas e o rastro de linhas fica por um instante."""
    stripes = float(np.clip((timeline - LINES_SECONDS) / STRIPES_SECONDS, 0.0, 1.0))
    if stripes >= 1.0:
        output = background.copy()
    else:
        rank = column_rank(mask.shape[1])
        visible = (rank > stripes).astype(np.float32)[None, :]
        alpha = (mask * visible)[:, :, None]
        person = frame.astype(np.float32)
        if stripes > 0.0:
            # As faixas prestes a sumir brilham um instante antes.
            flash = ((rank > stripes) & (rank < stripes + 0.08)).astype(np.float32)
            person = person + (255.0 - person) * flash[None, :, None] * 0.65
        output = (person * alpha + background.astype(np.float32) * (1.0 - alpha)).astype(np.uint8)
    draw_speed_lines(output, mask, timeline, lines_intensity(timeline))
    return output


class GokuTeleport:
    """Controla a contagem do gesto, o sumiço e o retorno no modo Goku."""

    def __init__(self, detector, sound=None, debug: bool = False):
        self.detector = detector
        self.sound = sound
        self.debug = debug
        self.reset()

    def reset(self) -> None:
        self.phase = "ready"
        self.hold_started: float | None = None
        self.released = True
        self.started: float | None = None
        self.last_check = float("-inf")
        self.last_report = float("-inf")
        self.countdown_step: int | None = None
        self.mask: np.ndarray | None = None
        self.mask_at = float("-inf")

    def _track_pose(self, pose: bool, now: float) -> None:
        if not self.released:
            # Depois de cada teletransporte é preciso baixar a mão antes de repetir.
            if not pose:
                self.released = True
                action = "reaparecer" if self.phase == "vanished" else "sumir de novo"
                print(f"[Goku] Mão abaixada. Repita o gesto por 1 segundo para {action}.")
            return
        if not pose:
            if self.hold_started is not None:
                print("[Goku] Pose interrompida. A contagem recomeça.")
            self.hold_started = None
            return
        if self.hold_started is None:
            self.hold_started = now
            self.countdown_step = None
        remaining = HOLD_SECONDS - (now - self.hold_started)
        step = max(0, int(np.ceil(remaining / 0.25)))
        if step != self.countdown_step and remaining > 0:
            print(f"[Goku] Segure a pose: {step * 0.25:.2f} s")
            self.countdown_step = step
        if remaining <= 0:
            self.phase = "out" if self.phase == "ready" else "in"
            self.started = now
            self.hold_started = None
            self.released = False
            self.mask = None
            print("[Goku] Teletransporte!" if self.phase == "out" else "[Goku] De volta!")
            if self.sound is not None:
                self.sound.play()

    def update(self, frame: np.ndarray, background: np.ndarray, image, timestamp_ms: int,
               now: float, mask_fn) -> np.ndarray:
        if self.phase in ("ready", "vanished") and now - self.last_check >= CHECK_INTERVAL_SECONDS:
            self.last_check = now
            pose = self.detector.detect(image, timestamp_ms)
            if self.debug and now - self.last_report >= 1.0:
                print(f"[Goku] mãos={self.detector.last_hand_count}, "
                      f"rostos={self.detector.last_face_count}, pose={pose}")
                self.last_report = now
            self._track_pose(pose, now)

        if self.phase == "ready":
            return frame
        if self.phase == "vanished":
            return background

        age = now - self.started
        if age >= TELEPORT_SECONDS:
            self.phase = "vanished" if self.phase == "out" else "ready"
            self.mask = None
            return background if self.phase == "vanished" else frame
        # O retorno é o mesmo efeito tocado ao contrário.
        timeline = age if self.phase == "out" else TELEPORT_SECONDS - age
        live = self.phase == "in" or timeline < FREEZE_SECONDS
        if self.mask is None or (live and now - self.mask_at >= MASK_INTERVAL_SECONDS):
            self.mask = mask_fn()
            self.mask_at = now
        return render_teleport(frame, background, self.mask, timeline)
