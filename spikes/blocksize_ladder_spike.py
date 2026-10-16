#!/usr/bin/env python3
"""Blocksize-ladder spike — both renderers in the real GTK3 stack.

Task 2.4 proof that the Alignment view's blocksize-relationship visual
renders at quality through the charting decision's selected renderer
(matplotlib ``FigureCanvasGTK3Agg``) and stays meaningful through the
Cairo fallback, from the same shared vocabulary:

1. ``charting.create_blocksize_ladder()`` selects matplotlib on this
   host and returns a canvas that packs into a real ``Gtk.Window``.
2. The ladder renders a two-pool sample — aligned pool, misaligned
   ashift-9 pool below its 4K disks, recordsize below the ashift block,
   512-byte guest sectors — with per-pool dashed ashift reference lines
   and state colours; the Agg buffer is non-blank.
3. The Cairo ``BlocksizeLadder`` (alignment_page fallback) draws the
   same ``blocksize_ladder()`` data side by side, also non-blank.
4. A window screenshot is written for visual review.

Run headless:

    NO_AT_BRIDGE=1 xvfb-run -a python3 spikes/blocksize_ladder_spike.py

Outputs ``spikes/blocksize_ladder_spike.png``; exit status 0 only if all
checks pass.
"""

import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in (os.path.join(_REPO, "python"),):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import gi

gi.require_version("Gtk", "3.0")

import alignment_stats as astats
from alignment_analysis import blocksize_ladder
from charting import MatplotlibBlocksizeLadder, create_blocksize_ladder
from gi.repository import GLib, Gtk
from zfs_repository import TopologyNode

_SCREENSHOT = os.path.join(_REPO, "spikes", "blocksize_ladder_spike.png")
_FAILURES = []


def _check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        _FAILURES.append(name)


def _member(path, logical, physical):
    return astats.MemberDisk(path=path, logical_sector=logical, physical_sector=physical)


def _topo_node(name, vdev_type, children=None):
    return TopologyNode(
        name=name,
        vdev_type=vdev_type,
        state="ONLINE" if vdev_type == "disk" else "-",
        read=0,
        write=0,
        cksum=0,
        ashift=None,
        children=children or [],
    )


def _sample():
    """Two pools: an aligned ashift-12 mirror and a misaligned ashift-9 stripe."""
    pools = [
        astats.PoolAlignment(
            name="tank",
            ashift_configured="12",
            ashift_effective=12,
            topology=_topo_node(
                "tank",
                "pool",
                [
                    _topo_node(
                        "mirror-0",
                        "mirror",
                        [
                            _topo_node("/dev/disk/by-id/ata-A1", "disk"),
                            _topo_node("/dev/disk/by-id/ata-A2", "disk"),
                        ],
                    ),
                    _topo_node("logs", "log", [_topo_node("/dev/disk/by-id/ata-S1", "disk")]),
                ],
            ),
            members=[
                _member("/dev/disk/by-id/ata-A1", 512, 4096),
                _member("/dev/disk/by-id/ata-A2", 512, 4096),
                _member("/dev/disk/by-id/ata-S1", 512, 4096),
            ],
        ),
        astats.PoolAlignment(
            name="old",
            ashift_configured="9",
            ashift_effective=9,
            topology=_topo_node(
                "old",
                "pool",
                [
                    _topo_node(
                        "mirror-1",
                        "mirror",
                        [
                            _topo_node("/dev/disk/by-id/ata-B1", "disk"),
                            _topo_node("/dev/disk/by-id/ata-B2", "disk"),
                        ],
                    )
                ],
            ),
            members=[
                _member("/dev/disk/by-id/ata-B1", 512, 4096),
                _member("/dev/disk/by-id/ata-B2", 512, 4096),
            ],
        ),
    ]
    datasets = [
        astats.DatasetBlocks(
            name="tank/backups", kind="filesystem", recordsize="128K", recordsize_source="local"
        ),
        astats.DatasetBlocks(
            name="tank/media", kind="filesystem", recordsize="128K", recordsize_source="local"
        ),
        astats.DatasetBlocks(
            name="tank/db", kind="filesystem", recordsize="512", recordsize_source="local"
        ),
        astats.DatasetBlocks(
            name="tank/vm-201-disk-0", kind="volume", volblocksize="16K", volblocksize_source="-"
        ),
        astats.DatasetBlocks(
            name="old/vm-205-disk-0", kind="volume", volblocksize="8K", volblocksize_source="-"
        ),
    ]
    return astats.AlignmentSample(
        monotonic=1.0,
        pools=pools,
        datasets=datasets,
        vm_disks={
            "vm-201-disk-0": astats.VMOption(
                vmid="201", disknum="0", bus="scsi0", options={"discard": "1"}
            ),
            "vm-205-disk-0": astats.VMOption(
                vmid="205", disknum="0", bus="virtio0", options={"discard": "1", "secs": "4096"}
            ),
        },
        pools_available=True,
        datasets_available=True,
        pve_available=True,
    )


def _nonblank(widget):
    """True when the widget's rendered pixels are not one uniform colour."""
    from gi.repository import Gdk

    window = widget.get_window()
    if window is None:
        return False
    pixbuf = Gdk.pixbuf_get_from_window(
        window, 0, 0, widget.get_allocated_width(), widget.get_allocated_height()
    )
    if pixbuf is None:
        return False
    pixels = pixbuf.get_pixels()
    first = pixels[:3]
    return any(pixels[i : i + 3] != first for i in range(0, len(pixels) - 2, 997))


def main():
    Gtk.init_check()
    sample = _sample()
    ladder_data = blocksize_ladder(sample)

    mpl = create_blocksize_ladder()
    _check("factory selected matplotlib on this host", isinstance(mpl, MatplotlibBlocksizeLadder))
    mpl.update(ladder_data)

    # The Cairo fallback, fed the very same data, side by side.
    from alignment_page import BlocksizeLadder

    cairo_ladder = BlocksizeLadder()
    cairo_ladder.update(ladder_data)

    win = Gtk.Window(title="Blocksize ladder spike")
    win.set_default_size(940, 760)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    box.set_margin_start(12)
    box.set_margin_end(12)
    box.set_margin_top(12)
    box.set_margin_bottom(12)
    box.pack_start(Gtk.Label(label="matplotlib renderer (selected)"), False, False, 0)
    box.pack_start(mpl.widget, False, False, 0)
    box.pack_start(Gtk.Label(label="Cairo fallback renderer"), False, False, 0)
    box.pack_start(cairo_ladder.widget, False, False, 0)
    win.add(box)
    win.show_all()
    win.connect("destroy", Gtk.main_quit)

    def _verify():
        _check("matplotlib ladder rendered non-blank", _nonblank(mpl.widget))
        _check("cairo ladder rendered non-blank", _nonblank(cairo_ladder.widget))
        win.get_window().process_updates(True)
        # Window screenshot for visual review.
        try:
            import cairo as cairo_mod

            surface = cairo_mod.ImageSurface(
                cairo_mod.FORMAT_ARGB32, win.get_allocated_width(), win.get_allocated_height()
            )
            ctx = cairo_mod.Context(surface)
            win.draw(ctx)
            surface.write_to_png(_SCREENSHOT)
            _check(f"screenshot written ({_SCREENSHOT})", os.path.exists(_SCREENSHOT))
        except Exception as exc:  # pragma: no cover - spike diagnostics
            _check(f"screenshot written ({exc})", False)
        Gtk.main_quit()
        return False

    GLib.timeout_add(800, _verify)
    GLib.timeout_add(4000, Gtk.main_quit)  # hard stop
    Gtk.main()
    if _FAILURES:
        print(f"{len(_FAILURES)} FAILED")
        return 1
    print("BLOCKSIZE-LADDER-SPIKE-OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
