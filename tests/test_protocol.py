import unittest

from cobra_rgb.protocol import (
    MODES,
    ORDERS,
    LedState,
    build_state,
    decode_color,
    encode_color,
    find_mode,
    mode_by_key,
    parse_hex_color,
)
from fakes import FakeDevice, fake_mouse


class SnapshotTest(unittest.TestCase):
    def test_reads_real_dump(self):
        snap = fake_mouse().read_snapshot()
        self.assertEqual(snap.active_profile, 0)
        self.assertEqual(snap.leds[0], LedState(0, 0, 255, 1, 0, 2, 1))
        self.assertEqual(snap.leds[0].mode.key, "fixo")
        self.assertEqual(snap.leds[1].mode.key, "onda")
        self.assertEqual(snap.leds[4].mode.key, "desligado")
        self.assertEqual(snap.polling_hz, [1000, 500, 500, 500, 1000])
        self.assertEqual(snap.dpi.active_level, 1)
        self.assertEqual(snap.dpi.levels, [400, 1600, 1600, 1600, 1600])
        self.assertEqual(snap.dpi.enabled, [True] * 5)

    def test_reads_happen_inside_a_session(self):
        dev = FakeDevice()
        fake_mouse(dev).read_snapshot()
        self.assertEqual(dev.packets[0][:3], b"\x02\xf5\x00")
        self.assertEqual(dev.packets[-1][:3], b"\x02\xf5\x01")
        self.assertFalse(dev.in_session)


class ApplyTest(unittest.TestCase):
    def test_active_profile_changes_the_lit_led(self):
        dev = FakeDevice()
        wanted = build_state((140, 0, 255), mode_by_key("fixo"), 3, 1)
        back = fake_mouse(dev).apply_led(0, wanted, active_profile=0)
        self.assertEqual(back, wanted)
        self.assertEqual(dev.led(0), wanted.to_bytes())
        self.assertEqual(dev.visible, wanted.to_bytes())
        self.assertEqual(dev.mem[0x2C], 0)

    def test_select_sequence_is_sent_outside_the_session(self):
        dev = FakeDevice()
        fake_mouse(dev).apply_led(0, build_state((1, 2, 3), MODES[0], 3, 1), active_profile=0)
        cmds = [p[1:4] for p in dev.packets]
        select_start = cmds.index(bytes([0xF3, 0x2C, 0x00]))
        self.assertEqual(cmds[select_start - 1][:2], bytes([0xF5, 0x01]))
        self.assertEqual([c for c in cmds[select_start + 1:select_start + 6]],
                         [bytes([0xF1, 0x02, s]) for s in (0x01, 0x08, 0x04, 0x02, 0x08)])

    def test_other_profile_only_changes_memory(self):
        dev = FakeDevice()
        before = dev.visible
        wanted = build_state((0, 255, 0), mode_by_key("respirando"), 2, 5)
        fake_mouse(dev).apply_led(2, wanted, active_profile=0)
        self.assertEqual(dev.led(2), wanted.to_bytes())
        self.assertEqual(dev.visible, before)
        self.assertEqual(dev.mem[0x2C], 0)
        self.assertNotIn(0xF1, [p[1] for p in dev.packets])

    def test_restore_writes_every_profile_and_reloads(self):
        dev = FakeDevice()
        mouse = fake_mouse(dev)
        original = mouse.read_snapshot().leds
        mouse.apply_led(0, build_state((255, 255, 0), MODES[0], 3, 1), 0)
        mouse.restore_leds(dict(enumerate(original)), active_profile=0)
        self.assertEqual([dev.led(p) for p in range(5)], [s.to_bytes() for s in original])
        self.assertEqual(dev.visible, original[0].to_bytes())

    def test_rejects_bad_lengths(self):
        mouse = fake_mouse()
        with self.assertRaises(ValueError):
            mouse.read(0x10, 9)
        with self.assertRaises(ValueError):
            mouse.write(0x10, b"")


class ColorTest(unittest.TestCase):
    def test_every_order_round_trips(self):
        for order in ORDERS:
            state = build_state((10, 20, 30), MODES[0], 3, 1, order)
            self.assertEqual(decode_color(state, order), (10, 20, 30), order)

    def test_order_moves_bytes(self):
        self.assertEqual(encode_color((10, 20, 30), "GRB"), (20, 10, 30))
        self.assertEqual(encode_color((10, 20, 30), "BGR"), (30, 20, 10))

    def test_parse_hex(self):
        self.assertEqual(parse_hex_color("ff0000"), (255, 0, 0))
        self.assertEqual(parse_hex_color("#8C00FF"), (140, 0, 255))
        self.assertEqual(parse_hex_color("0f0"), (0, 255, 0))
        for bad in ("", "12345", "zzzzzz", "#1234567"):
            with self.assertRaises(ValueError, msg=bad):
                parse_hex_color(bad)

    def test_modes_are_unique(self):
        self.assertEqual(len({(m.a, m.b) for m in MODES}), len(MODES))
        self.assertEqual(len({m.key for m in MODES}), len(MODES))
        self.assertIsNone(find_mode(0x09, 0x09))


if __name__ == "__main__":
    unittest.main()
