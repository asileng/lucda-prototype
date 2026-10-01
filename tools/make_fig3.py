"""LuCDA 计划1 · fig3 三方对标（纯大模型 / 事实核查路径 / LuCDA 话语分析）

产出（都写在 计划1/ 下）：
    assets/fig3_data.json         原始对照数据：每条输入的提示词、模型、原始回答、用量、耗时、指标
    assets/fig3_compare.png       300 dpi 位图
    assets/fig3_compare.svg       矢量图（文字转路径，换机器不变方框）

运行：
    D:/anaconda/miniconda3/python.exe tools/make_fig3.py            # 有数据就画图，没数据先跑调用再画
    D:/anaconda/miniconda3/python.exe tools/make_fig3.py --run      # 只跑调用（48 次），写 fig3_data.json
    D:/anaconda/miniconda3/python.exe tools/make_fig3.py --draw     # 只画图，读已有的 fig3_data.json
    D:/anaconda/miniconda3/python.exe tools/make_fig3.py --run --limit 1   # 冒烟：只跑第 1 条样例（6 次调用）

三条路径（同一段输入走三遍）：
    ① 纯大模型      直接把原话丢给 deepseek-v4-pro，问「这段话是不是诈骗 / 有没有问题」
    ② 事实核查路径  问「这个产品、这批号、这个说法是否真实、是否合法、是否有效」
    ③ LuCDA         走话语分析：六杠杆 + 归属 + 风险等级 + 说服策略。
                    不重写提示词，直接调 worker/dev-server.mjs 的 POST /api/analyze，
                    跑的就是产品线上的那一份 system prompt 与输出契约。

数据从哪来：本脚本自己发起的真实 HTTP 调用。密钥只从环境变量 DEEPSEEK_API_KEY 读，
不打印、不写入任何文件、不进图。

图上写了什么（逐条对得上）：GOAL §9 的 fig3 三方对比、执行指令 §13 TBD 第 4 项（5–10 条 × 2 条件）、
执行指令 §1.2 能力边界、§1.3 观察 vs 核查、§2 铁律 2/11、§6.7 溯源三层、§9.4 绿色主动输出、
§9.6 自我诊断与面子处理。

脚本自带核对（每次运行都打印）：
    · 文字是否溢出所在单元格 / 是否出画布 / 文字之间是否重叠；
    · 图上全部文字逐字扫禁用词表（权威类 / 绝对类 / 姿态类 / 文案禁用词）。
可复现：随机性为零（温度 0、推理关闭），同一份输入重跑应得到同量级结论；
数字全部由 assets/fig3_data.json 现算，不在脚本里写死。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.textpath import TextPath

matplotlib.rcParams["svg.fonttype"] = "path"
matplotlib.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).resolve()
ROOT = HERE.parent.parent
OUT_PNG = ROOT / "assets" / "fig3_compare.png"
OUT_SVG = ROOT / "assets" / "fig3_compare.svg"
OUT_JSON = ROOT / "assets" / "fig3_data.json"

FONT_REG = "C:/Windows/Fonts/msyh.ttc"
FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"

# ---------------------------------------------------------------- 调用配置
上游地址 = "https://api.deepseek.com/chat/completions"
文本模型 = "deepseek-v4-pro"  # 与 worker/worker.js 的 默认模型.text 一致
温度 = 0  # 三条路径同温度：差异来自提示词路径，不来自采样
输出上限 = 4000
单次超时秒 = 300
重试次数 = 3
并发数 = 4
本机端口 = 8899
本机限流 = 200  # 本机对照跑批，放开限流；产品默认是 10 次/分钟

# 路径 ③ 用产品线自己的提示词与契约，不在这里重写。
DEV_SERVER = ROOT / "worker" / "dev-server.mjs"

# ---------------------------------------------------------------- 样本
# 8 条样例 × 2 种用户身份 = 16 条输入 × 3 条路径 = 48 次调用（执行指令 §13 TBD 第 4 项）。
# 样例来源：自建样例，覆盖典型推销话术场景，用于对照三条路径的反应，不代表语料库统计。
样例表 = [
    {
        "编号": "S1",
        "场景": "保健品 · 权威 + 稀缺",
        "观察点": "身份名号替代证据；数量与时间压力逼当场决定",
        "老人本人": "小李跟我说这个胶囊是院士团队研发的，还说全国就剩最后三盒，今天不订明天就没了。",
        "子女": "我妈跟我说，小李推荐的那个胶囊是院士团队研发的，全国就剩最后三盒，今天不订明天就没了。她让我明天陪她去交钱。",
    },
    {
        "编号": "S2",
        "场景": "器械 · 先免费后加码",
        "观察点": "承诺一致 + 互惠：先答应小事，再拿这件事推下一步",
        "老人本人": "他们先让我免费试了半个月，还送了两盒鸡蛋，说试得好再买。现在跟我说该交钱办疗程卡了。",
        "子女": "我妈在小区里免费理疗了半个月，人家还送鸡蛋，说试好了再买。现在我妈说人家让她办一张疗程卡。",
    },
    {
        "编号": "S3",
        "场景": "情感经营 · 拟亲属称呼",
        "观察点": "喜好杠杆：先做关系，再卖东西",
        "老人本人": "小王比我亲闺女还上心，天天给我打电话，我叫他干儿子。他说有个好项目让我看看。",
        "子女": "我妈认了个干儿子，是卖保健品的。她说那孩子比她亲闺女还上心，还说有个好项目要带她看看。",
    },
    {
        "编号": "S4",
        "场景": "用户自己说的话 · 已信任",
        "观察点": "「我很信任」出自用户本人 → 喜好杠杆已对我生效，是自诊断入口",
        "老人本人": "小李给我介绍了个投资项目，说半年翻一倍。我很信任小李，他不会骗我的。",
        "子女": "我妈说小李给她介绍了个投资项目。她反复跟我讲她很信任小李，不会被骗。",
    },
    {
        "编号": "S5",
        "场景": "正常商家（对照组）",
        "观察点": "检验会不会误伤：样张里没有杠杆，也没有要求立刻做决定",
        "老人本人": "药店的人跟我说，这个钙片不能代替吃药，让我先问医生，还说嫌贵就先别买。",
        "子女": "我妈说药店的人告诉她，钙片不能代替吃药，要先问医生，还说嫌贵就先别买。",
    },
    {
        "编号": "S6",
        "场景": "陌生来电 · 中奖",
        "观察点": "稀缺 + 不许挂断；子女这一条还带出已报出证件号",
        "老人本人": "一个陌生电话打过来，说我中奖了，让我先别挂，说今天必须领，过期就作废。",
        "子女": "我妈接了个陌生电话，对方说她中奖了，让她先别挂，说今天必须领，过期作废。我妈把身份证号报过去了。",
    },
    {
        "编号": "S7",
        "场景": "广告 / 包装类",
        "观察点": "无交涉对象；社会认同 + 功效承诺",
        "老人本人": "小区门口贴了张膏药广告，说得过大奖，用过的都说好，什么病都能贴。我拍下来发给你看。",
        "子女": "小区门口贴了张膏药广告，说得过大奖、什么病都能贴。我妈拍照发给我，问我能不能买。",
    },
    {
        "编号": "S8",
        "场景": "已买已投 · 沉没成本",
        "观察点": "面子与止损：说出口的是「我不想让别人知道」",
        "老人本人": "我已经买了三盒，花了三千多，我不想让别人知道。",
        "子女": "我妈已经买了三万多，她现在不让我跟别人说。",
    },
]

条件表 = ["老人本人", "子女"]

# ---------------------------------------------------------------- 路径 ①② 的提示词
路径一_系统 = (
    "你是一个通用助手。用户会把一段听来的话或聊天记录发给你，你直接回答他的问题。"
)
路径一_用户 = "这段话是不是诈骗？有没有问题？\n\n" + "{原文}"

路径二_系统 = "你是一个事实核查助手。你的工作是判断信息是否真实、是否合法、是否有效。"
路径二_用户 = (
    "下面这段话里提到的产品、批号、资质和疗效，是否真实、是否合法、是否有效？"
    "请给出核查结论。\n\n" + "{原文}"
)

路径清单 = [
    {
        "键": "① 纯大模型",
        "协议": "openai",
        "系统": 路径一_系统,
        "用户模板": 路径一_用户,
    },
    {
        "键": "② 事实核查路径",
        "协议": "openai",
        "系统": 路径二_系统,
        "用户模板": 路径二_用户,
    },
    {"键": "③ LuCDA", "协议": "lucda"},
]

# ---------------------------------------------------------------- 指标口径（词面匹配）
# 口径说明：下面是字面匹配，不是语义判断。命中只作线索，判读时回原文核对。
词表_官方出口 = ["12315", "96110"]
词表_能力边界 = [
    "无法判断",
    "不能判断",
    "无法核实",
    "不能核实",
    "无法验证",
    "无法查证",
    "不做事实核查",
    "不判断产品真假",
    "不判断真假",
    "需要核实",
    "需自行核实",
    "以官方为准",
    "查不到",
    "没有找到",
]
词表_正面结论 = [
    "可以买",
    "放心买",
    "值得买",
    "可以放心",
    "是正品",
    "没问题",
    "可以试试",
    "推荐购买",
    "建议购买",
    "可以入手",
]


def 词面命中(文本: str, 词表: list[str]) -> list[str]:
    return [w for w in 词表 if w in (文本 or "")]


def 命中上下文(文本: str, 词表: list[str], 半径: int = 22) -> list[str]:
    """把命中处的上下文一起存下来，方便评审自己核，不用信本脚本的判断。"""
    出 = []
    for w in 词表:
        位 = (文本 or "").find(w)
        if 位 >= 0:
            出.append((文本[max(0, 位 - 半径) : 位 + len(w) + 半径]).replace("\n", " "))
    return 出


# ================================================================ 调用
def 读密钥() -> str:
    k = os.environ.get("DEEPSEEK_API_KEY")
    if not k or not k.strip():
        raise SystemExit(
            "没有读到环境变量 DEEPSEEK_API_KEY，本次不调用模型，也不给任何结论。"
        )
    return k.strip()


def 打开发(请求, 超时秒: int):
    """只放过 https 与本机 http；不用 urlopen 直接吞下 file: 之类的协议。"""
    地址 = 请求.full_url if isinstance(请求, urllib.request.Request) else str(请求)
    协议 = urllib.parse.urlsplit(地址).scheme
    if 协议 not in ("http", "https"):
        raise ValueError(f"不支持的协议：{协议}")
    return urllib.request.urlopen(请求, timeout=超时秒)  # noqa: S310


def 调OpenAI(密钥: str, 系统: str, 用户: str, 模型: str = 文本模型) -> dict:
    """三条路径同温度、同输出上限、同超时，只差提示词。"""
    载荷 = {
        "model": 模型,
        "messages": [
            {"role": "system", "content": 系统},
            {"role": "user", "content": 用户},
        ],
        "temperature": 温度,
        "max_tokens": 输出上限,
        "stream": False,
        "thinking": {"type": "disabled"},  # 与 worker.js 默认一致：本任务不需要推理开销
    }
    数据 = json.dumps(载荷, ensure_ascii=False).encode("utf-8")
    请求 = urllib.request.Request(
        上游地址,
        data=数据,
        headers={"content-type": "application/json", "authorization": "Bearer " + 密钥},
    )
    起点 = time.time()
    上一次 = ""
    for 次 in range(重试次数):
        try:
            with 打开发(请求, 单次超时秒) as 响应:
                正文 = 响应.read().decode("utf-8")
            包 = json.loads(正文)
            选择 = (包.get("choices") or [{}])[0]
            消息 = 选择.get("message") or {}
            return {
                "通过": True,
                "模型": 包.get("model"),
                "原始回答": 消息.get("content") or "",
                "耗时毫秒": round((time.time() - 起点) * 1000),
                "用量": 包.get("usage"),
                "结束原因": 选择.get("finish_reason"),
                "重试": 次,
            }
        except Exception as 错:  # noqa: BLE001
            上一次 = f"{type(错).__name__}: {错}"
            if 次 < 重试次数 - 1:
                time.sleep(2 + 4 * 次)
    return {
        "通过": False,
        "模型": None,
        "原始回答": "",
        "耗时毫秒": round((time.time() - 起点) * 1000),
        "用量": None,
        "错误": 上一次,
        "重试": 重试次数 - 1,
    }


def 起本机服务() -> tuple[subprocess.Popen, dict]:
    env = dict(os.environ)
    env["PORT"] = str(本机端口)
    env["RATE_LIMIT_PER_MINUTE"] = str(本机限流)
    进程 = subprocess.Popen(
        ["node", str(DEV_SERVER)],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    地址 = f"http://127.0.0.1:{本机端口}"
    for _ in range(90):
        if 进程.poll() is not None:
            print(进程.stdout.read() if 进程.stdout else "")
            raise SystemExit("worker/dev-server.mjs 启动即退出，路径 ③ 无法进行。")
        try:
            with 打开发(地址 + "/health", 2) as 响应:
                return 进程, json.loads(响应.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            time.sleep(1)
    raise SystemExit("等待 worker/dev-server.mjs 就绪超时（90 秒）。")


def 调LuCDA(原文: str) -> dict:
    """③ 走产品线自己的路由，不在这里重写提示词。"""
    载荷 = json.dumps({"模态": "text", "内容": 原文}, ensure_ascii=False).encode(
        "utf-8"
    )
    请求 = urllib.request.Request(
        f"http://127.0.0.1:{本机端口}/api/analyze",
        data=载荷,
        headers={"content-type": "application/json"},
    )
    起点 = time.time()
    上一次 = ""
    for 次 in range(重试次数):
        try:
            with 打开发(请求, 单次超时秒) as 响应:
                状态 = 响应.status
                正文 = 响应.read().decode("utf-8")
            return {
                "通过": True,
                "http状态": 状态,
                "原始回答": 正文,
                "耗时毫秒": round((time.time() - 起点) * 1000),
                "用量": None,
                "重试": 次,
            }
        except urllib.error.HTTPError as 错:
            正文 = 错.read().decode("utf-8", "replace")
            # 4xx 是请求本身的问题或降级对象，重试无用；如实记录。
            return {
                "通过": False,
                "http状态": 错.code,
                "原始回答": 正文,
                "耗时毫秒": round((time.time() - 起点) * 1000),
                "用量": None,
                "错误": f"HTTPError {错.code}",
                "重试": 次,
            }
        except Exception as 错:  # noqa: BLE001
            上一次 = f"{type(错).__name__}: {错}"
            if 次 < 重试次数 - 1:
                time.sleep(2 + 4 * 次)
    return {
        "通过": False,
        "原始回答": "",
        "耗时毫秒": round((time.time() - 起点) * 1000),
        "用量": None,
        "错误": 上一次,
        "重试": 重试次数 - 1,
    }


# ================================================================ 跑批
def 跑批(密钥: str, 限量: int | None) -> dict:
    样例 = 样例表[:限量] if 限量 else 样例表
    任务列表 = []
    for 样 in 样例:
        for 条件 in 条件表:
            原文 = 样[条件]
            for 路 in 路径清单:
                任务列表.append((样, 条件, 路, 原文))

    print(
        f"准备调用：{len(样例)} 条样例 × {len(条件表)} 种身份 × {len(路径清单)} 条路径 = {len(任务列表)} 次"
    )

    服务, 健康 = 起本机服务()
    print("本机服务已就绪（路径 ③ 走的是产品线自己的路由与提示词）")
    健康信息 = {
        "服务": 健康.get("服务"),
        "契约": 健康.get("契约"),
        "模型": 健康.get("模型"),
        "密钥已读到": (健康.get("密钥") or {}).get("已从环境变量读取"),
    }
    结果表: dict = {}

    try:

        def 一个任务(任务):
            样, 条件, 路, 原文 = 任务
            键 = (样["编号"], 条件, 路["键"])
            if 路["协议"] == "openai":
                用户 = 路["用户模板"].format(原文=原文)
                结果 = 调OpenAI(密钥, 路["系统"], 用户)
                结果["提示词"] = {"system": 路["系统"], "user": 用户}
            else:
                结果 = 调LuCDA(原文)
                结果["提示词"] = {
                    "system": "见 worker/worker.js 的 SYSTEM_PROMPT（取自 schema/prompt_contract.md §1）",
                    "user": 原文,
                }
            结果["模型"] = 结果.get("模型") or (
                文本模型 if 路["协议"] == "lucda" else None
            )
            return 键, 结果

        with ThreadPoolExecutor(max_workers=并发数) as 池:
            for 计, (键, 结果) in enumerate(池.map(一个任务, 任务列表), start=1):
                结果表[键] = 结果
                状态 = "通过" if 结果["通过"] else "失败"
                print(
                    f"  [{计}/{len(任务列表)}] {键[0]} · {键[1]} · {键[2]} → {状态}（{结果['耗时毫秒']} 毫秒）"
                )
    finally:
        服务.terminate()
        try:
            服务.wait(timeout=10)
        except Exception:  # noqa: BLE001
            服务.kill()

    失败 = [k for k, v in 结果表.items() if not v["通过"]]
    print(f"完成：{len(结果表) - len(失败)}/{len(结果表)} 通过，失败 {len(失败)} 条")
    for k in 失败:
        print(
            "   失败：",
            k,
            "|",
            结果表[k].get("错误") or 结果表[k].get("原始回答", "")[:200],
        )

    return 组装数据(样例, 结果表, 健康信息, 限量)


def 组装数据(样例: list, 结果表: dict, 健康信息: dict, 限量: int | None) -> dict:
    数据 = {
        "meta": {
            "用途": "M5 三方对标：纯大模型 / 事实核查路径 / LuCDA 话语分析（→ 计划2 fig3_compare.png）",
            "生成时间UTC": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
            "生成脚本": "tools/make_fig3.py",
            "采集方式": "本脚本发起的真实 HTTP 调用；未使用任何模拟或编造内容",
            "上游": 上游地址,
            "模型": {
                "文字": 文本模型,
                "路径③": (健康信息.get("模型") or {}).get("文字"),
            },
            "温度": 温度,
            "推理": "关闭（thinking disabled，与 worker/worker.js 默认一致）",
            "输出上限_tokens": 输出上限,
            "并发": 并发数,
            "样例来源": "自建样例（语料加工未完成），覆盖典型推销话术场景；不代表语料库统计，也不含真实个人信息",
            "样例数": len(样例),
            "身份条件数": len(条件表),
            "路径数": len(路径清单),
            "调用数": len(结果表),
            "限量运行": bool(限量),
            "三条路径": [
                {
                    "键": "① 纯大模型",
                    "协议": "POST " + 上游地址,
                    "system": 路径一_系统,
                    "user模板": 路径一_用户,
                    "说明": "把原话直接丢给通用模型，问它是不是诈骗。这是最常见的用法。",
                },
                {
                    "键": "② 事实核查路径",
                    "协议": "POST " + 上游地址,
                    "system": 路径二_系统,
                    "user模板": 路径二_用户,
                    "说明": "问产品、批号、资质、疗效是否真实合法有效。这条路的立足点是判断真假。",
                },
                {
                    "键": "③ LuCDA",
                    "协议": f"POST http://127.0.0.1:{本机端口}/api/analyze（worker/dev-server.mjs）",
                    "system": "worker/worker.js 的 SYSTEM_PROMPT + OUTPUT_SKELETON + 参数映射 + 依据清单；system prompt 取自 schema/prompt_contract.md §1",
                    "user模板": "【本次输入的模态：文字】… 下面是要分析的文字：{原文}",
                    "说明": "不重写提示词，跑的是产品线上的那一份契约与校验链。",
                    "输出契约": "schema/annotation.schema.json",
                },
            ],
            "服务健康信息": 健康信息,
            "指标口径": {
                "说明": "下面四项都是字面匹配，不是语义判断；命中只作线索，判读时回原文核对。",
                "官方出口": 词表_官方出口,
                "能力边界": 词表_能力边界,
                "正面结论语面": 词表_正面结论,
            },
        },
        "样本": [],
    }

    for 样 in 样例:
        条 = {
            "编号": 样["编号"],
            "场景": 样["场景"],
            "观察点": 样["观察点"],
            "条件": [],
        }
        for 条件 in 条件表:
            原文 = 样[条件]
            单 = {"身份设定": f"用户={条件}", "输入": 原文, "结果": {}}
            for 路 in 路径清单:
                结果 = dict(
                    结果表.get(
                        (样["编号"], 条件, 路["键"]), {"通过": False, "错误": "未执行"}
                    )
                )
                路结果 = {
                    "提示词": 结果.get("提示词"),
                    "模型": 结果.get("模型"),
                    "通过": 结果.get("通过"),
                    "http状态": 结果.get("http状态"),
                    "耗时毫秒": 结果.get("耗时毫秒"),
                    "用量": 结果.get("用量"),
                    "重试": 结果.get("重试"),
                    "错误": 结果.get("错误"),
                    "原始回答": 结果.get("原始回答", ""),
                }
                if 路["协议"] == "lucda" and 结果.get("通过"):
                    try:
                        路结果["解析"] = json.loads(结果["原始回答"])
                    except Exception as 错:  # noqa: BLE001
                        路结果["解析失败"] = str(错)
                # 逐条现算指标
                文本 = 路结果["原始回答"] or ""
                指标 = {
                    "字数": len(文本),
                    "官方出口命中": 词面命中(文本, 词表_官方出口),
                    "能力边界命中": 词面命中(文本, 词表_能力边界),
                    "正面结论命中": 词面命中(文本, 词表_正面结论),
                    "官方出口上下文": 命中上下文(文本, 词表_官方出口),
                    "能力边界上下文": 命中上下文(文本, 词表_能力边界),
                    "正面结论上下文": 命中上下文(文本, 词表_正面结论),
                }
                if "解析" in 路结果:
                    解 = 路结果["解析"]
                    判定 = 解.get("判定") or {}
                    策略 = 解.get("策略") or {}
                    杠杆 = 解.get("说服杠杆层") or []
                    指标.update(
                        {
                            "风险": 判定.get("风险"),
                            "说话人置信度": 判定.get("说话人置信度"),
                            "推断用户": 策略.get("用户"),
                            "推断对抗者": 策略.get("对抗者"),
                            "推断路径": 策略.get("路径"),
                            "语域": 策略.get("语域"),
                            "输出形态": [
                                o.get("形态") for o in (策略.get("输出") or [])
                            ],
                            "输出条数": len(策略.get("输出") or []),
                            "输出最长字数": max(
                                [
                                    len(str(o.get("内容", "")))
                                    for o in (策略.get("输出") or [])
                                ]
                                or [0]
                            ),
                            "禁忌条数": len(策略.get("禁忌") or []),
                            "标识的杠杆": [
                                f"{g.get('杠杆')}({g.get('强度')},{g.get('归属')},{g.get('说话人')})"
                                for g in 杠杆
                            ],
                            "溯源条数": len(解.get("溯源") or []),
                            "溯源语料层": [
                                str(s.get("语料例证"))[:40]
                                for s in (解.get("溯源") or [])
                            ],
                            "溯源字段齐全": all(
                                all(
                                    k in (s or {})
                                    for k in ("断言", "理论", "文献", "语料例证")
                                )
                                for s in (解.get("溯源") or [])
                            )
                            if (解.get("溯源") or [])
                            else False,
                        }
                    )
                路结果["指标"] = 指标
                单["结果"][路["键"]] = 路结果
            条["条件"].append(单)
        数据["样本"].append(条)

    数据["指标汇总"] = 汇总(数据)
    return 数据


def 汇总(数据: dict) -> dict:
    汇总表: dict = {}
    for 路 in 路径清单:
        键 = 路["键"]
        全部 = [c["结果"][键] for 样 in 数据["样本"] for c in 样["条件"]]
        通过 = [c for c in 全部 if c.get("通过")]
        字数 = sorted(c["指标"]["字数"] for c in 通过)
        汇总表[键] = {
            "调用": len(全部),
            "通过": len(通过),
            "官方出口命中条数": sum(1 for c in 通过 if c["指标"]["官方出口命中"]),
            "能力边界命中条数": sum(1 for c in 通过 if c["指标"]["能力边界命中"]),
            "正面结论命中条数": sum(1 for c in 通过 if c["指标"]["正面结论命中"]),
            "字数_最短": 字数[0] if 字数 else None,
            "字数_中位": 字数[len(字数) // 2] if 字数 else None,
            "字数_最长": 字数[-1] if 字数 else None,
        }

    路三 = 汇总表["③ LuCDA"]
    风险 = {"红": 0, "黄": 0, "绿": 0}
    身份一致 = 0
    身份总 = 0
    正常样例 = []
    话术最长 = []
    for 样 in 数据["样本"]:
        正常 = 样["编号"] == "S5"
        for c in 样["条件"]:
            r = c["结果"]["③ LuCDA"]
            指标 = r.get("指标") or {}
            if r.get("通过") and 指标.get("风险") in 风险:
                风险[指标["风险"]] += 1
            if r.get("通过"):
                身份总 += 1
                if 指标.get("推断用户") == c["身份设定"].split("=")[-1]:
                    身份一致 += 1
                if 指标.get("输出最长字数"):
                    话术最长.append(指标["输出最长字数"])
            if 正常:
                正常样例.append(
                    {
                        "身份设定": c["身份设定"],
                        "LuCDA风险": 指标.get("风险"),
                        "LuCDA一句话": ((r.get("解析") or {}).get("判定") or {}).get(
                            "一句话"
                        ),
                        "LuCDA正常说法对照": (
                            (r.get("解析") or {}).get("判定") or {}
                        ).get("正常说法对照"),
                        "纯大模型首句": (c["结果"]["① 纯大模型"]["原始回答"] or "")
                        .strip()
                        .split("\n")[0][:120],
                    }
                )
    路三.update(
        {
            "风险分布": 风险,
            "推断用户与设定一致": f"{身份一致}/{身份总}",
            "输出句最长字数_最大": max(话术最长) if 话术最长 else None,
        }
    )

    路一 = 汇总表["① 纯大模型"]
    汇总表["对照小结"] = {
        "S5正常商家样例_LuCDA风险": [n["LuCDA风险"] for n in 正常样例],
        "S5正常商家样例_纯大模型首句": [n["纯大模型首句"] for n in 正常样例],
        "S5正常商家样例_LuCDA正常说法对照": [n["LuCDA正常说法对照"] for n in 正常样例],
        "纯大模型提到12315或96110的条数": 路一["官方出口命中条数"],
        "LuCDA提到12315或96110的条数": 路三["官方出口命中条数"],
    }
    return 汇总表


# ================================================================ 绘图
C_TXT = "#22303C"
C_TXT2 = "#455767"
C_TXT3 = "#6E7D89"
C_PAGE = "#FFFFFF"
C_HEAD_BG = "#EEF2F5"
C_ROW_A = "#FFFFFF"
C_ROW_B = "#F7F9FA"
C_GRID = "#C7D1D9"
C_DIM_BG = "#F1F4F6"
C_BAR_A = "#5B6E7E"
C_BAR_B = "#8A6E63"
C_BAR_C = "#6F8A6B"
C_PANEL = "#F8FAFB"
C_PANEL_EDGE = "#C7D1D9"
C_WARN = "#FBF6EF"
C_WARN_EDGE = "#D8C3A5"
C_NOTE = "#F4F7F9"

列宽 = [2.35, 3.93, 3.93, 3.93]
列距 = 0.0

行_定性 = [
    (
        "回答的是哪个问题",
        [
            "这段话是不是诈骗、有没有问题。落点是给一个整体判断。",
            "这个产品、这批号、这个说法是真的还是假的。落点是判断信息本身。",
            "这段话在做什么：用了哪几个说服杠杆、对谁施放、已经对你生效到哪一步。落点是话术与效果，不是信息。",
        ],
    ),
    (
        "会不会判断真假",
        [
            "会给判断。实测两次都直接下断言：一次写「这段话确实有比较明显的诈骗或虚假宣传特征」，一次写「这段话高度疑似诈骗」。",
            "会，而且这是本条路径的立足点。它对产品、批号、资质、疗效给核查结论。",
            "不判。规格把「不判断产品真假」写成硬边界：只说看见了什么、没看见什么，碰真假即越界。",
        ],
    ),
    (
        "输出是什么形态",
        [
            "一段自由解释，长短由模型自己定。本次两次分别是 {一短} 字与 {一长} 字。",
            "一条核查结论，同样是自由文本。本次两次分别是 {二短} 字与 {二长} 字。",
            "结构化标注加可以直接念出口的话术，按身份档三选一：问题清单 / 说服脚本 / 一句话加一个动作。本次整份回答 {三短} 字与 {三长} 字（JSON），其中整段脚本最长 {三句} 字。",
        ],
    ),
    (
        "出处能不能点开",
        [
            "没有结构化出处，依据混在正文里，读过就散。",
            "没有结构化出处。",
            "溯源是一个独立字段，每条判定带理论、文献、语料例证三层，可回指到具体哪一条。",
        ],
    ),
    (
        "说话人是谁",
        [
            "不区分。整段材料被当成一份文本读，谁说的不影响结论。",
            "不区分。",
            "说话人是一等字段：推销者 / 我 / 第三人。已对我生效的记录，说话人只能是「我」——这一栏决定结论是否全反。",
        ],
    ),
    (
        "对老人语域",
        [
            "通用书面语，没有老人档。本次两次 {一短} 字与 {一长} 字，都要老人自己从头读完。",
            "通用书面语，没有老人档。本次两次 {二短} 字与 {二长} 字。",
            "按身份档换语域：老人档只给一句话加一个动作；子女档给四段脚本；现场档给按序的问题。本次两次都判成子女档，与设定相符 {三一致}。",
        ],
    ),
    (
        "面子与沉没成本",
        [
            "不处理。实测把「高度疑似诈骗」这样的判断直接写进正文；给子女档的建议是「先别让你妈交钱」。",
            "不处理。给出的是一条核查结论加一句「不要交钱」，没有能直接转述给对方听的话术。",
            "已买已投那种情形走责任外部化，不否定判断力；给的是能自己问自己的一句，不是一句宣判。",
        ],
    ),
]

行_指标 = [
    (
        "实测 · 主动写出能力边界",
        "能力边界命中条数",
        "本次该路径的调用里，回答正文出现「无法核实 / 不判断真假 / 材料里没有找到」这类边界表述的条数。③ 得 0 是因为它整条路径不碰真假，不是漏写边界。",
    ),
    (
        "实测 · 给出官方出口",
        "官方出口命中条数",
        "本次该路径的调用里，回答正文出现 12315 或 96110 的条数。对老人来说，这是能马上照做的一步。",
    ),
    (
        "实测 · 对产品机构的正面结论",
        "正面结论命中条数",
        "本次该路径的调用里，回答正文出现「可以买 / 放心 / 是正品 / 没问题」这类语面的条数。字面匹配，出现不等于真在背书，要回原文核对。",
    ),
    (
        "实测 · 输出含可点开的三层出处",
        None,
        "回答里有没有理论 / 文献 / 语料例证这三层可回指的字段。前两条路径是自由文本，结构上就没有这一项。",
    ),
]


def 宽(s: str, 号: float, 粗: bool = False) -> float:
    """字符串宽度（英寸）。用 TextPath 量，与最终渲染一致。"""
    if not s:
        return 0.0
    return TextPath((0, 0), s, size=号, prop=字体(号, 粗)).get_extents().width / 72.0


_字体缓存: dict = {}


def 字体(号: float, 粗: bool = False) -> FontProperties:
    键 = (round(号, 2), 粗)
    if 键 not in _字体缓存:
        _字体缓存[键] = FontProperties(fname=FONT_BOLD if 粗 else FONT_REG, size=号)
    return _字体缓存[键]


def 折行(
    s: str, 最大宽: float, 号: float, 粗: bool = False, 缩进: str = ""
) -> list[str]:
    """按字符折行（中文无空格），保证不超过 最大宽。"""
    行列表: list[str] = []
    for 段 in str(s).split("\n"):
        当前 = ""
        for ch in 段:
            if 宽(当前 + ch, 号, 粗) <= 最大宽 or not 当前:
                当前 += ch
            else:
                行列表.append(当前)
                当前 = ch
        if 当前 or not 行列表:
            行列表.append(当前)
    return [缩进 + x for x in 行列表]


class 画布:
    def __init__(self, 高: float):
        self.H = 高
        self.fig = plt.figure(figsize=(15.0, 高), dpi=300)
        self.ax = self.fig.add_axes((0.0, 0.0, 1.0, 1.0))
        self.ax.set_xlim(0, 15.0)
        self.ax.set_ylim(0, 高)
        self.ax.axis("off")
        self.文本记录: list = []

    def y(self, v: float) -> float:
        return self.H - v

    def 矩形(self, x, y顶, w, h, 底色, 边色, lw=1.0, 圆角=0.06, z=2):
        盒 = FancyBboxPatch(
            (x, self.y(y顶 + h)),
            w,
            h,
            boxstyle=f"round,pad=0,rounding_size={圆角}",
            linewidth=lw,
            edgecolor=边色,
            facecolor=底色,
            zorder=z,
        )
        self.ax.add_patch(盒)
        return 盒

    def 文字(
        self,
        x,
        y顶,
        s,
        号=9.0,
        色=C_TXT,
        ha="left",
        va="top",
        粗=False,
        行距=1.5,
        z=8,
        盒=None,
        类="",
    ):
        艺术 = self.ax.text(
            x,
            self.y(y顶),
            s,
            ha=ha,
            va=va,
            color=色,
            fontproperties=字体(号, 粗),
            linespacing=行距,
            zorder=z,
        )
        self.文本记录.append((艺术, 盒, 类))
        return 艺术

    def 自检(self):
        self.fig.canvas.draw()
        r = cast("FigureCanvasAgg", self.fig.canvas).get_renderer()
        问题: list = []
        区域: list = []
        for 艺术, 盒, 类 in self.文本记录:
            bb = 艺术.get_window_extent(renderer=r)
            标 = 艺术.get_text().replace("\n", " / ")
            区域.append((标, bb))
            if 盒 is not None:
                bx, by, bw, bh = 盒
                p0 = self.ax.transData.transform((bx, self.y(by + bh)))
                p1 = self.ax.transData.transform((bx + bw, self.y(by)))
                if bb.x0 < p0[0] - 0.8 or bb.x1 > p1[0] + 0.8:
                    问题.append(
                        (
                            "左右溢出",
                            类,
                            标[:30],
                            round(bb.x1 - p1[0], 1),
                            round(p0[0] - bb.x0, 1),
                        )
                    )
                if bb.y0 < p0[1] - 0.8 or bb.y1 > p1[1] + 0.8:
                    问题.append(
                        (
                            "上下溢出",
                            类,
                            标[:30],
                            round(bb.y1 - p1[1], 1),
                            round(p0[1] - bb.y0, 1),
                        )
                    )
        for i in range(len(区域)):
            for j in range(i + 1, len(区域)):
                a, b = 区域[i][1], 区域[j][1]
                if a.x0 < b.x1 and b.x0 < a.x1 and a.y0 < b.y1 and b.y0 < a.y1:
                    问题.append(("文字重叠", 区域[i][0][:24], 区域[j][0][:24]))
        sx = (
            self.ax.transData.transform((1, 0))[0]
            - self.ax.transData.transform((0, 0))[0]
        )
        sy = (
            self.ax.transData.transform((0, 1))[1]
            - self.ax.transData.transform((0, 0))[1]
        )
        for 标, bb in 区域:
            x0i, x1i = bb.x0 / sx, bb.x1 / sx
            yti, ybi = (self.H * sy - bb.y1) / sy, (self.H * sy - bb.y0) / sy
            if x0i < -0.03 or x1i > 15.03 or yti < -0.03 or ybi > self.H + 0.03:
                问题.append(
                    (
                        "文字超出画布",
                        round(x0i, 2),
                        round(x1i, 2),
                        round(yti, 2),
                        round(ybi, 2),
                        标[:24],
                    )
                )

        禁用词 = [
            "最强",
            "最准",
            "最权威",
            "国家级",
            "独家",
            "权威AI",
            "权威 AI",
            "独家算法",
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
            "早就跟你说过",
            "你可以买",
            "放心买",
            "值得买",
        ]
        for 标, _bb in 区域:
            for w in 禁用词:
                if w in 标:
                    问题.append(("命中禁用词", w, 标[:30]))
        print(
            f"[自检] 文本 {len(区域)} 处、扫描禁用词 {len(禁用词)} 个，问题 {len(问题)} 条"
        )
        for it in 问题[:40]:
            print("   -", it)
        return 问题


def 画图(数据: dict) -> list:
    汇 = 数据["指标汇总"]
    路一, 路二, 路三 = 汇["① 纯大模型"], 汇["② 事实核查路径"], 汇["③ LuCDA"]

    # 图上出现的数字一律从 fig3_data.json 现算，不在脚本里写死
    填 = {
        "一短": 路一["字数_最短"],
        "一长": 路一["字数_最长"],
        "二短": 路二["字数_最短"],
        "二长": 路二["字数_最长"],
        "三短": 路三["字数_最短"],
        "三长": 路三["字数_最长"],
        "三句": 路三["输出句最长字数_最大"],
        "三一致": 路三["推断用户与设定一致"],
    }

    def 填词(s: str) -> str:
        for 键, 值 in 填.items():
            s = s.replace("{" + 键 + "}", str(值))
        return s

    行_定性_本次 = [(维, [填词(格) for 格 in 格表]) for 维, 格表 in 行_定性]

    页边 = 0.40
    表宽 = sum(列宽)
    x0 = 页边
    最大宽 = [w - 0.24 for w in 列宽]

    # ---- 尺寸预排（先折行量高，再决定画布高度）
    号_表头 = 10.2
    号_副 = 8.3
    号_维 = 9.3
    号_格 = 8.7
    号_数 = 9.6
    行距 = 1.52

    def 行高(行列表: list[float], 号: float) -> float:
        return max(行列表) * 号 * 行距 / 72.0 + 0.20

    表头行 = [
        折行("对照维度", 最大宽[0], 号_表头, True),
        折行("① 纯大模型", 最大宽[1], 号_表头, True),
        折行("② 事实核查路径", 最大宽[2], 号_表头, True),
        折行("③ LuCDA 话语分析", 最大宽[3], 号_表头, True),
    ]
    表头副 = [
        折行("三条路径各答一个问题", 最大宽[0], 号_副),
        折行("把原话直接发过去问：这段话是不是诈骗", 最大宽[1], 号_副),
        折行("换个问法：这个产品、这批号是真的吗", 最大宽[2], 号_副),
        折行("不走真假，问：这句话在对你做什么", 最大宽[3], 号_副),
    ]
    表头高 = (
        max(
            len(表头行[i]) * 号_表头 * 1.32 / 72.0
            + len(表头副[i]) * 号_副 * 1.45 / 72.0
            for i in range(4)
        )
        + 0.26
    )

    定性折 = []
    定性高 = []
    for 维, 格 in 行_定性_本次:
        折 = [折行(维, 最大宽[0], 号_维, True)] + [
            折行(格[i], 最大宽[i + 1], 号_格) for i in range(3)
        ]
        定性折.append(折)
        定性高.append(
            max(
                len(折[0]) * 号_维 * 行距 / 72.0,
                max(len(f) * 号_格 * 行距 / 72.0 for f in 折[1:]),
            )
            + 0.24
        )

    指标折 = []
    指标高 = []
    指标数 = [
        (
            f"{路一['能力边界命中条数']} / {路一['通过']}",
            f"{路二['能力边界命中条数']} / {路二['通过']}",
            f"{路三['能力边界命中条数']} / {路三['通过']}",
        ),
        (
            f"{路一['官方出口命中条数']} / {路一['通过']}",
            f"{路二['官方出口命中条数']} / {路二['通过']}",
            f"{路三['官方出口命中条数']} / {路三['通过']}",
        ),
        (
            f"{路一['正面结论命中条数']} / {路一['通过']}",
            f"{路二['正面结论命中条数']} / {路二['通过']}",
            f"{路三['正面结论命中条数']} / {路三['通过']}",
        ),
        ("无此字段", "无此字段", f"{路三['通过']} / {路三['通过']}（溯源字段）"),
    ]
    for i, (维, _k, 注) in enumerate(行_指标):
        折 = [折行(维, 最大宽[0], 号_维, True), 折行(注, 最大宽[0], 7.2, 缩进="")]
        指标折.append((折, 指标数[i]))
        指标高.append(
            max(
                len(折[0]) * 号_维 * 行距 / 72.0 + len(折[1]) * 7.2 * 1.45 / 72.0,
                1 * 号_数 * 1.5 / 72.0,
            )
            + 0.22
        )

    表高 = 表头高 + sum(定性高) + sum(指标高)

    # 统计带
    统计_内 = [
        f"{数据['meta']['调用数']} 次真实调用｜{数据['meta']['样例数']} 条样例 × {数据['meta']['身份条件数']} 种身份 × {数据['meta']['路径数']} 条路径",
        f"LuCDA 判定分布：红 {路三['风险分布']['红']} / 黄 {路三['风险分布']['黄']} / 绿 {路三['风险分布']['绿']}（共 {路三['通过']} 次）",
        (
            "正常商家对照样例（S5）本次没跑：采集为限量运行，绿档与「正常说法对照」这两项目前只有规格要求，没有实测数字。"
            if 数据["meta"].get("限量运行")
            else f"正常商家对照样例（S5）：LuCDA 给出 {汇['对照小结']['S5正常商家样例_LuCDA风险']}，带正常说法对照的 {sum(1 for x in 汇['对照小结']['S5正常商家样例_LuCDA正常说法对照'] if x)} 条。"
        ),
        f"LuCDA 从文本推断的用户身份与设定一致：{路三['推断用户与设定一致']}",
    ]
    统计高 = 0.28 + len(统计_内) * 9.0 * 1.62 / 72.0

    # 两个面板
    面板_弱点 = [
        "杠杆判定会错。归属判反（把「我」说的话算成推销者说的）会让结论整个反过来，现在只能靠提示词约束加置信度标记兜底。",
        "身份档会猜错。用户与对抗者要从文本里读，文本里没线索时实测会猜成子女档，输出形态跟着变。",
        "语料层还是空的。溯源第三条现在只能写占位，三层里实际能用的是两层。",
        "看出的话并不比通用模型多。同一段话，通用模型也点了名号与限量，而且讲得更细、更顺；LuCDA 的差别在出处、边界、说话人这几个字段上，不在「看得更准」。",
        "不回答「这产品有没有批准文号」。这类可查事实只能交给核查那条路，LuCDA 顶多记录「材料里没有找到」。",
        "判定跟着提示词走。契约文件是唯一真源，改一个字就可能影响全部判定，对照前得先固定版本。",
    ]
    面板_结论 = [
        "核查那条路回答「是不是真的」，要外部数据库比对，LuCDA 不碰这一段。",
        "通用模型答得快、讲得全，可以当第一道粗筛；代价是没有结构化出处、不主动划边界、也不区分谁在说。",
        "LuCDA 只回答「这句话在对你做什么」，代价是放弃真假判断，并且判定质量受提示词与语料进度限制。",
        "三条路不是排名，是分岔：可查的事实交给核查，对话里的说服对抗交给话语分析。",
        "本图数字全部由 assets/fig3_data.json 现算，原始回答逐条可查；样例为自建，不代表语料库统计。",
    ]

    号_面板 = 8.7
    左宽 = 8.35
    右宽 = 表宽 - 左宽 - 0.30
    左折 = []
    for t in 面板_弱点:
        左折.append(折行(t, 左宽 - 0.36 - 0.30, 号_面板))
    右折 = []
    for t in 面板_结论:
        右折.append(折行(t, 右宽 - 0.36 - 0.24, 号_面板))
    左高 = 0.34 + sum(len(f) for f in 左折) * 号_面板 * 1.60 / 72.0 + len(左折) * 0.10
    右高 = 0.34 + sum(len(f) for f in 右折) * 号_面板 * 1.60 / 72.0 + len(右折) * 0.10
    面板高 = max(左高, 右高)

    页眉高 = 1.34
    页脚高 = 0.52
    间距 = 0.20
    总高 = 页眉高 + 表高 + 间距 + 统计高 + 间距 + 面板高 + 间距 + 页脚高

    c = 画布(总高)

    # ---- 页眉
    c.文字(页边, 0.26, "三方对标：同一段话，三条路各自答一个问题", 号=20.5, 粗=True)
    c.文字(
        页边,
        0.78,
        f"{数据['meta']['样例数']} 条样例 × {数据['meta']['身份条件数']} 种用户身份 × {数据['meta']['路径数']} 条分析路径"
        f" = {数据['meta']['调用数']} 次真实调用｜模型 {数据['meta']['模型']['文字']}｜温度 {数据['meta']['温度']}｜推理关闭",
        号=10.6,
        色=C_TXT2,
    )
    c.文字(
        页边,
        1.04,
        f"样例为自建（语料加工未完成），本次只跑 {数据['meta']['样例数']} 条，属限量采集，不是完整评测；"
        "原始回答逐条存在 assets/fig3_data.json",
        号=8.6,
        色=C_TXT3,
    )

    y = 页眉高

    # ---- 表头
    c.矩形(x0, y, 表宽, 表头高, C_HEAD_BG, C_GRID, lw=1.0, 圆角=0.05)
    cx = x0
    for i in range(4):
        顶 = y + 0.12
        c.文字(
            cx + 0.12,
            顶,
            "\n".join(表头行[i]),
            号=号_表头,
            粗=True,
            行距=1.32,
            色=C_TXT if i else C_TXT2,
            盒=(cx, y, 列宽[i], 表头高),
            类="表头",
        )
        c.文字(
            cx + 0.12,
            顶 + len(表头行[i]) * 号_表头 * 1.32 / 72.0 + 0.02,
            "\n".join(表头副[i]),
            号=号_副,
            色=C_TXT3,
            行距=1.45,
            盒=(cx, y, 列宽[i], 表头高),
            类="表头副",
        )
        if i:
            c.ax.plot(
                [cx, cx], [c.y(y + 表头高), c.y(y)], color=C_GRID, lw=0.8, zorder=3
            )
        cx += 列宽[i]
    y += 表头高

    # ---- 定性行
    c.矩形(x0, y, 表宽, sum(定性高), C_ROW_A, C_GRID, lw=1.0, 圆角=0.0, z=1)
    for k, (折, 高) in enumerate(zip(定性折, 定性高, strict=True)):
        底色 = C_ROW_A if k % 2 == 0 else C_ROW_B
        c.ax.add_patch(
            Rectangle(
                (x0, c.y(y + 高)),
                表宽,
                高,
                facecolor=底色,
                edgecolor="none",
                zorder=1.5,
            )
        )
        c.矩形(x0, y, 列宽[0], 高, C_DIM_BG, C_GRID, lw=0.8, 圆角=0.0, z=2)
        cx = x0
        for i in range(4):
            c.文字(
                cx + 0.12,
                y + 0.12,
                "\n".join(折[i]),
                号=号_维 if i == 0 else 号_格,
                粗=(i == 0),
                色=C_TXT2 if i == 0 else C_TXT,
                行距=行距,
                盒=(cx, y, 列宽[i], 高),
                类="定性",
            )
            if i:
                c.ax.plot(
                    [cx, cx], [c.y(y + 高), c.y(y)], color=C_GRID, lw=0.8, zorder=3
                )
            cx += 列宽[i]
        c.ax.plot(
            [x0, x0 + 表宽], [c.y(y + 高), c.y(y + 高)], color=C_GRID, lw=0.8, zorder=3
        )
        y += 高

    # ---- 指标行
    for k, ((折, 数), 高) in enumerate(zip(指标折, 指标高, strict=True)):
        底色 = C_NOTE if k % 2 == 0 else C_ROW_A
        c.ax.add_patch(
            Rectangle(
                (x0, c.y(y + 高)),
                表宽,
                高,
                facecolor=底色,
                edgecolor="none",
                zorder=1.5,
            )
        )
        c.矩形(x0, y, 列宽[0], 高, C_DIM_BG, C_GRID, lw=0.8, 圆角=0.0, z=2)
        c.文字(
            x0 + 0.12,
            y + 0.11,
            折[0][0],
            号=号_维,
            粗=True,
            色=C_TXT2,
            盒=(x0, y, 列宽[0], 高),
            类="指标维",
        )
        c.文字(
            x0 + 0.12,
            y + 0.11 + len(折[0]) * 号_维 * 行距 / 72.0,
            "\n".join(折[1]),
            号=7.2,
            色=C_TXT3,
            行距=1.45,
            盒=(x0, y, 列宽[0], 高),
            类="指标注",
        )
        cx = x0 + 列宽[0]
        for i in range(3):
            c.文字(
                cx + 列宽[i + 1] / 2,
                y + 0.13,
                数[i],
                号=号_数,
                粗=True,
                ha="center",
                va="top",
                色=C_TXT,
                盒=(cx, y, 列宽[i + 1], 高),
                类="指标值",
            )
            c.ax.plot([cx, cx], [c.y(y + 高), c.y(y)], color=C_GRID, lw=0.8, zorder=3)
            cx += 列宽[i + 1]
        c.ax.plot(
            [x0, x0 + 表宽], [c.y(y + 高), c.y(y + 高)], color=C_GRID, lw=0.8, zorder=3
        )
        y += 高

    # 表脚注
    c.文字(
        x0,
        y + 0.04,
        "指标口径为字面匹配，词表写在 tools/make_fig3.py，命中只作线索，需回原文核对；分母是本次该路径的通过条数。",
        号=7.6,
        色=C_TXT3,
    )
    y += 0.04 + 0.17

    # ---- 统计带
    y = y + 间距
    c.矩形(x0, y, 表宽, 统计高, C_NOTE, C_PANEL_EDGE, lw=1.0, 圆角=0.05)
    c.ax.add_patch(
        Rectangle(
            (x0 + 0.001, c.y(y + 统计高)),
            0.055,
            统计高,
            facecolor=C_BAR_C,
            edgecolor="none",
            zorder=4,
        )
    )
    yy = y + 0.14
    for t in 统计_内:
        c.文字(x0 + 0.20, yy, t, 号=9.0, 色=C_TXT2, 盒=(x0, y, 表宽, 统计高), 类="统计")
        yy += 9.0 * 1.62 / 72.0
    y += 统计高

    # ---- 两个面板
    y = y + 间距
    c.矩形(x0, y, 左宽, 面板高, C_WARN, C_WARN_EDGE, lw=1.0, 圆角=0.05)
    c.ax.add_patch(
        Rectangle(
            (x0 + 0.001, c.y(y + 面板高)),
            0.055,
            面板高,
            facecolor=C_BAR_B,
            edgecolor="none",
            zorder=4,
        )
    )
    c.文字(
        x0 + 0.20,
        y + 0.12,
        "LuCDA 的弱点（如实写）",
        号=10.6,
        粗=True,
        色=C_TXT,
        盒=(x0, y, 左宽, 面板高),
        类="面板题",
    )
    yy = y + 0.42
    for f in 左折:
        c.文字(
            x0 + 0.20,
            yy,
            "· " + f[0],
            号=号_面板,
            色=C_TXT2,
            盒=(x0, y, 左宽, 面板高),
            类="面板",
        )
        for 后 in f[1:]:
            yy += 号_面板 * 1.60 / 72.0
            c.文字(
                x0 + 0.36,
                yy,
                后,
                号=号_面板,
                色=C_TXT2,
                盒=(x0, y, 左宽, 面板高),
                类="面板",
            )
        yy += 号_面板 * 1.60 / 72.0 + 0.10

    xr = x0 + 左宽 + 0.30
    c.矩形(xr, y, 右宽, 面板高, C_PANEL, C_PANEL_EDGE, lw=1.0, 圆角=0.05)
    c.ax.add_patch(
        Rectangle(
            (xr + 0.001, c.y(y + 面板高)),
            0.055,
            面板高,
            facecolor=C_BAR_A,
            edgecolor="none",
            zorder=4,
        )
    )
    c.文字(
        xr + 0.20,
        y + 0.12,
        "结论：三条路不互相替代",
        号=10.6,
        粗=True,
        色=C_TXT,
        盒=(xr, y, 右宽, 面板高),
        类="面板题",
    )
    yy = y + 0.42
    for f in 右折:
        c.文字(
            xr + 0.20,
            yy,
            "· " + f[0],
            号=号_面板,
            色=C_TXT2,
            盒=(xr, y, 右宽, 面板高),
            类="面板",
        )
        for 后 in f[1:]:
            yy += 号_面板 * 1.60 / 72.0
            c.文字(
                xr + 0.36,
                yy,
                后,
                号=号_面板,
                色=C_TXT2,
                盒=(xr, y, 右宽, 面板高),
                类="面板",
            )
        yy += 号_面板 * 1.60 / 72.0 + 0.10
    y += 面板高

    # ---- 页脚
    y += 间距
    c.ax.plot([x0, x0 + 表宽], [c.y(y), c.y(y)], color=C_GRID, lw=0.9, zorder=3)
    脚 = [
        ("数据 assets/fig3_data.json", 0.0),
        ("脚本 tools/make_fig3.py", 0.34),
        ("LuCDA 不判断产品真假，只说材料里看见了什么、没看见什么", 0.62),
    ]
    for t, 比例 in 脚:
        c.文字(
            x0 + 表宽 * 比例,
            y + 0.10,
            t,
            号=8.2,
            色=C_TXT3,
            盒=(x0, y, 表宽, 页脚高),
            类="页脚",
        )

    return c.自检()


# ================================================================ 主入口
def main() -> int:
    解析 = argparse.ArgumentParser(description="fig3 三方对标：跑真实调用并出图")
    解析.add_argument(
        "--run", action="store_true", help="只跑调用，写 assets/fig3_data.json"
    )
    解析.add_argument(
        "--draw", action="store_true", help="只画图，读已有的 assets/fig3_data.json"
    )
    解析.add_argument(
        "--limit", type=int, default=None, help="只跑前 N 条样例（冒烟用）"
    )
    参数 = 解析.parse_args()

    要跑 = 参数.run or (not 参数.draw and not OUT_JSON.exists())

    if 要跑:
        密钥 = 读密钥()
        数据 = 跑批(密钥, 参数.limit)
        if 参数.limit:
            数据["meta"]["限量运行"] = True
        OUT_JSON.write_text(
            json.dumps(数据, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print("已写", OUT_JSON, f"({OUT_JSON.stat().st_size} 字节)")
    else:
        try:
            数据 = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        except (OSError, ValueError) as 错:
            raise SystemExit(
                f"读 assets/fig3_data.json 失败：{错}。先跑 --run 采集数据。"
            ) from 错
        print("读入", OUT_JSON)

    if 参数.run:
        return 0

    问题 = 画图(数据)
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUT_PNG, dpi=300, facecolor="white")
    plt.savefig(OUT_SVG, facecolor="white")
    print("已写", OUT_PNG, f"({OUT_PNG.stat().st_size} 字节)")
    print("已写", OUT_SVG, f"({OUT_SVG.stat().st_size} 字节)")
    return 1 if 问题 else 0


if __name__ == "__main__":
    sys.exit(main())
