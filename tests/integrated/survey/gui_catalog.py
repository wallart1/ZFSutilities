"""gui_catalog — the survey's declarative GUI interaction catalog.

Pure data, stdlib-only, no product imports: sample.py reads it to
enumerate the GUI universe, and gui_probe.py interprets it against the
real built window.  Two layers:

L2_INTERACTIONS — single-widget interactions in the central content
areas (the "more going on" beyond action buttons): row selection,
multi-select, expand/collapse, per-row active toggles, cell edits,
entries, comboboxes, spinbuttons, the Dry Run toggle, page navigation.
Each entry names a ROLE the probe resolves by walking the page's widget
tree (first/second Gtk.TreeView, its toggle renderers, entries, ...), so
the catalog tracks the product's shape without hard widget paths.

L3_COMPOSITES — curated multi-widget sequences that bind central-area
state to the action buttons and assert the LINKAGE (sensitivity wiring,
dirty-state flow, selection scoping, persistence).  `impl` names the
probe function that executes the sequence; `checks` describes what must
hold at each step (the probe asserts programmatically).

The probe additionally reports drift: catalog entries that no longer
resolve, and interactable widgets it finds that the catalog missed.
"""

# role: how the probe drives the widget
#   select-first    select the first row of the page's first TreeView
#   select-second   select the first row of the second TreeView
#   select-multi    extend the selection to the first two rows
#   toggle-active   flip the first per-row "active" toggle renderer
#   toggle-check    flip the page's first CheckButton (grid-style pages)
#   edit-cell       commit an edit into the first editable text cell
#   cycle-combo     change the first ComboBoxText
#   set-entry       replace the text of the first Entry
#   adjust-spin     nudge the first SpinButton by one step
#   toggle-dry-run  flip the page's Dry Run toggle button
#   navigate        switch the stack to this page (sidebar click path)
#   expand-first    expand the first row of the page's tree
#   collapse-all    collapse the page's tree

L2_INTERACTIONS = {
    "backup": [
        {"suffix": "select-step", "label": "select a backup step row", "role": "select-first"},
        {
            "suffix": "toggle-step-active",
            "label": "toggle a step row active",
            "role": "toggle-active",
        },
        {"suffix": "edit-step-cell", "label": "edit a step cell", "role": "edit-cell"},
        {"suffix": "dry-run", "label": "toggle Dry Run", "role": "toggle-dry-run"},
        {"suffix": "navigate", "label": "open the Backup page", "role": "navigate"},
    ],
    "offsite": [
        {"suffix": "select-step", "label": "select an offsite step row", "role": "select-first"},
        {
            "suffix": "toggle-step-active",
            "label": "toggle a step row active",
            "role": "toggle-active",
        },
        {"suffix": "edit-step-cell", "label": "edit a step cell", "role": "edit-cell"},
        {"suffix": "dry-run", "label": "toggle Dry Run", "role": "toggle-dry-run"},
        {"suffix": "navigate", "label": "open the Offsite page", "role": "navigate"},
    ],
    "restore": [
        # The restore page's central area is an Entry/CheckButton grid
        # (no step treeview, unlike Backup/Offsite) — the widget census
        # from the first live survey run proved it.
        {"suffix": "select-step", "label": "edit a restore step field", "role": "set-entry"},
        {
            "suffix": "toggle-step-active",
            "label": "toggle a restore option",
            "role": "toggle-check",
        },
        {"suffix": "dry-run", "label": "toggle Dry Run", "role": "toggle-dry-run"},
        {"suffix": "navigate", "label": "open the Restore page", "role": "navigate"},
    ],
    "schedule": [
        {"suffix": "select-entry", "label": "select a schedule entry", "role": "select-first"},
        {
            "suffix": "select-multi",
            "label": "multi-select schedule entries",
            "role": "select-multi",
        },
        {"suffix": "set-entry", "label": "edit a schedule field", "role": "set-entry"},
        {"suffix": "adjust-spin", "label": "adjust a schedule spinbutton", "role": "adjust-spin"},
        {"suffix": "navigate", "label": "open the Schedule page", "role": "navigate"},
    ],
    "disks": [
        {"suffix": "select-disk", "label": "select a disk row", "role": "select-first"},
        {"suffix": "select-multi", "label": "multi-select disk rows", "role": "select-multi"},
        {"suffix": "navigate", "label": "open the Disks page", "role": "navigate"},
    ],
    "pools": [
        {"suffix": "select-pool", "label": "select a pool row", "role": "select-first"},
        {"suffix": "select-scrub", "label": "select a scrub-queue row", "role": "select-second"},
        {"suffix": "cycle-combo", "label": "change a pools combobox", "role": "cycle-combo"},
        {"suffix": "navigate", "label": "open the Pools page", "role": "navigate"},
    ],
    "datasets": [
        {"suffix": "select-dataset", "label": "select a dataset row", "role": "select-first"},
        {"suffix": "select-multi", "label": "multi-select dataset rows", "role": "select-multi"},
        {"suffix": "expand-first", "label": "expand a dataset row", "role": "expand-first"},
        {"suffix": "collapse-all", "label": "collapse the dataset tree", "role": "collapse-all"},
        {"suffix": "navigate", "label": "open the Datasets page", "role": "navigate"},
    ],
    "checkagainst": [
        {"suffix": "select-row", "label": "select a comparison row", "role": "select-first"},
        {"suffix": "edit-cell", "label": "edit a comparison cell", "role": "edit-cell"},
        {"suffix": "navigate", "label": "open the Check Against page", "role": "navigate"},
    ],
    "dashboard": [
        {"suffix": "select-task", "label": "select a task row", "role": "select-first"},
        {"suffix": "navigate", "label": "open the Dashboard page", "role": "navigate"},
    ],
    "logs": [
        {"suffix": "select-log", "label": "select a log row", "role": "select-first"},
        {"suffix": "select-multi", "label": "multi-select log rows", "role": "select-multi"},
        {"suffix": "navigate", "label": "open the Logs page", "role": "navigate"},
    ],
    "memory": [
        {"suffix": "select-row", "label": "select a blocksize-scan row", "role": "select-first"},
        {"suffix": "navigate", "label": "open the Memory page", "role": "navigate"},
    ],
    "retention": [
        {
            "suffix": "select-policy",
            "label": "select a retention policy row",
            "role": "select-first",
        },
        {"suffix": "adjust-spin", "label": "adjust a bucket spinbutton", "role": "adjust-spin"},
        {"suffix": "navigate", "label": "open the Retention page", "role": "navigate"},
    ],
}

# L3 composites: impl = gui_probe function key; the probe asserts every
# step named in `checks` programmatically and records pass/fail per step.
L3_COMPOSITES = [
    {
        "id": "datasets-selection-scopes-snapshot",
        "page": "datasets",
        "label": "selection drives Snapshot sensitivity and scope",
        "impl": "datasets_selection_scopes_actions",
        "checks": "no selection -> Snapshot insensitive; select a row -> "
        "sensitive; the action targets exactly the selection",
    },
    {
        "id": "backup-edit-makes-dirty-save-persists",
        "page": "backup",
        "label": "step edit flips dirty, Save persists, Revert restores",
        "impl": "backup_edit_dirty_save_revert",
        "checks": "toggle a step row -> dirty predicate True -> Save Config "
        "writes the config -> Revert Config restores the saved state",
    },
    {
        "id": "backup-dry-run-affects-runner",
        "page": "backup",
        "label": "Dry Run toggle changes the runner's posture",
        "impl": "dry_run_toggle_flips_flag",
        "checks": "toggle -> _dry_run_active True and button styling marks it; "
        "run starts in dry-run posture (log records the dry run)",
    },
    {
        "id": "pools-scrub-selection-drives-buttons",
        "page": "pools",
        "label": "scrub-queue selection drives scrub buttons",
        "impl": "pools_scrub_selection_buttons",
        "checks": "no selection -> Start Scrub state reflects it; select a "
        "pool row -> scrub buttons act on exactly that pool",
    },
    {
        "id": "schedule-selection-drives-run-now",
        "page": "schedule",
        "label": "schedule selection scopes Run Now / Delete",
        "impl": "schedule_selection_actions",
        "checks": "Run Now and Delete act only on the selected entry; with no "
        "selection they refuse or disable",
    },
    {
        "id": "logs-selection-drives-delete",
        "page": "logs",
        "label": "log selection drives Delete Selected",
        "impl": "logs_selection_delete",
        "checks": "Delete Selected requires a selection; it names exactly the "
        "selected rows in its confirmation",
    },
    {
        "id": "dashboard-selection-drives-task-actions",
        "page": "dashboard",
        "label": "task selection drives View Log / Cancel / Remove",
        "impl": "dashboard_selection_actions",
        "checks": "task actions require a selection and act on exactly it",
    },
    {
        "id": "checkagainst-add-remove-row",
        "page": "checkagainst",
        "label": "Add Row then Remove Row track row count",
        "impl": "checkagainst_add_remove_row",
        "checks": "Add Row -> row count grows; Remove Row -> shrinks back; "
        "Save persists the row set",
    },
    {
        "id": "retention-add-policy-save",
        "page": "retention",
        "label": "Add Policy -> dirty -> Save persists the policy",
        "impl": "retention_add_policy_save",
        "checks": "Add Policy grows the policy list, Save writes it to the "
        "config, Remove Policy + Save takes it back out",
    },
    {
        "id": "disks-selection-drives-wipe",
        "page": "disks",
        "label": "disk selection drives Wipe Labels sensitivity",
        "impl": "disks_selection_wipe_sensitivity",
        "checks": "Wipe Labels requires an unused-disk selection; pool-member "
        "selections leave it disabled or refused",
    },
    {
        "id": "sidebar-visits-every-page",
        "page": "*",
        "label": "sidebar navigation builds and shows every page",
        "impl": "sidebar_visits_every_page",
        "checks": "each page becomes the visible stack child and its content "
        "stays mapped afterwards",
    },
    {
        "id": "datasets-expand-selected-tree",
        "page": "datasets",
        "label": "Expand Selected / Collapse All track tree state",
        "impl": "datasets_expand_collapse",
        "checks": "Expand Selected expands the selected row's children; "
        "Collapse All leaves no expanded rows",
    },
]
