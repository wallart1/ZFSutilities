"""Notifications configuration dialog (File → Notifications…).

Configures the desktop and email notification channels: per-channel mode
(off / failures only / all runs), per-run-type toggles, SMTP connection
settings, and delivery test buttons. Settings persist through
feature_config.save_notifications_config; the SMTP password goes to the
root-only credentials file via notifications.save_smtp_password.
"""

import gi

gi.require_version("Gtk", "3.0")
from feature_config import NOTIFICATION_TYPES, get_notifications_config, save_notifications_config
from gi.repository import Gtk
from logging_config import log_msg
from notifications import (
    load_smtp_password,
    run_type_label,
    save_smtp_password,
    send_desktop_test,
    send_email_test,
)

MODE_CHOICES = (
    ("off", "Off"),
    ("failures", "Failures only"),
    ("all", "All runs"),
)

SECURITY_CHOICES = (
    ("starttls", "STARTTLS"),
    ("ssl", "SSL/TLS"),
    ("none", "None"),
)


def _combo_value(combo, choices):
    """Return the value key for the combo's active row."""
    idx = combo.get_active()
    if isinstance(idx, int) and 0 <= idx < len(choices):
        return choices[idx][0]
    return choices[0][0]


def _set_combo_value(combo, choices, value):
    """Select the row whose value key matches *value* (first row fallback)."""
    for idx, (key, _text) in enumerate(choices):
        if key == value:
            combo.set_active(idx)
            return
    combo.set_active(0)


class NotificationsDialog:
    """Modal-ish dialog editing the notifications config for one session."""

    def __init__(self, parent, config):
        self.config = config
        self._settings = get_notifications_config(config)
        self._widgets = {}
        self.dialog = self._build_dialog(parent)
        self._load()

    # -- construction ------------------------------------------------------

    def _build_dialog(self, parent):
        dialog = Gtk.Dialog(title="Notifications", transient_for=parent, flags=0)
        dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        dialog.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)
        dialog.set_default_size(560, -1)

        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_margin_top(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_bottom(10)

        box.pack_start(self._build_desktop_frame(), False, False, 0)
        box.pack_start(self._build_email_frame(), False, False, 0)
        return dialog

    def _build_mode_row(self, channel):
        """Return (box, combo) for the channel's mode selection."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        label = Gtk.Label(label="Notify:")
        label.set_halign(Gtk.Align.START)
        combo = Gtk.ComboBoxText()
        for _key, text in MODE_CHOICES:
            combo.append_text(text)
        combo.set_active(0)
        row.pack_start(label, False, False, 0)
        row.pack_start(combo, False, False, 0)
        self._widgets[f"{channel}_mode"] = combo
        return row

    def _build_type_row(self, channel):
        """Return the run-type toggle row for the channel."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        checks = {}
        for run_type in NOTIFICATION_TYPES:
            check = Gtk.CheckButton(label=run_type_label(run_type))
            checks[run_type] = check
            row.pack_start(check, False, False, 0)
        self._widgets[f"{channel}_types"] = checks
        return row

    def _build_desktop_frame(self):
        frame = Gtk.Frame(label="Desktop notifications")
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_top(6)
        vbox.set_margin_bottom(6)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)

        vbox.pack_start(self._build_mode_row("desktop"), False, False, 0)
        vbox.pack_start(self._build_type_row("desktop"), False, False, 0)

        hint = Gtk.Label(label="Bubbles appear on this host's logged-in desktop session.")
        hint.set_halign(Gtk.Align.START)
        hint.get_style_context().add_class("dim-label")
        vbox.pack_start(hint, False, False, 0)

        button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        test_button = Gtk.Button(label="Show test notification")
        test_button.connect("clicked", self._on_test_desktop)
        status = Gtk.Label(label="")
        status.set_halign(Gtk.Align.START)
        self._widgets["desktop_status"] = status
        button_row.pack_start(test_button, False, False, 0)
        button_row.pack_start(status, False, False, 0)
        vbox.pack_start(button_row, False, False, 0)

        frame.add(vbox)
        return frame

    def _build_email_frame(self):
        frame = Gtk.Frame(label="Email notifications")
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_top(6)
        vbox.set_margin_bottom(6)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)

        vbox.pack_start(self._build_mode_row("email"), False, False, 0)
        vbox.pack_start(self._build_type_row("email"), False, False, 0)
        vbox.pack_start(self._build_smtp_grid(), False, False, 0)

        button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        test_button = Gtk.Button(label="Send test email")
        test_button.connect("clicked", self._on_test_email)
        status = Gtk.Label(label="")
        status.set_halign(Gtk.Align.START)
        self._widgets["email_status"] = status
        button_row.pack_start(test_button, False, False, 0)
        button_row.pack_start(status, False, False, 0)
        vbox.pack_start(button_row, False, False, 0)

        frame.add(vbox)
        return frame

    def _build_smtp_grid(self):
        grid = Gtk.Grid()
        grid.set_row_spacing(6)
        grid.set_column_spacing(10)

        def attach(row, text, widget, widget2=None):
            label = Gtk.Label(label=text)
            label.set_halign(Gtk.Align.END)
            grid.attach(label, 0, row, 1, 1)
            if widget2 is not None:
                grid.attach(widget, 1, row, 1, 1)
                grid.attach(widget2, 2, row, 1, 1)
            else:
                grid.attach(widget, 1, row, 2, 1)

        host = Gtk.Entry()
        host.set_width_chars(1)
        host.set_placeholder_text("smtp.example.com")
        self._widgets["smtp_host"] = host

        port = Gtk.SpinButton.new_with_range(1, 65535, 1)
        port.set_value(587)
        self._widgets["smtp_port"] = port

        security = Gtk.ComboBoxText()
        for _key, text in SECURITY_CHOICES:
            security.append_text(text)
        security.set_active(0)
        self._widgets["smtp_security"] = security

        username = Gtk.Entry()
        username.set_width_chars(1)
        self._widgets["smtp_username"] = username

        password = Gtk.Entry()
        password.set_width_chars(1)
        password.set_visibility(False)
        self._widgets["smtp_password"] = password
        show_password = Gtk.CheckButton(label="Show")
        show_password.connect("toggled", self._on_toggle_password_visibility)
        password_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        password_box.pack_start(password, True, True, 0)
        password_box.pack_start(show_password, False, False, 0)

        from_addr = Gtk.Entry()
        from_addr.set_width_chars(1)
        from_addr.set_placeholder_text("optional — defaults to the username")
        self._widgets["smtp_from"] = from_addr

        to_addrs = Gtk.Entry()
        to_addrs.set_width_chars(1)
        to_addrs.set_placeholder_text("you@example.com, other@example.com")
        self._widgets["smtp_to"] = to_addrs

        attach(0, "SMTP server:", host)
        attach(1, "Port:", port)
        attach(2, "Security:", security)
        attach(3, "Username:", username)
        attach(4, "Password:", password_box)
        attach(5, "From address:", from_addr)
        attach(6, "Send to:", to_addrs)

        hint = Gtk.Label(label="Recipients are comma-separated. A blank username skips SMTP login.")
        hint.set_halign(Gtk.Align.START)
        hint.get_style_context().add_class("dim-label")
        grid.attach(hint, 0, 7, 3, 1)
        return grid

    # -- load / collect ----------------------------------------------------

    def _load(self):
        desktop = self._settings["desktop"]
        email = self._settings["email"]
        _set_combo_value(self._widgets["desktop_mode"], MODE_CHOICES, desktop["mode"])
        _set_combo_value(self._widgets["email_mode"], MODE_CHOICES, email["mode"])
        for run_type, check in self._widgets["desktop_types"].items():
            check.set_active(desktop["types"].get(run_type, True))
        for run_type, check in self._widgets["email_types"].items():
            check.set_active(email["types"].get(run_type, True))
        self._widgets["smtp_host"].set_text(email.get("smtp_host", ""))
        self._widgets["smtp_port"].set_value(email.get("smtp_port", 587))
        _set_combo_value(
            self._widgets["smtp_security"], SECURITY_CHOICES, email.get("smtp_security")
        )
        self._widgets["smtp_username"].set_text(email.get("smtp_username", ""))
        self._widgets["smtp_password"].set_text(load_smtp_password())
        self._widgets["smtp_from"].set_text(email.get("smtp_from", ""))
        self._widgets["smtp_to"].set_text(", ".join(email.get("smtp_to", [])))

    def _collect(self):
        """Read every widget into a notifications-shaped settings dict."""
        return {
            "desktop": {
                "mode": _combo_value(self._widgets["desktop_mode"], MODE_CHOICES),
                "types": {
                    run_type: check.get_active()
                    for run_type, check in self._widgets["desktop_types"].items()
                },
            },
            "email": {
                "mode": _combo_value(self._widgets["email_mode"], MODE_CHOICES),
                "types": {
                    run_type: check.get_active()
                    for run_type, check in self._widgets["email_types"].items()
                },
                "smtp_host": self._widgets["smtp_host"].get_text().strip(),
                "smtp_port": int(self._widgets["smtp_port"].get_value()),
                "smtp_security": _combo_value(self._widgets["smtp_security"], SECURITY_CHOICES),
                "smtp_username": self._widgets["smtp_username"].get_text().strip(),
                "smtp_from": self._widgets["smtp_from"].get_text().strip(),
                "smtp_to": self._widgets["smtp_to"].get_text(),
            },
        }

    def _password(self):
        return self._widgets["smtp_password"].get_text()

    # -- callbacks ---------------------------------------------------------

    def _on_toggle_password_visibility(self, check):
        self._widgets["smtp_password"].set_visibility(check.get_active())

    def _on_test_desktop(self, _button):
        self._widgets["desktop_status"].set_text("Sending test notification…")
        send_desktop_test(
            on_done=lambda ok: self._widgets["desktop_status"].set_text(
                "Test notification sent." if ok else "Test failed — see the log panel."
            )
        )

    def _on_test_email(self, _button):
        self._widgets["email_status"].set_text("Sending test email…")
        send_email_test(
            config={"notifications": self._collect()},
            password=self._password(),
            on_done=lambda ok: self._widgets["email_status"].set_text(
                "Test email sent." if ok else "Test failed — see the log panel."
            ),
        )

    # -- run / save --------------------------------------------------------

    def _save(self):
        save_notifications_config(self.config, self._collect())
        save_smtp_password(self._password())
        log_msg("INFO: Notification settings saved")

    def run(self):
        """Show the dialog; persist settings when OK is pressed."""
        self.dialog.show_all()
        response = self.dialog.run()
        if response == Gtk.ResponseType.OK:
            self._save()
        self.dialog.destroy()
