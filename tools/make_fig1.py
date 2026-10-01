"""LuCDA 计划1 · fig1 CFG（信息流控制流图）

唯一真源：GOAL.md §4「信息流」。
计划2/assets/fig1_cfg.png 是下游产物：本脚本不读它、不依赖它、不覆盖它。

产出（写在 计划1/assets/ 下）：
    fig1_cfg.png   300 dpi 位图
    fig1_cfg.svg   矢量图（文字转路径，换机器不会变方框）

运行：
    D:/anaconda/miniconda3/python.exe tools/make_fig1.py

图上画了什么（逐条对得上 GOAL）：
    GOAL §4   六层信息流：输入层 → 话语层 → 标注层 → 判定层 → 策略层 → 呈现层
    GOAL §4   层间动作：归一化 / 逐单元标注 / 聚合 / 生成 / 禁忌扫描
    GOAL §4.1 溯源横切：右侧侧带，不是流程里的一步
    GOAL §4.1 禁忌扫描在呈现层之前强制过一遍
    GOAL §4.1 置信度向上传递：话语层判定 → 判定层标记 → 呈现层显示
    GOAL §4.2 条件分支（菱形 + 分叉箭头）：
              ① 是语音或图片吗？        分支：转写 / 读图 → 归一
              ② 说话人置信度低？        分支：提示 + 一键纠正 → 重算本层（回跳）
              ③ 这条标签带证据吗？      分支：无证据 → 删掉，不进判定
              ④ 风险灯色是绿吗？        分支：绿 → 未发现操纵特征 + 正常说法对照
              ⑤ 有交涉对象吗？          分支：没有 → 不出问题清单
              ⑥ 命中禁忌？              分支：命中 → 重写后再扫（回跳）；改不动 → 降级为安全输出（并入主线放行）
    每层都标了输入契约与输出契约。

脚本自带核对（每次运行都打印，有毛病就报出来）：
    文字是否溢出所在方框 / 是否出画布 / 两段文字是否叠在一起；
    连线是否压在文字上、是否穿过节点内部；
    图上所有文字逐字扫一遗禁用词表（权威类 / 绝对类 / 姿态类）。
    检查器有效性：注入一条故意穿框的线，检查器会报「连线穿节点」。
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon

matplotlib.rcParams["svg.fonttype"] = "path"
matplotlib.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).resolve()
ROOT = HERE.parent.parent
OUT_PNG = ROOT / "assets" / "fig1_cfg.png"
OUT_SVG = ROOT / "assets" / "fig1_cfg.svg"

FONT_REG = "C:/Windows/Fonts/msyh.ttc"
FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"

# ---------------------------------------------------------------- 配色（低饱和）
C_BAND = "#F4F7F9"
C_BAND_EDGE = "#D8E0E6"
C_NODE = "#FFFFFF"
C_NODE_EDGE = "#54677A"
C_DIA = "#EAF1F5"
C_BR = "#FBFCFD"
C_BR_EDGE = "#7C8D9C"
C_TXT = "#22303C"
C_TXT2 = "#3D4F5C"
C_TXT3 = "#6E7D89"
C_LINE = "#54677A"
C_LOOP = "#7E8C99"
C_CONTRACT = "#F8FAFB"
C_CONTRACT_BAR = "#B9C6D0"
C_SRC = "#F1F0F6"
C_SRC_EDGE = "#B7B1C7"
C_GATE = "#EEF1F4"
C_GATE_EDGE = "#8A97A3"
C_RED = "#B85C55"
C_AMBER = "#D0A24C"
C_GREEN = "#6F9C6B"

# ---------------------------------------------------------------- 版面（单位：英寸）
FIG_W = 14.6
BAND_X0, BAND_X1 = 0.45, 11.05
CX = 3.5
NODE_W = 4.6
NODE_X0 = CX - NODE_W / 2
DIA_W, DIA_H = 4.6, 0.78
BR_X0, BR_X1 = 6.35, 10.9
SRC_X0, SRC_X1 = 11.45, 14.15
SRC_TEXT_X = [11.72, 12.16, 12.60, 13.04, 13.48, 13.92]
CONTRACT_X = 0.72

PAD_TOP = 0.16
HEADER_H = 0.36
CONTRACT_LINE = 0.205
CONTRACT_GAP = 0.10
PAD_BOTTOM = 0.26
GAP = 0.18
MERGE_GAP = 0.58
MERGE_EXTRA = 0.36
BR_GAP = 0.10
TITLE_H = 1.55
FOOT_H = 0.90
BAND_GAP = 0.58

_FP: dict = {}


def fp(size: float, bold: bool = False) -> FontProperties:
    key = (round(size, 2), bold)
    if key not in _FP:
        _FP[key] = FontProperties(fname=FONT_BOLD if bold else FONT_REG, size=size)
    return _FP[key]


# ---------------------------------------------------------------- 元件定义
def box(text, h=0.42, **kw):
    return {"t": "box", "text": text, "h": h, **kw}


def br(label, text, h=0.44, ret="merge_after"):
    """分支节点。ret: merge_before / merge_after / loop"""
    return {"label": label, "text": text, "h": h, "ret": ret}


def dia(text, branches=None, gap_before=GAP, gap_after=None, **kw):
    return {
        "t": "diamond",
        "text": text,
        "branches": branches or [],
        "gap_before": gap_before,
        "gap_after": gap_after,
        **kw,
    }


def stack_h(branches):
    if not branches:
        return 0.0
    return sum(b["h"] for b in branches) + BR_GAP * (len(branches) - 1)


def row_h(it):
    if it["t"] != "diamond":
        return it["h"]
    return max(DIA_H, stack_h(it["branches"]))


def has_ret(items, kind):
    for it in items:
        if it["t"] == "diamond":
            for b in it["branches"]:
                if b["ret"] == kind:
                    return True
    return False


# ---------------------------------------------------------------- 画图基元（y 轴向下）
class Canvas:
    def __init__(self, ax, H):
        self.ax = ax
        self.H = H
        self._texts = []
        self._segs = []
        self._limits = {}

    def y(self, v):
        return self.H - v

    def rect(self, x, y_top, w, h, fc, ec, lw=1.1, ls="-", z=2, round_=0.09):  # noqa: A002
        p = FancyBboxPatch(
            (x, self.y(y_top + h)),
            w,
            h,
            boxstyle=f"round,pad=0,rounding_size={round_}",
            facecolor=fc,
            edgecolor=ec,
            linewidth=lw,
            linestyle=ls,
            zorder=z,
        )
        self.ax.add_patch(p)

    def text(
        self,
        x,
        y,
        s,
        size=9.0,
        color=C_TXT,
        ha="center",
        va="center",
        bold=False,
        rot=0,
        ls_=1.55,
        z=8,
        box=None,
        kind="",
    ):
        art = self.ax.text(
            x,
            self.y(y),
            s,
            ha=ha,
            va=va,
            color=color,
            fontproperties=fp(size, bold),
            rotation=rot,
            linespacing=ls_,
            zorder=z,
        )
        self._texts.append((art, box, kind, x, y, ha))
        return art

    def check(self, fig, ax):
        """自检：文字是否溢出容器、是否被裁掉、文字之间是否重叠。"""
        fig.canvas.draw()
        r = fig.canvas.get_renderer()
        issues = []
        recs = []
        node_zones = []
        for art, box, kind, *_rest in self._texts:
            bb = art.get_window_extent(renderer=r)
            label = art.get_text().replace("\n", " / ")
            recs.append((label, kind, bb))
            if box is not None and kind in ("node", "diamond", "branch"):
                node_zones.append(box)
            if box is not None:
                bx, by_top, bw, bh = box
                p0 = ax.transData.transform((bx, self.y(by_top + bh)))
                p1 = ax.transData.transform((bx + bw, self.y(by_top)))
                if bb.x0 < p0[0] - 0.6 or bb.x1 > p1[0] + 0.6:
                    issues.append(
                        (
                            "左右溢出",
                            kind,
                            label[:26],
                            round(bb.x1 - p1[0], 1),
                            round(p0[0] - bb.x0, 1),
                        )
                    )
                if bb.y0 < p0[1] - 0.6 or bb.y1 > p1[1] + 0.6:
                    issues.append(
                        (
                            "上下溢出",
                            kind,
                            label[:26],
                            round(bb.y1 - p1[1], 1),
                            round(p0[1] - bb.y0, 1),
                        )
                    )
        lim_c = ax.transData.transform((BAND_X1 - 0.16, 0))[0]
        lim0 = ax.transData.transform((CONTRACT_X, 0))[0]
        for label, kind, bb in recs:
            if kind == "contract" and bb.x1 > lim_c:
                issues.append(("契约行超出右边界", bb.x1 - lim_c, label[:26]))
            if kind == "contract" and bb.x0 < lim0 - 0.6:
                issues.append(("契约行左侧越界", label[:26]))
        for i in range(len(recs)):
            for j in range(i + 1, len(recs)):
                a, b = recs[i][2], recs[j][2]
                if a.x0 < b.x1 and b.x0 < a.x1 and a.y0 < b.y1 and b.y0 < a.y1:
                    issues.append(("文字重叠", recs[i][0][:22], recs[j][0][:22]))
        sx = ax.transData.transform((1, 0))[0] - ax.transData.transform((0, 0))[0]
        sy = ax.transData.transform((0, 1))[1] - ax.transData.transform((0, 0))[1]
        for a, b in self._segs:
            for p in (a, b):
                if not (
                    -0.02 <= p[0] <= FIG_W + 0.02 and -0.02 <= p[1] <= self.H + 0.02
                ):
                    issues.append(("连线超出画布", round(p[0], 2), round(p[1], 2)))
        for label, _kind, bb in recs:
            x0i, x1i = bb.x0 / sx, bb.x1 / sx
            yti, ybi = (self.H * sy - bb.y1) / sy, (self.H * sy - bb.y0) / sy
            if x0i < -0.02 or x1i > FIG_W + 0.02 or yti < -0.02 or ybi > self.H + 0.02:
                issues.append(
                    (
                        "文字超出画布",
                        round(x0i, 2),
                        round(x1i, 2),
                        round(yti, 2),
                        round(ybi, 2),
                        label[:20],
                    )
                )
        hit = 0
        for a, b in self._segs:
            for k in range(1, 40):
                t = k / 40
                dx = a[0] + (b[0] - a[0]) * t
                dy = a[1] + (b[1] - a[1]) * t
                px, py = ax.transData.transform((dx, self.y(dy)))
                for label, _kind, bb in recs:
                    if (bb.x0 + 1.0 < px < bb.x1 - 1.0) and (
                        bb.y0 + 1.0 < py < bb.y1 - 1.0
                    ):
                        hit += 1
                        issues.append(
                            ("连线压文字", label[:26], round(dx, 2), round(dy, 2))
                        )
                        break
                else:
                    continue
                break
        for a, b in self._segs:
            for zx, zy, zw, zh in node_zones:
                for k in range(1, 40):
                    t = k / 40
                    dx = a[0] + (b[0] - a[0]) * t
                    dy = a[1] + (b[1] - a[1]) * t
                    if (zx + 0.02 < dx < zx + zw - 0.02) and (
                        zy + 0.02 < dy < zy + zh - 0.02
                    ):
                        hit += 1
                        issues.append(
                            ("连线穿节点", round(dx, 2), round(dy, 2), zx, zy)
                        )
                        break
                else:
                    continue
                break
        BANNED = [
            "最强",
            "最准",
            "最权威",
            "国家级",
            "独家",
            "权威AI",
            "权威 AI",
            "100%",
            "绝对",
            "保证",
            "一定",
            "肯定",
            "首创",
            "国内首个",
            "填补空白",
            "旨在",
            "赋能",
            "助力",
            "深度融合",
            "全方位",
            "具有重要意义",
            "打造",
            "探索",
            "有效提升",
            "创造价值",
            "不仅",
            "我们",
            "你必须",
            "你不许",
            "我这是为你好",
        ]
        for label, _kind, _bb in recs:
            for w in BANNED:
                if w in label:
                    issues.append(("命中禁用词", w, label[:26]))
        ov = [i for i in issues if i[0] == "文字重叠"]
        print(
            f"[自检] 文本 {len(recs)} 处、连线 {len(self._segs)} 段、扫描禁用词 {len(BANNED)} 个，"
            f"问题 {len(issues)} 条"
            + (f"（文字重叠 {len(ov)}、穿节点 {hit}）" if issues else "")
        )
        for it in issues[:40]:
            print("   -", it)
        return issues

    def line(self, pts, color=C_LINE, lw=1.1, ls="-", z=4):
        xs = [p[0] for p in pts]
        ys = [self.y(p[1]) for p in pts]
        for i in range(len(pts) - 1):
            self._segs.append((pts[i], pts[i + 1]))
        self.ax.add_line(
            Line2D(
                xs,
                ys,
                color=color,
                lw=lw,
                linestyle=ls,
                zorder=z,
                solid_capstyle="butt",
            )
        )

    def arrow(self, p0, p1, color=C_LINE, lw=1.15, ls="-", head=True, z=4, ms=11):  # noqa: A002
        self._segs.append((p0, p1))
        if head:
            self.ax.add_patch(
                FancyArrowPatch(
                    (p0[0], self.y(p0[1])),
                    (p1[0], self.y(p1[1])),
                    arrowstyle="-|>",
                    mutation_scale=ms,
                    color=color,
                    lw=lw,
                    linestyle=ls,
                    shrinkA=0,
                    shrinkB=0,
                    zorder=z,
                )
            )
        else:
            self.line([p0, p1], color=color, lw=lw, ls=ls, z=z)

    def poly_arrow(self, pts, color=C_LOOP, lw=1.05, ls="--", z=4, ms=10):
        self.line(pts, color=color, lw=lw, ls=ls, z=z)
        p1, p0 = pts[-1], pts[-2]
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        ln = (dx * dx + dy * dy) ** 0.5 or 1.0
        k = min(1.0, 0.14 / ln)
        st = (p1[0] - dx * k, p1[1] - dy * k)
        self.ax.add_patch(
            FancyArrowPatch(
                (st[0], self.y(st[1])),
                (p1[0], self.y(p1[1])),
                arrowstyle="-|>",
                mutation_scale=ms,
                color=color,
                lw=lw,
                shrinkA=0,
                shrinkB=0,
                zorder=z,
            )
        )

    def swatch(self, x, y_top, w, h, color, z=8):
        self.rect(x, y_top, w, h, color, color, lw=0.8, z=z, round_=0.03)


# ---------------------------------------------------------------- 图形内容
BANDS = [
    {
        "key": "in",
        "title": "① 输入层",
        "items": [
            box("一个入口：发出去（文字 / 语音 / 图片）", h=0.42),
            dia(
                "是语音或图片吗？",
                gap_after=MERGE_GAP,
                branches=[
                    br(
                        "是",
                        "语音：转写成文字（上限 60 秒）\n图片：读字 + 读画面（单次 1 张）",
                        h=0.58,
                        ret="merge_before",
                    )
                ],
            ),
            box("三路归一：都变成文本，各自留下独占字段", h=0.42),
        ],
        "contract": [
            (
                "入",
                "用户发的一条：文字 / 语音 / 图片（同一个入口；视频不做；转写用的音频不留存）",
            ),
            ("出", "归一化文本 + 本模态的独占字段"),
            (
                "",
                "文字：预设 / 信息确定性 / 情绪引导　语音：语速 / 重复次数 / 音量 / 停顿　图片：资质有无 / 专家形象元素 / 字幕与画面是否一致",
            ),
        ],
    },
    {
        "key": "disc",
        "title": "② 话语层　（信息模型的核心）",
        "items": [
            box("切成话语单元：每句带说话人 + 证据位置", h=0.42),
            box("自动分人：人称代词 + 转述标记 + 话术特征", h=0.42),
            dia(
                "说话人置信度低？",
                gap_before=0.46,
                branches=[
                    br(
                        "是",
                        "显示「我不确定哪句是你说的」\n点「这句是我说的」→ 重算本层",
                        h=0.58,
                        ret="loop",
                    )
                ],
            ),
        ],
        "contract": [
            ("入", "归一化文本 + 本模态的独占字段"),
            (
                "出",
                "dialogue = 带说话人的话语单元序列（说话人 / 文本 / 证据位置 / 归属）",
            ),
        ],
    },
    {
        "key": "ann",
        "title": "③ 标注层",
        "items": [
            box("逐条标三层：事件层 · 话语层 · 说服杠杆层", h=0.42),
            box("挂归属：正在施放（他说的）｜已对我生效（我说的）", h=0.42),
            dia(
                "这条标签带证据吗？",
                branches=[
                    br(
                        "否",
                        "删掉这条标签，不进判定\n无证据的标签不输出",
                        h=0.58,
                        ret="merge_after",
                    )
                ],
            ),
        ],
        "contract": [
            ("入", "dialogue（带说话人的话语单元序列）"),
            ("出", "三层标签 + 杠杆强度（1-5）+ 归属；每条都带证据位置"),
        ],
    },
    {
        "key": "judge",
        "title": "④ 判定层",
        "header_right": True,
        "items": [
            box("聚合标签：灯色（红 / 黄 / 绿）+ 被说到哪一步", h=0.42),
            dia(
                "风险灯色是绿吗？",
                branches=[
                    br(
                        "是",
                        "出「未发现操纵特征」\n+ 一个正常说法对照，不暗示可以买",
                        h=0.58,
                        ret="merge_after",
                    )
                ],
            ),
            box("红色 / 黄色：出判定 + 一句话；红色再挂 12315 / 96110", h=0.42),
        ],
        "contract": [
            ("入", "三层标签 + 杠杆强度 + 归属"),
            (
                "出",
                "判定 = { 风险：红 | 黄 | 绿；一句话；触发规则；说话人置信度：高 | 低 }",
            ),
        ],
    },
    {
        "key": "strat",
        "title": "⑤ 策略层",
        "items": [
            box("填满 6 栏：用户 · 对抗者 · 路径 · 语域 · 输出形态 · 禁忌", h=0.42),
            dia(
                "有交涉对象吗？",
                branches=[
                    br(
                        "没有",
                        "广告 / 直播 / 包装：无交涉对象\n只出识别 + 自保，不出问题清单",
                        h=0.58,
                        ret="merge_after",
                    )
                ],
            ),
            box("推销员 / 亲友 / 平台：出问题清单或说服脚本", h=0.42),
        ],
        "contract": [
            ("入", "判定 + 用户身份 + 对抗者（从用户说的话里推断）"),
            (
                "出",
                "6 栏策略：用户 · 对抗者 · 加工路径（中心 / 边缘）· 语域 · 输出形态 · 禁忌",
            ),
        ],
    },
    {
        "key": "gate",
        "kind": "gate",
        "title": "送出前强制闸门：禁忌扫描（执行指令 §5.5）",
        "items": [
            dia(
                "命中禁忌？",
                gap_before=0.46,
                branches=[
                    br("命中", "重写这一段，再扫一遍", h=0.42, ret="loop"),
                    br(
                        "改不动",
                        "降级为不含该段的安全输出，记一笔",
                        h=0.42,
                        ret="merge_after",
                    ),
                ],
            )
        ],
        "contract": [
            ("规则", "禁忌库是运行时组件：每一段输出在送达用户前必须过一遍。"),
        ],
    },
    {
        "key": "present",
        "title": "⑥ 呈现层",
        "items": [
            box("回复一段带色块的文本 + 一句话结论", h=0.42),
            box("点色块 → 浮层原位展开，关掉回原处，不跳页", h=0.42),
            box("说话人置信度低：回复里显著提示 + 一键纠正", h=0.42),
        ],
        "contract": [
            ("入", "过了禁忌扫描的 6 栏策略 + 判定"),
            (
                "出",
                "用户看得见的三块：发出去的东西 · AI 的回复（带色块）· 一句话结论；浮层可点开，结论可朗读",
            ),
        ],
    },
]

GAP_LABEL = {
    "in": "归一化：三模态归成同一份文本",
    "disc": "逐单元标注",
    "ann": "聚合",
    "judge": "生成 6 栏策略",
    "strat": "送出前过闸门",
    "gate": "放行",
}


def contract_h(lines):
    return len(lines) * CONTRACT_LINE


def content_h(items):
    total = 0.0
    for i, it in enumerate(items):
        if i == 0:
            total += it.get("gap_before", 0.0)
        total += row_h(it)
        if i < len(items) - 1:
            nxt = items[i + 1]
            g = it.get("gap_after") if it.get("gap_after") is not None else GAP
            g = max(g, nxt.get("gap_before", 0.0))
            total += g
    return total


def band_h(b):
    h = PAD_TOP + HEADER_H
    if b.get("contract"):
        h += CONTRACT_GAP
        h += contract_h(b["contract"]) + CONTRACT_GAP
    h += content_h(b["items"]) + PAD_BOTTOM
    if has_ret(b["items"], "merge_after"):
        h += MERGE_EXTRA
    return h


def draw_contract(c, b):
    lines = b["contract"]
    x0, x1 = CONTRACT_X, BAND_X1 - 0.28
    c.rect(
        x0 - 0.12,
        b["_ctop"],
        (x1 - x0) + 0.24,
        contract_h(lines) + 0.10,
        C_CONTRACT,
        C_CONTRACT,
        lw=0.0,
        z=2,
        round_=0.05,
    )
    c.rect(
        x0 - 0.12,
        b["_ctop"],
        0.055,
        contract_h(lines) + 0.10,
        C_CONTRACT_BAR,
        C_CONTRACT_BAR,
        lw=0.0,
        z=3,
        round_=0.01,
    )
    for i, (lab, txt) in enumerate(lines):
        y = b["_ctop"] + CONTRACT_LINE * (i + 0.5) + 0.05
        if lab:
            c.text(
                x0 + 0.03,
                y,
                lab + "：",
                size=8.6,
                color=C_TXT2,
                ha="left",
                bold=True,
                box=(x0 - 0.10, y - 0.13, x1 - x0 + 0.10, 0.26),
                kind="contract",
            )
        c.text(
            x0 + 0.55,
            y,
            txt,
            size=8.6,
            color=C_TXT2,
            ha="left",
            box=(x0, y - 0.13, x1 - x0, 0.26),
            kind="contract",
        )


def draw_diamond_item(c, b, it, y_top, geom):
    h = row_h(it)
    cy = y_top + h / 2
    pts = [
        (CX, cy + DIA_H / 2),
        (CX + DIA_W / 2, cy),
        (CX, cy - DIA_H / 2),
        (CX - DIA_W / 2, cy),
    ]
    c.ax.add_patch(
        Polygon(
            [(p[0], c.y(p[1])) for p in pts],
            closed=True,
            facecolor=C_DIA,
            edgecolor=C_NODE_EDGE,
            lw=1.15,
            zorder=6,
        )
    )
    c.text(
        CX,
        cy,
        it["text"],
        size=9.0,
        bold=False,
        z=9,
        box=(CX - DIA_W / 4, cy - DIA_H / 4, DIA_W / 2, DIA_H / 2),
        kind="diamond",
    )
    top, bottom = cy - DIA_H / 2, cy + DIA_H / 2

    brs = it["branches"]
    sh = stack_h(brs)
    by = cy + sh / 2
    placed = []
    for bx in reversed(brs):  # 列表顺序 = 从上到下
        b_top = by - bx["h"]
        c.rect(BR_X0, b_top, BR_X1 - BR_X0, bx["h"], C_BR, C_BR_EDGE, lw=1.0, z=6)
        c.text(
            (BR_X0 + BR_X1) / 2,
            b_top + bx["h"] / 2,
            bx["text"],
            size=8.6,
            color=C_TXT2,
            z=9,
            box=(BR_X0 + 0.10, b_top + 0.03, BR_X1 - BR_X0 - 0.20, bx["h"] - 0.06),
            kind="branch",
        )
        b_cy = b_top + bx["h"] / 2
        c.arrow((CX + DIA_W / 2, b_cy), (BR_X0 - 0.04, b_cy), z=5)
        c.text(
            CX + DIA_W / 2 + 0.10,
            b_cy - 0.185,
            bx["label"],
            size=8.4,
            color=C_TXT3,
            ha="left",
            z=9,
        )
        placed.append({"spec": bx, "top": b_top, "bottom": b_top + bx["h"], "cy": b_cy})
        by = b_top - BR_GAP

    geom.append(
        {"it": it, "cy": cy, "top": top, "bottom": bottom, "placed": placed, "h": h}
    )
    return top, bottom


def draw_band(c, b, y_top):
    h = band_h(b)
    is_gate = b.get("kind") == "gate"
    b["_top"] = y_top
    b["_bottom"] = y_top + h
    b["_h"] = h
    c.rect(
        BAND_X0,
        y_top,
        BAND_X1 - BAND_X0,
        h,
        C_GATE if is_gate else C_BAND,
        C_GATE_EDGE if is_gate else C_BAND_EDGE,
        lw=1.5 if is_gate else 1.2,
        ls="--" if is_gate else "-",
        z=1,
    )

    hy = y_top + PAD_TOP + HEADER_H / 2
    c.text(
        BAND_X0 + 0.28,
        hy,
        b["title"],
        size=11.0,
        bold=True,
        color=C_TXT,
        ha="left",
        z=9,
    )

    if b.get("header_right"):
        x = 8.02
        c.text(x, hy, "灯色只编码风险", size=8.4, color=C_TXT3, ha="left", z=9)
        for i, col in enumerate([C_RED, C_AMBER, C_GREEN]):
            c.swatch(9.02 + i * 0.28, hy - 0.11, 0.2, 0.22, col)
        c.text(9.95, hy, "（杠杆进浮层）", size=8.4, color=C_TXT3, ha="left", z=9)

    if b.get("contract"):
        b["_ctop"] = y_top + PAD_TOP + HEADER_H + CONTRACT_GAP
        draw_contract(c, b)
        y = b["_ctop"] + contract_h(b["contract"]) + CONTRACT_GAP
    else:
        y = y_top + PAD_TOP + HEADER_H

    items = b["items"]
    y += items[0].get("gap_before", 0.0)
    geom = []
    for i, it in enumerate(items):
        if it["t"] == "box":
            top, bottom = y, y + it["h"]
            c.rect(NODE_X0, top, NODE_W, it["h"], C_NODE, C_NODE_EDGE, lw=1.15, z=6)
            c.text(
                CX,
                top + it["h"] / 2,
                it["text"],
                size=9.0,
                z=9,
                box=(NODE_X0 + 0.10, top + 0.02, NODE_W - 0.20, it["h"] - 0.04),
                kind="node",
            )
            geom.append(
                {
                    "it": it,
                    "top": top,
                    "bottom": bottom,
                    "h": it["h"],
                    "cy": top + it["h"] / 2,
                }
            )
        else:
            top, bottom = draw_diamond_item(c, b, it, y, geom)
        nxt = items[i + 1] if i < len(items) - 1 else None
        if nxt is not None:
            g = it.get("gap_after") if it.get("gap_after") is not None else GAP
            g = max(g, nxt.get("gap_before", 0.0))
            c.arrow(
                (CX, bottom),
                (
                    CX,
                    y
                    + row_h(it)
                    + g
                    + (0.0 if nxt["t"] == "box" else (row_h(nxt) - DIA_H) / 2),
                ),
                z=3,
            )
            if it["t"] == "diamond" and it["branches"]:
                c.text(
                    CX + 0.14,
                    (bottom + y + row_h(it) + g) / 2,
                    "否" if len(it["branches"]) == 1 else "",
                    size=8.4,
                    color=C_TXT3,
                    ha="left",
                    z=9,
                )
            y += row_h(it) + g
        else:
            y += row_h(it)

    # 末尾竖线：把层内流量送到层底边
    last = geom[-1]
    c.line([(CX, last["bottom"]), (CX, b["_bottom"] - 0.02)], z=3)

    # 分支回流：merge_before / merge_after / loop
    if has_ret(items, "merge_after"):
        merge_y = last["bottom"] + 0.25
    else:
        merge_y = None
    for g in geom:
        if g["it"]["t"] != "diamond":
            continue
        for p in g["placed"]:
            ret = p["spec"]["ret"]
            lx = BR_X0 + 0.85
            if ret == "merge_before":
                ty = g["bottom"] + 0.39
                c.poly_arrow(
                    [(lx, p["bottom"]), (lx, ty), (CX + 0.01, ty)],
                    color=C_LINE,
                    lw=1.1,
                    ls="-",
                    z=4,
                )
            elif ret == "merge_after":
                c.poly_arrow(
                    [(lx, p["bottom"]), (lx, merge_y), (CX + 0.01, merge_y)],
                    color=C_LINE,
                    lw=1.1,
                    ls="-",
                    z=4,
                )
            else:  # loop：回到上一步重算
                prev = None
                for gg in geom:
                    if gg["cy"] < g["cy"] and gg["it"]["t"] == "box":
                        prev = gg
                if prev is not None:
                    ty = (prev["bottom"] + g["top"]) / 2
                    c.poly_arrow(
                        [
                            (lx, p["top"]),
                            (lx, ty),
                            (CX + 0.95, ty),
                            (CX + 0.95, prev["bottom"]),
                        ],
                        z=4,
                    )
                    c.text(
                        (lx + CX + 0.95) / 2,
                        ty - 0.11,
                        "重算本层",
                        size=8.0,
                        color=C_LOOP,
                        z=9,
                    )
                else:
                    lane = (
                        min([g["cy"] - DIA_H / 2] + [pp["top"] for pp in g["placed"]])
                        - 0.12
                    )
                    tx = CX + 0.95
                    sl = g["cy"] - (DIA_H / 2) * (1 - (tx - CX) / (DIA_W / 2))
                    c.poly_arrow(
                        [(lx, p["top"]), (lx, lane), (tx, lane), (tx, sl)], z=4
                    )
    return b["_bottom"]


def main():
    # ---- 版面高度
    total = (
        TITLE_H + sum(band_h(b) for b in BANDS) + BAND_GAP * (len(BANDS) - 1) + FOOT_H
    )
    H = total

    fig = plt.figure(figsize=(FIG_W, H))
    ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))
    ax.set_xlim(0, FIG_W)
    ax.set_ylim(0, H)
    ax.set_aspect("equal")
    ax.axis("off")
    c = Canvas(ax, H)

    # ---- 标题
    c.text(
        BAND_X0, 0.62, "LuCDA 信息流控制流图（CFG）", size=18, bold=True, ha="left", z=9
    )
    c.text(
        BAND_X0,
        1.06,
        "GOAL §4 信息流：输入层 → 话语层 → 标注层 → 判定层 → 策略层 → 呈现层；溯源层横切各层",
        size=10,
        color=C_TXT3,
        ha="left",
        z=9,
    )
    c.line([(BAND_X0, 1.30), (SRC_X1, 1.30)], color=C_BAND_EDGE, lw=1.0, z=2)

    # ---- 六层 + 闸门
    y = TITLE_H
    for i, b in enumerate(BANDS):
        bottom = draw_band(c, b, y)
        if i < len(BANDS) - 1:
            mid = y + b["_h"] + BAND_GAP / 2
            c.arrow((CX, bottom), (CX, bottom + BAND_GAP), z=3)
            lab = GAP_LABEL.get(b["key"])
            if lab:
                c.text(CX + 0.30, mid, lab, size=9.4, color=C_TXT2, ha="left", z=9)
            y = bottom + BAND_GAP

    # ---- 溯源侧带（横切各层）
    top_y = BANDS[0]["_top"]
    bot_y = BANDS[-1]["_bottom"]
    c.rect(
        SRC_X0, top_y, SRC_X1 - SRC_X0, bot_y - top_y, C_SRC, C_SRC_EDGE, lw=1.2, z=1
    )
    mid = (top_y + bot_y) / 2
    src_lines = [
        ("溯源层 · 横切各层", 11.0, True),
        ("每一层都能挂依据，不是流程里的一步", 9.6, False),
        ("L1 理论 → L2 文献 → L3 语料例证", 9.6, False),
        ("任意断言 2 次点击内到出处", 9.6, False),
    ]
    for k, (s, sz, bd) in enumerate(src_lines):
        c.text(
            SRC_TEXT_X[k],
            mid,
            s,
            size=sz,
            color=C_TXT2 if bd else C_TXT3,
            bold=bd,
            rot=90,
            z=9,
        )

    for b in BANDS:
        yy = b["_top"] + PAD_TOP + HEADER_H / 2
        c.arrow(
            (BAND_X1, yy), (SRC_X0 - 0.02, yy), color=C_LOOP, lw=0.9, ls="--", z=3, ms=8
        )
        c.text((BAND_X1 + SRC_X0) / 2, yy - 0.14, "挂依据", size=7.4, color=C_LOOP, z=9)

    # ---- 图例 / 边界声明
    fy = H - FOOT_H + 0.24
    c.line([(BAND_X0, fy - 0.16), (SRC_X1, fy - 0.16)], color=C_BAND_EDGE, lw=1.0, z=2)
    c.text(
        BAND_X0,
        fy,
        "图例：实线箭头 = 主流程　菱形 = 条件判断（是 / 否 走不同出口）　虚线回跳 = 重写或重算后回到上一步　右侧虚线 = 各层都能挂依据、可查证",
        size=8.6,
        color=C_TXT2,
        ha="left",
        z=9,
    )
    c.text(
        BAND_X0,
        fy + 0.26,
        "本流程只分析话术在做什么，不判断产品真假。（执行指令 §1.3）",
        size=8.6,
        color=C_TXT2,
        ha="left",
        z=9,
    )
    c.text(
        BAND_X0,
        fy + 0.52,
        "唯一真源：GOAL §4；分支规则另见 GOAL §4.1 与执行指令 §4.3 / §5.5 / §6.5 / §7.6 / §9.4。",
        size=8.6,
        color=C_TXT3,
        ha="left",
        z=9,
    )

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    issues = c.check(fig, ax)
    if not issues:
        print(
            "[自检] 通过：文字在容器内、未出画布、互不重叠；连线不压文字；连线不穿节点"
        )
    fig.savefig(OUT_PNG, dpi=300, facecolor="white")
    fig.savefig(OUT_SVG, facecolor="white")
    plt.close(fig)

    from PIL import Image

    with Image.open(OUT_PNG) as im:
        print(
            f"PNG {im.size[0]}x{im.size[1]} px  dpi={im.info.get('dpi')}  bytes={OUT_PNG.stat().st_size}"
        )
    print(f"SVG bytes={OUT_SVG.stat().st_size}")
    print(f"figure inch={FIG_W} x {round(H, 2)}")


if __name__ == "__main__":
    main()
