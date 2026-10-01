"""Fig.3 三方对标：把「同一条输入」问三种方式，真实返回并排摆出来。

对应交付：assets/fig3_compare.png（GOAL §9；计划2 的 D2 展板会直接用）

设计口径（这一版重做的原因）：
  上一版是「自己画的框 + 自定指标」，读者看不到真实回答，等于自说自话。
  这一版只做一件事：**把三边的真实输出原样摆出来**，谁好用读者自己看。
    · ①② 用通用对话产品的常见界面样式渲染（气泡 + 头像），正文是模型返回原文，一字不改
    · ③ 直接用 LuCDA 自己的界面截图（发布产物 docs/，与线上同一份代码）
  图上没有任何「我比它好」的结论，只有三栏原样输出 + 一段如实注文。

数据：真实 HTTP 调用，原文存进 assets/fig3_data.json（含提示词、模型、耗时、用量）。
      ③ 复用 data/demo_samples.json 里 demo-01 的真实结果（同一条输入），不重算、不手编。

用法：
  python tools/make_fig3.py              # 用已有数据渲染；数据缺失才去取
  python tools/make_fig3.py --recollect  # 强制重新调模型取数
"""

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
数据文件 = os.path.join(根目录, "assets", "fig3_data.json")
产物 = os.path.join(根目录, "assets", "fig3_compare.png")
临时 = os.path.join(os.environ.get("TEMP", "."), "lucda_fig3")

接口 = "https://api.deepseek.com/chat/completions"
模型名 = "deepseek-v4-pro"

路径说明 = [
    {
        "键": "① 直接问通用助手",
        "说明": "把原话丢给 ChatGPT / DeepSeek 这类通用助手，直接问它是不是诈骗。最常用的问法。",
        "system": "你是一个通用助手。用户会把一段听来的话或聊天记录发给你，你直接回答他的问题。",
        "user模板": "这段话是不是诈骗？有没有问题？\n\n{原文}",
    },
    {
        "键": "② 事实核查式提问",
        "说明": "问这东西是真是假、合不合法。这是事实核查类产品的路子，要外部数据库才能答。",
        "system": "你是一个事实核查助手。你的工作是判断信息是否真实、是否合法、是否有效。",
        "user模板": (
            "下面这段话里提到的产品、批号、资质和疗效，是否真实、是否合法、是否有效？"
            "请给出核查结论。\n\n{原文}"
        ),
    },
    {
        "键": "③ 问 LuCDA",
        "说明": "同一句话，问 LuCDA。它只说话术在做什么、说到哪一步、该怎么说，不判断产品真假。",
    },
]


# ---------------- 读写（都带异常处理，出错时给得出原因） ----------------


def 读JSON(路径):
    try:
        with open(路径, encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        raise RuntimeError(f"读不到 {路径}：{e}") from e
    except ValueError as e:
        raise RuntimeError(f"{路径} 不是合法 JSON：{e}") from e


def 写JSON(路径, 数据):
    try:
        with open(路径, "w", encoding="utf-8") as f:
            json.dump(数据, f, ensure_ascii=False, indent=1)
    except OSError as e:
        raise RuntimeError(f"写不了 {路径}：{e}") from e


def 写文本(路径, 文本):
    try:
        with open(路径, "w", encoding="utf-8") as f:
            f.write(文本)
    except OSError as e:
        raise RuntimeError(f"写不了 {路径}：{e}") from e


# ---------------- 取数 ----------------


def 取密钥():
    k = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DEEP_SEEK_API_KEY")
    if not k:
        raise RuntimeError("环境里没有 DEEPSEEK_API_KEY，取不到数就没法出图")
    return k


def 调模型(密钥, system, user):
    """真实调用。返回 (原文, 元信息)。"""
    body = {
        "model": 模型名,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 2000,
        "temperature": 0,
    }
    req = urllib.request.Request(
        接口,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {密钥}", "Content-Type": "application/json"},
    )
    开始 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=180) as r:  # noqa: S310 —— 常量 https 端点
            载荷 = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        详情 = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"上游返回 {e.code}：{详情}") from e
    except OSError as e:
        raise RuntimeError(f"连不上上游：{e}") from e

    try:
        用时 = int((time.time() - 开始) * 1000)
    except (TypeError, ValueError, OverflowError):
        用时 = -1

    try:
        d = json.loads(载荷)
    except ValueError as e:
        raise RuntimeError(f"上游返回的不是 JSON：{载荷[:300]}") from e
    try:
        回答 = d["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"上游返回里没有 choices[0].message.content：{载荷[:300]}") from e
    return 回答, {"模型": 模型名, "耗时毫秒": 用时, "用量": d.get("usage")}


def 取输入():
    """用 demo-01 的输入：它在 data/demo_samples.json 里已有真实的 LuCDA 结果，
    三栏用同一条输入才算公平对比。"""
    D = 读JSON(os.path.join(根目录, "data", "demo_samples.json"))
    for s in D.get("样例", []):
        if s.get("id") == "demo-01":
            return s["输入"]["内容"], s
    raise RuntimeError("data/demo_samples.json 里找不到 demo-01")


def 采集():
    原文, 样例 = 取输入()
    密钥 = 取密钥()
    结果 = {}
    for p in 路径说明[:2]:
        user = p["user模板"].replace("{原文}", 原文)
        print(f"  调用 {p['键']} …", flush=True)
        回答, 元 = 调模型(密钥, p["system"], user)
        结果[p["键"]] = {"system": p["system"], "user": user, "原始回答": 回答, **元}
        print(f"    返回 {len(回答)} 字，{元['耗时毫秒']} ms", flush=True)

    数据 = {
        "meta": {
            "用途": "M5 三方对标（→ 计划2 fig3_compare.png）",
            "形式": "同一条输入问三种方式，把三边真实返回并排摆出来；图上不下任何「谁更好」的结论",
            "输入来源": "data/demo_samples.json 的 demo-01（自建样例，语料加工未完成；不含真实个人信息）",
            "模型": 模型名,
            "上游": 接口,
            "温度": 0,
            "①②采集方式": "本脚本发起的真实 HTTP 调用，原文逐字保留，未做任何转述或润色",
            "③采集方式": "复用 demo-01 已产出的真实结果，未重算",
            "界面说明": "①②的界面是按通用对话产品的常见形态渲染的；内容为模型返回原文，一字未改",
        },
        "输入": 原文,
        "路径": [{"键": p["键"], "说明": p["说明"]} for p in 路径说明],
        "结果": 结果,
        "lucda": {"结果": 样例["结果"], "色块锚点": 样例.get("色块锚点")},
    }
    写JSON(数据文件, 数据)
    print(f"  已存 {数据文件}")
    return 数据


# ---------------- 渲染 ----------------


def esc0(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def 加粗(s):
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)


def 简易markdown(文本):
    """把模型返回的 markdown 渲染成 HTML。只处理粗体、列表、分段 —— 够用就行，
    不做完整解析器，也绝不改动任何文字内容。"""
    出 = []
    for 段 in re.split(r"\n\s*\n", str(文本).strip()):
        段 = 段.strip()
        if not 段:
            continue
        行 = [x for x in 段.split("\n") if x.strip()]
        有序 = bool(行) and all(re.match(r"^\s*\d+[.、)]", x) for x in 行)
        无序 = bool(行) and all(re.match(r"^\s*[-*•]\s", x) for x in 行)
        if 有序 or 无序:
            tag = "ol" if 有序 else "ul"
            出.append(f"<{tag}>")
            for x in 行:
                t = re.sub(r"^\s*(?:\d+[.、)]|[-*•])\s*", "", x)
                出.append(f"<li>{加粗(esc0(t))}</li>")
            出.append(f"</{tag}>")
        else:
            出.append(f"<p>{加粗(esc0(' '.join(行)))}</p>")
    return "".join(出)


def 找空端口():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def 起服务(目录):
    端口 = 找空端口()
    try:
        p = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(端口), "--bind", "127.0.0.1"],
            cwd=目录,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as e:
        raise RuntimeError(f"静态服务器起不来：{e}") from e
    return p, 端口


def 等就绪(端口, 子路径):
    地址 = f"http://127.0.0.1:{端口}/{子路径}"
    if not 地址.startswith("http://127.0.0.1:"):
        raise RuntimeError(f"探测地址不是本机 http，拒绝打开：{地址}")
    for _ in range(80):
        try:
            with urllib.request.urlopen(地址, timeout=1) as r:  # noqa: S310 —— scheme 已限定
                if r.status == 200:
                    return 地址
        except OSError:
            time.sleep(0.25)
    raise RuntimeError(f"静态服务器没起来：{地址}")


def 截_lucda():
    """截 LuCDA 真实界面（发布产物 docs/，与线上版本同一份代码）。"""
    from playwright.sync_api import sync_playwright

    服务, 端口 = 起服务(根目录)
    try:
        地址 = 等就绪(端口, "docs/index.html")
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=3)
            pg.goto(地址, wait_until="load")
            pg.wait_for_timeout(1800)
            pg.evaluate("() => window.LuCDA_UI.载入样例('demo-01','')")
            pg.wait_for_timeout(800)
            pg.evaluate(
                "() => { const t=document.querySelectorAll('.turn');"
                " t[t.length-1].scrollIntoView({block:'start'}); }"
            )
            pg.wait_for_timeout(400)
            目标 = os.path.join(临时, "lucda.png")
            pg.screenshot(path=目标)
            br.close()
        return 目标
    finally:
        服务.terminate()


CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 1780px; padding: 34px 34px 26px; background: #f4f6f8;
  font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
  color: #0f172a; }
h1 { font-size: 40px; font-weight: 800; letter-spacing: -0.01em; }
.lead { margin-top: 12px; font-size: 20px; line-height: 1.75; color: #475569; max-width: 1560px; }
.lead b { color: #0f172a; }
.row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 22px; margin-top: 26px; align-items: start; }
.col { background: #fff; border: 1px solid #e6ebf1; border-radius: 20px; overflow: hidden;
  box-shadow: 0 2px 8px rgba(15,23,42,.05); }
.col-head { padding: 16px 20px 14px; border-bottom: 1px solid #e6ebf1; background: #f8fafc; }
.col-title { font-size: 24px; font-weight: 800; }
.col-sub { margin-top: 6px; font-size: 16px; line-height: 1.6; color: #64748b; }
.chat { padding: 18px; height: 1210px; overflow: hidden; }
.msg { display: flex; margin-bottom: 14px; }
.msg.user { justify-content: flex-end; }
.bubble { max-width: 90%; padding: 12px 15px; border-radius: 16px; font-size: 17px;
  line-height: 1.78; word-break: break-word; }
.msg.user .bubble { background: #0d6e60; color: #fff; border-bottom-right-radius: 5px; }
.msg.bot .bubble { background: #f6f8fa; border: 1px solid #e6ebf1; border-bottom-left-radius: 5px; }
.av { flex: none; width: 30px; height: 30px; margin-right: 9px; border-radius: 999px;
  background: #dfe7ee; color: #475569; font-size: 13px; font-weight: 800;
  display: flex; align-items: center; justify-content: center; }
.md p { margin-bottom: 9px; }
.md ol, .md ul { margin: 0 0 9px 1.15em; }
.md li { margin-bottom: 5px; }
.md strong { font-weight: 800; }
.lucda-shot { display: block; width: 100%; height: 1210px; object-fit: cover; object-position: top; }
.lucda-fold { border-top: 1px solid #e6ebf1; padding: 14px 18px; background: #f8fafc; }
.lucda-fold .k { font-size: 13px; font-weight: 700; letter-spacing: .08em; color: #8a97a8; }
.lucda-fold .v { margin-top: 5px; font-size: 20px; line-height: 1.6; font-weight: 700; }
.bar { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 11px; }
.pill { padding: 5px 12px; border-radius: 999px; font-size: 15px; font-weight: 700;
  background: #fff; border: 1px solid #dde4ec; color: #475569; }
.foot { margin-top: 22px; font-size: 16px; line-height: 1.85; color: #64748b; }
.foot b { color: #0f172a; }
"""

模板 = (
    '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
    "<title>fig3</title><style>"
    + CSS
    + "</style></head><body>"
    + """
<h1>同一条输入，三种问法</h1>
<div class="lead">输入是同一句话。左边两栏是把它丢给<b>通用助手</b>与<b>事实核查助手</b>的真实返回；
第三栏是在 <b>LuCDA</b> 里问同一句话的真实结果。三栏都是原文，没有任何润色或转述 —— 差别在哪，读者自己看。</div>
<div class="row">
__COL_A__
__COL_B__
__COL_C__
</div>
<div class="foot">
<b>怎么读这张图。</b>左边两栏回答的是「这东西是不是诈骗 / 是不是真的」—— 要答准，得去查批号、查资质、
查医学资料，本质是外部数据库的活。LuCDA 那一栏不给这类结论，它只说这句话<b>正在对你做什么</b>
（哪几个杠杆、说到哪一步），并给出<b>你能照着说的</b>那一句。两条路不重叠。
<br>
<b>如实说明。</b>①②的界面按通用对话产品的常见形态渲染，内容为模型返回原文，一字未改；
第三栏是 LuCDA 发布产物的真实界面截图。输入为自建样例（语料加工未完成，不含真实个人信息）。
同一输入只跑了 1 例，样本量小，<b>不足以支撑任何统计结论</b>；完整原始返回见 assets/fig3_data.json。
图里不比较「哪个更好」：通用助手在语言流畅度与覆盖面上有优势，事实核查在可查事实上能给出
LuCDA 给不了的东西；LuCDA 的位置只是在「话术正在做什么」这一格。
</div>
</body></html>"""
)


def 一栏(键, 说明, 输入, 回答):
    return (
        '<div class="col"><div class="col-head">'
        f'<div class="col-title">{esc0(键)}</div><div class="col-sub">{esc0(说明)}</div></div>'
        '<div class="chat">'
        f'<div class="msg user"><div class="bubble">{esc0(输入)}</div></div>'
        f'<div class="msg bot"><div class="av">AI</div><div class="bubble md">{简易markdown(回答)}</div></div>'
        "</div></div>"
    )


def 拼图(数据, lucda_png):
    from playwright.sync_api import sync_playwright

    输入 = 数据["输入"]
    a = 数据["结果"]["① 直接问通用助手"]["原始回答"]
    b = 数据["结果"]["② 事实核查式提问"]["原始回答"]
    判定 = (数据.get("lucda") or {}).get("结果", {}).get("判定", {}) or {}
    风险 = 判定.get("风险", "")
    结论 = 判定.get("一句话", "")
    出口 = 判定.get("官方出口") or []

    药丸 = ""
    if 风险:
        药丸 += f'<span class="pill">风险 {esc0(风险)}</span>'
    for x in 出口:
        药丸 += f'<span class="pill">官方出口 {esc0(x)}</span>'

    栏C = (
        '<div class="col"><div class="col-head">'
        '<div class="col-title">③ 问 LuCDA</div>'
        '<div class="col-sub">只说话术在做什么、说到哪一步、该怎么说，不判断产品真假</div></div>'
        '<img class="lucda-shot" src="__LUC__" alt="LuCDA 界面">'
        '<div class="lucda-fold"><div class="k">界面里的结论行</div>'
        f'<div class="v">{esc0(结论)}</div><div class="bar">{药丸}</div></div></div>'
    )

    页 = (
        模板.replace("__COL_A__", 一栏("① 直接问通用助手", 路径说明[0]["说明"], 输入, a))
        .replace("__COL_B__", 一栏("② 事实核查式提问", 路径说明[1]["说明"], 输入, b))
        .replace("__COL_C__", 栏C)
        .replace("__LUC__", "file:///" + lucda_png.replace("\\", "/"))
    )

    h = os.path.join(临时, "fig3.html")
    写文本(h, 页)
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(viewport={"width": 1780, "height": 1200}, device_scale_factor=2)
        pg.goto("file:///" + h.replace("\\", "/"), wait_until="load")
        pg.wait_for_timeout(900)
        pg.screenshot(path=产物, full_page=True)
        br.close()
    return 产物


def main():
    try:
        os.makedirs(临时, exist_ok=True)
    except OSError as e:
        raise RuntimeError(f"建不了临时目录 {临时}：{e}") from e

    重取 = "--recollect" in sys.argv
    if 重取 or not os.path.exists(数据文件):
        print("取数（真实调用 DeepSeek）")
        数据 = 采集()
    else:
        print(f"用已有数据 {数据文件}")
        数据 = 读JSON(数据文件)

    print("截 LuCDA 界面 …", flush=True)
    shot = 截_lucda()
    print("拼图 …", flush=True)
    出 = 拼图(数据, shot)

    from PIL import Image

    im = Image.open(出)
    print(f"✓ 已生成 {出}")
    print(f"  尺寸 {im.size}  大小 {os.path.getsize(出) / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
