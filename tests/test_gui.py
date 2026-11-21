import os
import tempfile
import unittest
from unittest import mock

import fake_gi
from cobra_rgb import config, hidraw
from cobra_rgb.protocol import MODES, ORDERS, mode_by_key
from fakes import FakeDevice, fake_mouse

BLUE_ORIGINAL = bytes([0x00, 0x00, 0xFF, 0x01, 0x00, 0x02, 0x01])


def setUpModule():
    global glib, saved_modules, gui
    glib, saved_modules = fake_gi.install()
    from cobra_rgb import gui  # noqa: F401  (importado depois do GTK falso)


def tearDownModule():
    fake_gi.uninstall(saved_modules)


class GuiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = {"XDG_CONFIG_HOME": os.path.join(self.tmp.name, "cfg"), "XDG_DATA_HOME": os.path.join(self.tmp.name, "data")}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        self.dev = FakeDevice()
        self.open = mock.patch.object(hidraw, "open_mouse", side_effect=lambda: fake_mouse(self.dev))
        self.open.start()
        glib.idle.clear()
        glib.timeouts.clear()
        self.w = gui.CobraWindow(gui.Gtk.Application())
        glib.run_pending()

    def tearDown(self):
        self.open.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_startup_reads_the_mouse(self):
        self.assertIn("Perfil ativo: 1", self.w.status.label)
        self.assertIn("DPI: 1600 (nível 2)", self.w.status.label)
        self.assertIn("400 / 1600", self.w.status.label)
        self.assertEqual(self.w.profile_dd.model[0], "Perfil 1 (ativo)")
        self.assertEqual(self.w.color, (0, 0, 255))
        self.assertEqual(self.w.hex_label.label, "#0000FF")
        self.assertEqual(MODES[self.w.mode_dd.selected].key, "fixo")
        self.assertEqual(self.w.bright.value, 1)
        self.assertFalse(self.w.speed.sensitive)  # fixo nao usa velocidade
        self.assertIn("backup", self.w.msg.label)
        self.assertTrue(config.backup_file().exists())

    def test_preset_and_apply(self):
        self.w.swatch_buttons[6].emit("clicked")  # roxo
        self.w.bright.set_value(3)
        self.w.apply_btn.emit("clicked")
        self.assertEqual(self.dev.visible, bytes([0x8C, 0x00, 0xFF, 0x01, 0x01, 0x02, 0x03]))
        self.assertIn("msg-ok", self.w.msg.css)

    def test_color_dialog(self):
        rgba = gui.Gdk.RGBA()
        rgba.parse("#ff5a00")
        self.w.color_btn.set_rgba(rgba)
        self.assertEqual(self.w.color, (255, 90, 0))
        self.assertEqual(self.w.hex_label.label, "#FF5A00")

    def test_mode_changes_what_is_editable(self):
        self.w.mode_dd.set_selected(MODES.index(mode_by_key("arco-iris")))
        self.assertTrue(self.w.speed.sensitive)
        self.assertFalse(self.w.color_btn.sensitive)
        self.w.mode_dd.set_selected(MODES.index(mode_by_key("desligado")))
        self.assertFalse(self.w.speed.sensitive)

    def test_other_profile(self):
        self.w.profile_dd.set_selected(1)
        self.assertEqual(MODES[self.w.mode_dd.selected].key, "onda")
        self.assertEqual(self.w.color, (255, 0, 0))
        self.w.swatch_buttons[3].emit("clicked")  # verde
        self.w.apply_btn.emit("clicked")
        self.assertEqual(self.dev.led(1)[:3], b"\x00\xff\x00")
        self.assertEqual(self.dev.visible, BLUE_ORIGINAL)
        self.assertIn("não é o perfil ativo", self.w.msg.label)

    def test_led_test_runs_and_restores(self):
        self.w.profile_dd.set_selected(2)
        lit = []
        real_set = self.dev.set_feature

        def spy(packet):
            real_set(packet)
            if not lit or lit[-1] != self.dev.visible:
                lit.append(self.dev.visible)

        self.dev.set_feature = spy
        self.w.test_btn.emit("clicked")
        self.assertTrue(self.w.testing)
        self.assertFalse(self.w.apply_btn.sensitive)
        self.assertEqual(self.w.profile_dd.selected, 0)  # testa no perfil ativo
        glib.run_pending()
        self.assertEqual([v[:3] for v in lit],  # azul de antes, R, G, B, branco, azul restaurado
                         [b"\x00\x00\xff", b"\xff\x00\x00", b"\x00\xff\x00", b"\x00\x00\xff", b"\xff\xff\xff",
                          b"\x00\x00\xff"])
        self.assertEqual(self.dev.visible, BLUE_ORIGINAL)
        self.assertFalse(self.w.testing)
        self.assertTrue(self.w.apply_btn.sensitive)
        self.assertIn("Teste feito", self.w.msg.label)

    def test_closing_during_test_restores(self):
        self.w.test_btn.emit("clicked")
        self.assertEqual(self.dev.visible[:3], b"\xff\x00\x00")
        self.w._on_close(self.w.win)
        self.assertEqual(self.dev.visible, BLUE_ORIGINAL)
        self.assertTrue(self.dev.closed)
        glib.run_pending()  # o timeout que sobrou nao pode quebrar nada

    def test_order_change_is_saved(self):
        self.w.order_dd.set_selected(ORDERS.index("GRB"))
        self.assertEqual(config.load_order(), "GRB")
        self.assertEqual(self.w.color, (0, 0, 255))  # azul nao muda com G/R trocados

    def test_restore_backup(self):
        self.w.swatch_buttons[0].emit("clicked")
        self.w.apply_btn.emit("clicked")
        self.assertEqual(self.dev.visible[:3], b"\xff\x00\x00")
        self.w.restore_btn.emit("clicked")
        self.assertEqual(self.dev.visible, BLUE_ORIGINAL)
        self.assertIn("restauradas", self.w.msg.label)

    def test_usb_error_then_reconnect(self):
        self.dev.fail_after = len(self.dev.packets)
        self.w.apply_btn.emit("clicked")
        self.assertIn("msg-err", self.w.msg.css)
        self.assertIsNone(self.w.mouse)
        self.dev.fail_after = None
        self.w.read_btn.emit("clicked")
        self.assertIsNotNone(self.w.mouse)
        self.assertIn("Configuração lida", self.w.msg.label)

    def test_mouse_missing(self):
        self.open.stop()
        with mock.patch.object(hidraw, "find_devices", return_value=[]):
            self.w.read_btn.emit("clicked")
        self.open.start()
        self.assertIn("não encontrado", self.w.status.label)
        self.assertIsNone(self.w.mouse)


if __name__ == "__main__":
    unittest.main()
