# This file is maintained by Kimi Code. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

- 2026-10-01 (docs): `docs/docs/user-guide/gtk-gui.md` "Snapshot and hold
  actions" table — the **Delete** row says "Enabled when: Only snapshots
  and/or holds selected", but `datasets_page.update_ds_button_sensitivity()`
  (`can_delete = types <= {"dataset", "snapshot", "hold"}`) also enables
  Delete for dataset rows, and `dataset_actions.on_datasets_delete()` runs
  `zfsdelfs` pre-flight checks + deletion for selected datasets. Dataset
  deletion is not documented anywhere in the user guide. Pre-dates this
  cycle (this cycle only narrowed the condition to exclude pool and
  volume-partition rows). Not resolved (docs freeze).
