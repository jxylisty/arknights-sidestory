"""Run a 作业集 (copilot set) through MAA's 多作业模式.

    python set_run.py --search 昨日海        # 找作业集（只查网络，不动 MAA）
    python set_run.py --describe 55511      # 这个集覆盖哪些关（只查网络）
    python set_run.py --status              # MAA 里当前勾了哪些（只读）
    python set_run.py --run 55511           # 载入 + 校验 + 开打（会真的打）

Why a set instead of per-stage jobs: a set is one id covering the whole event,
and MAA's 多作业模式 navigates, forms, fights and advances by itself. That is
the primary path for monthly SideStory events; the agent only steps in when a
stage fails.

Two hard requirements, both learned the hard way:

  * The game must be showing stage names (event map or stage detail). MAA
    navigates by OCR-ing labels on the map, so on any other screen it just
    swipes around forever without fighting.
  * Importing a set APPENDS to the task list -- it does not replace it. Stale
    rows from earlier sets stay in the list (UIA still reports them, at
    negative screen coordinates). They are harmless because MAA only runs
    checked rows, but never treat "row exists" as "row is part of this set".

`--run` requires an explicit --yes: an earlier version started a live run from
a test invocation, which is exactly the accident this guard prevents.
"""
import argparse
import sys
import time

import _shared  # noqa: F401  (puts the shared core on sys.path)

import copilot_api as CA
import game
import maa_drive as M

import re

STAGE_RE = re.compile(r"^(?P<prefix>[A-Z]{1,3})-(?P<tail>EX-?\d+|\d+|SP\d+|[A-D])$",
                      re.IGNORECASE)


def norm_stage(name):
    """'YW-EX-1' / 'YW-EX1' -> ('YW', 'EX-1'); 'VEC-SP12' -> ('VEC', 'SP12')."""
    n = (name or "").strip().upper().replace(" ", "")
    m = STAGE_RE.match(n)
    if not m:
        return None, n
    tail = m.group("tail").upper()
    if tail.startswith("EX"):
        tail = "EX-" + tail[2:].lstrip("-")
    return m.group("prefix"), tail


# --------------------------------------------------------------------------
# network-only helpers (safe: never touch MAA)
# --------------------------------------------------------------------------

def find_sets(keyword, limit=20):
    out = []
    for s in CA.search_sets(keyword, limit=limit):
        out.append({"id": s["id"], "name": s.get("name", ""),
                    "n": len(s.get("copilot_ids") or [])})
    return out


def describe(set_id):
    s, rows = CA.set_stages(set_id)
    return s, rows


# --------------------------------------------------------------------------
# MAA state helpers (read-only unless noted)
# --------------------------------------------------------------------------

def stage_rows(w):
    """Every copilot row UIA currently exposes, sorted by logical position.

    UIA reports rows that are scrolled out of view too, at negative or
    beyond-viewport coordinates, so this is the *logical* list rather than
    what is visible. That is what we want for status reporting; it is NOT a
    reliable basis for "which rows belong to the set I just imported".
    """
    rows = []
    for el in w.descendants():
        try:
            i = el.element_info
            if i.control_type != "CheckBox":
                continue
            name = (el.window_text() or "").strip()
            pre, tail = norm_stage(name)
            if pre is None:
                continue
            rows.append({"el": el, "name": name, "prefix": pre, "tail": tail,
                         "checked": el.get_toggle_state(),
                         "top": el.rectangle().top})
        except Exception:
            pass
    rows.sort(key=lambda x: x["top"])
    # MAA renders 普通 directly above 突袭 for the same stage, so the second
    # occurrence within the sorted list is the raid entry.
    seen = {}
    for row in rows:
        key = (row["prefix"], row["tail"])
        row["raid"] = key in seen
        seen[key] = True
    return rows


def ensure_multi(w):
    st = M.checkbox_state(w, M.CB_MULTI)
    if st is None:
        raise RuntimeError("找不到「多作业模式」复选框——MAA 版本可能变了")
    if not st:
        M.set_checkbox(w, M.CB_MULTI, True)
        time.sleep(0.6)
    return M.checkbox_state(w, M.CB_MULTI)


def load_set(w, set_id):
    """Type prts://s<id> so MAA imports the set. Appends to the task list.

    The fetch makes MAA activate its own window, so this runs inside
    keep_focus() with a settle window long enough for the fetch to land.
    """
    before = len(stage_rows(w))
    with M.keep_focus():
        M.set_path(w, f"prts://s{set_id}", settle=3.0)
    time.sleep(0.8)
    after = len(stage_rows(w))
    return before, after


def checked_rows(w):
    return [r for r in stage_rows(w) if r["checked"]]


def print_rows(rows, limit=None):
    for row in (rows if limit is None else rows[:limit]):
        mark = "RAID" if row["raid"] else "norm"
        flag = "x" if row["checked"] else " "
        print(f"  [{flag}] {row['name']:12} {mark}  y={row['top']}")


def wait_chain(off, timeout=3600, poll=10):
    """Block until the task chain ends. Returns (ok, text).

    Error markers are checked before completion markers: on a loss MAA writes
    both 任务出错 and 完成任务, so looking for completion first reports every
    defeat as success.
    """
    t0 = time.time()
    last = ""
    while time.time() - t0 < timeout:
        txt = M.log_since(off)
        if "任务已全部完成" in txt:
            return True, txt
        if "任务出错" in txt or "战斗出错" in txt:
            return False, txt
        cur = ""
        for line in txt.splitlines():
            if "Parse config" in line or "完成战斗" in line:
                cur = line
        if cur and cur != last:
            last = cur
            print("  " + cur[-92:])
        time.sleep(poll)
    return False, M.log_since(off)


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--search", metavar="KEYWORD")
    ap.add_argument("--describe", type=int, metavar="SET_ID")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--run", type=int, metavar="SET_ID")
    ap.add_argument("--yes", action="store_true",
                    help="确认真的开打（--run 必须带这个）")
    ap.add_argument("--timeout", type=int, default=3600)
    args = ap.parse_args()

    if args.search is not None:
        for s in find_sets(args.search):
            print(f"s{s['id']:<7} {s['n']:2d}关 {s['name'][:58]}")
        return 0

    if args.describe:
        s, rows = describe(args.describe)
        print(f"作业集 s{args.describe}: {s.get('name')}")
        print(f"  {len(rows)} 个作业")
        for cid, stage, title in rows:
            print(f"    {cid:8} {stage:20} {title[:44]}")
        return 0

    # no focus(): the UIA helpers restore the foreground after each mutation
    w = M.win()
    if not M.tab_click(w, "作业"):
        print("ERROR: 找不到作业页")
        return 1

    if args.status:
        rows = stage_rows(w)
        if not rows:
            print("作业列表是空的")
            return 0
        print(f"{len(rows)} 行（含视口外的历史行），已勾选 "
              f"{sum(1 for r in rows if r['checked'])} 行：")
        print_rows(rows)
        return 0

    if not args.run:
        ap.error("需要 --search / --describe / --status / --run 之一")

    s, rows = describe(args.run)
    print(f"作业集 s{args.run}: {s.get('name')}  ({len(rows)} 个作业)")

    cur, _ = game.detect_stage()
    print(f"游戏当前识别到的关卡：{cur}")
    if cur is None:
        print("警告：没识别出关卡名。MAA 靠 OCR 地图上的关卡名导航，")
        print("      请先进入活动地图或关卡详情界面，否则它会一直滑动找不到。")

    ensure_multi(w)
    before, after = load_set(w, args.run)
    print(f"载入完成：列表 {before} -> {after} 行（导入是追加，旧行会留着）")

    chk = checked_rows(w)
    print(f"当前勾选 {len(chk)} 行：")
    print_rows(chk)

    if not chk:
        print("ERROR: 没有任何作业被勾选，MAA 会拒绝启动")
        return 1

    if not args.yes:
        print("\n未开打。确认上面的勾选无误后，加 --yes 重新执行：")
        print(f"  python set_run.py --run {args.run} --yes")
        return 0

    off = M.log_size()
    if not M.click_start(w):
        print("ERROR: 找不到「开始」按钮")
        return 1
    print("已启动，等待任务链……（Ctrl-C 不会停 MAA，需要手动点停止）")
    ok, txt = wait_chain(off, timeout=args.timeout)
    print("\nRESULT:", "DONE" if ok else "STOPPED")
    tail = [l for l in txt.splitlines()
            if any(k in l for k in ("完成战斗", "战斗出错", "任务出错",
                                    "Parse config", "任务已全部完成"))]
    for line in tail[-12:]:
        print("  " + line[-100:])
    if not ok:
        print("\n下一步看游戏画面：")
        print("  · 结算网络错误（错误号:0）→ 战斗其实已过，点重试收奖励")
        print("  · 突袭 0 星 / 理智返还 → 取消该关勾选，用单作业换个配置")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
