import unittest

import menu_ui


class MenuUiTests(unittest.TestCase):
    def test_render_is_double_resolution_bgr(self):
        image = menu_ui.render()
        self.assertEqual(image.shape, (menu_ui.HEIGHT * menu_ui.SCALE, menu_ui.WIDTH * menu_ui.SCALE, 3))

    def test_hover_and_choice_change_the_image(self):
        plain = menu_ui.render()
        self.assertTrue((menu_ui.render(hovered="naruto") != plain).any())
        self.assertTrue((menu_ui.render(chosen="goku") != plain).any())

    def test_hit_test_uses_image_coordinates(self):
        def center(index):
            return ((menu_ui.LIST_LEFT + 100) * menu_ui.SCALE,
                    (menu_ui.row_top(index) + menu_ui.ROW_HEIGHT // 2) * menu_ui.SCALE)

        for index, mode in enumerate(("normal", "naruto", "particles", "goku")):
            self.assertEqual(menu_ui.hit_test(*center(index)), mode)
        self.assertIsNone(menu_ui.hit_test(5, 5))
        self.assertIsNone(menu_ui.hit_test(10, center(1)[1]))


if __name__ == "__main__":
    unittest.main()
