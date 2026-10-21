"""Find the button that opens the stage list, by trying them.

The hard part of navigating a new event is not the stage list -- MAA's
多作业模式 navigates inside it fine. The hard part is the ONE button on the
event hub that leads into the stage list, and events name it things like
「打捞方案」/「雷亚-伊比利亚」/「我们的伊比利亚」/「劳工配给所」. A human
often guesses wrong on the first try too.

So do not guess. Probe:

    python find_entry.py                 # 报告当前界面 + 候选入口
    python find_entry.py --probe         # 逐个点，看哪个进了关卡列表
    python find_entry.py --probe --tap   # 找到后停在那张关卡图上

How "is this the stage list" is decided: the stage list / map screen shows
SEVERAL stage codes at once (YW-EX-1..8), while the event hub shows none.
That is a much more robust signal than matching any particular label, because
it does not care what the entry is called.

Every probe records what it saw so a failed guess can be undone (back out)
and the next candidate tried.
"""
import argparse
import re
import sys
import time

import _shared  # noqa: F401

import adb
import winocr

# stage codes anywhere on screen, tolerant of the OCR noise seen in practice
CODE_RE = re.compile(r"\b([A-Z]{2,4})[-\s]?((?:EX|E\)\()?[-\s]?[0-9IO\)\]\|]{1,2}|SP[0-9IO]{1,2}|[A-D])\b")
_NOISE = re.compile(r"OP[FE]?[RA]ATION|OPERAT1ON|OPERATION")
_DIGITS = str.maketrans({"I": "1", "O": "0", ")": "1", "]": "1", "|": "1"})

# UI labels that mean "you are inside an event", used only for the report
EVENT_LABELS = ("打捞方案", "商店", "任务", "兑换", "情报", "档案", "关卡")
STAGE_LIST_HINTS = ("开始行动", "突袭", "普通", "代理指挥", "理智")


def norm(t):
    return winocr.norm(t or "").upper()


def _ocr_all(im, band=90, step=60):
    """OCR in overlapping bands. Full-screen passes miss most map plates."""
    w, h = im.size
    parts = []
    for y0 in range(0, h, step):
        parts.append(winocr.ocr_region(im, (0, y0, w, min(h, y0 + band))))
    return winocr.norm("\n".join(parts))


def count_stage_codes(im, text=None):
    """How many distinct stage codes are visible. 0 = probably not a stage list."""
    text = text if text is not None else _ocr_all(im)
    text = _NOISE.sub("|", norm(text))
    codes = set()
    for m in CODE_RE.finditer(text):
        pre = m.group(1).lstrip("IO")
        if len(pre) < 2:
            continue
        tail = m.group(2).replace("E)(", "EX").translate(_DIGITS)
        if not re.search(r"\d|[A-D]$", tail):
            continue
        codes.add(f"{pre}-{tail}")
    return len(codes), sorted(codes)


def screen_kind(im, text=None):
    """Classify the screen loosely. Returns (kind, codes).

    The discriminator that matters is "are several stage codes visible":
    the stage map shows many, the event hub shows none. That works regardless
    of what the entry button is called, which is the whole point -- events
    rename it every time.

    Threshold is 2, not 3: OCR reliably finds only a couple of plates on some
    maps, and a false "stage_list" is harmless (it just stops the probe).
    """
    text = text if text is not None else _ocr_all(im)
    n, codes = count_stage_codes(im, text)
    raw = winocr.norm(text)
    up = raw.upper()
    if "开始行动" in raw or "OPERATIONSTART" in up:
        return "stage_detail", codes
    if n >= 2:
        return "stage_list", codes
    if any(lbl in raw for lbl in EVENT_LABELS):
        return "event_hub", codes
    return "unknown", codes


def candidate_points(im, grid=6, margin=0.12):
    """Grid of points over the central area, skipping the edge chrome.

    The entry button on an event hub is a big tappable node somewhere in the
    middle of the screen; the edges hold the back arrow, the currency bar and
    the bottom nav, which must not be tapped.
    """
    w, h = im.size
    x0, x1 = int(w * margin), int(w * (1 - margin))
    y0, y1 = int(h * margin), int(h * (1 - margin))
    pts = []
    for i in range(grid):
        for j in range(grid):
            pts.append((x0 + (x1 - x0) * (2 * i + 1) // (2 * grid),
                        y0 + (y1 - y0) * (2 * j + 1) // (2 * grid)))
    return pts


def labeled_candidates(im, keywords=("打捞", "方案", "关卡", "行动", "作战")):
    """Points at OCR labels that look like a stage entry, best guess first."""
    out = []
    for text, cx, cy, *_ in winocr.ocr_text_lines(im):
        t = winocr.norm(text)
        if any(k in t for k in keywords):
            out.append((cx, cy, t))
    return out


def probe(max_tries=12, grid=6, settle=2.2, verbose=True):
    """Tap candidate points until the stage list appears.

    Returns (point, kind) on success, or (None, last_kind). Always leaves the
    game wherever the successful tap landed; on total failure it backs out to
    the screen it started on.
    """
    start = adb.screenshot()
    kind0, codes0 = screen_kind(start)
    if verbose:
        print(f"起始界面: {kind0}  关卡码={codes0}")
    if kind0 in ("stage_list", "stage_detail"):
        if verbose:
            print("已经在关卡界面了，不需要探测入口。")
        return None, kind0

    # try labels first: cheaper and less disruptive than blind grid taps
    tries = []
    for cx, cy, t in labeled_candidates(start):
        tries.append(((cx, cy), f"label:{t}"))
    for p in candidate_points(start, grid=grid):
        tries.append((p, "grid"))

    seen = set()
    for pt, why in tries[:max_tries]:
        key = (pt[0] // 40, pt[1] // 40)
        if key in seen:
            continue
        seen.add(key)

        if verbose:
            print(f"  试 {pt} ({why}) ...", end=" ", flush=True)
        adb.tap(*pt, settle=settle)
        im = adb.screenshot()
        kind, codes = screen_kind(im)

        if kind in ("stage_list", "stage_detail"):
            if verbose:
                print(f"-> {kind}  关卡码={codes[:6]}")
            return pt, kind

        if verbose:
            print(f"-> {kind}")
        # wrong place: back out so the next tap starts from the hub again
        adb.back()
        time.sleep(0.9)

    if verbose:
        print("没找到入口。")
    return None, "unknown"


def report(im=None):
    im = im or adb.screenshot()
    kind, codes = screen_kind(im)
    print(f"界面类型: {kind}")
    print(f"可见关卡码: {codes if codes else '无'}")
    print("OCR 标签（可作为点击候选）:")
    for text, cx, cy, x0, y0, x1, y1 in winocr.ocr_text_lines(im):
        t = winocr.norm(text)
        if len(t) >= 2:
            print(f"  ({cx:4},{cy:4}) {t[:44]}")
    return kind


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="只报告，不点")
    ap.add_argument("--probe", action="store_true", help="逐个试点找入口")
    ap.add_argument("--tries", type=int, default=12)
    ap.add_argument("--grid", type=int, default=6)
    args = ap.parse_args()

    if args.probe:
        pt, kind = probe(max_tries=args.tries, grid=args.grid)
        print(f"\n结果: {'入口 ' + str(pt) if pt else '未找到'}  界面={kind}")
        if pt:
            print("现在停在关卡界面，可以直接跑 set_run.py 了。")
        return 0 if pt else 1

    report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
