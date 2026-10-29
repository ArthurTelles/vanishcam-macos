import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from goku_effect import (
    FREEZE_SECONDS, TELEPORT_SECONDS, Face, GokuTeleport, face_from_detection,
    fingers_on_forehead, render_teleport, two_fingers_together,
)
from particles_effect import PARTICLE_SECONDS, ParticleBurst


def straight(mcp, tip):
    mcp, tip = np.array(mcp, float), np.array(tip, float)
    return [mcp + (tip - mcp) * k for k in (0, 1 / 3, 2 / 3, 1)]


def folded(mcp):
    mcp = np.array(mcp, float)
    return [mcp, mcp + (3, -22), mcp + (2, -7), mcp + (-2, 8)]


def hand(index_tip=(88, 140), middle_tip=(100, 135), ring_open=False, offset=(0, 0)):
    points = np.zeros((21, 2))
    points[0] = (100, 300)
    points[1:5] = [(85, 285), (75, 265), (72, 250), (74, 238)]
    points[5:9] = straight((90, 220), index_tip)
    points[9:13] = straight((100, 218), middle_tip)
    points[13:17] = straight((110, 222), (115, 140)) if ring_open else folded((110, 222))
    points[17:21] = folded((120, 228))
    points += offset
    return np.column_stack([points, np.zeros(21)])


FACE = Face(left=60, top=120, width=90, height=110, eye_y=160)


class GokuPoseTests(unittest.TestCase):
    def test_two_fingers_together_is_recognized(self):
        self.assertTrue(two_fingers_together(hand()))

    def test_v_sign_open_hand_and_invalid_points_are_rejected(self):
        self.assertFalse(two_fingers_together(hand(index_tip=(55, 145), middle_tip=(118, 135))))
        self.assertFalse(two_fingers_together(hand(ring_open=True)))
        self.assertFalse(two_fingers_together(np.full((21, 3), np.nan)))
        self.assertFalse(two_fingers_together(np.zeros((20, 3))))

    def test_pose_needs_fingertips_on_the_forehead(self):
        self.assertTrue(fingers_on_forehead([(hand(), None)], [FACE]))
        chin = Face(left=60, top=300, width=90, height=110, eye_y=340)
        self.assertFalse(fingers_on_forehead([(hand(), None)], [chin]))
        self.assertFalse(fingers_on_forehead([(hand(offset=(400, 0)), None)], [FACE]))
        self.assertFalse(fingers_on_forehead([(hand(), None)], []))

    def test_world_landmarks_rescue_a_flattened_image_view(self):
        flattened = hand()
        flattened[8] = flattened[6]
        self.assertFalse(fingers_on_forehead([(flattened, None)], [FACE]))
        self.assertTrue(fingers_on_forehead([(flattened, hand())], [FACE]))

    def test_face_from_detection_uses_eye_keypoints(self):
        detection = SimpleNamespace(
            bounding_box=SimpleNamespace(origin_x=10, origin_y=20, width=50, height=60),
            keypoints=[SimpleNamespace(x=0.2, y=0.25), SimpleNamespace(x=0.3, y=0.35)],
        )
        face = face_from_detection(detection, 200, 100)
        self.assertEqual((face.left, face.top, face.width, face.height), (10, 20, 50, 60))
        self.assertAlmostEqual(face.eye_y, 30.0)


class TeleportRenderTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.full((60, 90, 3), 200, np.uint8)
        self.background = np.full_like(self.frame, 30)
        self.mask = np.zeros((60, 90), np.float32)
        self.mask[10:55, 30:60] = 1.0

    def test_effect_starts_clean_and_ends_on_background(self):
        start = render_teleport(self.frame, self.background, self.mask, 0.0)
        expected = np.where(self.mask[:, :, None] > 0, self.frame, self.background)
        np.testing.assert_array_equal(start, expected)
        end = render_teleport(self.frame, self.background, self.mask, TELEPORT_SECONDS)
        np.testing.assert_array_equal(end, self.background)

    def test_lines_and_stripes_appear_mid_effect(self):
        middle = render_teleport(self.frame, self.background, self.mask, 0.45)
        person = self.mask > 0
        self.assertTrue(np.any(middle[person] != self.frame[person]))
        self.assertTrue(np.any(middle[person] != self.background[person]))
        np.testing.assert_array_equal(middle[:, :5], self.background[:, :5])

    def test_lines_linger_after_the_person_is_gone(self):
        linger = render_teleport(self.frame, self.background, self.mask, FREEZE_SECONDS + 0.05)
        self.assertTrue(np.any(linger != self.background))
        self.assertFalse(np.any((linger == self.frame).all(axis=2)))


class FakeDetector:
    def __init__(self):
        self.pose = False
        self.last_hand_count = 0
        self.last_face_count = 0

    def detect(self, image, timestamp_ms):
        return self.pose


class TeleportControllerTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.full((40, 60, 3), 200, np.uint8)
        self.background = np.full_like(self.frame, 30)
        self.detector = FakeDetector()
        self.sound = Mock()
        self.teleport = GokuTeleport(self.detector, self.sound)
        self.mask_fn = Mock(return_value=np.ones((40, 60), np.float32))
        printing = patch("builtins.print")
        printing.start()
        self.addCleanup(printing.stop)

    def step(self, now, pose=None):
        if pose is not None:
            self.detector.pose = pose
        return self.teleport.update(self.frame, self.background, None, int(now * 1000),
                                    now, self.mask_fn)

    def test_hold_for_one_second_to_vanish_then_again_to_return(self):
        self.assertIs(self.step(0.0, True), self.frame)
        self.assertIs(self.step(0.5), self.frame)
        self.assertEqual(self.teleport.phase, "ready")
        self.step(1.0)
        self.assertEqual(self.teleport.phase, "out")
        self.sound.play.assert_called_once()
        middle = self.step(1.45)
        self.assertTrue(np.any(middle != self.frame))
        np.testing.assert_array_equal(self.step(2.05), self.background)
        self.assertEqual(self.teleport.phase, "vanished")

        # Manter a mão na testa não traz a pessoa de volta: é preciso baixar antes.
        self.step(2.2, True)
        self.step(3.4)
        self.assertEqual(self.teleport.phase, "vanished")
        self.step(3.5, False)
        self.step(3.6, True)
        self.step(4.0)
        self.assertEqual(self.teleport.phase, "vanished")
        self.step(4.61)
        self.assertEqual(self.teleport.phase, "in")
        self.assertEqual(self.sound.play.call_count, 2)
        self.assertIs(self.step(5.72), self.frame)
        self.assertEqual(self.teleport.phase, "ready")

    def test_breaking_the_pose_restarts_the_countdown(self):
        self.step(0.0, True)
        self.step(0.7)
        self.step(0.8, False)
        self.step(0.9, True)
        self.step(1.5)
        self.assertEqual(self.teleport.phase, "ready")
        self.step(1.91)
        self.assertEqual(self.teleport.phase, "out")

    def test_reset_goes_back_to_ready(self):
        self.step(0.0, True)
        self.step(1.0)
        self.teleport.reset()
        self.assertEqual(self.teleport.phase, "ready")
        self.assertIsNone(self.teleport.hold_started)


class ParticleTests(unittest.TestCase):
    def test_body_breaks_into_fragments_then_only_background_remains(self):
        frame = np.zeros((60, 90, 3), np.uint8)
        frame[:] = (40, 160, 220)
        background = np.full_like(frame, 25)
        mask = np.zeros((60, 90), np.float32)
        mask[10:55, 30:60] = 1.0
        burst = ParticleBurst(frame, mask)
        start = burst.render(background, 0.0)
        np.testing.assert_array_equal(start[30, 45], frame[30, 45])
        np.testing.assert_array_equal(start[0, 0], background[0, 0])
        middle = burst.render(background, 1.0)
        right_of_body = middle[:, 62:]
        self.assertTrue(np.any(right_of_body != background[:, 62:]))  # Levado pelo vento.
        np.testing.assert_array_equal(burst.render(background, PARTICLE_SECONDS), background)

    def test_empty_mask_shows_background(self):
        frame = np.full((30, 40, 3), 90, np.uint8)
        background = np.full_like(frame, 10)
        burst = ParticleBurst(frame, np.zeros((30, 40), np.float32))
        np.testing.assert_array_equal(burst.render(background, 0.5), background)


if __name__ == "__main__":
    unittest.main()
