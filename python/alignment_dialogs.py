"""Alignment survey dialog — the user-declared workload half of the advice.

One dataset at a time: the dataset selected in the Blocksize scan (or any
other filesystem/volume from the last Alignment-view sample) and a workload
profile — or "(not surveyed)" — then Save.  The survey is stored by
feature_config and consumed by alignment_analysis.analyse(); it is advisory
input only, never an action.
"""

import gi

gi.require_version("Gtk", "3.0")
from backup_config import log_msg
from feature_config import (
    get_alignment_survey,
    get_workload_profiles,
    save_alignment_survey,
)
from gi.repository import Gtk
from gui_helpers import create_dialog

NOT_SURVEYED = "(not surveyed)"


def _info_dialog(app, message):
    dialog = create_dialog("Workload Survey", app, [(Gtk.STOCK_OK, Gtk.ResponseType.OK)])
    label = Gtk.Label(label=message)
    label.set_line_wrap(True)
    dialog.get_content_area().pack_start(label, False, False, 0)
    dialog.show_all()
    dialog.run()
    dialog.destroy()


def _selected_survey_dataset(app, datasets):
    """Dataset named by the selected Blocksize-scan row, if any.

    The Survey… button sits in the page action bar, so the row the user
    last clicked in the scan table is the natural subject: Dataset and VM
    rows map to exactly one sample dataset (their hidden identity key
    carries the full name — VM rows display only the short tail).  Pool
    and Device rows name no single dataset, so they — like an empty or
    absent selection — yield None and the combo falls back to its first
    entry.  *datasets* is the combo's list; a key naming a dataset the
    last sample no longer carries is ignored the same way.
    """
    view = getattr(app, "_alignment_chain_view", None)
    if view is None:
        return None
    selection = view.get_selection()
    if selection is None:
        return None
    chosen = selection.get_selected_rows()
    if not chosen:
        return None
    model, paths = chosen[0], chosen[1]
    for path in paths or []:
        tree_iter = model.get_iter(path) if model is not None else None
        if tree_iter is None:
            continue
        key = model.get_value(tree_iter, 0)
        if not isinstance(key, str):
            continue
        for prefix in ("Dataset:", "VM:"):
            if key.startswith(prefix) and key[len(prefix) :] in datasets:
                return key[len(prefix) :]
    return None


def open_alignment_survey(app):
    """Open the workload survey dialog and persist the answer on Save."""
    sample = getattr(app, "_alignment_sample", None)
    datasets = sorted(ds.name for ds in sample.datasets) if sample is not None else []
    if not datasets:
        _info_dialog(
            app,
            "No dataset block data yet — open the Alignment view and let it "
            "refresh once, then retry.",
        )
        return

    survey = get_alignment_survey(app.config)
    profiles = get_workload_profiles(app.config)

    dialog = create_dialog(
        "Workload Survey",
        app,
        [
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL),
            (Gtk.STOCK_OK, Gtk.ResponseType.OK),
        ],
        default_response=Gtk.ResponseType.OK,
        size=(560, 220),
    )
    grid = Gtk.Grid()
    grid.set_column_spacing(10)
    grid.set_row_spacing(10)
    dialog.get_content_area().pack_start(grid, False, False, 0)

    dataset_combo = Gtk.ComboBoxText()
    for name in datasets:
        dataset_combo.append_text(name)
    preselect = _selected_survey_dataset(app, datasets)
    dataset_combo.set_active(datasets.index(preselect) if preselect else 0)
    dataset_combo.set_tooltip_text(
        "Dataset the declaration below applies to (from the last Alignment-view "
        "sample); a Dataset or VM row selected in the Blocksize scan is preloaded"
    )

    profile_combo = Gtk.ComboBoxText()
    for choice in [NOT_SURVEYED] + sorted(profiles):
        profile_combo.append_text(choice)
    profile_combo.set_tooltip_text(
        "Declared workload for the dataset — sharpens Alignment-view "
        f"recommendations; {NOT_SURVEYED} clears the declaration"
    )

    def _sync_profile_combo():
        name = dataset_combo.get_active_text()
        current = survey.get(name, NOT_SURVEYED) if isinstance(name, str) else NOT_SURVEYED
        if current not in [NOT_SURVEYED] + sorted(profiles):
            current = NOT_SURVEYED
        model = profile_combo.get_model()
        choices = [row[0] for row in model] if model is not None else []
        profile_combo.set_active(choices.index(current) if current in choices else 0)

    dataset_combo.connect("changed", lambda _combo: _sync_profile_combo())
    _sync_profile_combo()

    def _add_row(row, caption, widget):
        label = Gtk.Label(label=caption)
        label.set_halign(Gtk.Align.START)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(widget, 1, row, 1, 1)

    _add_row(0, "Dataset:", dataset_combo)
    _add_row(1, "Declared workload:", profile_combo)

    hint = Gtk.Label()
    hint.set_markup(
        "<small><i>Advisory input: sharpens Alignment-view recommendations "
        "when observed traffic is thin.</i></small>"
    )
    hint.set_halign(Gtk.Align.START)
    hint.set_line_wrap(True)
    grid.attach(hint, 0, 2, 2, 1)

    dialog.show_all()
    response = dialog.run()
    saved = False
    if response == Gtk.ResponseType.OK:
        dataset = dataset_combo.get_active_text()
        profile = profile_combo.get_active_text()
        if isinstance(dataset, str) and dataset and isinstance(profile, str):
            if profile == NOT_SURVEYED:
                survey.pop(dataset, None)
            else:
                survey[dataset] = profile
            save_alignment_survey(app.config, survey)
            log_msg(f"INFO: Workload survey saved for {dataset} ({profile})")
            saved = True
    dialog.destroy()

    if saved:
        # The new survey changes the findings immediately; refresh in place.
        from alignment_page import refresh_alignment_view

        refresh_alignment_view(app)
