"""Protocolo de config dos mouses Redragon com chip Holtek (VID 04D9).

Tudo vai por feature report 0x02 (16 bytes, contando o report ID) na interface de usage page 0xFFA0.
Mapeado pelo projeto mouse_m908 (github.com/dokutan/mouse_m908) e conferido no King Cobra (04D9:FC62):

    02 f5 00                                   -> abre sessao de config
    02 f5 01                                   -> fecha sessao (grava)
    02 f2 <addr lo> <addr hi> <len>            -> pede leitura; GET feature 0x02 devolve os dados do byte 8 em diante
    02 f3 <addr lo> <addr hi> <len> 0 0 0 <d>  -> grava ate 8 bytes
    02 f1 02 <secao>                           -> recarrega uma secao (usado em select_profile)

Gravar o LED so muda a memoria: o LED so troca de cor depois da sequencia de "selecionar perfil"
que o software oficial manda (select_profile), enviada fora da sessao.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Protocol

VID = 0x04D9
PIDS = (0xFC62, 0xFC30)  # King Cobra (testado) e Cobra M711 classico
REPORT_ID = 0x02
REPORT_LEN = 16
PROFILES = 5

ADDR_ACTIVE_PROFILE = 0x002C
ADDR_DPI_ACTIVE = 0x0042  # so o layout do perfil 1 foi confirmado neste mouse


def led_address(profile: int) -> int:
    return 0x0449 + 8 * profile


@dataclass(frozen=True)
class Mode:
    key: str
    name: str
    a: int
    b: int
    uses_color: bool
    uses_speed: bool


MODES = (
    Mode("fixo", "Fixo", 0x01, 0x02, True, False),
    Mode("respirando", "Respirando", 0x01, 0x04, True, True),
    Mode("piscando", "Piscando", 0x01, 0x10, True, True),
    Mode("arco-iris", "Arco-íris", 0x01, 0x08, False, True),
    Mode("respirando-arco-iris", "Respirando arco-íris", 0x01, 0x01, False, True),
    Mode("onda", "Onda", 0x02, 0x00, True, True),
    Mode("reativo", "Reativo (acende ao clicar)", 0x07, 0x00, True, True),
    Mode("reativo-botao", "Reativo por botão", 0x03, 0x00, True, True),
    Mode("aleatorio", "Aleatório", 0x04, 0x00, False, True),
    Mode("alternado", "Alternado", 0x06, 0x00, True, True),
    Mode("desligado", "Desligado", 0x00, 0x00, False, False),
)

ORDERS = ("RGB", "RBG", "GRB", "GBR", "BRG", "BGR")

TEST_COLORS = (
    ("VERMELHO", (255, 0, 0)),
    ("VERDE", (0, 255, 0)),
    ("AZUL", (0, 0, 255)),
    ("BRANCO", (255, 255, 255)),
)


def find_mode(a: int, b: int) -> Mode | None:
    return next((m for m in MODES if m.a == a and m.b == b), None)


def mode_by_key(key: str) -> Mode:
    return next(m for m in MODES if m.key == key)


@dataclass
class LedState:
    r: int
    g: int
    b: int
    mode_a: int
    speed: int
    mode_b: int
    brightness: int

    @classmethod
    def from_bytes(cls, d: bytes) -> LedState:
        return cls(*d[:7])

    def to_bytes(self) -> bytes:
        return bytes([self.r, self.g, self.b, self.mode_a, self.speed, self.mode_b, self.brightness])

    @property
    def mode(self) -> Mode | None:
        return find_mode(self.mode_a, self.mode_b)


def encode_color(rgb: tuple[int, int, int], order: str) -> tuple[int, int, int]:
    """Cor real -> bytes na ordem que o LED espera."""
    value = dict(zip("RGB", rgb))
    return tuple(value[ch] for ch in order)


def decode_color(state: LedState, order: str) -> tuple[int, int, int]:
    """Bytes gravados no mouse -> cor real."""
    value = dict(zip(order, (state.r, state.g, state.b)))
    return value["R"], value["G"], value["B"]


def build_state(rgb: tuple[int, int, int], mode: Mode, brightness: int, speed: int, order: str = "RGB") -> LedState:
    r, g, b = encode_color(rgb, order)
    return LedState(r, g, b, mode.a, speed, mode.b, brightness)


def parse_hex_color(text: str) -> tuple[int, int, int]:
    s = text.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        raise ValueError(f"cor inválida: {text!r} (use algo tipo ff0000)")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


@dataclass
class DpiInfo:
    active_level: int
    levels: list[int] = field(default_factory=list)
    enabled: list[bool] = field(default_factory=list)


@dataclass
class Snapshot:
    active_profile: int
    leds: list[LedState]
    polling_hz: list[int]
    dpi: DpiInfo | None


class Transport(Protocol):
    def set_feature(self, packet: bytes) -> None: ...
    def get_feature(self, report_id: int) -> bytes: ...
    def close(self) -> None: ...


_POLLING = {1: 1000, 2: 500, 4: 250, 8: 125}


class RedragonMouse:
    def __init__(self, transport: Transport, name: str = "USB Gaming Mouse", pid: int = 0xFC62):
        self.transport = transport
        self.name = name
        self.pid = pid

    def close(self) -> None:
        self.transport.close()

    def __enter__(self) -> RedragonMouse:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- transporte ---

    def _set(self, *packet: int) -> None:
        self.transport.set_feature(bytes(packet).ljust(REPORT_LEN, b"\0"))

    def begin(self) -> None:
        self._set(REPORT_ID, 0xF5, 0x00)

    def end(self) -> None:
        self._set(REPORT_ID, 0xF5, 0x01)

    @contextmanager
    def session(self):
        self.begin()
        try:
            yield self
        finally:
            self.end()

    def read(self, addr: int, length: int) -> bytes:
        if not 1 <= length <= 8:
            raise ValueError("leitura de 1 a 8 bytes")
        self._set(REPORT_ID, 0xF2, addr & 0xFF, addr >> 8, length)
        return self.transport.get_feature(REPORT_ID)[8:8 + length]

    def write(self, addr: int, data: bytes) -> None:
        if not 1 <= len(data) <= 8:
            raise ValueError("escrita de 1 a 8 bytes")
        self._set(REPORT_ID, 0xF3, addr & 0xFF, addr >> 8, len(data), 0, 0, 0, *data)

    def select_profile(self, profile: int) -> None:
        """Sequencia que o software oficial manda ao selecionar perfil; e ela que faz o LED
        recarregar o que foi gravado. Chamar fora da sessao."""
        self._set(REPORT_ID, 0xF3, ADDR_ACTIVE_PROFILE & 0xFF, ADDR_ACTIVE_PROFILE >> 8, 0x02, 0, 0, 0, profile, 0)
        for section in (0x01, 0x08, 0x04, 0x02, 0x08):
            self._set(REPORT_ID, 0xF1, 0x02, section)

    # --- leituras/escritas (dentro de uma sessao) ---

    def read_active_profile(self) -> int:
        return max(0, min(PROFILES - 1, self.read(ADDR_ACTIVE_PROFILE, 1)[0]))

    def read_led(self, profile: int) -> LedState:
        return LedState.from_bytes(self.read(led_address(profile), 7))

    def write_led(self, profile: int, state: LedState) -> None:
        data = state.to_bytes()
        self.write(led_address(profile), data[:6])
        self.write(led_address(profile) + 6, data[6:7])

    def read_polling_hz(self, profile: int) -> int:
        addr = 0x0032 + 2 * profile if profile < 3 else 0x0038 + 2 * (profile - 3)
        return _POLLING.get(self.read(addr, 1)[0], 0)

    def read_dpi_profile1(self) -> DpiInfo:
        info = DpiInfo(active_level=self.read(ADDR_DPI_ACTIVE, 1)[0])
        for level in range(5):
            d = self.read(ADDR_DPI_ACTIVE + 2 + 6 * level, 3)
            info.enabled.append(d[0] != 0)
            info.levels.append((d[1] | (d[2] << 8)) * 50)
        return info

    # --- operacoes completas ---

    def read_snapshot(self) -> Snapshot:
        with self.session():
            active = self.read_active_profile()
            leds = [self.read_led(p) for p in range(PROFILES)]
            polling = [self.read_polling_hz(p) for p in range(PROFILES)]
            dpi = self.read_dpi_profile1() if active == 0 else None
        return Snapshot(active, leds, polling, dpi)

    def apply_led(self, profile: int, state: LedState, active_profile: int) -> LedState:
        """Grava o LED, faz o mouse recarregar se for o perfil ativo e devolve o que ficou gravado."""
        with self.session():
            self.write_led(profile, state)
        if profile == active_profile:
            self.select_profile(profile)
        with self.session():
            return self.read_led(profile)

    def restore_leds(self, leds: dict[int, LedState], active_profile: int) -> None:
        with self.session():
            for profile, state in leds.items():
                self.write_led(profile, state)
        self.select_profile(active_profile)
