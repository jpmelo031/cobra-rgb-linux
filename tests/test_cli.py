import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from cobra_rgb import cli, config, hidraw
from fakes import FakeDevice, fake_mouse


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = {"XDG_CONFIG_HOME": os.path.join(self.tmp.name, "cfg"), "XDG_DATA_HOME": os.path.join(self.tmp.name, "data")}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        self.dev = FakeDevice()
        self.open = mock.patch.object(hidraw, "open_mouse", side_effect=lambda: fake_mouse(self.dev))
        self.open.start()

    def tearDown(self):
        self.open.stop()
        self.env.stop()
        self.tmp.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_status_reads_and_makes_backup(self):
        code, out, _ = self.run_cli("status")
        self.assertEqual(code, 0)
        self.assertIn("Perfil ativo: 1", out)
        self.assertIn("Polling: 1000 Hz", out)
        self.assertIn("DPI: 1600 (nível 2)", out)
        self.assertIn("* perfil 1: #0000ff  Fixo, brilho 1", out)
        self.assertTrue(config.backup_file().exists())
        self.assertIn("perfil1=00 00 ff 01 00 02 01", config.backup_file().read_text())

    def test_apply_keeps_what_was_not_passed(self):
        code, out, _ = self.run_cli("aplicar", "--cor", "#8c00ff", "--brilho", "3")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.dev.visible, bytes([0x8C, 0x00, 0xFF, 0x01, 0x01, 0x02, 0x03]))
        code, _, _ = self.run_cli("aplicar", "--modo", "respirando", "--velocidade", "6")
        self.assertEqual(self.dev.visible, bytes([0x8C, 0x00, 0xFF, 0x01, 0x06, 0x04, 0x03]))

    def test_apply_other_profile(self):
        code, out, _ = self.run_cli("aplicar", "--perfil", "3", "--cor", "00ff00", "--modo", "fixo")
        self.assertEqual(code, 0)
        self.assertIn("não é o perfil ativo", out)
        self.assertEqual(self.dev.led(2)[:3], b"\x00\xff\x00")
        self.assertEqual(self.dev.visible[:3], b"\x00\x00\xff")

    def test_backup_keeps_the_first_colors(self):
        self.run_cli("aplicar", "--cor", "ff0000")
        self.run_cli("aplicar", "--cor", "00ff00")
        self.assertIn("perfil1=00 00 ff 01 00 02 01", config.backup_file().read_text())
        code, out, _ = self.run_cli("restaurar")
        self.assertEqual(code, 0)
        self.assertEqual(self.dev.visible, bytes([0x00, 0x00, 0xFF, 0x01, 0x00, 0x02, 0x01]))

    def test_test_flashes_and_restores(self):
        seen = []
        real_set = self.dev.set_feature

        def spy(packet):
            real_set(packet)
            seen.append(self.dev.visible)

        self.dev.set_feature = spy
        with mock.patch.object(cli.time, "sleep"):
            code, out, _ = self.run_cli("testar")
        self.assertEqual(code, 0)
        lit = [v[:3] for i, v in enumerate(seen) if i == 0 or v != seen[i - 1]]
        self.assertEqual(lit, [b"\x00\x00\xff", b"\xff\x00\x00", b"\x00\xff\x00", b"\x00\x00\xff", b"\xff\xff\xff",
                               b"\x00\x00\xff"])
        self.assertEqual(self.dev.visible, bytes([0x00, 0x00, 0xFF, 0x01, 0x00, 0x02, 0x01]))

    def test_restore_without_backup(self):
        code, _, err = self.run_cli("restaurar")
        self.assertEqual(code, 1)
        self.assertIn("Ainda não tem backup", err)

    def test_mouse_not_found(self):
        self.open.stop()
        with mock.patch.object(hidraw, "find_devices", return_value=[]):
            code, _, err = self.run_cli("status")
        self.open.start()
        self.assertEqual(code, 1)
        self.assertIn("não encontrado", err)

    def test_usb_error_is_reported(self):
        self.dev.fail_after = 3
        code, _, err = self.run_cli("status")
        self.assertEqual(code, 1)
        self.assertIn("Erro falando com o mouse", err)

    def test_bad_color_is_rejected_before_touching_the_mouse(self):
        with self.assertRaises(SystemExit):
            self.run_cli("aplicar", "--cor", "roxo")
        self.assertEqual(self.dev.packets, [])

    def test_modes_list(self):
        code, out, _ = self.run_cli("modos")
        self.assertEqual(code, 0)
        self.assertIn("arco-iris", out)

    def test_order_from_config(self):
        config.save_order("GRB")
        self.run_cli("aplicar", "--cor", "ff0000", "--modo", "fixo")
        self.assertEqual(self.dev.visible[:3], b"\x00\xff\x00")
        code, out, _ = self.run_cli("status")
        self.assertIn("perfil 1: #ff0000", out)


if __name__ == "__main__":
    unittest.main()
