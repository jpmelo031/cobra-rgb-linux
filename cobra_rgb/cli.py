"""Linha de comando do Cobra RGB."""

from __future__ import annotations

import argparse
import os
import sys
import time

from . import __version__, config, hidraw
from .protocol import (
    MODES,
    TEST_COLORS,
    LedState,
    RedragonMouse,
    build_state,
    decode_color,
    mode_by_key,
    parse_hex_color,
)


def hex_color(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


def describe(state: LedState, order: str) -> str:
    mode = state.mode
    name = mode.name if mode else f"modo desconhecido ({state.mode_a:#04x}, {state.mode_b:#04x})"
    return f"{hex_color(decode_color(state, order))}  {name}, brilho {state.brightness}, velocidade {state.speed}"


def cmd_status(mouse: RedragonMouse, args) -> int:
    snap = mouse.read_snapshot()
    order = config.load_order()
    made = config.save_backup_if_missing(snap.leds)

    hz = snap.polling_hz[snap.active_profile]
    print(f"{mouse.name}  ·  04D9:{mouse.pid:04X}")
    line = f"Perfil ativo: {snap.active_profile + 1}  ·  Polling: {f'{hz} Hz' if hz else '?'}"
    if snap.dpi and 0 <= snap.dpi.active_level < 5:
        line += f"  ·  DPI: {snap.dpi.levels[snap.dpi.active_level]} (nível {snap.dpi.active_level + 1})"
    print(line)
    if snap.dpi:
        print("Níveis de DPI salvos: " + " / ".join(str(v) for v, on in zip(snap.dpi.levels, snap.dpi.enabled) if on))
    print()
    for p, led in enumerate(snap.leds):
        mark = "*" if p == snap.active_profile else " "
        print(f" {mark} perfil {p + 1}: {describe(led, order)}")
    if made:
        print(f"\nBackup das cores atuais salvo em {config.backup_file()}")
    return 0


def cmd_apply(mouse: RedragonMouse, args) -> int:
    snap = mouse.read_snapshot()
    config.save_backup_if_missing(snap.leds)
    order = config.load_order()

    profile = args.perfil - 1 if args.perfil else snap.active_profile
    current = snap.leds[profile]
    rgb = args.cor or decode_color(current, order)
    mode = mode_by_key(args.modo) if args.modo else (current.mode or MODES[0])
    brightness = args.brilho or max(1, min(3, current.brightness))
    speed = args.velocidade or max(1, min(8, current.speed))

    wanted = build_state(rgb, mode, brightness, speed, order)
    back = mouse.apply_led(profile, wanted, snap.active_profile)
    if back.to_bytes() != wanted.to_bytes():
        print(f"O mouse aceitou, mas devolveu outros valores: {back.to_bytes().hex(' ')}", file=sys.stderr)
        return 1
    print(f"perfil {profile + 1}: {describe(back, order)}")
    if profile != snap.active_profile:
        print("(não é o perfil ativo: essa cor aparece quando você trocar pra ele no mouse)")
    return 0


def cmd_test(mouse: RedragonMouse, args) -> int:
    snap = mouse.read_snapshot()
    config.save_backup_if_missing(snap.leds)
    order = config.load_order()
    p = snap.active_profile
    saved = snap.leds[p]
    try:
        for name, rgb in TEST_COLORS:
            mouse.apply_led(p, build_state(rgb, MODES[0], 3, 1, order), p)
            print(f"olha o mouse: tem que estar {name} agora", flush=True)
            time.sleep(1.8)
    finally:
        mouse.apply_led(p, saved, p)
    print("Pronto, voltei pro que estava. Se alguma cor veio trocada, muda 'ordem=' em", config.config_file())
    return 0


def cmd_restore(mouse: RedragonMouse, args) -> int:
    try:
        leds = config.load_backup()
    except FileNotFoundError:
        print("Ainda não tem backup (ele é criado na primeira vez que o Cobra RGB lê o mouse).", file=sys.stderr)
        return 1
    if not leds:
        print(f"O backup em {config.backup_file()} tá vazio ou corrompido.", file=sys.stderr)
        return 1
    mouse.restore_leds(leds, mouse.read_snapshot().active_profile)
    print(f"Cores originais restauradas ({len(leds)} perfis).")
    return 0


COMMANDS = {"status": cmd_status, "aplicar": cmd_apply, "testar": cmd_test, "restaurar": cmd_restore}


def _color_arg(text: str) -> tuple[int, int, int]:
    try:
        return parse_hex_color(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cobra-rgb",
        description="Configura o LED do mouse Redragon Cobra (USB 04D9:FC62). Sem argumentos, abre a interface.",
    )
    parser.add_argument("--version", action="version", version=f"cobra-rgb {__version__}")
    sub = parser.add_subparsers(dest="cmd", metavar="comando")
    sub.add_parser("gui", help="abre a interface gráfica")
    sub.add_parser("status", help="mostra perfil, polling, DPI e o LED de cada perfil")
    sub.add_parser("modos", help="lista os modos de LED")
    ap = sub.add_parser("aplicar", help="muda o LED (o que você não passar continua como está)")
    ap.add_argument("--cor", type=_color_arg, metavar="HEX", help="ex: ff0000 ou '#8c00ff'")
    ap.add_argument("--modo", choices=[m.key for m in MODES], metavar="MODO", help="veja 'cobra-rgb modos'")
    ap.add_argument("--brilho", type=int, choices=(1, 2, 3), help="1 a 3")
    ap.add_argument("--velocidade", type=int, choices=range(1, 9), metavar="1-8")
    ap.add_argument("--perfil", type=int, choices=range(1, 6), metavar="1-5", help="padrão: o perfil ativo")
    sub.add_parser("testar", help="pisca vermelho, verde, azul e branco e volta pro que estava")
    sub.add_parser("restaurar", help="grava de volta as cores do backup")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cmd = args.cmd
    if cmd is None:
        cmd = "gui" if (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")) else "status"

    if cmd == "gui":
        try:
            from .gui import run
        except (ImportError, ValueError) as e:
            print(f"A interface precisa do GTK4 e do PyGObject (sudo pacman -S gtk4 python-gobject): {e}", file=sys.stderr)
            return 1
        return run()

    if cmd == "modos":
        for m in MODES:
            print(f"  {m.key:<22} {m.name}")
        return 0

    try:
        with hidraw.open_mouse() as mouse:
            return COMMANDS[cmd](mouse, args)
    except (hidraw.MouseNotFound, hidraw.NoPermission) as e:
        print(e, file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Erro falando com o mouse: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
