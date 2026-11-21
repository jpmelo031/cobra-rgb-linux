"""Acesso ao mouse pelo /dev/hidraw* do Linux, sem dependencias."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .protocol import PIDS, REPORT_LEN, VID, RedragonMouse

SYSFS_HIDRAW = "/sys/class/hidraw"
VENDOR_USAGE_PAGE_ITEM = b"\x06\xa0\xff"  # Usage Page (0xFFA0) no report descriptor da interface de config

UDEV_HINT = (
    "Instala a regra do udev (o pacote do Arch ja instala) e pluga o mouse de novo:\n"
    "  sudo install -Dm644 data/70-cobra-rgb.rules /usr/lib/udev/rules.d/70-cobra-rgb.rules\n"
    "  sudo udevadm control --reload && sudo udevadm trigger"
)


def _ioc(direction: int, kind: str, nr: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord(kind) << 8) | nr


def hidiocsfeature(size: int) -> int:
    return _ioc(3, "H", 0x06, size)  # _IOC_WRITE | _IOC_READ


def hidiocgfeature(size: int) -> int:
    return _ioc(3, "H", 0x07, size)


class MouseNotFound(Exception):
    pass


class NoPermission(Exception):
    pass


@dataclass
class HidrawDevice:
    node: str
    pid: int
    name: str


def _parse_uevent(text: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def find_devices(sysfs_root: str = SYSFS_HIDRAW, dev_root: str = "/dev") -> list[HidrawDevice]:
    """Acha os hidraw da interface de config (cada interface USB vira um hidraw; a de config e a
    que tem a usage page 0xFFA0 no report descriptor)."""
    if not os.path.isdir(sysfs_root):
        return []
    found = []
    for entry in sorted(os.listdir(sysfs_root)):
        base = os.path.join(sysfs_root, entry, "device")
        try:
            with open(os.path.join(base, "uevent"), encoding="utf-8", errors="replace") as fh:
                uevent = _parse_uevent(fh.read())
            with open(os.path.join(base, "report_descriptor"), "rb") as fh:
                rdesc = fh.read()
        except OSError:
            continue
        parts = uevent.get("HID_ID", "").split(":")  # ex: 0003:000004D9:0000FC62
        if len(parts) != 3:
            continue
        try:
            vid, pid = int(parts[1], 16), int(parts[2], 16)
        except ValueError:
            continue
        if vid != VID or pid not in PIDS or VENDOR_USAGE_PAGE_ITEM not in rdesc:
            continue
        found.append(HidrawDevice(os.path.join(dev_root, entry), pid, uevent.get("HID_NAME") or "USB Gaming Mouse"))
    return found


class HidrawTransport:
    def __init__(self, node: str):
        self.node = node
        try:
            self.fd = os.open(node, os.O_RDWR)
        except PermissionError as e:
            raise NoPermission(f"Sem permissão pra abrir {node}.\n{UDEV_HINT}") from e

    def set_feature(self, packet: bytes) -> None:
        import fcntl

        buf = bytearray(packet)
        fcntl.ioctl(self.fd, hidiocsfeature(len(buf)), buf, True)

    def get_feature(self, report_id: int) -> bytes:
        import fcntl

        buf = bytearray(REPORT_LEN)
        buf[0] = report_id
        fcntl.ioctl(self.fd, hidiocgfeature(len(buf)), buf, True)
        return bytes(buf)

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def open_mouse() -> RedragonMouse:
    devices = find_devices()
    if not devices:
        raise MouseNotFound("Mouse Redragon (04D9:FC62) não encontrado. Tá plugado?")
    dev = devices[0]
    return RedragonMouse(HidrawTransport(dev.node), dev.name, dev.pid)
