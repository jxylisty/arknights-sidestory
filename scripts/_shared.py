"""Locate the shared MAA/adb core from the sibling 矢量突破 skill.

The adb/MAA/UIA layer (config, adb, winocr, maa_drive, copilot_api, game) is
identical for both activity types, and it is where all the nasty bugs live.
Keeping one copy instead of two means a fix lands once.

Resolution order:
  1. $MAA_COPILOT_SKILL/scripts
  2. sibling directory ../arknights-maa-copilot/scripts
  3. this skill's own scripts/ (in case someone vendors a copy there)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)


def _candidates():
    env = os.environ.get("MAA_COPILOT_SKILL")
    if env:
        yield os.path.join(env, "scripts")
        yield env
    yield os.path.join(os.path.dirname(SKILL_DIR),
                       "arknights-maa-copilot", "scripts")
    yield HERE


def _has_core(path):
    return all(os.path.isfile(os.path.join(path, f))
               for f in ("config.py", "maa_drive.py", "copilot_api.py"))


def find_core():
    for p in _candidates():
        if _has_core(p):
            return p
    return None


def bootstrap():
    """Make the shared core importable. Returns the directory used."""
    p = find_core()
    if p is None:
        raise RuntimeError(
            "找不到共享核心脚本（config.py / maa_drive.py / copilot_api.py）。\n"
            "本 skill 复用 arknights-maa-copilot 的 adb/MAA 层。请任选一种修法：\n"
            "  1. 把 arknights-maa-copilot 放在同级目录（~/.zcode/skills/ 下）\n"
            "  2. 设置环境变量 MAA_COPILOT_SKILL=<arknights-maa-copilot 路径>")
    if p not in sys.path:
        sys.path.insert(0, p)
    return p


CORE = bootstrap()
