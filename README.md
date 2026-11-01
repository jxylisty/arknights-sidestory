# arknights-sidestory

> **起因**：我太懒，不想玩明日方舟，让 AI 自己去玩。
> 这是它长出的第二块肌肉。第一块在
> [arknights-maa-copilot](https://github.com/jxylisty/arknights-maa-copilot)。

月度 SideStory（「昨日海」这类每月一换的活动）一次就是 8 关 + 8 突袭，逐关手动导航不现实。
所以策略是：**先找作业集**——一个 id 覆盖整张活动图，MAA 的多作业模式能直接吃，
自动逐关导航、编队、战斗、推进；**打不过的关**才让 AI 点进地图、换单作业补打。

本 skill 只管「找集、喂集、盯失败」；adb / MAA / OCR 层复用 maa-copilot，不重复造轮子。

## 快速开始

```bash
pip install -r requirements.txt
cd scripts

# 现在开的是什么活动
python -c "import _shared, copilot_api as CA; [print(a['tip'], a['expire']) for a in CA.current_activities()]"

# 搜作业集（只查网络）
python set_run.py --search 昨日海

# 看覆盖了哪些关（只查网络）
python set_run.py --describe 55511

# 看 MAA 里现在勾了哪些（只读）
python set_run.py --status

# 真正开打（必须 --yes）
python set_run.py --run 55511 --yes
```

**`--run` 之前游戏必须停在能看到关卡名的界面**（活动地图 / 关卡详情）。MAA 靠 OCR
地图上的关卡名导航，停在主界面或别的活动地图上，它只会一直左右滑动。

`--run` 强制要求 `--yes`：开发时曾经一次测试调用直接把游戏打起来了，这个门闩就是防那个。

## 血泪实录

- 「战斗记录未能成功同步到神经网络（错误号:0）」——**战斗其实三星通过了**，点重试即可
- **导入是追加，不是替换**：填 `prts://s<id>` 后新作业追加到列表末尾，旧行不清空。
  MAA 只跑勾选的行所以旧行无害，但别用「列表里有这行」推断「这行属于当前集」
- 同一关渲染两行 = 普通 + 突袭，按 `top` 排序后上面是普通
- **失败即中止**：任何一关失败整条链就停。恢复：看画面判断类型 → 取消已通关的勾 → 重开
- **突袭要单独挑作业**：带「仅突袭」的作业是作者为突袭单独调的轴。
  实测 `107380`（维什戴尔 + 凯尔希·思衡托）通吃 EX-5/EX-7 突袭

## 依赖

```bash
pip install -r requirements.txt
```

本 skill 自己只有 `set_run.py` 和 `_shared.py`；其余来自同级的 `arknights-maa-copilot`。
解析顺序：`$MAA_COPILOT_SKILL/scripts` → 同级 `../arknights-maa-copilot/scripts` → 本地 `scripts/`。
找不到会明确报错并提示怎么修。

环境：Windows（UIA 与 Windows OCR）+ MAA 在跑 + 模拟器 **1920×1080 横屏** + Python 3.10+。

## 免责

仅供个人自动化学习使用。作业集版权归 prts.plus 原作者。
打游戏的是 AI，肝坏的是 MAA，掉落归主人。
