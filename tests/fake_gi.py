"""GTK falso, so pra exercitar a logica da interface sem tela (nao valida a API do GTK em si)."""

import sys
import types


class FakeWidget:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.handlers = {}
        self.css = set()
        self.children = []
        self.sensitive = True
        self.selected = 0
        self.value = 0.0
        self.label = kwargs.get("label", "")
        self.rgba = None
        self.model = None

    def connect(self, signal, callback, *extra):
        self.handlers.setdefault(signal, []).append((callback, extra))
        return len(self.handlers[signal])

    def emit(self, signal, *args):
        for callback, extra in self.handlers.get(signal, []):
            callback(self, *args, *extra)

    def add_css_class(self, name):
        self.css.add(name)

    def remove_css_class(self, name):
        self.css.discard(name)

    def set_sensitive(self, value):
        self.sensitive = value

    def set_label(self, text):
        self.label = text

    def get_label(self):
        return self.label

    def append(self, widget):
        self.children.append(widget)

    def attach(self, widget, *_pos):
        self.children.append(widget)

    def set_child(self, widget):
        self.children = [widget]

    def set_selected(self, index):
        changed = index != self.selected
        self.selected = index
        if changed:
            self.emit("notify::selected", None)

    def get_selected(self):
        return self.selected

    def set_value(self, value):
        self.value = float(value)
        self.emit("value-changed")

    def get_value(self):
        return self.value

    def set_rgba(self, rgba):
        self.rgba = rgba
        self.emit("notify::rgba", None)

    def get_rgba(self):
        return self.rgba

    def set_model(self, model):
        self.model = model

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *args, **kwargs: None


class DropDown(FakeWidget):
    @classmethod
    def new_from_strings(cls, strings):
        w = cls()
        w.model = list(strings)
        return w


class Scale(FakeWidget):
    @classmethod
    def new_with_range(cls, orientation, low, high, step):
        w = cls()
        w.value = float(low)
        return w


class StringList:
    @staticmethod
    def new(strings):
        return list(strings)


class StyleContext:
    @staticmethod
    def add_provider_for_display(*args):
        pass


class RGBA:
    def __init__(self):
        self.red = self.green = self.blue = 0.0
        self.alpha = 1.0

    def parse(self, text):
        s = text.lstrip("#")
        self.red, self.green, self.blue = (int(s[i:i + 2], 16) / 255 for i in (0, 2, 4))
        return True


class Display:
    @staticmethod
    def get_default():
        return None


class _Enum:
    def __getattr__(self, name):
        return name


class FakeGLib(types.ModuleType):
    SOURCE_REMOVE = False
    SOURCE_CONTINUE = True

    def __init__(self):
        super().__init__("gi.repository.GLib")
        self.idle = []
        self.timeouts = []

    def idle_add(self, callback, *args):
        self.idle.append((callback, args))
        return len(self.idle)

    def timeout_add(self, ms, callback, *args):
        self.timeouts.append((ms, callback, args))
        return len(self.timeouts)

    def run_pending(self):
        """Roda idle/timeouts ate esvaziar (simula o loop do GTK)."""
        while self.idle or self.timeouts:
            if self.idle:
                callback, args = self.idle.pop(0)
            else:
                _ms, callback, args = self.timeouts.pop(0)
            callback(*args)


def install():
    gtk = types.ModuleType("gi.repository.Gtk")
    for name in ("ApplicationWindow", "Box", "Label", "Grid", "Button", "ColorDialog", "ColorDialogButton",
                 "CssProvider", "Application"):
        setattr(gtk, name, type(name, (FakeWidget,), {}))
    gtk.DropDown = DropDown
    gtk.Scale = Scale
    gtk.StringList = StringList
    gtk.StyleContext = StyleContext
    gtk.Orientation = gtk.PositionType = gtk.Align = _Enum()
    gtk.STYLE_PROVIDER_PRIORITY_APPLICATION = 600

    gdk = types.ModuleType("gi.repository.Gdk")
    gdk.RGBA = RGBA
    gdk.Display = Display

    glib = FakeGLib()

    repository = types.ModuleType("gi.repository")
    repository.Gtk, repository.Gdk, repository.GLib = gtk, gdk, glib
    gi = types.ModuleType("gi")
    gi.require_version = lambda *args: None
    gi.repository = repository

    saved = {k: sys.modules.get(k) for k in ("gi", "gi.repository", "cobra_rgb.gui")}
    sys.modules["gi"] = gi
    sys.modules["gi.repository"] = repository
    sys.modules.pop("cobra_rgb.gui", None)
    return glib, saved


def uninstall(saved):
    for key, module in saved.items():
        if module is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = module
