"""Mouse falso que imita a memoria e o comportamento do King Cobra (valores lidos do mouse de verdade)."""

from cobra_rgb.protocol import RedragonMouse, led_address

REAL_DUMP = {
    0x002C: bytes([0x00, 0x00]),
    0x0032: bytes([0x01, 0x00, 0x02, 0x00, 0x02, 0x00]),
    0x0038: bytes([0x02, 0x00, 0x01, 0x00]),
    0x0042: bytes([0x01, 0x00]),
    0x0044: bytes([0x01, 0x08, 0x00, 0x08, 0x00, 0x00]),
    0x004A: bytes([0x01, 0x20, 0x00, 0x20, 0x00, 0x00]),
    0x0050: bytes([0x01, 0x20, 0x00, 0x20, 0x00, 0x00]),
    0x0056: bytes([0x01, 0x20, 0x00, 0x20, 0x00, 0x00]),
    0x005C: bytes([0x01, 0x20, 0x00, 0x20, 0x00, 0x00]),
    0x0449: bytes([0x00, 0x00, 0xFF, 0x01, 0x00, 0x02, 0x01]),
    0x0451: bytes([0xFF, 0x00, 0x00, 0x02, 0x04, 0x00, 0x02]),
    0x0459: bytes([0xFF, 0x00, 0x00, 0x02, 0x04, 0x00, 0x02]),
    0x0461: bytes([0xFF, 0x00, 0x00, 0x02, 0x04, 0x00, 0x02]),
    0x0469: bytes([0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02]),
}


class FakeDevice:
    """Transporte falso. Como no mouse real, o LED aceso (visible) so muda com a sequencia de
    selecionar perfil (grava 0x2C fora da sessao e depois 02 f1 02 01)."""

    def __init__(self):
        self.mem = bytearray(0x800)
        for addr, data in REAL_DUMP.items():
            self.mem[addr:addr + len(data)] = data
        self.in_session = False
        self.response = bytes(16)
        self.select_pending = False
        self.visible = self.led(self.mem[0x2C])
        self.packets = []
        self.closed = False
        self.fail_after = None  # numero de pacotes ate simular um erro de USB

    def led(self, profile):
        a = led_address(profile)
        return bytes(self.mem[a:a + 7])

    def set_feature(self, packet):
        assert len(packet) == 16 and packet[0] == 0x02, packet
        if self.fail_after is not None and len(self.packets) >= self.fail_after:
            raise OSError(5, "Input/output error")
        self.packets.append(bytes(packet))
        cmd, addr, length = packet[1], packet[2] | (packet[3] << 8), packet[4]
        if cmd == 0xF5:
            self.in_session = packet[2] == 0x00
        elif cmd == 0xF2:
            self.response = bytes(packet[:8]) + bytes(self.mem[addr:addr + length]).ljust(8, b"\0")
        elif cmd == 0xF3:
            self.mem[addr:addr + length] = packet[8:8 + length]
            if addr == 0x2C and not self.in_session:
                self.select_pending = True
        elif cmd == 0xF1 and packet[2] == 0x02 and packet[3] == 0x01:
            if self.select_pending and not self.in_session:
                self.visible = self.led(self.mem[0x2C])
            self.select_pending = False

    def get_feature(self, report_id):
        assert report_id == 0x02
        return self.response

    def close(self):
        self.closed = True


def fake_mouse(device=None):
    return RedragonMouse(device or FakeDevice(), "USB Gaming Mouse", 0xFC62)
