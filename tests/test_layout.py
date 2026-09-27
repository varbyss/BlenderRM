"""Dockable-layout tests for BRM_opencode (stdlib unittest, needs a display).

Run:  python -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import types
import unittest

# Isolate HOME so tests never touch the real user config.
_TMPHOME = tempfile.mkdtemp(prefix="brm_test_home_")
os.environ["USERPROFILE"] = _TMPHOME
os.environ["HOMEDRIVE"] = ""
os.environ["HOMEPATH"] = ""
os.environ["HOME"] = _TMPHOME

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
if PROJ not in sys.path:
    sys.path.insert(0, PROJ)

try:
    import tkinter as _tk
    _r = _tk.Tk()
    _r.withdraw()
    _r.destroy()
    HAS_DISPLAY = True
except Exception:
    HAS_DISPLAY = False

PYW = os.path.join(PROJ, "BRM_opencode.pyw")


def load_brm():
    brm = types.ModuleType("brm_under_test")
    with open(PYW, encoding="utf-8") as f:
        src = f.read()
    src = src.replace(
        'if __name__ == "__main__":\n    app = BlenderRenderApp()\n    app.mainloop()', "")
    exec(compile(src, PYW, "exec"), brm.__dict__)
    return brm


@unittest.skipUnless(HAS_DISPLAY, "no Tk display available")
class LayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.brm = load_brm()

    def setUp(self):
        # Fresh config per test: layout persists to disk, so isolation matters.
        # Belt and suspenders: HOME is redirected to tmp, but back up any
        # real file first and restore it afterwards no matter what.
        self._cfg_backup = self.brm.CONFIG_FILE + ".testbak"
        try:
            if os.path.exists(self.brm.CONFIG_FILE):
                import shutil
                shutil.copy2(self.brm.CONFIG_FILE, self._cfg_backup)
        except Exception:
            pass
        try:
            os.remove(self.brm.CONFIG_FILE)
        except Exception:
            pass
        self.app = self.brm.BlenderRenderApp()
        # Park off-screen: real geometry for hit-testing, invisible to user.
        try:
            self.app.geometry("1400x900+10000+10000")
            self.app.deiconify()
        except Exception:
            self.app.withdraw()
        self.app.update_idletasks()
        self.app.update()

    def tearDown(self):
        try:
            self.app._drag = None
            self.app.destroy()
        except Exception:
            pass
        try:
            if getattr(self, "_cfg_backup", None) and os.path.exists(self._cfg_backup):
                import shutil
                shutil.copy2(self._cfg_backup, self.brm.CONFIG_FILE)
                os.remove(self._cfg_backup)
            elif os.path.exists(self.brm.CONFIG_FILE):
                os.remove(self.brm.CONFIG_FILE)
        except Exception:
            pass

    # -- pure layout validation -------------------------------------
    def test_valid_layout_accepts_permutation(self):
        lay = {"left": ["log"], "center": ["props", "view"], "right": ["queue"],
               "bottom": ["prog"]}
        self.assertEqual(self.app._valid_layout(lay), lay)

    def test_valid_layout_migrates_legacy_strings(self):
        legacy = {"left": "queue", "center": "view", "right": "props", "bottom": "log"}
        got = self.app._valid_layout(legacy)
        self.assertEqual(got["left"], ["queue"])
        self.assertEqual(got["center"], ["view"])
        self.assertEqual(got["right"], ["props"])
        flat = sorted(p for v in got.values() for p in v)
        self.assertEqual(flat, ["log", "prog", "props", "queue", "view"])

    def test_valid_layout_rejects_garbage(self):
        for bad in (None, {}, {"left": ["queue"]},
                    {"left": ["queue"], "center": ["view"], "right": ["props"], "bottom": ["log"]}):
            got = self.app._valid_layout(bad)
            self.assertEqual(got, self.brm.DEFAULT_LAYOUT, bad)

    def test_valid_layout_dedupes_to_first_slot(self):
        bad = {"left": ["queue"], "center": ["queue"], "right": ["props"],
               "bottom": ["log", "prog"]}
        got = self.app._valid_layout(bad)
        self.assertEqual(got["left"], ["queue"])
        self.assertEqual(got["center"], ["view"])
        flat = sorted(p for v in got.values() for p in v)
        self.assertEqual(flat, ["log", "prog", "props", "queue", "view"])

    def test_valid_layout_repairs_unknown_names(self):
        # unknown names are dropped, missing panels return home, the rest
        # (including tab order) is preserved instead of resetting all
        bad = {"left": ["nope"], "center": ["view"], "right": ["props"],
               "bottom": ["log", "prog"]}
        got = self.app._valid_layout(bad)
        self.assertEqual(got["left"], ["queue"])
        self.assertEqual(got["bottom"], ["log", "prog"])
        flat = sorted(p for v in got.values() for p in v)
        self.assertEqual(flat, ["log", "prog", "props", "queue", "view"])

    # -- docking (Premiere-style tabbed slots) --------------------------
    def _placed(self, app, slot):
        # Panels docked into a slot's tab group (visible or as background tab).
        try:
            return [app._panel_widget(p) for p in app.layout.get(slot, [])]
        except Exception:
            return []

    def _tab_btn(self, app, slot, panel):
        return (app.slot_tabs.get(slot) or {}).get(panel)

    def test_default_docking(self):
        app = self.app
        self.assertEqual(app.layout, self.brm.DEFAULT_LAYOUT)
        self.assertEqual(app.layout_hidden, [])
        self.assertIs(app._panel_widget("queue"), app.panel_queue)
        self.assertIs(app._panel_widget("prog"), app.panel_prog)
        for slot, panels in app.layout.items():
            for panel in panels:
                w = app._panel_widget(panel)
                self.assertIn(w, self._placed(app, slot), (slot, panel))
                # every docked panel owns a tab button
                self.assertIsNotNone(self._tab_btn(app, slot, panel), (slot, panel))
            # exactly the active tab's widget is mapped
            active = app.layout_active.get(slot)
            self.assertIn(active, panels)
            for panel in panels:
                mapped = bool(app._panel_widget(panel).winfo_ismapped())
                self.assertEqual(mapped, panel == active, (slot, panel))

    def test_bottom_tabs_prog_log(self):
        # progress + log share the bottom slot as tabs (Premiere-style):
        # exactly one is visible, clicking the other tab flips visibility.
        app = self.app
        self.assertEqual(app.layout["bottom"], ["prog", "log"])
        app.update_idletasks()
        app.update()
        self.assertEqual(app.layout_active.get("bottom"), "prog")
        self.assertTrue(app.panel_prog.winfo_ismapped())
        self.assertFalse(app.panel_log.winfo_ismapped())
        app._activate_tab("bottom", "log")
        app.update_idletasks()
        app.update()
        self.assertTrue(app.panel_log.winfo_ismapped())
        self.assertFalse(app.panel_prog.winfo_ismapped())
        # tab buttons exist for both, active one highlighted
        self.assertIsNotNone(self._tab_btn(app, "bottom", "prog"))
        self.assertIsNotNone(self._tab_btn(app, "bottom", "log"))
        self.assertEqual(
            str(self._tab_btn(app, "bottom", "log").cget("bg")).lower(),
            str(self.brm.C_LINE2).lower())

    def test_active_tab_persists(self):
        app = self.app
        app._activate_tab("bottom", "log")
        app.apply_layout()
        app.update_idletasks()
        app.update()
        self.assertEqual(app.layout_active.get("bottom"), "log")
        self.assertEqual((app.config.get("layout_active") or {}).get("bottom"), "log")
        import json
        with open(os.path.join(_TMPHOME, "blender_monitor_config.json")) as f:
            saved = json.load(f)
        self.assertEqual((saved.get("layout_active") or {}).get("bottom"), "log")
        # a fresh validation round keeps the stored active tab
        app.apply_layout()
        app.update_idletasks()
        app.update()
        self.assertEqual(app.layout_active.get("bottom"), "log")
        self.assertTrue(app.panel_log.winfo_ismapped())

    def test_view_and_prog_are_separate_panels(self):
        app = self.app
        self.assertIsNot(app.panel_view, app.panel_prog)
        # move prog to the right slot: view must stay put
        app.layout["right"].append("prog")
        app.layout["bottom"] = [p for p in app.layout["bottom"] if p != "prog"]
        app.apply_layout()
        app.update_idletasks()
        self.assertEqual(app._slot_of("prog"), "right")
        self.assertEqual(app._slot_of("view"), "center")
        self.assertTrue(app.vp_canvas.winfo_exists())
        self.assertTrue(app.lbl_prog_job.winfo_exists())

    def test_move_via_drag_end(self):
        # Premiere-style pure move: props joins left as a tab, right empties.
        app = self.app
        app._drag_start(_FakeEvent(app, 10, 10), "props")
        try:
            bar = app.slot_bar["left"]
            app._drag_end(_FakeEvent(app, bar.winfo_rootx() + 5, bar.winfo_rooty() + 5))
            self.assertEqual(app.layout["left"], ["props", "queue"])
            self.assertEqual(app.layout["right"], [])
            self.assertEqual(app._slot_of("props"), "left")
            self.assertEqual(app.layout_active.get("left"), "props")
            # persisted
            import json
            with open(os.path.join(_TMPHOME, "blender_monitor_config.json")) as f:
                saved = json.load(f)
            self.assertEqual(saved["layout"]["left"], ["props", "queue"])
            self.assertEqual(saved["layout"]["right"], [])
        finally:
            app._drag = None

    def test_drop_outside_hides_panel(self):
        # browser-tab UX: releasing far outside the window dismisses the panel
        app = self.app
        app._drag_start(_FakeEvent(app, 10, 10), "view")
        app._drag_end(_FakeEvent(app, -5000, -5000))
        self.assertIsNone(app._slot_of("view"))
        self.assertIn("view", app.layout_hidden)
        self.assertFalse(app.panel_view.winfo_ismapped())

    def test_drop_on_topbar_is_noop(self):
        # inside the window but on no slot (top bar): layout untouched
        app = self.app
        before = (dict(app.layout), list(app.layout_hidden))
        app._drag_start(_FakeEvent(app, 10, 10), "view")
        try:
            tx = app.winfo_rootx() + app.winfo_width() // 2
            ty = app.winfo_rooty() + 12
        except Exception:
            tx, ty = 10, 10
        app._drag_end(_FakeEvent(app, tx, ty))
        self.assertEqual(app.layout, before[0])
        self.assertEqual(app.layout_hidden, before[1])

    def test_presets(self):
        app = self.app
        app.set_layout_preset("Viewport left")
        self.assertEqual(app.layout["left"], ["view"])
        app.set_layout_preset("Log right")
        self.assertEqual(app.layout["right"], ["log"])
        # presets also reset hidden panels + active tabs
        app.close_panel("view")
        self.assertIn("view", app.layout_hidden)
        app.set_layout_preset("Default")
        self.assertEqual(app.layout, self.brm.DEFAULT_LAYOUT)
        self.assertEqual(app.layout_hidden, [])
        self.assertEqual(app.layout_split, {})

    def test_stack_insert_position(self):
        app = self.app
        # drop log at the TOP of the left slot -> becomes first
        app._drag_start(_FakeEvent(app, 10, 10), "log")
        try:
            f = app.slot_frames["left"]
            app._drag_end(_FakeEvent(app, f.winfo_rootx() + 5, f.winfo_rooty() + 5))
            self.assertEqual(app.layout["left"], ["log", "queue"])
            self.assertEqual(app.layout["bottom"], ["prog"])
            # reorder within the same slot: drag queue above log
            app._drag_start(_FakeEvent(app, 10, 10), "queue")
            app._drag_end(_FakeEvent(app, f.winfo_rootx() + 5, f.winfo_rooty() + 5))
            self.assertEqual(app.layout["left"], ["queue", "log"])
        finally:
            app._drag = None

    def test_empty_slot_allowed_and_collapses(self):
        app = self.app
        # queue is alone in left: dragging it out empties + collapses left
        app._drag_start(_FakeEvent(app, 10, 10), "queue")
        try:
            bar = app.slot_bar["right"]
            app._drag_end(_FakeEvent(app, bar.winfo_rootx() + 5, bar.winfo_rooty() + 5))
            self.assertEqual(app.layout["left"], [])
            self.assertIn("queue", app.layout["right"])
            self.assertEqual(app.layout_hidden, [])
            app.update_idletasks()
            app.update()
            self.assertFalse(app.slot_body["left"].winfo_ismapped())
            # queue moved to right as its active tab: still visible, there
            self.assertTrue(app.panel_queue.winfo_ismapped())
            self.assertEqual(app.layout_active.get("right"), "queue")
            # moving it back expands the slot again
            app._drag_start(_FakeEvent(app, 10, 10), "queue")
            bar = app.slot_bar["left"]
            app._drag_end(_FakeEvent(app, bar.winfo_rootx() + 5, bar.winfo_rooty() + 5))
            self.assertIn("queue", app.layout["left"])
            app.update_idletasks()
            app.update()
            self.assertTrue(app.slot_body["left"].winfo_ismapped())
            self.assertTrue(app.panel_queue.winfo_ismapped())
        finally:
            app._drag = None

    def test_valid_layout_allows_empty_slots(self):
        lay = {"left": [], "center": ["view", "queue"], "right": ["props"],
               "bottom": ["prog", "log"]}
        self.assertEqual(self.app._valid_layout(lay), lay)

    def test_valid_layout_respects_hidden(self):
        lay = {"left": ["queue"], "center": [], "right": ["props"],
               "bottom": ["prog", "log"]}
        got = self.app._valid_layout(lay, hidden=["view"])
        self.assertEqual(got["center"], [])
        flat = sorted(p for v in got.values() for p in v)
        self.assertEqual(flat, ["log", "prog", "props", "queue"])

    def test_close_reopen_panel(self):
        app = self.app
        app.close_panel("view")
        app.update_idletasks()
        app.update()
        self.assertEqual(app.layout["center"], [])
        self.assertEqual(app.layout_hidden, ["view"])
        self.assertIsNone(app._slot_of("view"))
        self.assertFalse(app.panel_view.winfo_ismapped())
        import json
        with open(os.path.join(_TMPHOME, "blender_monitor_config.json")) as f:
            saved = json.load(f)
        self.assertEqual(saved["layout"]["center"], [])
        self.assertEqual(saved.get("layout_hidden"), ["view"])
        app.show_panel("view")
        app.update_idletasks()
        app.update()
        self.assertEqual(app.layout_hidden, [])
        self.assertEqual(app._slot_of("view"), "center")
        self.assertEqual(app.layout_active.get("center"), "view")
        self.assertTrue(app.panel_view.winfo_ismapped())

    def test_legacy_string_layout_migrates(self):
        app = self.app
        legacy = {"left": "queue", "center": "view", "right": "props", "bottom": "log"}
        self.assertEqual(app._valid_layout(legacy), self.brm.DEFAULT_LAYOUT)

    def test_tabs_are_drag_handles(self):
        # tabs ARE the drag handles now (panel grip dots removed): every
        # visible panel must own a tab with press/motion/release bindings,
        # and no grip canvases may remain inside the panels.
        app = self.app
        for slot, panels in app.layout.items():
            for panel in panels:
                b = (app.slot_tabs.get(slot) or {}).get(panel)
                self.assertIsNotNone(b, "no tab for %s" % panel)
                for seq in ("<ButtonPress-1>", "<B1-Motion>", "<ButtonRelease-1>"):
                    try:
                        bound = bool(b.bind(seq))
                    except Exception:
                        bound = False
                    self.assertTrue(bound, "tab not draggable (%s): %s" % (panel, seq))
        for panel in ("queue", "view", "prog", "props", "log"):
            for w in self._all_children(app._panel_widget(panel)):
                # old grips were 14x16 dot canvases (viewport's own big
                # canvas is legitimate content and much larger)
                try:
                    tiny = (w.__class__.__name__ == "Canvas"
                            and int(w.cget("width")) <= 16
                            and int(w.cget("height")) <= 18)
                except Exception:
                    tiny = False
                self.assertFalse(tiny, "leftover grip canvas in %s" % panel)

    def _all_children(self, w):
        out = []
        try:
            kids = w.winfo_children()
        except Exception:
            return out
        for k in kids:
            # tab buttons live in the slot bar, not the panel: skip nothing,
            # but only flag small unnamed canvases (the old grip dots)
            out.append(k)
            out.extend(self._all_children(k))
        return out

    def test_drop_bottom_right_end(self):
        # tab-bar drops stay tab flow: viewport (center) lands as the LAST
        # bottom tab when dropped at the tab-bar right end or the "+" button.
        app = self.app
        self.assertEqual(app._slot_of("view"), "center")
        for probe in (self._pt_tabs_end, self._pt_plus):
            app.show_panel("view", "center")
            app.update_idletasks()
            app.update()
            tx, ty = probe(app)
            app._drag_start(_FakeEvent(app, 10, 10), "view")
            try:
                app._drag_end(_FakeEvent(app, tx, ty))
            finally:
                app._drag = None
            app.update_idletasks()
            app.update()
            self.assertEqual(app.layout["bottom"][-1], "view", (tx, ty))
            self.assertEqual(app.layout_active.get("bottom"), "view")
            self.assertTrue(app.panel_view.winfo_ismapped())
            self.assertFalse(app.panel_prog.winfo_ismapped())

    def test_drop_bottom_edge_splits(self):
        # body edge-band drops split instead: viewport lands side-by-side
        # with LOG/PROGRESS (right side), both groups visible at once.
        app = self.app
        for probe in (self._pt_body_edge, self._pt_past_edge):
            app.show_panel("view", "center")
            app.update_idletasks()
            app.update()
            tx, ty = probe(app)
            app._drag_start(_FakeEvent(app, 10, 10), "view")
            try:
                app._drag_end(_FakeEvent(app, tx, ty))
            finally:
                app._drag = None
            app.update_idletasks()
            app.update()
            sp = app.layout_split.get("bottom")
            self.assertIsNotNone(sp, (tx, ty))
            self.assertEqual(sp.get("side"), "right")
            self.assertEqual(sp.get("tabs"), ["view"])
            self.assertEqual(app.layout["bottom"], ["prog", "log"])
            # side-by-side: primary AND secondary content mapped together
            self.assertTrue(app.panel_view.winfo_ismapped())
            self.assertTrue(app.panel_prog.winfo_ismapped())
            self.assertEqual(str(app.panel_view.pack_info()["in"]),
                             str(app.slot_body2["bottom"]))
            app.close_panel("view")
            app.update_idletasks()
            app.update()

    def test_split_collapses_and_promotes(self):
        app = self.app
        app.show_panel("view", "center")
        tx, ty = self._pt_body_edge(app)
        app._drag_start(_FakeEvent(app, 10, 10), "view")
        try:
            app._drag_end(_FakeEvent(app, tx, ty))
        finally:
            app._drag = None
        app.update_idletasks()
        app.update()
        self.assertTrue(app._has_split("bottom"))
        # closing the split tab removes the split, primary untouched
        app.close_panel("view")
        app.update_idletasks()
        app.update()
        self.assertFalse(app._has_split("bottom"))
        self.assertEqual(app.layout["bottom"], ["prog", "log"])
        self.assertEqual(app.layout_hidden, ["view"])
        # closing the whole primary promotes the split back to plain tabs
        app.show_panel("view")
        app.update_idletasks()
        app.update()
        tx, ty = self._pt_body_edge(app)
        app._drag_start(_FakeEvent(app, 10, 10), "log")
        try:
            app._drag_end(_FakeEvent(app, tx, ty))
        finally:
            app._drag = None
        app.update_idletasks()
        app.update()
        self.assertTrue(app._has_split("bottom"))
        app.close_panel("prog")
        app.close_panel("view")
        app.update_idletasks()
        app.update()
        # primary emptied -> split promotes to primary tabs, split gone
        self.assertFalse(app._has_split("bottom"))
        self.assertIn("log", app.layout["bottom"])

    def test_collapse_center_really_collapses(self):
        # empty slots must shrink to a strip: center has stretch="always",
        # which used to re-absorb free space and defeat the collapse width
        app = self.app
        fr = app.slot_frames["center"]
        app.update_idletasks()
        app.update()
        self.assertGreater(fr.winfo_width(), 200)
        app.close_panel("view")
        app.update_idletasks()
        app.update()
        self.assertLessEqual(fr.winfo_width(), 60)
        app.show_panel("view")
        app.update_idletasks()
        app.update()
        self.assertGreater(fr.winfo_width(), 200)

    def _stretch_of(self, app, slot):
        return str(app.main_paned.panecget(app.slot_frames[slot], "stretch"))

    def test_rebalance_center_holder(self):
        # normal 3-pane: only a non-empty center absorbs free width,
        # sidebars keep their set widths
        app = self.app
        app.update_idletasks()
        app.update()
        self.assertEqual(self._stretch_of(app, "center"), "always")
        self.assertEqual(self._stretch_of(app, "left"), "never")
        self.assertEqual(self._stretch_of(app, "right"), "never")

    def test_rebalance_no_gray_void(self):
        # empty center: neighbors share the slack, nothing left bare
        app = self.app
        app.close_panel("view")
        app.update_idletasks()
        app.update()
        self.assertEqual(self._stretch_of(app, "center"), "never")
        self.assertEqual(self._stretch_of(app, "left"), "always")
        self.assertEqual(self._stretch_of(app, "right"), "always")
        lw = app.slot_frames["left"].winfo_width()
        cw = app.slot_frames["center"].winfo_width()
        rw = app.slot_frames["right"].winfo_width()
        mw = app.main_paned.winfo_width()
        self.assertLessEqual(cw, 60)
        self.assertLess(mw - (lw + cw + rw), 40, (lw, cw, rw, mw))
        app.show_panel("view")
        app.update_idletasks()
        app.update()
        self.assertEqual(self._stretch_of(app, "center"), "always")

    def test_band_trays_highlight(self):
        app = self.app
        app._drag_start(_FakeEvent(app, 10, 10), "view")
        try:
            body = app.slot_body["bottom"]
            app.update_idletasks()
            app.update()
            tx = body.winfo_rootx() + body.winfo_width() - 10
            ty = body.winfo_rooty() + max(30, body.winfo_height() // 2)
            app._drag_move(_FakeEvent(app, tx, ty))
            self.assertEqual(app._drag.get("target"), "bottom")
            self.assertEqual(app._drag.get("band"), "right")
            tray = (app._drag.get("trays") or {}).get(("bottom", "right"))
            self.assertIsNotNone(tray)
            self.assertEqual(str(tray.cget("bg")).lower(), "#4d80f0")
            # back to the middle: band clears, tray dims again
            app._drag_move(_FakeEvent(app,
                                      body.winfo_rootx() + body.winfo_width() // 2, ty))
            self.assertIsNone(app._drag.get("band"))
            self.assertEqual(str(tray.cget("bg")).lower(), "#101623")
        finally:
            app._drag_end(_FakeEvent(app, -5000, -5000))
            app._drag = None

    def test_split_persists(self):
        app = self.app
        tx, ty = self._pt_body_edge(app)
        app._drag_start(_FakeEvent(app, 10, 10), "view")
        try:
            app._drag_end(_FakeEvent(app, tx, ty))
        finally:
            app._drag = None
        app.update_idletasks()
        import json
        with open(os.path.join(_TMPHOME, "blender_monitor_config.json")) as f:
            saved = json.load(f)
        sp = (saved.get("layout_split") or {}).get("bottom")
        self.assertIsNotNone(sp)
        self.assertEqual(sp.get("side"), "right")
        self.assertEqual(sp.get("tabs"), ["view"])

    def _pt_tabs_end(self, app):
        bar = app.slot_bar["bottom"]
        tabs = app.slot_tabs["bottom"]
        last = tabs["log"]  # default bottom order [prog, log]
        return (last.winfo_rootx() + last.winfo_width() - 2,
                bar.winfo_rooty() + 5)

    def _pt_plus(self, app):
        bar = app.slot_bar["bottom"]
        plus = [w for w in bar.winfo_children()
                if w.__class__.__name__ == "Button"
                and str(w.cget("text")) == "+"][0]
        return (plus.winfo_rootx() + 2, plus.winfo_rooty() + 5)

    def _pt_body_edge(self, app):
        body = app.slot_body["bottom"]
        return (body.winfo_rootx() + body.winfo_width() - 5,
                body.winfo_rooty() + max(10, body.winfo_height() // 2))

    def _pt_past_edge(self, app):
        # a few px past the window's right edge: clamp must forgive it
        body = app.slot_body["bottom"]
        return (app.winfo_rootx() + app.winfo_width() + 20,
                body.winfo_rooty() + max(10, body.winfo_height() // 2))

    # -- backend still works after docking ------------------------------
    def test_rows_and_inspector_after_swap(self):
        app = self.app
        app.config["queue_list"] = [
            self.brm.migrate_queue_item({"path": r"C:\tmp\a.blend"}),
            self.brm.migrate_queue_item({"path": r"C:\tmp\b.blend"}),
        ]
        app.refresh_all_rows()
        app.update_idletasks()
        self.assertEqual(len(app.row_widgets), 2)
        app.selected_idx = 0
        app.refresh_inspector()
        app.update_idletasks()
        # swap view and props, rows/inspector must keep working
        app.layout["center"], app.layout["right"] = ["props"], ["view"]
        app.apply_layout()
        app.update_idletasks()
        app.refresh_all_rows()
        app.refresh_inspector()
        app.update_idletasks()
        self.assertEqual(len(app.row_widgets), 2)
        self.assertTrue(app.lbl_prog_job.winfo_exists())
        self.assertTrue(app.log_box.winfo_exists())
        self.assertTrue(app.vp_canvas.winfo_exists())

    # -- match source -------------------------------------------------
    def _probed_item(self, scene):
        return self.brm.migrate_queue_item({
            "path": r"C:\tmp\a.blend",
            "probe": {"active": "Scene", "fast": True, "scenes": [scene]},
        })

    def test_match_source_needs_resolution_data(self):
        # Preview probes (name + frames only) must NOT blank the item:
        # warn instead and leave everything untouched.
        app = self.app
        app.config["queue_list"] = [self._probed_item(
            {"name": "Scene", "frame_start": 1, "frame_end": 10})]
        app.selected_idx = 0
        app.refresh_all_rows()
        app.refresh_inspector()
        app.update_idletasks()
        shown = []
        orig = self.brm.messagebox.showinfo
        self.brm.messagebox.showinfo = lambda *a, **k: shown.append(a)
        try:
            app.match_source()
        finally:
            self.brm.messagebox.showinfo = orig
        item = app.config["queue_list"][0]
        self.assertTrue(shown, "expected a 'refresh file info' popup")
        self.assertIsNone(item.get("res_x"))
        self.assertIsNone(item.get("res_y"))
        self.assertIsNone(item.get("res_pct"))

    def test_match_source_fills_resolution_and_pct(self):
        app = self.app
        app.config["queue_list"] = [self._probed_item(
            {"name": "Scene", "frame_start": 1, "frame_end": 10,
             "res_x": 1920, "res_y": 1080, "res_pct": 50,
             "engine": "CYCLES", "samples": 128,
             "cameras": ["Camera"], "view_layers": ["ViewLayer"],
             "file_format": "PNG", "color_mode": "RGB",
             "fps": 24.0, "output": "//"})]
        app.selected_idx = 0
        app.refresh_all_rows()
        app.refresh_inspector()
        app.update_idletasks()
        app.match_source()
        app.update_idletasks()
        item = app.config["queue_list"][0]
        self.assertEqual(item.get("res_x"), 1920)
        self.assertEqual(item.get("res_y"), 1080)
        self.assertEqual(item.get("res_pct"), 50)
        self.assertEqual(app.lbl_pscale.cget("text"), "50%")
        eff = self.brm.effective_job_settings(item, item.get("probe"))
        self.assertEqual(eff.get("res_pct"), 50)

    # -- checkboxes ---------------------------------------------------
    def test_mkcheck_high_contrast(self):
        import tkinter as tk
        app = self.app
        fr = tk.Frame(app)
        var = tk.BooleanVar(master=app, value=False)
        c = app._mkcheck(fr, "GUI mode render (sim-safe)", var=var, cmd=lambda: None)
        self.assertIn("CheckBox", type(c).__name__)
        self.assertEqual(c.cget("checkbox_width"), 20)
        self.assertEqual(c.cget("checkbox_height"), 20)
        self.assertEqual(c.cget("border_width"), 2)
        self.assertEqual(str(c.cget("checkmark_color")).lower(), "#ffffff")
        self.assertEqual(str(c.cget("fg_color")), str(self.brm.C_ACCENT))
        c2 = app._pcheck(fr, "Film Transparent", var, lambda: None)
        self.assertIn("CheckBox", type(c2).__name__)
        self.assertEqual(c2.cget("checkbox_width"), 20)

    # -- auto deep probe ----------------------------------------------
    def _preview_item_on_disk(self, path):
        return self.brm.migrate_queue_item({
            "path": path,
            "probe": {"active": "Scene", "preview": True, "fast": True,
                      "scenes": [{"name": "Scene", "frame_start": 1,
                                  "frame_end": 10}]},
        })

    def _full_probe(self):
        return {"active": "Scene", "fast": True,
                "scenes": [{"name": "Scene", "frame_start": 1, "frame_end": 10,
                            "res_x": 1920, "res_y": 1080, "res_pct": 100,
                            "cameras": ["Camera"], "view_layers": ["ViewLayer"],
                            "engine": "CYCLES", "samples": 128,
                            "file_format": "PNG", "color_mode": "RGB",
                            "fps": 24.0, "output": "//"}]}

    def test_auto_probe_new_deep_pass(self):
        app = self.app
        fd, path = tempfile.mkstemp(suffix=".blend")
        os.close(fd)
        try:
            app.config["queue_list"] = [self._preview_item_on_disk(path)]
            calls = []
            orig = self.brm.render_probe
            def fake(blender_path, blend_file, timeout=240, **kw):
                calls.append(blend_file)
                return dict(self._full_probe())
            self.brm.render_probe = fake
            try:
                app.is_rendering = False
                app._auto_probe_new()
            finally:
                self.brm.render_probe = orig
            self.assertEqual(calls, [path])
            got = app.config["queue_list"][0].get("probe") or {}
            self.assertFalse(got.get("preview"))
            self.assertEqual((got.get("scenes") or [{}])[0].get("cameras"),
                             ["Camera"])
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    def test_auto_probe_new_skips_while_rendering(self):
        app = self.app
        fd, path = tempfile.mkstemp(suffix=".blend")
        os.close(fd)
        try:
            app.config["queue_list"] = [self._preview_item_on_disk(path)]
            orig = self.brm.render_probe
            def fake(*a, **k):
                raise AssertionError("must not probe while rendering")
            self.brm.render_probe = fake
            try:
                app.is_rendering = True
                app._auto_probe_new()
            finally:
                self.brm.render_probe = orig
                app.is_rendering = False
            got = app.config["queue_list"][0].get("probe") or {}
            self.assertTrue(got.get("preview"))
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    def test_sash_save_restore_guarded(self):
        app = self.app
        app._save_pane_sizes()  # must not crash; records widths + bottom
        sizes = app.config.get("layout_sizes") or {}
        self.assertIn("left", sizes)
        self.assertIn("right", sizes)
        app._restore_pane_sizes()  # must not crash
        # bottom height round-trips through save/restore (native sash)
        sizes = dict(app.config.get("layout_sizes") or {})
        sizes["bottom"] = 220
        app.config["layout_sizes"] = sizes
        app._restore_pane_sizes()
        app.update_idletasks()
        app.update()
        self.assertEqual(app.slot_bottom.winfo_height(), 220)
        app._save_pane_sizes()
        got = (app.config.get("layout_sizes") or {}).get("bottom", 0)
        self.assertEqual(got, 220)

    def test_validate_geometry(self):
        v = self.brm._validate_geometry
        self.assertEqual(v("1500x950+40+30", 1920, 1080), "1500x950+40+30")
        self.assertIsNone(v("junk", 1920, 1080))
        self.assertIsNone(v("", 1920, 1080))
        self.assertIsNone(v("100x100+0+0", 1920, 1080))
        # off-screen position clamps into view instead of being rejected
        self.assertIsNotNone(v("1500x950+5000+30", 1920, 1080))

    def test_save_ui_state_records_selection(self):
        app = self.app
        app.config["queue_list"] = [
            self.brm.migrate_queue_item({"path": r"C:\tmp\a.blend"}),
            self.brm.migrate_queue_item({"path": r"C:\tmp\b.blend"}),
        ]
        app.refresh_all_rows()
        app.selected_idx = 1
        app._save_ui_state()
        self.assertEqual(app.config.get("selected_path"), r"C:\tmp\b.blend")
        self.assertTrue(app.config.get("geometry"), "geometry must persist")
        self.assertIn("queue_scroll", app.config)

    def test_queue_menu_has_layout(self):
        app = self.app
        names = []
        orig_post = None
        import tkinter as tk
        real_post = tk.Menu.post
        seen = {}

        def fake_post(self, *a, **k):
            seen["menu"] = self
        tk.Menu.post = fake_post
        try:
            app.queue_menu()
        finally:
            tk.Menu.post = real_post
        m = seen.get("menu")
        self.assertIsNotNone(m)
        try:
            labels = []
            last = m.index("end")
            for i in range(last + 1):
                try:
                    if m.type(i) == "cascade":
                        labels.append(m.entrycget(i, "label"))
                except Exception:
                    pass
            self.assertIn("Layout", labels)
            self.assertIn("Panels", labels)
        finally:
            try:
                m.destroy()
            except Exception:
                pass


    # -- drop guide overlay -------------------------------------------
    def test_drop_guide_shown_and_hidden(self):
        app = self.app
        app._drag_start(_FakeEvent(app, 10, 10), "queue")
        try:
            d = app._drag
            self.assertIsNotNone(d.get("guide"))
            self.assertEqual(set(d.get("zones") or {}),
                             {"left", "center", "right", "bottom"})
            guide = d.get("guide")
            app._drag_end(_FakeEvent(app, -5000, -5000))
            self.assertIsNone(app._drag)
            if guide is not None:
                self.assertFalse(guide.winfo_exists())
        finally:
            app._drag = None
            app._hide_drop_guide()

    def test_drop_guide_highlights_hovered_zone(self):
        app = self.app
        app._drag_start(_FakeEvent(app, 10, 10), "queue")
        try:
            f = app.slot_frames["right"]
            tx = f.winfo_rootx() + max(1, f.winfo_width() // 2)
            ty = f.winfo_rooty() + max(1, f.winfo_height() // 2)
            app._drag_move(_FakeEvent(app, tx, ty))
            self.assertEqual(app._drag.get("target"), "right")
            zones = app._drag.get("zones") or {}
            self.assertIn("right", zones)
            # hovered zone uses the accent border color
            import tkinter as tk
            self.assertEqual(str(zones["right"].cget("highlightbackground")), "#4d80f0")
        finally:
            app._drag_end(_FakeEvent(app, -5000, -5000))
            app._drag = None

    def test_drop_onto_panel_resolves_its_slot(self):
        app = self.app
        # a widget deep inside the props panel must resolve to props' slot
        deep = app.prop_scroll
        self.assertEqual(app._panel_of_widget(deep), "props")
        # tab buttons resolve to their own panel too
        btn = (app.slot_tabs.get("right") or {}).get("props")
        self.assertIsNotNone(btn)
        self.assertEqual(app._panel_of_widget(btn), "props")
        self.assertEqual(app._slot_at(10**9, 10**9), None)  # off-screen: nothing

    def test_ghost_excluded_from_panel_lookup(self):
        app = self.app
        app._drag_start(_FakeEvent(app, 10, 10), "queue")
        try:
            ghost = app._drag.get("ghost")
            self.assertIsNotNone(ghost)
            self.assertIsNone(app._panel_of_widget(ghost))
        finally:
            app._drag_end(_FakeEvent(app, -5000, -5000))
            app._drag = None

    # -- settings window matches app theme ------------------------------
    def _open_settings(self):
        app = self.app
        app.open_settings_window()
        app.update_idletasks()
        app.update()
        return app.settings_win

    def _close_settings(self):
        app = self.app
        try:
            if app.settings_win is not None and app.settings_win.winfo_exists():
                app.settings_win.destroy()
        except Exception:
            pass
        app.settings_win = None

    def test_settings_window_themed(self):
        app = self.app
        win = self._open_settings()
        try:
            self.assertTrue(win.winfo_exists())
            found = {"label": False, "entry": False, "button": False,
                     "check": False, "tabview": False}

            def walk(w):
                try:
                    kids = w.winfo_children()
                except Exception:
                    return
                for k in kids:
                    cls = k.__class__.__name__
                    if cls == "CTkLabel" and not getattr(k, "_keep_style", False):
                        try:
                            self.assertEqual(tuple(k.cget("font")), tuple(self.brm.F_SET),
                                             "label font")
                        except Exception:
                            pass
                        found["label"] = True
                    elif cls == "CTkEntry":
                        self.assertEqual(k.cget("fg_color"), self.brm.C_ENTRY, "entry bg")
                        found["entry"] = True
                    elif cls == "CTkButton":
                        self.assertEqual(k.cget("corner_radius"), 0, "button radius")
                        found["button"] = True
                    elif cls == "CTkCheckBox":
                        self.assertEqual(k.cget("fg_color"), self.brm.C_ACCENT, "check accent")
                        self.assertEqual(k.cget("checkbox_width"), 22, "check size")
                        found["check"] = True
                    elif cls == "CTkTabview":
                        found["tabview"] = True
                    walk(k)

            walk(win)
            for k, v in found.items():
                self.assertTrue(v, "no %s themed in settings" % k)
        finally:
            self._close_settings()

    # -- settings entry point -----------------------------------------
    def test_settings_button_opens_window(self):
        app = self.app
        self.assertTrue(hasattr(app, "btn_settings"))
        app.btn_settings.invoke()
        app.update_idletasks()
        app.update()
        try:
            self.assertIsNotNone(app.settings_win)
            self.assertTrue(app.settings_win.winfo_exists())
        finally:
            try:
                app.settings_win.destroy()
            except Exception:
                pass
            app.settings_win = None

    def test_settings_restart_tries_and_sound(self):
        app = self.app
        win = self._open_settings()
        try:
            self.assertEqual(app.s_retries.get(), str(app.config.get("max_retries", 5)))
            self.assertTrue(bool(app.s_sound.get()) ==
                            bool(app.config.get("finish_sound", True)))
            for attr in ("s_startmsg", "s_donetitle", "s_donemsg", "s_crashtitle",
                         "s_crashmsg", "s_stoptitle", "s_stopmsg"):
                self.assertTrue(hasattr(app, attr), attr)
                self.assertTrue(getattr(app, attr).winfo_exists())
        finally:
            self._close_settings()

    def test_dfmt_fallback(self):
        app = self.app
        self.assertEqual(app._dfmt("Hi {filename}", "FB", filename="a.blend"), "Hi a.blend")
        self.assertEqual(app._dfmt("Hi {missing}", "FB {filename}", filename="a.blend"),
                         "FB a.blend")
        self.assertEqual(app._dfmt("", "FB", filename="a.blend"), "FB")

    def test_finish_sound_never_raises(self):
        import sys
        from unittest import mock
        from types import ModuleType
        fake = ModuleType("winsound")
        fake.MB_OK = 0
        fake.MessageBeep = mock.Mock(side_effect=Exception("nope"))
        fake.Beep = mock.Mock()
        with mock.patch.dict(sys.modules, {"winsound": fake}):
            self.brm.play_finish_sound()
        self.assertTrue(fake.Beep.called)

    def test_history_projects_only_done(self):
        app = self.app
        self.brm.log_history({"time": "t", "kind": "render", "file": "a.blend",
                              "status": "Done", "detail": "", "folder": ""})
        self.brm.log_history({"time": "t", "kind": "render", "file": "b.blend",
                              "status": "Failed", "detail": "", "folder": ""})
        self.brm.log_history({"time": "t", "kind": "ffmpeg", "file": "c",
                              "status": "Done", "detail": "", "folder": ""})
        got = app._history_projects()
        self.assertEqual([h["file"] for h in got], ["a.blend"])
        win = self._open_settings()
        try:
            app.refresh_history_ui()
            rows = list(app.history_box.get(0, "end"))
            self.assertEqual(len(rows), 1)
            self.assertIn("a.blend", rows[0])
        finally:
            self._close_settings()

    def test_row_sub_text(self):
        app = self.app
        eff = {"frame_start": 1, "frame_end": 250}
        t, c = app._row_sub_text({"status": "Pending", "path": "nope.blend",
                                  "enabled": True}, eff)
        self.assertEqual(t, "MISSING FILE")
        t, c = app._row_sub_text({"status": "Rendering", "current_frame": 125,
                                  "enabled": True}, eff)
        self.assertIn("50%", t)
        t, c = app._row_sub_text({"status": "Stopped", "enabled": True}, eff)
        self.assertEqual(t, "STOPPED")
        t, c = app._row_sub_text({"status": "Done", "last_duration": "1m 2s",
                                  "enabled": True}, eff)
        self.assertIn("DONE", t)
        self.assertEqual(c, self.brm.C_GREEN)
        import tempfile
        fd, mp4 = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        try:
            t, c = app._row_sub_text({"status": "Done", "enabled": True,
                                      "converted_mp4": mp4}, eff)
            self.assertIn("MP4", t)
        finally:
            os.remove(mp4)

    def test_log_tag_mapping(self):
        app = self.app
        self.assertEqual(app._log_tag("RENDER DONE: x"), "log_ok")
        self.assertEqual(app._log_tag("CONVERT DONE"), "log_ok")
        self.assertEqual(app._log_tag("RENDER CRASHED: x"), "log_err")
        self.assertEqual(app._log_tag("RENDER STOP: x"), "log_warn")
        self.assertEqual(app._log_tag("Moved VIEWPORT panel."), "log_info")
        self.assertIsNone(app._log_tag("just some line"))

    def test_pmenu_is_ctk(self):
        import tkinter as tk
        app = self.app
        var = tk.StringVar(master=app, value="a")
        om = app._pmenu(tk.Frame(app), var, ["a", "b"], lambda: None)
        try:
            self.assertEqual(om.__class__.__name__, "CTkOptionMenu")
            app._pset_menu(om, var, ["x", "y"], "y")
            self.assertEqual(var.get(), "y")
        finally:
            try:
                om.destroy()
            except Exception:
                pass

    def test_stopped_status_mappings(self):
        app = self.app
        self.assertEqual(app._status_kind({"status": "Stopped"}), "paused")
        self.assertEqual(self.brm.status_text({"status": "Stopped"}), "Stopped")
        d = self.brm.describe_item({"status": "Stopped", "path": "x.blend"})
        self.assertTrue(d.startswith("S "), d)

    def test_delete_key_removes_selected(self):
        import tkinter as tk
        app = self.app
        app.config["queue_list"] = [
            self.brm.migrate_queue_item({"path": r"C:\tmp\a.blend"}),
            self.brm.migrate_queue_item({"path": r"C:\tmp\b.blend"}),
        ]
        app.refresh_all_rows()
        app.selected_idx = 0

        class FakeWidget:
            pass
        FakeWidget.__name__ = "CTkEntry"

        class FakeEvent:
            widget = FakeWidget()
        app._on_delete_key(FakeEvent())
        self.assertEqual(len(app.config["queue_list"]), 2)

        class FakeEvent2:
            widget = tk.Frame(app)
        app._on_delete_key(FakeEvent2())
        self.assertEqual(len(app.config["queue_list"]), 1)

    def test_autodetect_blender(self):
        from unittest import mock
        with mock.patch.object(self.brm.os.path, "exists", return_value=True):
            found = self.brm.autodetect_blender()
        self.assertTrue(found and found.lower().endswith("blender.exe"), found)

    def test_row_name_stays_left_in_wide_queue(self):
        # the name column (not the status icon) must absorb extra width,
        # otherwise a dead gap opens mid-row and the name floats right
        app = self.app
        app.config["queue_list"] = [
            self.brm.migrate_queue_item({"path": r"C:\tmp\a.blend", "status": "Done"}),
        ]
        app.refresh_all_rows()
        app._slot_w["left"] = 1200
        app.apply_layout()
        app.update_idletasks()
        app.update()
        w = app.row_widgets[0]
        self.assertLess(w["name"].winfo_x(), 200)
        self.assertLessEqual(w["status"].winfo_width(), 30)
        self.assertGreater(w["frames"].winfo_x(), w["name"].winfo_x() + 200)
        self.assertEqual(w["sub"].winfo_x(), w["name"].winfo_x())

    def test_click_burst_converges_on_last(self):
        import time
        app = self.app
        app.config["queue_list"] = [
            self.brm.migrate_queue_item({"path": r"C:\tmp\job%d.blend" % i})
            for i in range(7)
        ]
        app.refresh_all_rows()
        app.update_idletasks()
        app.update()
        for i in range(7):
            app._row_click(i)
            app.update_idletasks()
        self.assertEqual(app.selected_idx, 6)
        # heavy panels trail the burst, then settle on the last click
        time.sleep(0.25)
        app.update()
        self.assertEqual(app.lbl_pfile.cget("text"), "job6.blend")
        self.assertEqual(app.vp_idx, 6)

    def test_click_paints_instantly(self):
        app = self.app
        app.config["queue_list"] = [
            self.brm.migrate_queue_item({"path": r"C:\tmp\a.blend"}),
            self.brm.migrate_queue_item({"path": r"C:\tmp\b.blend"}),
        ]
        app.refresh_all_rows()
        app.update_idletasks()
        app.update()
        app._row_click(1)
        app.update_idletasks()
        self.assertEqual(app.row_widgets[1]["frame"].cget("bg"), "#141a26")
        self.assertEqual(app.row_widgets[0]["frame"].cget("bg"),
                         self.brm.C_PANEL)

    def test_status_code_letters(self):
        app = self.app
        app.config["queue_list"] = [
            self.brm.migrate_queue_item({"path": r"C:\tmp\a.blend", "status": "Pending"}),
            self.brm.migrate_queue_item({"path": r"C:\tmp\b.blend", "status": "Rendering"}),
            self.brm.migrate_queue_item({"path": r"C:\tmp\c.blend", "status": "Done"}),
            self.brm.migrate_queue_item({"path": r"C:\tmp\d.blend", "status": "Failed"}),
            self.brm.migrate_queue_item({"path": r"C:\tmp\e.blend", "status": "Pending",
                                          "enabled": False}),
        ]
        app.refresh_all_rows()
        app.update_idletasks()
        app.update()
        codes = [w["status"].cget("text") for w in app.row_widgets]
        self.assertEqual(codes, ["Q", "R", "D", "F", "OFF"])
        self.assertEqual(app.row_widgets[2]["status"].cget("fg"), self.brm.C_GREEN)
        # crashed rows blink red/faint on the anim tick: letter is the stable part
        self.assertIn(app.row_widgets[3]["status"].cget("fg"),
                      (self.brm.C_RED, self.brm.C_FAINT))

    def test_anim_tick_keeps_text_codes(self):
        app = self.app
        app.config["queue_list"] = [
            self.brm.migrate_queue_item({"path": r"C:\tmp\a.blend", "status": "Rendering"}),
        ]
        app.refresh_all_rows()
        app.update_idletasks()
        app.update()
        app._anim_tick()
        app.update_idletasks()
        w = app.row_widgets[0]
        self.assertEqual(w["status"].cget("text"), "R")
        self.assertEqual(str(w["status"].cget("image")), "")

    def test_tooltip_delayed_single(self):
        import tkinter as tk
        app = self.app
        fr = tk.Frame(app)
        tip = self.brm.ToolTip(fr, "hello", delay=10000)
        tip._schedule()
        app.update_idletasks()
        self.assertIsNone(tip.tip_window)
        self.assertIsNotNone(tip._after)
        tip.hide_tip()
        self.assertIsNone(tip._after)
        self.assertIsNone(tip.tip_window)
        try:
            fr.destroy()
        except Exception:
            pass

    def test_hover_storm_spawns_no_tips(self):
        app = self.app
        app.config["queue_list"] = [
            self.brm.migrate_queue_item({"path": r"C:\tmp\a.blend"}),
            self.brm.migrate_queue_item({"path": r"C:\tmp\b.blend"}),
        ]
        app.refresh_all_rows()
        app.update_idletasks()
        app.update()
        widgets = []
        for w in app.row_widgets:
            widgets.extend([w["frame"], w["idx"], w["status"], w["name"],
                            w["frames"], w["sub"]])
        for _ in range(30):
            for wd in widgets:
                wd.event_generate("<Enter>")
                wd.event_generate("<Leave>")
            app.update_idletasks()
        tips = [w for w in app.winfo_children()
                if w.__class__.__name__ == "Toplevel"]
        self.assertEqual(tips, [])

    def _pump_until_preview(self, app, timeout=10):
        # Tk forbids cross-thread UI calls unless the main thread sits in
        # mainloop() (tests pump with sleep/update instead), so drive decode
        # workers synchronously here; production threads work the same way
        import time
        t0 = time.time()
        while not list(app.vp_canvas.find_withtag("preview")):
            if time.time() - t0 > timeout:
                break
            try:
                path = app.vp_path
                app._vp_decoding = False
                app._vp_pending = None
                if path:
                    app._vp_decode_worker(path, (path,))
            except Exception:
                pass
            time.sleep(0.05)
            app.update()

    def test_viewport_image_above_chrome(self):
        from PIL import Image
        import tempfile
        fd, png = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            Image.new("RGB", (32, 32), (10, 200, 90)).save(png)
            app = self.app
            app.update_image_preview(png)
            self._pump_until_preview(app)
            c = app.vp_canvas
            prev = list(c.find_withtag("preview"))
            chrome = list(c.find_withtag("chrome"))
            self.assertTrue(prev)
            if chrome:
                self.assertGreater(max(prev), max(chrome))
            # progress tiles must never cover the picture
            app.vp_update_tiles(2, 32)
            app.update_idletasks()
            self.assertEqual(list(c.find_withtag("tiles")), [])
            # cleared -> tiles may render again
            app._vp_clear_image()
            app.vp_update_tiles(2, 32)
            app.update_idletasks()
            self.assertTrue(list(c.find_withtag("tiles")))
        finally:
            try:
                os.remove(png)
            except Exception:
                pass

    def test_row_sub_spec_segments(self):
        app = self.app
        eff = {"frame_start": 0, "frame_end": 400, "scene": "Scene",
               "camera": "Camera.004", "res_x": 1920, "res_y": 1080,
               "res_pct": 100, "engine": "CYCLES", "samples": 128, "fps": 24.0}
        t, c = app._row_sub_text({"status": "Rendering", "current_frame": 56,
                                  "enabled": True}, eff)
        for seg in ("14%", "Scene", "Camera.004", "1920x1080@100%", "CYCLES 128"):
            self.assertIn(seg, t)
        t2, _ = app._row_sub_text({"status": "Pending", "enabled": True,
                                   "path": __file__}, eff)
        self.assertTrue(t2.startswith("QUEUED"), t2)
        self.assertIn("Scene", t2)

    def test_probe_gui_policy(self):
        # global ON: sim probe auto-enables per-job GUI; OFF: leaves it alone;
        # explicit per-job choices always win either way
        app = self.app
        probe = {"hurricane": True, "scenes": []}
        app.config["gui_for_hurricane"] = True
        item = self.brm.migrate_queue_item({"path": r"C:\tmp\a.blend"})
        app._apply_probe_defaults(item, probe)
        self.assertTrue(item.get("gui_mode"))
        app.config["gui_for_hurricane"] = False
        item2 = self.brm.migrate_queue_item({"path": r"C:\tmp\b.blend"})
        app._apply_probe_defaults(item2, probe)
        self.assertIsNone(item2.get("gui_mode"))
        item3 = self.brm.migrate_queue_item({"path": r"C:\tmp\c.blend",
                                             "gui_mode": False})
        app.config["gui_for_hurricane"] = True
        app._apply_probe_defaults(item3, probe)
        self.assertFalse(item3.get("gui_mode"))

    def test_gui_template_quits_with_code(self):
        # GUI Blender never exits on its own: the driver script must render
        # then quit with an exit code, or the queue hangs after sim jobs
        gen = self.brm.write_setup_script(scene="Scene", camera="Camera", res_pct=100,
                                          output="//", frame_s=1, frame_e=5, gui=True)
        try:
            body = open(gen, encoding="utf-8").read()
        finally:
            os.remove(gen)
        self.assertNotIn("@FS@", body)
        self.assertNotIn("@PYTRAILER@", body)
        self.assertIn("render(animation=True)", body)
        self.assertIn("_os._exit(0 if _brm_ok else 1)", body)
        compile(body, "<gui_template>", "exec")

    def test_decompress_chunked_roundtrip(self):
        try:
            import zstandard
        except ImportError:
            self.skipTest("zstandard not installed")
        bp = self.brm.brm_blendparse
        # 10MB of random data forces multiple 4MB chunks through the new path
        raw = os.urandom(10 * 1024 * 1024)
        blob = zstandard.ZstdCompressor().compress(raw)
        self.assertTrue(blob[:4] == bytes([0x28, 0xB5, 0x2F, 0xFD]))
        self.assertEqual(bp._decompress("x.blend", blob), raw)
        self.assertEqual(bp._decompress("x.blend", b"plain"), b"plain")
        junk = bp._decompress("x.blend", bytes([0x28, 0xB5, 0x2F, 0xFD]) + b"junk")
        with self.assertRaises(Exception):
            bp._decode_header(junk)

    def _no_dialogs(self):
        import tkinter.messagebox as _mb
        orig = _mb.showwarning
        _mb.showwarning = lambda *a, **k: None
        orig2 = _mb.showinfo
        _mb.showinfo = lambda *a, **k: None
        return (orig, orig2)

    def _restore_dialogs(self, saved):
        import tkinter.messagebox as _mb
        _mb.showwarning, _mb.showinfo = saved

    def test_double_start_guarded(self):
        app = self.app
        app.config["queue_list"] = [
            self.brm.migrate_queue_item({"path": r"C:\tmp\a.blend"}),
        ]
        app.is_rendering = True
        app.stop_event.set()
        saved = self._no_dialogs()
        try:
            app.start_render_thread()
            still_set = app.stop_event.is_set()
        finally:
            self._restore_dialogs(saved)
            app.is_rendering = False
            app.stop_event.clear()
        # early return: stop flag untouched (never reached clear/spawn)
        self.assertTrue(still_set)

    def test_structural_edits_blocked_while_rendering(self):
        app = self.app
        app.config["queue_list"] = [
            self.brm.migrate_queue_item({"path": r"C:\tmp\a.blend", "status": "Done"}),
            self.brm.migrate_queue_item({"path": r"C:\tmp\b.blend"}),
        ]
        app.refresh_all_rows()
        app.is_rendering = True
        saved = self._no_dialogs()
        try:
            app.remove_at(0)
            app.move_at(0, 1)
            app.selected_idx = 0
            app.duplicate_selected()
            app.clear_finished()
        finally:
            self._restore_dialogs(saved)
            app.is_rendering = False
        paths = [i["path"] for i in app.config["queue_list"]]
        self.assertEqual(paths, [r"C:\tmp\a.blend", r"C:\tmp\b.blend"])

    def test_store_probe_matches_by_path(self):
        app = self.app
        app.config["queue_list"] = [
            self.brm.migrate_queue_item({"path": r"C:\tmp\a.blend"}),
            self.brm.migrate_queue_item({"path": r"C:\tmp\b.blend"}),
        ]
        app.refresh_all_rows()
        probe = {"active": "Scene", "fast": True, "scenes": [{"name": "Scene"}]}
        # stale index 0, but path says second job
        app._store_probe(0, dict(probe), match_path=r"C:\tmp\b.blend")
        self.assertIsNone(app.config["queue_list"][0].get("probe"))
        self.assertEqual(app.config["queue_list"][1]["probe"]["active"], "Scene")
        # vanished job: dropped, nothing written
        app._store_probe(0, dict(probe), match_path=r"C:\tmp\gone.blend")
        self.assertIsNone(app.config["queue_list"][0].get("probe"))

    def test_corrupt_config_falls_back_to_defaults(self):
        with open(self.brm.CONFIG_FILE, "w") as f:
            f.write("{not json!!!")
        cfg = self.brm.load_config()
        self.assertEqual(cfg.get("queue_list"), [])
        # a full boot on the corrupt file must survive too (sequential root:
        # two live Tk interpreters can't share image names)
        try:
            self.app.destroy()
        except Exception:
            pass
        self.app = None
        app2 = self.brm.BlenderRenderApp()
        try:
            app2.geometry("800x600+10000+10000")
            app2.deiconify()
            app2.update_idletasks()
            app2.update()
            self.assertEqual(app2.config.get("queue_list"), [])
        finally:
            try:
                app2.destroy()
            except Exception:
                pass

    def test_terminate_child_kills(self):
        import subprocess as sp
        proc = sp.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        try:
            self.app._terminate_child(proc)
            self.assertIsNotNone(proc.poll())
        finally:
            try:
                proc.kill()
            except Exception:
                pass

    def test_render_probe_no_blender_when_disallowed(self):
        import subprocess as sp
        from unittest import mock
        orig_fast = self.brm.brm_blendparse.fast_probe
        self.brm.brm_blendparse.fast_probe = mock.Mock(side_effect=Exception("parse boom"))
        try:
            with mock.patch.object(sp, "run") as mrun:
                mrun.side_effect = AssertionError("must not launch Blender")
                out = self.brm.render_probe(sys.executable,
                                            os.path.join(_TMPHOME, "x.blend"),
                                            allow_blender=False)
            self.assertIsNone(out)
            self.assertFalse(mrun.called)
        finally:
            self.brm.brm_blendparse.fast_probe = orig_fast

    def test_auto_probe_respects_toggle(self):
        app = self.app
        fd, path = tempfile.mkstemp(suffix=".blend")
        os.close(fd)
        try:
            app.config["queue_list"] = [self._preview_item_on_disk(path)]
            app.config["auto_full_probe"] = False
            calls = []
            orig = self.brm.render_probe
            self.brm.render_probe = lambda *a, **k: calls.append(a) or {"fast": True}
            try:
                app.is_rendering = False
                app._auto_probe_new()
            finally:
                self.brm.render_probe = orig
            self.assertEqual(calls, [])
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    def test_title_carries_version(self):
        self.assertIn("v", self.app.title())
        self.assertIn(self.brm.APP_VERSION, self.app.title())

    def test_add_appends_single_row(self):
        import tempfile
        from unittest import mock
        app = self.app
        app.config["queue_list"] = [
            self.brm.migrate_queue_item({"path": r"C:\tmp\a.blend"}),
        ]
        app.refresh_all_rows()
        app.update_idletasks()
        first_frame = app.row_widgets[0]["frame"]
        fd, path = tempfile.mkstemp(suffix=".blend")
        os.close(fd)
        try:
            with mock.patch.object(self.brm.filedialog, "askopenfilenames",
                                   return_value=[path]):
                app.add_to_queue()
            app.update_idletasks()
            self.assertEqual(len(app.row_widgets), 2)
            # pre-existing row untouched: no full rebuild flash
            self.assertIs(app.row_widgets[0]["frame"], first_frame)
            self.assertEqual(len(app.config["queue_list"]), 2)
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    def test_autoprobe_single_flight(self):
        app = self.app
        app._autoprobe_busy = True
        try:
            orig = self.brm.render_probe
            calls = []
            self.brm.render_probe = lambda *a, **k: calls.append(a)
            try:
                app._auto_probe_new()
            finally:
                self.brm.render_probe = orig
            self.assertEqual(calls, [])
        finally:
            app._autoprobe_busy = False

    def _row_xy(self, app, idx, dy=0):
        w = app.row_widgets[idx]["frame"]
        return (w.winfo_rootx() + 10, w.winfo_rooty() + w.winfo_height() // 2 + dy)

    def _queue_paths(self, app):
        return [i["path"] for i in app.config["queue_list"]]

    def _three_jobs(self, app):
        app.config["queue_list"] = [
            self.brm.migrate_queue_item({"path": r"C:\tmp\a.blend"}),
            self.brm.migrate_queue_item({"path": r"C:\tmp\b.blend"}),
            self.brm.migrate_queue_item({"path": r"C:\tmp\c.blend"}),
        ]
        app.refresh_all_rows()
        app.update_idletasks()
        app.update()

    def test_row_drag_reorders_down(self):
        app = self.app
        self._three_jobs(app)
        app.selected_idx = 0
        x, y = self._row_xy(app, 0)
        app._row_click(0, _FakeEvent(app, x, y))
        app._row_motion(_FakeEvent(app, x, y + 60), 0)
        self.assertTrue((getattr(app, "_row_down", None) or {}).get("dragging"))
        x2, y2 = self._row_xy(app, 2, dy=-5)
        app._row_release(_FakeEvent(app, x2, y2), 0)
        app.update_idletasks()
        self.assertEqual(self._queue_paths(app),
                         [r"C:\tmp\b.blend", r"C:\tmp\c.blend", r"C:\tmp\a.blend"])
        self.assertEqual(app.selected_idx, 2)
        self.assertIsNone(getattr(app, "_row_ghost", None))

    def test_row_drag_reorders_up(self):
        app = self.app
        self._three_jobs(app)
        x, y = self._row_xy(app, 2)
        app._row_click(2, _FakeEvent(app, x, y))
        app._row_motion(_FakeEvent(app, x, y - 60), 2)
        x0, y0 = self._row_xy(app, 0, dy=-5)
        app._row_release(_FakeEvent(app, x0, y0), 2)
        app.update_idletasks()
        self.assertEqual(self._queue_paths(app),
                         [r"C:\tmp\c.blend", r"C:\tmp\a.blend", r"C:\tmp\b.blend"])

    def test_row_click_without_motion_keeps_order(self):
        app = self.app
        self._three_jobs(app)
        x, y = self._row_xy(app, 1)
        app._row_click(1, _FakeEvent(app, x, y))
        app._row_release(_FakeEvent(app, x, y), 1)
        self.assertEqual(self._queue_paths(app),
                         [r"C:\tmp\a.blend", r"C:\tmp\b.blend", r"C:\tmp\c.blend"])
        self.assertEqual(app.selected_idx, 1)

    def test_row_drag_blocked_while_rendering(self):
        app = self.app
        self._three_jobs(app)
        app.is_rendering = True
        saved = self._no_dialogs()
        try:
            app._row_move(0, 2)
        finally:
            self._restore_dialogs(saved)
            app.is_rendering = False
        self.assertEqual(self._queue_paths(app),
                         [r"C:\tmp\a.blend", r"C:\tmp\b.blend", r"C:\tmp\c.blend"])

    def test_row_target_geometry(self):
        app = self.app
        self._three_jobs(app)
        x, y = self._row_xy(app, 0, dy=-5)
        self.assertEqual(app._row_target_at(x, y), 0)
        last = app.row_widgets[-1]["frame"]
        self.assertEqual(app._row_target_at(x, last.winfo_rooty() + last.winfo_height() + 50), 3)

    def _five_jobs(self, app):
        app.config["queue_list"] = [
            self.brm.migrate_queue_item({"path": r"C:\tmp\%d.blend" % i})
            for i in range(5)
        ]
        app.refresh_all_rows()
        app.update_idletasks()
        app.update()

    def test_ctrl_click_toggles_multi(self):
        app = self.app
        self._five_jobs(app)
        app._row_click(0, _FakeEvent(app, 10, 10))
        app._row_click(2, _FakeEvent(app, 10, 10, state=0x4))
        app._row_click(4, _FakeEvent(app, 10, 10, state=0x4))
        paths = sorted(app.selected_paths)
        self.assertEqual(paths, sorted([r"C:\tmp\0.blend", r"C:\tmp\2.blend",
                                        r"C:\tmp\4.blend"]))
        self.assertEqual(app.selected_idx, 4)
        # ctrl-click again deselects one
        app._row_click(2, _FakeEvent(app, 10, 10, state=0x4))
        self.assertNotIn(r"C:\tmp\2.blend", app.selected_paths)
        # plain click resets to single
        app._row_click(1, _FakeEvent(app, 10, 10))
        self.assertEqual(app.selected_paths, set([r"C:\tmp\1.blend"]))

    def test_shift_click_selects_range(self):
        app = self.app
        self._five_jobs(app)
        app._row_click(1, _FakeEvent(app, 10, 10))
        app._row_click(3, _FakeEvent(app, 10, 10, state=0x1))
        self.assertEqual(app.selected_paths, set([r"C:\tmp\1.blend", r"C:\tmp\2.blend",
                                                  r"C:\tmp\3.blend"]))
        self.assertEqual(app.selected_idx, 3)

    def test_multi_delete_key(self):
        app = self.app
        self._five_jobs(app)
        app._row_click(0, _FakeEvent(app, 10, 10))
        app._row_click(1, _FakeEvent(app, 10, 10, state=0x4))
        app._on_delete_key(None)
        app.update_idletasks()
        self.assertEqual([i["path"] for i in app.config["queue_list"]],
                         [r"C:\tmp\2.blend", r"C:\tmp\3.blend", r"C:\tmp\4.blend"])

    def test_batch_convert_max_two(self):
        import time
        app = self.app
        app.config["queue_list"] = [
            self.brm.migrate_queue_item({"path": r"C:\tmp\%d.blend" % i,
                                         "output": "//out%d/" % i})
            for i in range(5)
        ]
        app.refresh_all_rows()
        app.update_idletasks()
        app.update()
        app._row_click(0, _FakeEvent(app, 10, 10))
        app._row_click(1, _FakeEvent(app, 10, 10, state=0x4))
        app._row_click(2, _FakeEvent(app, 10, 10, state=0x4))
        calls = []
        orig = app._convert_one_folder
        app._convert_one_folder = lambda *a, **k: calls.append(a) or True
        try:
            app.convert_selected_to_mp4()
            t0 = time.time()
            while app.is_converting and time.time() - t0 < 20:
                time.sleep(0.05)
                app.update_idletasks()
            app.update()
        finally:
            app._convert_one_folder = orig
        self.assertEqual(len(calls), 3)
        folders = sorted(c[0] for c in calls)
        self.assertEqual(len(set(folders)), 3)

    def test_log_box_fills_slot(self):
        app = self.app
        self.assertEqual(set(str(app.log_box.grid_info()["sticky"])), set("nsew"))
        self.assertEqual(app.panel_log.grid_rowconfigure(2)["weight"], 1)

    def _footer_buttons(self, app):
        out = []

        def walk(w):
            try:
                kids = w.winfo_children()
            except Exception:
                return
            for k in kids:
                if k.__class__.__name__ == "Button":
                    try:
                        out.append(k.cget("text"))
                    except Exception:
                        pass
                walk(k)
        walk(app.panel_queue)
        return out

    def test_footer_has_mass_convert(self):
        self.assertIn("Convert MP4", self._footer_buttons(self.app))

    def test_mass_convert_selection_or_finished(self):
        import time
        import tempfile
        app = self.app
        fd, mp4 = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        try:
            app.config["queue_list"] = [
                self.brm.migrate_queue_item({"path": r"C:\tmp\a.blend", "status": "Done",
                                             "converted_mp4": mp4}),
                self.brm.migrate_queue_item({"path": r"C:\tmp\b.blend", "status": "Done"}),
                self.brm.migrate_queue_item({"path": r"C:\tmp\c.blend", "status": "Pending"}),
            ]
            app.refresh_all_rows()
            app.update_idletasks()
            calls = []
            orig = app._convert_one_folder
            app._convert_one_folder = lambda *a, **k: calls.append(a) or True
            try:
                # no selection -> only finished-without-mp4
                app.selected_idx = None
                app.selected_paths = set()
                app.convert_mass_mp4()
                t0 = time.time()
                while app.is_converting and time.time() - t0 < 20:
                    time.sleep(0.05)
                    app.update_idletasks()
                app.update()
            finally:
                app._convert_one_folder = orig
            self.assertEqual(len(calls), 1)
        finally:
            os.remove(mp4)

    def test_latest_frame_file_picks_max(self):
        import tempfile
        from PIL import Image
        d = tempfile.mkdtemp(prefix="brm_frames_")
        try:
            for name in ("shot_0007.png", "shot_0003.png", "shot_0042.png",
                         "notes.txt", "shot_0010.jpg"):
                p = os.path.join(d, name)
                if name.endswith(".txt"):
                    open(p, "w").write("x")
                else:
                    Image.new("RGB", (8, 8), (1, 2, 3)).save(p)
            got = self.app._latest_frame_file(d)
            self.assertEqual(os.path.basename(got or ""), "shot_0042.png")
            self.assertIsNone(self.app._latest_frame_file(os.path.join(d, "nope")))
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_vp_show_last_frame_fallback(self):
        import tempfile
        from PIL import Image
        d = tempfile.mkdtemp(prefix="brm_last_")
        try:
            p = os.path.join(d, "r_0005.png")
            Image.new("RGB", (16, 16), (200, 10, 90)).save(p)
            app = self.app
            item = self.brm.migrate_queue_item({"path": os.path.join(d, "a.blend"),
                                                "status": "Done", "output": d + "/",
                                                "frame_start": 1, "frame_end": 5})
            self.assertTrue(app._vp_show_last_frame(item, {"frame_start": 1,
                                                           "frame_end": 5}))
            self.assertEqual(item.get("last_frame_path"), p)
            self._pump_until_preview(app)
            self.assertTrue(list(app.vp_canvas.find_withtag("preview")))
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_on_complete_end_of_queue_only(self):
        from unittest import mock
        app = self.app
        app.config["queue_list"] = [
            self.brm.migrate_queue_item({"path": r"C:\tmp\a.blend", "status": "Done"}),
            self.brm.migrate_queue_item({"path": r"C:\tmp\b.blend", "status": "Pending"}),
        ]
        app.config["on_complete"] = "Shutdown PC"
        app.stop_event.clear()
        with mock.patch.object(self.brm.os, "system") as msys:
            self.assertFalse(app._on_complete_action())
            self.assertFalse(msys.called)
        app.config["queue_list"][1]["status"] = "Done"
        with mock.patch.object(self.brm.os, "system") as msys:
            self.assertTrue(app._on_complete_action())
            self.assertTrue(msys.called)
        app.stop_event.set()
        try:
            with mock.patch.object(self.brm.os, "system") as msys:
                self.assertFalse(app._on_complete_action())
                self.assertFalse(msys.called)
        finally:
            app.stop_event.clear()
        app.config["on_complete"] = "Do nothing"

    def test_store_probe_prefers_requesting_slot(self):
        # duplicate paths: the result belongs to the slot that asked for it,
        # not blindly the first row with that path
        app = self.app
        app.config["queue_list"] = [
            self.brm.migrate_queue_item({"path": r"C:\tmp\same.blend"}),
            self.brm.migrate_queue_item({"path": r"C:\tmp\same.blend"}),
        ]
        app.refresh_all_rows()
        probe = {"active": "Scene", "fast": True, "scenes": [{"name": "Scene"}]}
        app._store_probe(1, dict(probe), match_path=r"C:\tmp\same.blend")
        self.assertIsNone(app.config["queue_list"][0].get("probe"))
        self.assertEqual(app.config["queue_list"][1]["probe"]["active"], "Scene")

    def test_duplicate_paths_probed_once_and_fanned_out(self):
        app = self.app
        fd, path = tempfile.mkstemp(suffix=".blend")
        os.close(fd)
        try:
            app.config["queue_list"] = [self._preview_item_on_disk(path),
                                        self._preview_item_on_disk(path)]
            calls = []
            orig = self.brm.render_probe
            def fake(blender_path, blend_file, timeout=240, **kw):
                calls.append(blend_file)
                return dict(self._full_probe())
            self.brm.render_probe = fake
            try:
                app.is_rendering = False
                app._auto_probe_new()
            finally:
                self.brm.render_probe = orig
            self.assertEqual(calls, [path])
            for it in app.config["queue_list"]:
                got = it.get("probe") or {}
                self.assertFalse(got.get("preview"))
                self.assertEqual((got.get("scenes") or [{}])[0].get("cameras"),
                                 ["Camera"])
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    def test_live_render_owns_viewport(self):
        import time
        app = self.app
        app.config["queue_list"] = [
            self.brm.migrate_queue_item({"path": r"C:\tmp\a.blend", "status": "Rendering"}),
            self.brm.migrate_queue_item({"path": r"C:\tmp\b.blend"}),
        ]
        app.refresh_all_rows()
        app.update_idletasks()
        app.update()
        app._live_on = True
        app.vp_idx = 0
        app._row_click(1, _FakeEvent(app, 10, 10))
        time.sleep(0.25)
        app.update()
        self.assertEqual(app.selected_idx, 1)
        self.assertEqual(app.lbl_pfile.cget("text"), "b.blend")
        self.assertEqual(app.vp_idx, 0)
        app._live_on = False
        app._row_click(1, _FakeEvent(app, 10, 10))
        time.sleep(0.25)
        app.update()
        self.assertEqual(app.vp_idx, 1)

    def test_hidden_viewport_skips_decode(self):
        from PIL import Image
        import tempfile
        fd, png = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            Image.new("RGB", (32, 32), (10, 200, 90)).save(png)
            app = self.app
            app.close_panel("view")
            app.update_idletasks()
            app.update()
            self.assertFalse(app._vp_visible())
            app.update_image_preview(png)
            app.update_idletasks()
            app.update()
            self.assertEqual(list(app.vp_canvas.find_withtag("preview")), [])
            self.assertEqual(app.vp_path, png)
            app.show_panel("view")
            import time
            time.sleep(0.3)
            app.update()
            self.assertTrue(app._vp_visible())
            self._pump_until_preview(app)
            self.assertTrue(list(app.vp_canvas.find_withtag("preview")))
        finally:
            try:
                os.remove(png)
            except Exception:
                pass

    def test_vp_poll_latest_adopts_newer_file(self):
        import tempfile
        from PIL import Image
        d = tempfile.mkdtemp(prefix="brm_poll_")
        try:
            for name in ("f_0001.png", "f_0009.png"):
                Image.new("RGB", (8, 8), (1, 2, 3)).save(os.path.join(d, name))
            app = self.app
            item = self.brm.migrate_queue_item({"path": os.path.join(d, "a.blend"),
                                                "output": d + "/", "status": "Rendering"})
            self.assertTrue(app._vp_poll_latest(item))
            self.assertEqual(os.path.basename(item.get("last_frame_path") or ""),
                             "f_0009.png")
            self.assertFalse(app._vp_poll_latest(item))
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_preview_tif_draws_exr_notes(self):
        from PIL import Image
        import tempfile
        fd, tif = tempfile.mkstemp(suffix=".tif")
        os.close(fd)
        try:
            Image.new("RGB", (24, 24), (90, 10, 200)).save(tif)
            app = self.app
            app.update_image_preview(tif)
            self._pump_until_preview(app)
            self.assertTrue(list(app.vp_canvas.find_withtag("preview")))
            before = app.log_box._textbox.get("1.0", "end-1c")
            app.update_image_preview(os.path.join("C:\\tmp", "f_0001.exr"))
            app.update_idletasks()
            after = app.log_box._textbox.get("1.0", "end-1c")
            self.assertIn("can't display", after[len(before):])
        finally:
            try:
                os.remove(tif)
            except Exception:
                pass

    def test_preview_fullres_no_downscale(self):
        # user rule: load the file as Blender wrote it (no thumbnail refining)
        from PIL import Image
        import tempfile
        fd, png = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            Image.new("RGB", (640, 480), (10, 200, 90)).save(png)
            app = self.app
            app.update_image_preview(png)
            self._pump_until_preview(app)
            self.assertIsNotNone(app.vp_photo)
            self.assertEqual((app.vp_photo.width(), app.vp_photo.height()), (640, 480))
            self.assertTrue(list(app.vp_canvas.find_withtag("preview")))
        finally:
            try:
                os.remove(png)
            except Exception:
                pass

    def test_log_trim_caps_growth(self):
        app = self.app
        for i in range(3120):
            app.log("x")
        tb = app.log_box._textbox
        n = int(str(tb.index("end-1c")).split(".")[0])
        self.assertLess(n, 2200, n)

    # -- silent subprocess --------------------------------------------
    def test_silent_popen_kwargs_on_windows(self):
        import subprocess as sp
        kw = self.brm._silent_popen_kwargs()
        if os.name == "nt":
            self.assertIn("creationflags", kw)
            self.assertTrue(kw["creationflags"] & sp.CREATE_NO_WINDOW)
            self.assertIn("startupinfo", kw)
        else:
            self.assertEqual(kw, {})

    def test_version_check_hides_console(self):
        import subprocess as sp
        from unittest import mock
        app = self.app
        app.config["blender_path"] = sys.executable
        with mock.patch.object(sp, "run") as mrun:
            mrun.return_value = type("R", (), {"stdout": "Blender 4.2.0"})()
            app._detect_blender_version()
        self.assertTrue(mrun.called)
        _, kwargs = mrun.call_args
        if os.name == "nt":
            self.assertIn("startupinfo", kwargs)
            import subprocess as sp2
            self.assertTrue(kwargs.get("creationflags", 0) & sp2.CREATE_NO_WINDOW)
        self.assertEqual(app.blender_version_label, "4.2")

    def test_render_probe_fallback_hides_console(self):
        import subprocess as sp
        from unittest import mock
        app = self.app
        with mock.patch.object(sp, "run") as mrun:
            mrun.return_value = type("R", (), {"stdout": "", "stderr": ""})()
            out = self.brm.render_probe(sys.executable, os.path.join(_TMPHOME, "x.blend"),
                                        timeout=5)
        self.assertIsNone(out)
        self.assertTrue(mrun.called)
        _, kwargs = mrun.call_args
        if os.name == "nt":
            self.assertIn("startupinfo", kwargs)


class _FakeEvent:
    def __init__(self, app, x, y, state=0):
        self.x_root = x
        self.y_root = y
        self.state = state


if __name__ == "__main__":
    unittest.main()
