"""Fig.2 原型配图：LuCDA 网页在手机浏览器里的实际样子。

对应交付：assets/fig2_prototype.png（GOAL §9；计划2 的 D2 展板会直接用）

只放截图本身，不放二维码、不放访问地址、不放说明段 —— 图上多余的元信息
读者不会看，展板自己有图注。

三屏取同一个界面的三个状态：
  ① 首屏（老人档：可见元素 ≤4）
  ② 带色块的回复 + 一句话结论
  ③ 点开色块后的浮层（覆盖在原界面上，没有跳页）

截图取自发布产物 docs/（与线上版本同一份代码），用本机静态服务器打开，不依赖外网。

用法：python tools/make_fig2.py
"""

import os
import socket
import subprocess
import sys
import time
import urllib.request

from PIL import Image, ImageDraw, ImageFont

根目录 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
产物 = os.path.join(根目录, "assets", "fig2_prototype.png")
临时 = os.path.join(os.environ.get("TEMP", "."), "lucda_fig2")

字体常规 = "C:/Windows/Fonts/msyh.ttc"

屏高 = 1700  # 每台手机在图里的高度
边距 = 40
间隔 = 34


def 找空端口():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def 起服务(端口):
    try:
        p = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(端口), "--bind", "127.0.0.1"],
            cwd=根目录,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as e:
        raise RuntimeError(f"静态服务器起不来：{e}") from e
    return p


def 等就绪(端口):
    地址 = f"http://127.0.0.1:{端口}/docs/index.html"
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


def 截三屏(地址):
    from playwright.sync_api import sync_playwright

    try:
        os.makedirs(临时, exist_ok=True)
    except OSError as e:
        raise RuntimeError(f"建不了临时目录 {临时}：{e}") from e

    出 = {}
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=3)
        pg.goto(地址, wait_until="load")
        pg.wait_for_timeout(1800)

        # ① 首屏
        p1 = os.path.join(临时, "01.png")
        pg.screenshot(path=p1)
        出["首屏"] = p1

        # ② 带色块的回复 + 一句话结论
        pg.evaluate("() => window.LuCDA_UI.载入样例('demo-01','')")
        pg.wait_for_timeout(800)
        pg.evaluate(
            "() => { const t=document.querySelectorAll('.turn');"
            " t[t.length-1].scrollIntoView({block:'start'}); }"
        )
        pg.wait_for_timeout(400)
        p2 = os.path.join(临时, "02.png")
        pg.screenshot(path=p2)
        出["回复"] = p2

        # ③ 点开色块后的浮层
        pg.evaluate("() => document.querySelectorAll('.blk')[0].click()")
        pg.wait_for_timeout(700)
        p3 = os.path.join(临时, "03.png")
        pg.screenshot(path=p3)
        出["浮层"] = p3

        br.close()
    return 出


标签 = {"首屏": "首屏", "回复": "带色块的回复与结论", "浮层": "点色块出浮层，不跳页"}


def 拼版(截图):
    手机 = []
    for k in ["首屏", "回复", "浮层"]:
        im = Image.open(截图[k]).convert("RGB")
        try:
            宽 = int(im.size[0] * 屏高 / im.size[1])
        except (TypeError, ValueError, ZeroDivisionError) as e:
            raise RuntimeError(f"{k} 截图尺寸异常 {im.size}：{e}") from e
        手机.append(im.resize((宽, 屏高), Image.Resampling.LANCZOS))

    宽 = [m.size[0] for m in 手机]
    标签区 = 74
    总宽 = 边距 * 2 + sum(宽) + 间隔 * (len(手机) - 1)
    总高 = 边距 * 2 + 屏高 + 标签区

    画布 = Image.new("RGB", (总宽, 总高), "#ffffff")
    d = ImageDraw.Draw(画布)
    f = ImageFont.truetype(字体常规, 30)

    x = 边距
    y = 边距
    for i, m in enumerate(手机):
        画布.paste(m, (x, y))
        d.rounded_rectangle(
            [x, y, x + m.size[0] - 1, y + m.size[1] - 1],
            radius=16,
            outline="#d8dee6",
            width=2,
        )
        t = 标签[["首屏", "回复", "浮层"][i]]
        tw = d.textlength(t, font=f)
        d.text(
            (x + (m.size[0] - tw) / 2, y + 屏高 + 18),
            t,
            font=f,
            fill="#3f4753",
        )
        x += m.size[0] + 间隔

    画布.save(产物, dpi=(300, 300))
    return 产物


def main():
    if not os.path.exists(os.path.join(根目录, "docs", "index.html")):
        raise RuntimeError("docs/index.html 不存在，先跑 node tools/build_site.mjs")

    端口 = 找空端口()
    服务 = 起服务(端口)
    try:
        地址 = 等就绪(端口)
        截图 = 截三屏(地址)
    finally:
        服务.terminate()

    出 = 拼版(截图)
    im = Image.open(出)
    print(f"✓ 已生成 {出}")
    print(f"  尺寸 {im.size}  dpi {im.info.get('dpi')}  大小 {os.path.getsize(出) / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
