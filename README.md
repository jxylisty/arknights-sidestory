# arknights-sidestory

用 MAA **多作业模式**一口气打穿明日方舟**月度 SideStory 活动**（「昨日海」这类每月一换的活动关）。

配套 skill：[arknights-maa-copilot](https://github.com/jxylisty/arknights-maa-copilot)（年度高难活动，矢量突破 / 拟生态）。本 skill 复用它的 adb / MAA / OCR 层，不重复实现。

## 思路

月度活动关卡多（8 关 + 8 关突袭），逐关手动导航是浪费。作业站有**作业集**：一个 id 覆盖整张活动图，MAA 的**多作业模式**能直接吃，自动逐关导航、编队、战斗、推进。

所以分工是：

1. **先找作业集** → 丢给 MAA 多作业模式连打
2. **失败的那几关** → 才用 agent 点屏幕 + 单作业补打

逐关手动导航是兜底，不是主路径。

## 快速开始

```bash
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

**`--run` 之前游戏必须停在能看到关卡名的界面**（活动地图 / 关卡详情）。MAA 靠 OCR 地图上的关卡名导航，停在主界面或别的活动地图上，它只会一直左右滑动。

`--run` 强制要求 `--yes`：开发时曾经一次测试调用直接把游戏打起来了，这个门闩就是防那个。

## 实测结论

**导入是追加，不是替换。** 填 `prts://s<id>` 后，新作业追加到任务列表末尾，旧集的行不清空。UIA 仍能读到旧行（坐标是负的或在视口外）。MAA 只跑勾选的行，所以旧行无害——但别用「列表里有这行」推断「这行属于当前集」。

**同名两行 = 普通 + 突袭。** 同一关渲染两行，按 `top` 排序后上面那行是普通。

**失败即中止。** 任何一关失败整条链就停，不会跳过继续。恢复：看画面判断类型 → 取消已通关的勾 → 重新开始。

| 现象 | 真相 |
|---|---|
| 「战斗记录未能成功同步到神经网络（错误号:0）」 | **战斗其实三星通过了**，点重试即可 |
| 突袭 0 星 + 理智返还 | 阵容撑不住，换单作业重打 |

**突袭要单独挑作业。** 带「仅突袭」字样的作业是作者为突袭单独调的轴。实测 `107380`（维什戴尔 + 凯尔希·思衡托）通吃 EX-5/EX-7 突袭。

## 依赖

```bash
pip install -r requirements.txt
```

本 skill 自己只有 `set_run.py` 和 `_shared.py`；其余（`adb.py`、`maa_drive.py`、`copilot_api.py`、`game.py`、`winocr.py`、`config.py`）来自同级的 `arknights-maa-copilot`。

解析顺序：

1. `$MAA_COPILOT_SKILL/scripts`
2. 同级目录 `../arknights-maa-copilot/scripts`
3. 本地 `scripts/`

找不到会明确报错并提示怎么修。

## 环境

Windows（MAA 是 WPF 应用，UIA 与 `Windows.Media.Ocr` 都是 Windows 专有）、MAA 在跑、模拟器 **1920×1080 横屏**、Python 3.10+。
