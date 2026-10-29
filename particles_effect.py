"""Modo Particles: a silhueta se desfaz em fragmentos coloridos levados pelo vento."""

from __future__ import annotations

import numpy as np
import cv2


PARTICLE_SECONDS = 2.1
LAUNCH_SECONDS = 1.0
CELL = 5


class ParticleBurst:
    """Captura a silhueta uma vez e anima os fragmentos sem novas segmentações."""

    def __init__(self, frame: np.ndarray, mask: np.ndarray, seed: int = 2718):
        height, width = mask.shape
        self.person = frame.copy()
        self.mask = mask.astype(np.float32)
        rng = np.random.default_rng(seed)

        grid_height, grid_width = -(-height // CELL), -(-width // CELL)
        padded_mask = np.zeros((grid_height * CELL, grid_width * CELL), np.float32)
        padded_mask[:height, :width] = self.mask
        padded_frame = np.zeros((grid_height * CELL, grid_width * CELL, 3), np.uint8)
        padded_frame[:height, :width] = frame
        coverage = padded_mask.reshape(grid_height, CELL, grid_width, CELL).mean(axis=(1, 3))
        colors = padded_frame.reshape(grid_height, CELL, grid_width, CELL, 3).mean(axis=(1, 3))
        launch_grid = np.full((grid_height, grid_width), 99.0, np.float32)
        touched = coverage > 0.01
        if touched.any():
            # O vento sopra para a direita: o lado direito se desfaz primeiro.
            # Toda célula tocada pela silhueta some, mas só as cheias viram fragmento.
            touched_rows, touched_cols = np.nonzero(touched)
            first, span = touched_cols.min(), max(1, int(np.ptp(touched_cols)))
            reach = (touched_cols - first) / span
            launch = (1.0 - reach) * 0.72 + rng.random(len(touched_cols)) * 0.28
            launch_grid[touched_rows, touched_cols] = launch * LAUNCH_SECONDS
        self.launch_at = np.repeat(np.repeat(launch_grid, CELL, axis=0), CELL, axis=1)[:height, :width]
        rows, cols = np.nonzero(coverage > 0.45)

        count = len(cols)
        self.x0 = (cols * CELL).astype(np.float32)
        self.y0 = (rows * CELL).astype(np.float32)
        self.launch = launch_grid[rows, cols]
        tint = rng.uniform(0.85, 1.35, (count, 1)).astype(np.float32)
        self.colors = np.clip(colors[rows, cols] * tint, 0, 255).astype(np.float32)
        self.vx = rng.uniform(width * 0.16, width * 0.40, count).astype(np.float32)
        self.ax = rng.uniform(width * 0.20, width * 0.45, count).astype(np.float32)
        self.vy = rng.uniform(-height * 0.14, height * 0.03, count).astype(np.float32)
        self.wobble = rng.uniform(2.0, 9.0, count).astype(np.float32)
        self.wobble_phase = rng.uniform(0, 2 * np.pi, count).astype(np.float32)
        self.life = rng.uniform(0.75, PARTICLE_SECONDS - LAUNCH_SECONDS, count).astype(np.float32)
        self.size = rng.integers(2, CELL + 1, count)

        points = cv2.findNonZero((self.mask > 0.01).astype(np.uint8))
        self.body = cv2.boundingRect(points) if points is not None else None

    def render(self, background: np.ndarray, age: float) -> np.ndarray:
        output = background.copy()
        if self.body is not None:
            x, y, width, height = self.body
            area = np.s_[y:y + height, x:x + width]
            alpha = (self.mask[area] * (self.launch_at[area] > age))[:, :, None]
            output[area] = (
                self.person[area].astype(np.float32) * alpha
                + output[area].astype(np.float32) * (1.0 - alpha)
            ).astype(np.uint8)

        elapsed = age - self.launch
        active = (elapsed >= 0) & (elapsed < self.life)
        if not active.any():
            return output
        elapsed = elapsed[active]
        fade = 1.0 - elapsed / self.life[active]
        xs = self.x0[active] + self.vx[active] * elapsed + 0.5 * self.ax[active] * elapsed ** 2
        ys = (self.y0[active] + self.vy[active] * elapsed
              + self.wobble[active] * np.sin(elapsed * 9.0 + self.wobble_phase[active]))
        xs, ys = xs.astype(np.int32), ys.astype(np.int32)
        sizes = np.maximum(1, (self.size[active] * (0.4 + 0.6 * fade)).astype(np.int32))
        colors = self.colors[active]
        alpha = fade[:, None]
        height, width = output.shape[:2]
        for dy in range(CELL):
            for dx in range(CELL):
                px, py = xs + dx, ys + dy
                chosen = (sizes > max(dx, dy)) & (px >= 0) & (px < width) & (py >= 0) & (py < height)
                if not chosen.any():
                    continue
                py, px = py[chosen], px[chosen]
                under = output[py, px].astype(np.float32)
                output[py, px] = (colors[chosen] * alpha[chosen]
                                  + under * (1.0 - alpha[chosen])).astype(np.uint8)
        return output
