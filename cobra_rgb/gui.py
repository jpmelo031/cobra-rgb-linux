"""Interface GTK4 do Cobra RGB."""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import config, hidraw  # noqa: E402
from .protocol import MODES, ORDERS, PROFILES, TEST_COLORS, build_state, decode_color  # noqa: E402

APP_ID = "io.github.jpmelo031.CobraRGB"

PRESETS = (
    (255, 0, 0), (255, 90, 0), (255, 210, 0),
    (0, 255, 0), (0, 255, 255), (0, 0, 255),
    (140, 0, 255), (255, 0, 140), (255, 255, 255),
)

CSS = """
.app-title { font-size: 20pt; font-weight: 800; }
.status-card { padding: 10px 12px; border-radius: 10px; background-color: alpha(currentColor, 0.07); }
.swatch { min-width: 26px; min-height: 26px; padding: 0; border-radius: 6px; border: 1px solid alpha(currentColor, 0.25); }
.swatch:disabled { opacity: 0.35; }
.msg-ok { color: #57c26b; }
.msg-err { color: #e5534b; }
""" + "".join(f".swatch-{i} {{ background: rgb({r}, {g}, {b}); }}\n" for i, (r, g, b) in enumerate(PRESETS))


def hex_color(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


class CobraWindow:
    def __init__(self, app: Gtk.Application):
        self.mouse = None
        self.leds = [None] * PROFILES
        self.active = 0
        self.color = (255, 0, 0)
        self.order = config.load_order()
        self.loading = False
        self.syncing_color = False
        self.testing = False
        self.test_queue = []
        self.test_saved = None

        self.win = Gtk.ApplicationWindow(application=app, title="Cobra RGB")
        self.win.set_resizable(False)
        self.win.set_icon_name(APP_ID)
        self.win.connect("close-request", self._on_close)
        self._build()
        GLib.idle_add(self._initial_connect)

    def present(self) -> None:
        self.win.present()

    # ---------------- UI ----------------

    def _build(self) -> None:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)

        title = Gtk.Label(label="COBRA RGB", xalign=0)
        title.add_css_class("app-title")
        subtitle = Gtk.Label(label="configurador leve pro Redragon Cobra", xalign=0)
        subtitle.add_css_class("dim-label")
        self.status = Gtk.Label(label="Procurando o mouse...", xalign=0, wrap=True, max_width_chars=50)
        self.status.add_css_class("status-card")
        for w in (title, subtitle, self.status):
            root.append(w)

        grid = Gtk.Grid(column_spacing=14, row_spacing=10)
        rows = 0

        def add_row(text: str, widget) -> None:
            nonlocal rows
            grid.attach(Gtk.Label(label=text, xalign=0), 0, rows, 1, 1)
            grid.attach(widget, 1, rows, 1, 1)
            rows += 1

        self.profile_dd = Gtk.DropDown.new_from_strings([f"Perfil {p + 1}" for p in range(PROFILES)])
        self.profile_dd.connect("notify::selected", self._on_profile_changed)
        add_row("Perfil", self.profile_dd)

        color_box = Gtk.Box(spacing=10)
        self.color_btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(title="Cor do LED", with_alpha=False))
        self.color_btn.connect("notify::rgba", self._on_color_picked)
        self.hex_label = Gtk.Label(label="")
        self.hex_label.add_css_class("dim-label")
        color_box.append(self.color_btn)
        color_box.append(self.hex_label)
        add_row("Cor", color_box)

        swatches = Gtk.Box(spacing=6)
        self.swatch_buttons = []
        for i, rgb in enumerate(PRESETS):
            b = Gtk.Button()
            b.add_css_class("swatch")
            b.add_css_class(f"swatch-{i}")
            b.set_tooltip_text(hex_color(rgb))
            b.connect("clicked", self._on_preset, rgb)
            swatches.append(b)
            self.swatch_buttons.append(b)
        add_row("", swatches)

        self.mode_dd = Gtk.DropDown.new_from_strings([m.name for m in MODES])
        self.mode_dd.connect("notify::selected", lambda *_: self._update_sensitivity())
        add_row("Modo", self.mode_dd)

        self.bright = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 3, 1)
        self.bright.set_round_digits(0)
        self.bright.set_draw_value(False)
        self.bright.set_hexpand(True)
        for value, name in ((1, "baixo"), (2, "médio"), (3, "alto")):
            self.bright.add_mark(value, Gtk.PositionType.BOTTOM, name)
        add_row("Brilho", self.bright)

        self.speed = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 8, 1)
        self.speed.set_round_digits(0)
        self.speed.set_digits(0)
        self.speed.set_draw_value(True)
        self.speed.set_value_pos(Gtk.PositionType.RIGHT)
        for value in range(1, 9):
            self.speed.add_mark(value, Gtk.PositionType.BOTTOM, None)
        add_row("Velocidade", self.speed)

        order_box = Gtk.Box(spacing=10)
        self.order_dd = Gtk.DropDown.new_from_strings(list(ORDERS))
        self.order_dd.set_selected(ORDERS.index(self.order))
        self.order_dd.connect("notify::selected", self._on_order_changed)
        hint = Gtk.Label(label="só mexe se o teste de LED mostrar cor trocada", xalign=0, wrap=True, max_width_chars=26)
        hint.add_css_class("dim-label")
        order_box.append(self.order_dd)
        order_box.append(hint)
        add_row("Ordem das cores", order_box)
        root.append(grid)

        buttons = Gtk.Box(spacing=8, homogeneous=True)
        self.apply_btn = Gtk.Button(label="Aplicar")
        self.apply_btn.add_css_class("suggested-action")
        self.apply_btn.connect("clicked", self._on_apply)
        self.test_btn = Gtk.Button(label="Testar LEDs")
        self.test_btn.connect("clicked", self._on_test)
        self.read_btn = Gtk.Button(label="Ler do mouse")
        self.read_btn.connect("clicked", lambda *_: self._connect())
        for b in (self.apply_btn, self.test_btn, self.read_btn):
            buttons.append(b)
        root.append(buttons)

        self.restore_btn = Gtk.Button(label="Restaurar as cores que estavam antes (backup)", halign=Gtk.Align.START)
        self.restore_btn.add_css_class("flat")
        self.restore_btn.connect("clicked", self._on_restore)
        root.append(self.restore_btn)

        self.msg = Gtk.Label(label="", xalign=0, wrap=True, max_width_chars=50)
        root.append(self.msg)

        self.inputs = [self.profile_dd, self.color_btn, *self.swatch_buttons, self.mode_dd, self.bright,
                       self.speed, self.order_dd, self.apply_btn, self.test_btn, self.read_btn, self.restore_btn]
        self.win.set_child(root)

    def _say(self, text: str, kind: str | None = None) -> None:
        self.msg.remove_css_class("msg-ok")
        self.msg.remove_css_class("msg-err")
        if kind:
            self.msg.add_css_class(f"msg-{kind}")
        self.msg.set_label(text)

    def _set_busy(self, busy: bool) -> None:
        for w in self.inputs:
            w.set_sensitive(not busy)
        if not busy:
            self._update_sensitivity()

    def _update_sensitivity(self) -> None:
        selected = self.mode_dd.get_selected()
        if selected >= len(MODES):
            return
        mode = MODES[selected]
        self.speed.set_sensitive(mode.uses_speed)
        for w in (self.color_btn, *self.swatch_buttons):
            w.set_sensitive(mode.uses_color)

    def _set_color(self, rgb) -> None:
        self.color = tuple(int(v) for v in rgb)
        self.hex_label.set_label(hex_color(self.color).upper())
        rgba = Gdk.RGBA()
        rgba.parse(hex_color(self.color))
        self.syncing_color = True
        try:
            self.color_btn.set_rgba(rgba)
        finally:
            self.syncing_color = False

    def _on_color_picked(self, button, _pspec) -> None:
        if self.syncing_color:
            return
        c = button.get_rgba()
        self._set_color((round(c.red * 255), round(c.green * 255), round(c.blue * 255)))

    def _on_preset(self, _button, rgb) -> None:
        self._set_color(rgb)

    def _on_profile_changed(self, dropdown, _pspec) -> None:
        if not self.loading and dropdown.get_selected() < PROFILES:
            self._show_profile(dropdown.get_selected())

    def _on_order_changed(self, dropdown, _pspec) -> None:
        if self.loading or dropdown.get_selected() >= len(ORDERS):
            return
        self.order = ORDERS[dropdown.get_selected()]
        try:
            config.save_order(self.order)
        except OSError:
            pass
        self._show_profile(self.profile_dd.get_selected())
        self._say(f"Ordem das cores: {self.order}. Clica em 'Testar LEDs' pra conferir.")

    def _show_profile(self, p: int) -> None:
        if not 0 <= p < PROFILES or self.leds[p] is None:
            return
        s = self.leds[p]
        self.loading = True
        try:
            self.mode_dd.set_selected(MODES.index(s.mode or MODES[0]))
            self.bright.set_value(max(1, min(3, s.brightness)))
            self.speed.set_value(max(1, min(8, s.speed)))
        finally:
            self.loading = False
        self._set_color(decode_color(s, self.order))
        self._update_sensitivity()

    # ---------------- mouse ----------------

    def _close_mouse(self) -> None:
        if self.mouse is not None:
            try:
                self.mouse.close()
            except OSError:
                pass
            self.mouse = None

    def _fail(self, error: Exception) -> None:
        self._close_mouse()
        self._say(f"Deu erro falando com o mouse: {error}\nConfere se ele tá plugado e clica em 'Ler do mouse'.", "err")

    def _ensure_mouse(self) -> bool:
        return self.mouse is not None or self._connect()

    def _initial_connect(self) -> bool:
        self._connect()
        return GLib.SOURCE_REMOVE

    def _connect(self) -> bool:
        self._close_mouse()
        try:
            self.mouse = hidraw.open_mouse()
            snap = self.mouse.read_snapshot()
        except (hidraw.MouseNotFound, hidraw.NoPermission) as e:
            self._close_mouse()
            self.status.set_label(str(e))
            self._say("")
            return False
        except OSError as e:
            self._fail(e)
            return False

        self.active = snap.active_profile
        self.leds = list(snap.leds)
        hz = snap.polling_hz[self.active]
        lines = [f"{self.mouse.name}  ·  04D9:{self.mouse.pid:04X}"]
        line = f"Perfil ativo: {self.active + 1}   ·   Polling: {f'{hz} Hz' if hz else '?'}"
        if snap.dpi and 0 <= snap.dpi.active_level < 5:
            line += f"   ·   DPI: {snap.dpi.levels[snap.dpi.active_level]} (nível {snap.dpi.active_level + 1})"
        lines.append(line)
        if snap.dpi:
            levels = [str(v) for v, on in zip(snap.dpi.levels, snap.dpi.enabled) if on]
            lines.append("Níveis de DPI salvos: " + " / ".join(levels))
        self.status.set_label("\n".join(lines))

        try:
            made = config.save_backup_if_missing(self.leds)
        except OSError:
            made = False

        self.loading = True
        names = [f"Perfil {p + 1}" + (" (ativo)" if p == self.active else "") for p in range(PROFILES)]
        self.profile_dd.set_model(Gtk.StringList.new(names))
        self.profile_dd.set_selected(self.active)
        self.loading = False
        self._show_profile(self.active)
        self._say(f"Configuração lida. Salvei um backup das cores atuais em {config.backup_file()}."
                  if made else "Configuração lida do mouse.")
        return True

    def _on_apply(self, *_args) -> None:
        if not self._ensure_mouse():
            return
        p = self.profile_dd.get_selected()
        if p >= PROFILES or self.mode_dd.get_selected() >= len(MODES):
            return
        mode = MODES[self.mode_dd.get_selected()]
        wanted = build_state(self.color, mode, round(self.bright.get_value()), round(self.speed.get_value()), self.order)
        try:
            back = self.mouse.apply_led(p, wanted, self.active)
        except OSError as e:
            self._fail(e)
            return
        self.leds[p] = back
        if back.to_bytes() != wanted.to_bytes():
            self._say(f"O mouse aceitou, mas devolveu valores diferentes ({back.to_bytes().hex(' ')}).", "err")
        elif p == self.active:
            self._say(f"Aplicado no perfil {p + 1} e salvo na memória do mouse.", "ok")
        else:
            self._say(f"Salvo no perfil {p + 1}. Ele não é o perfil ativo, então essa cor só aparece "
                      "quando você trocar pra ele no mouse.", "ok")

    def _on_test(self, *_args) -> None:
        if self.testing or not self._ensure_mouse():
            return
        p = self.active  # o teste so aparece no LED do perfil ativo
        self.loading = True
        self.profile_dd.set_selected(p)
        self.loading = False
        self.test_saved = self.leds[p]
        self.test_queue = list(TEST_COLORS)
        self.testing = True
        self._set_busy(True)
        self._test_step()

    def _test_step(self) -> bool:
        if not self.testing or self.mouse is None:
            return GLib.SOURCE_REMOVE
        p = self.active
        try:
            if self.test_queue:
                name, rgb = self.test_queue.pop(0)
                self.mouse.apply_led(p, build_state(rgb, MODES[0], 3, 1, self.order), p)
                self._say(f"Olha o mouse: ele tem que estar {name} agora.")
                GLib.timeout_add(1800, self._test_step)
                return GLib.SOURCE_REMOVE
            self.mouse.apply_led(p, self.test_saved, p)
            self._say("Teste feito, voltei pro que tava antes. Se alguma cor veio trocada (pediu VERMELHO e veio "
                      "VERDE, por ex.), muda a 'Ordem das cores' e testa de novo. Se o BRANCO saiu puxado pra uma "
                      "cor, algum LED tá fraco.")
        except OSError as e:
            self._fail(e)
        self.testing = False
        self._set_busy(False)
        self._show_profile(p)
        return GLib.SOURCE_REMOVE

    def _on_restore(self, *_args) -> None:
        try:
            leds = config.load_backup()
        except FileNotFoundError:
            self._say("Ainda não tem backup (ele é criado na primeira vez que o programa lê o mouse).", "err")
            return
        except OSError as e:
            self._say(f"Não consegui ler o backup: {e}", "err")
            return
        if not leds:
            self._say("O backup tá vazio ou corrompido.", "err")
            return
        if not self._ensure_mouse():
            return
        try:
            self.mouse.restore_leds(leds, self.active)
        except OSError as e:
            self._fail(e)
            return
        if self._connect():
            self._say(f"Cores originais restauradas ({len(leds)} perfis).", "ok")

    def _on_close(self, _window) -> bool:
        if self.testing and self.mouse is not None and self.test_saved is not None:
            try:
                self.mouse.apply_led(self.active, self.test_saved, self.active)
            except OSError:
                pass
        self.testing = False
        self._close_mouse()
        return False


def _install_css() -> None:
    provider = Gtk.CssProvider()
    if hasattr(provider, "load_from_string"):  # GTK 4.12+
        provider.load_from_string(CSS)
    else:
        provider.load_from_data(CSS, -1)
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                              Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def run() -> int:
    app = Gtk.Application(application_id=APP_ID)
    windows = []

    def on_activate(application) -> None:
        if not windows:
            _install_css()
            windows.append(CobraWindow(application))
        windows[0].present()

    app.connect("activate", on_activate)
    return app.run([sys.argv[0]])
