"""Look at the game: screenshot + OCR, so the agent can read the screen.

The stage-entry path changes every event, so the agent has to LOOK rather than
replay coordinates. This tool makes that one step cheap:

    python look.py                 # 截图并报告当前界面
    python look.py --save out.png  # 顺便存图（配合 Read 工具看图）
    python look.py --text          # 只看 OCR 原文

**The screenshot is the authoritative output, not the OCR.** OCR on the dark
event map is noisy: digits come back as I/)/], "OPERATION" glues onto codes,
and adjacent plates merge ("YW-EX-I0" for EX-1). Treat the code list as a hint
for orientation and read the image itself when a decision depends on it.

What the OCR IS reliable for:
  * 开始行动 / 突袭 present -> you are on a stage-detail page
  * Chinese UI labels (打捞方案 / 商店 / 任务) -> which event sub-page you are on
  * 理智 numbers

What it is NOT reliable for:
  * exact stage numbers on the map -- use the image
"""
import argparse
import re
import sys

import _shared  # noqa: F401

import adb
import winocr

# The map prints "OPERATION" above every stage code, and OCR glues the two
# together ("OPFRATIONOYW-E)(-2"). Strip that noise word first, otherwise the
# prefix picks up its tail and the code never matches cleanly.
_NOISE_WORDS = re.compile(r"OP[FE]?[RA]ATION|OPERAT1ON|OPERATION")

# OCR noise seen on real maps: the prefix keeps a leading I/O ("IYW-EX-4"),
# digits come back as I ) ] | 0/O, and "EX" as "E)(" or "EX".
CODE_RE = re.compile(
    r"([A-Z]{2,4})[-\s]?((?:EX|E\)\()[-\s]?[0-9IO\)\]\|]{1,2}|[0-9IO]{1,2}|SP[0-9IO]{1,2}|[A-D])\b")

_PREFIX_NOISE = re.compile(r"^[IO]+")
_DIGIT_FIX = str.maketrans({"I": "1", "O": "0", ")": "1", "]": "1",
                            "|": "1", "(": "X"})

_KNOWN_PREFIX = ("VEC", "YW", "EX", "S", "WD", "SV", "CB", "IW", "ZT",
                 "RS", "DV")
_MAX_STAGE = 12


def repair_tail(tail):
    """'EX-I0' -> 'EX-10', 'E)(-2' -> 'EX-2', 'O' -> '0'.

    Deliberately does NOT trim: when OCR merges a plate with stray marks the
    extra digit is usually real-looking, and guessing which digit to drop
    invents a stage. Leaving it lets the plausibility filter reject it.
    """
    t = tail.upper().replace(" ", "")
    t = t.replace("E)(", "EX")
    m = re.match(r"(EX)?-?([0-9IO\)\]\|]+)$", t)
    if m:
        num = m.group(2).translate(_DIGIT_FIX).lstrip("0") or "0"
        return ("EX-" if m.group(1) else "") + num
    return t.translate(_DIGIT_FIX)


def _plausible(prefix, tail):
    if prefix.upper() not in _KNOWN_PREFIX:
        return False
    m = re.search(r"(\d+)$", tail)
    if not m:
        return tail in ("A", "B", "C", "D")
    return 1 <= int(m.group(1)) <= _MAX_STAGE


def norm(t):
    return winocr.norm(t or "").upper()


def _ocr_bands(im, band=90, step=60):
    """OCR the screen in overlapping horizontal bands and concatenate.

    A single full-screen pass misses most of the white stage-name plates on
    the dark event map (verified: 1 of 7 codes). Overlapping bands catch more,
    though not perfectly -- see the module docstring on trusting the image.
    """
    w, h = im.size
    parts = []
    for y0 in range(0, h, step):
        y1 = min(h, y0 + band)
        parts.append(winocr.ocr_region(im, (0, y0, w, y1)))
    return "\n".join(parts)


def screen_report(im):
    raw = winocr.norm(_ocr_bands(im))
    full = norm(raw)
    clean = _NOISE_WORDS.sub("|", full)

    codes = set()
    for m in CODE_RE.finditer(clean):
        pre = _PREFIX_NOISE.sub("", m.group(1))
        if len(pre) < 2:
            continue
        tail = repair_tail(m.group(2))
        if not _plausible(pre, tail):
            continue
        codes.add(f"{pre}-{tail}")

    return {
        "codes": sorted(codes),
        "stage_detail": "开始行动" in raw or "OPERATIONSTART" in full,
        "raid_toggle": "突袭" in raw or "RAID" in full,
        "text": full,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save")
    ap.add_argument("--text", action="store_true", help="只输出 OCR 原文")
    args = ap.parse_args()

    im = adb.screenshot(args.save)
    r = screen_report(im)

    if args.text:
        print(r["text"][:1500])
        return 0

    print(f"画面尺寸: {im.size}" + (f"  已存到 {args.save}" if args.save else ""))
    print(f"关卡码（仅供参考，以图为准）: "
          f"{', '.join(r['codes']) if r['codes'] else '未识别'}")
    print(f"像关卡详情页（有「开始行动」）: {r['stage_detail']}")
    print(f"有「突袭」字样: {r['raid_toggle']}")
    print("--- OCR ---")
    print(r["text"][:900])
    return 0


if __name__ == "__main__":
    sys.exit(main())
