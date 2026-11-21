import os
import tempfile
import unittest

from cobra_rgb import hidraw

# trechos de report descriptor: interface do mouse (usage page generic desktop) e a de config (0xFFA0)
MOUSE_RDESC = bytes.fromhex("05010902a1010901a10005091901290515002501")
VENDOR_RDESC = bytes.fromhex("050c0901a101c006a0ff0901a1018502")


class IoctlTest(unittest.TestCase):
    def test_numbers_match_linux_headers(self):
        # HIDIOCSFEATURE(16) / HIDIOCGFEATURE(16) de <linux/hidraw.h>
        self.assertEqual(hidraw.hidiocsfeature(16), 0xC0104806)
        self.assertEqual(hidraw.hidiocgfeature(16), 0xC0104807)


class FindDevicesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, name, hid_id, rdesc, hid_name="USB Gaming Mouse"):
        d = os.path.join(self.root, name, "device")
        os.makedirs(d)
        with open(os.path.join(d, "uevent"), "w") as fh:
            fh.write(f"DRIVER=hid-generic\nHID_ID={hid_id}\nHID_NAME={hid_name}\nHID_PHYS=usb-0000:00:14.0-3/input0\n")
        with open(os.path.join(d, "report_descriptor"), "wb") as fh:
            fh.write(rdesc)

    def test_picks_only_the_config_interface(self):
        self.add("hidraw0", "0003:0000046D:0000C52B", VENDOR_RDESC, "Logitech USB Receiver")
        self.add("hidraw1", "0003:000004D9:0000FC62", MOUSE_RDESC)
        self.add("hidraw3", "0003:000004D9:0000FC62", VENDOR_RDESC)
        self.add("hidraw4", "0003:000004D9:0000A04A", VENDOR_RDESC, "Outro Holtek")
        found = hidraw.find_devices(self.root, "/dev")
        self.assertEqual([(d.node, d.pid, d.name) for d in found],
                         [(os.path.join("/dev", "hidraw3"), 0xFC62, "USB Gaming Mouse")])

    def test_ignores_broken_entries(self):
        os.makedirs(os.path.join(self.root, "hidraw0", "device"))
        self.add("hidraw1", "lixo", VENDOR_RDESC)
        self.assertEqual(hidraw.find_devices(self.root), [])

    def test_missing_sysfs(self):
        self.assertEqual(hidraw.find_devices(os.path.join(self.root, "nao-existe")), [])


if __name__ == "__main__":
    unittest.main()
