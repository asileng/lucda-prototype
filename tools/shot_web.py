"""tools/shot_web.py —— M4 前端自测（执行指令 §11 可判定项）

做什么
  1. 在 计划1/ 目录起一个本机静态服务器（python -m http.server），用 playwright chromium 打开 web/index.html；
  2. viewport 390x844（手机）；
  3. 截三张图：① 首屏  ② 带色块的回复 + 一句话结论  ③ 点开色块后的浮层；
  4. 顺手把关可判定的项量一遍并打印：首屏可见元素数、按钮高度、正文与行高、色块热区高度、
     结论字号、点 1 次出浮层、浮层关掉回到原处、全程是否换过 URL、控制台有没有报错、中文字体是否命中。

截图存到系统临时目录下的 lucda_m4_shots/（不写进 assets/，那是别的 lane 的目录）。

跑法
  D:/anaconda/miniconda3/python.exe tools/shot_web.py
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 计划1/
WEB = os.path.join(ROOT, "web")
临时目录 = os.path.join(tempfile.gettempdir(), "lucda_m4_shots")
结果 = {}  # 打印用的量测结果


def 找空端口():
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
        s.close()
        return p


def 起服务器(端口):
        try:
                p = subprocess.Popen(
                        [
                                sys.executable,
                                "-m",
                                "http.server",
                                str(端口),
                                "--bind",
                                "127.0.0.1",
                        ],
                        cwd=ROOT,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                )
        except OSError as e:
                raise RuntimeError("静态服务器起不来：" + str(e)) from e

        # 只探测本机 http，别把别的 scheme 交给 urlopen
        探测地址 = f"http://127.0.0.1:{端口}/web/index.html"
        if not 探测地址.startswith("http://127.0.0.1:"):
                raise RuntimeError("探测地址不是本机 http，拒绝打开：" + 探测地址)

        for _ in range(60):
                try:
                        with urllib.request.urlopen(探测地址, timeout=1) as r:  # noqa: S310 —— scheme 已在上方限定为本机 http
                                if r.status == 200:
                                        return p
                except Exception:
                        time.sleep(0.25)
        p.terminate()
        raise RuntimeError("静态服务器没起来")


# 页面里量一遍可判定的项，返回 JSON
量测脚本 = r"""
() => {
  const 可见 = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const st = getComputedStyle(el);
    return st.visibility !== 'hidden' && st.display !== 'none' && st.opacity !== '0';
  };
  const 矩形 = (el) => { const r = el.getBoundingClientRect(); return {w: Math.round(r.width), h: Math.round(r.height), top: Math.round(r.top)}; };
  const 首屏内 = (el) => { const r = el.getBoundingClientRect(); return r.top < window.innerHeight && r.bottom > 0; };

  const 控件 = [];
  document.querySelectorAll('button, textarea, input, select, a[href]').forEach((el) => {
    if (可见(el) && 首屏内(el)) 控件.push({
      文本: (el.textContent || el.placeholder || el.tagName).trim().slice(0, 18),
      类: el.className, 高: 矩形(el).h, id: el.id || ''
    });
  });

  const 种类 = { 输入口: false, 已发消息: false, AI回复: false, 色块: 0, 浮层: 可见(document.getElementById('overlay')) };
  种类.输入口 = 可见(document.getElementById('composer'));
  种类.已发消息 = !!document.querySelector('.sent');
  种类.AI回复 = !!document.querySelector('.reply');
  种类.色块 = document.querySelectorAll('.blk').length;

  const 正文 = document.querySelector('.sent-body') || document.querySelector('.blk-quote');
  const 结论 = document.querySelector('.conclusion');
  const 主按钮 = document.getElementById('micBtn');
  const 次按钮 = document.getElementById('camBtn');
  const 块 = document.querySelector('.blk');
  const 出口 = document.querySelector('.official');
  const 两行 = document.querySelectorAll('.notice p');

  const st = 正文 ? getComputedStyle(正文) : null;
  return {
    首屏可点控件: 控件,
    首屏可点控件数: 控件.length,
    元素种类: 种类,
    主按钮高: 主按钮 ? 矩形(主按钮).h : 0,
    次按钮高: 次按钮 ? 矩形(次按钮).h : 0,
    正文字号: st ? parseFloat(st.fontSize) : 0,
    正文行高比: st ? +(parseFloat(st.lineHeight) / parseFloat(st.fontSize)).toFixed(2) : 0,
    色块高: 块 ? 矩形(块).h : 0,
    色块竖条: 块 ? getComputedStyle(块).borderLeftWidth : '',
    结论字号: 结论 ? parseFloat(getComputedStyle(结论).fontSize) : 0,
    结论文字: 结论 ? 结论.textContent : '',
    色块数: 种类.色块,
    官方出口文字: 出口 ? 出口.textContent : '',
    小字行数: 两行.length,
    小字: Array.from(两行).map((p) => p.textContent),
    URL: location.href,
    文档宽度: document.documentElement.scrollWidth,
    视口宽度: window.innerWidth,
    字体: getComputedStyle(document.body).fontFamily,
  };
}
"""


def main():
        try:
                os.makedirs(临时目录, exist_ok=True)
        except OSError as e:
                raise RuntimeError("截图临时目录建不出来：" + str(e)) from e
        from playwright.sync_api import sync_playwright

        端口 = 找空端口()
        服务器 = 起服务器(端口)
        基础 = f"http://127.0.0.1:{端口}/web/index.html"
        控制台报错 = []
        页面错误 = []
        try:
                with sync_playwright() as pw:
                        br = pw.chromium.launch()
                        pg = br.new_page(
                                viewport={"width": 390, "height": 844},
                                device_scale_factor=2,
                        )
                        pg.on(
                                "console",
                                lambda m: (
                                        控制台报错.append(m.type + ": " + m.text)
                                        if m.type == "error"
                                        else None
                                ),
                        )
                        pg.on("pageerror", lambda e: 页面错误.append(str(e)))
                        pg.goto(基础, wait_until="load")
                        pg.wait_for_timeout(1200)  # 等 data/*.json 读完

                        结果["URL_首屏"] = pg.url

                        # ① 首屏
                        首屏 = pg.evaluate(量测脚本)
                        p1 = os.path.join(临时目录, "01_首屏.png")
                        pg.screenshot(path=p1)
                        结果["截图_首屏"] = p1

                        # ② 载入一条演示样例（红色 + 官方出口），出带色块的回复
                        pg.evaluate("() => window.LuCDA_UI.载入样例('demo-01', '')")
                        pg.wait_for_timeout(500)
                        p2 = os.path.join(临时目录, "02_回复与色块.png")
                        pg.screenshot(path=p2)
                        结果["截图_回复"] = p2
                        回复态 = pg.evaluate(量测脚本)

                        # 浮层开之前的正文位置。这里量的是「文档坐标」（top + scrollY），
                        # 不把 playwright 自己为了点得到色块而做的滚动算进去 ——
                        # 要验的是「不重排正文」，不是「测试脚本滚没滚」。
                        前 = pg.evaluate(
                                "() => { const r = document.querySelector('.reply').getBoundingClientRect(); return {文档top: Math.round(r.top + window.scrollY), h: Math.round(r.height), scroll: Math.round(window.scrollY)}; }"
                        )

                        # ③ 点一下色块 → 浮层，且 URL 不变
                        pg.click(".blk")
                        pg.wait_for_timeout(400)
                        # 「原处」的定义 = 浮层刚打开时的滚动位置
                        开时 = pg.evaluate(
                                "() => { const r = document.querySelector('.reply').getBoundingClientRect(); return {文档top: Math.round(r.top + window.scrollY), h: Math.round(r.height), scroll: Math.round(window.scrollY)}; }"
                        )
                        p3 = os.path.join(临时目录, "03_浮层.png")
                        pg.screenshot(path=p3)
                        结果["截图_浮层"] = p3
                        浮层态 = pg.evaluate(量测脚本)
                        结果["点1次出浮层"] = bool(浮层态["元素种类"]["浮层"])
                        结果["URL_点浮层后"] = pg.url
                        结果["浮层_kicker"] = pg.inner_text("#ovKicker")
                        结果["浮层_首屏节"] = pg.evaluate(
                                "() => Array.from(document.querySelectorAll('#ovBody .k')).map(x => x.textContent).slice(0, 8)"
                        )
                        结果["浮层_正文项"] = pg.evaluate(
                                "() => Array.from(document.querySelectorAll('#ovBody .v')).map(x => x.textContent.slice(0, 40)).slice(0, 6)"
                        )

                        # 关掉浮层 → 回原处
                        pg.click("#ovClose")
                        pg.wait_for_timeout(300)
                        后 = pg.evaluate(
                                "() => { const r = document.querySelector('.reply').getBoundingClientRect(); return {文档top: Math.round(r.top + window.scrollY), h: Math.round(r.height), scroll: Math.round(window.scrollY)}; }"
                        )
                        # 两件事都得成立：① 正文没被重排（文档坐标与高度不变）
                        #               ② 关掉后回到开之前的滚动位置（位置不丢）
                        结果["关掉回原处"] = (
                                前["文档top"] == 后["文档top"]
                                and 前["h"] == 后["h"]
                                and 开时["scroll"] == 后["scroll"]
                        )
                        结果["关掉前后"] = {"开之前": 前, "开时": 开时, "关掉后": 后}
                        结果["浮层已关"] = not 浮层态["元素种类"][
                                "浮层"
                        ] and pg.evaluate(
                                "() => document.getElementById('overlay').hidden"
                        )

                        # 绿色样例：正常说法对照 + 未发现操纵特征
                        # （只量最后一轮 —— 前面几条还在页面上，不加限定会量到第一条）
                        pg.evaluate("() => window.LuCDA_UI.载入样例('demo-03', '')")
                        pg.wait_for_timeout(400)
                        绿 = pg.evaluate(
                                "() => { const a = document.querySelectorAll('.turn'); const t = a[a.length-1]; const n = t.querySelector('.normal'); const c = t.querySelector('.conclusion'); return {normal: n ? n.textContent : '', 结论: c ? c.textContent : ''}; }"
                        )
                        结果["绿色档"] = 绿

                        # 语音样例：不伪造实时结果
                        pg.evaluate("() => window.LuCDA_UI.载入样例('demo-05', '')")
                        pg.wait_for_timeout(400)
                        语 = pg.evaluate(
                                "() => { const a = document.querySelectorAll('.turn'); const t = a[a.length-1]; const g = t.querySelector('.sample-tag'); const k = t.querySelector('.sent-kicker'); return {样例标识: g ? g.textContent.slice(0, 80) : '', 输入标签: k ? k.textContent : ''}; }"
                        )
                        结果["语音样例"] = 语

                        # 依据查询（本地检索，不上向量库）
                        pg.evaluate(
                                "() => window.LuCDA_UI.发送文字('最后三盒这种话术有什么研究')"
                        )
                        pg.wait_for_timeout(400)
                        查 = pg.evaluate(
                                "() => { const c = document.querySelectorAll('.conclusion'); const last = c[c.length-1]; const n = document.querySelectorAll('.note'); return {结论: last ? last.textContent : '', 提示: n.length ? n[n.length-1].textContent.slice(0, 60) : ''}; }"
                        )
                        结果["依据查询"] = 查
                        p4 = os.path.join(临时目录, "04_依据查询.png")
                        pg.screenshot(path=p4)
                        结果["截图_依据查询"] = p4

                        # 禁忌扫描自检：拿三条本来就该被拦下的文字过一遍扫描器
                        扫 = pg.evaluate(
                                """() => {
                  const f = window.LuCDA_UI.扫描;
                  const 用例 = [
                    ['你被骗了，别再买了。', {用户:'老人本人', 对抗者:'推销员（面谈）'}],
                    ['我早就跟你说过那人靠不住。', {用户:'子女', 对抗者:'父母'}],
                    ['你必须现在就把钱要回来。', {用户:'老人本人', 对抗者:'推销员（面谈）'}]
                  ];
                  return 用例.map(([t, c]) => {
                    // 前端调用前会把契约取值归一到 §5.3 的用词，这里照同一条路走
                    const u = {'老人本人':'老人','子女':'子女','社区工作者':'社区工作者','当事人':'当事人'}[c.用户] || '';
                    const o = {'推销员（面谈）':'推销员','推销员（电话）':'推销员','广告':'广告','亲友':'父母','亲友即推销者':'父母','自己':'自己','平台客服':'平台','老人群体':'老人（群体）'}[c.对抗者] || '';
                    const r = window.LuCDA.taboo.enforce(t, {用户: u, 对抗者: o});
                    return {文本: t, 状态: r.状态, 命中: (r.命中 || []).map(h => h.规则)};
                  });
                }"""
                        )
                        结果["禁忌扫描用例"] = 扫
                        结果["禁忌扫描记录条数"] = pg.evaluate(
                                "() => window.LuCDA_UI.状态.scanLog.length"
                        )

                        # ===== ⑤ 全样例逐条核验（§8 / §9 / §11 硬项） =====
                        # 每条样例：自己渲染成一轮，量它的色块、三种输出形态、官方出口行、绿色对照。
                        样例清单 = pg.evaluate(
                                "() => window.LuCDA_UI.状态.samples.样例.map((s) => ({id: s.id, 模态: s.输入.模态, 风险: s.结果.判定.风险}))"
                        )
                        逐条 = []
                        for 样 in 样例清单:
                                逐条.append(
                                        pg.evaluate(
                                                """(id) => {
                    const U = window.LuCDA_UI;
                    U.载入样例(id, '');
                    const a = document.querySelectorAll('.turn');
                    const t = a[a.length - 1];
                    const 文 = (sel) => { const e = t.querySelector(sel); return e ? e.textContent : null; };
                    const 数 = (sel) => t.querySelectorAll(sel).length;
                    const 色 = (b) => { const m = /blk--(红|黄|绿|中性)/.exec(b.className); return m ? m[1] : ''; };
                    return {
                      id: id,
                      色块数: 数('.blk'),
                      色块颜色: Array.from(t.querySelectorAll('.blk')).map(色),
                      结论: 文('.conclusion'),
                      正常说法: 文('.normal'),
                      官方出口: 文('.official'),
                      小字行数: 数('.notice p'),
                      说话人提示: !!t.querySelector('.warn'),
                      纠错按钮: Array.from(t.querySelectorAll('.warn .choice')).map((b) => b.textContent),
                      问题数: 数('.q-item'),
                      问题挂接: Array.from(t.querySelectorAll('.q-item')).map((b) => b.querySelectorAll('.q-follow').length),
                      脚本段数: 数('.script-seg'),
                      一句话: Array.from(t.querySelectorAll('.one-body')).map((e) => e.textContent),
                      禁忌块: 文('.forbid'),
                      自查块: 文('.selfcheck'),
                    };
                  }""",
                                                样["id"],
                                        )
                                )
                        结果["全样例逐条"] = 逐条

                        # 浮层随模式变 + 色块 ≤2 次点击到 理论 → 文献 → 语料例证 + 只开一个浮层
                        浮层扫描 = {}
                        for 号 in ["demo-01", "demo-02", "demo-06", "demo-07"]:
                                浮层扫描[号] = pg.evaluate(
                                        """(id) => {
                    const U = window.LuCDA_UI;
                    U.载入样例(id, '');
                    const a = document.querySelectorAll('.turn');
                    const t = a[a.length - 1];
                    const bs = Array.from(t.querySelectorAll('.blk'));
                    const 出 = [];
                    for (let i = 0; i < bs.length; i++) {
                      bs[i].click();                       // 第 1 次点击：色块 → 浮层
                      const 第1 = {
                        kicker: document.getElementById('ovKicker').textContent,
                        k: Array.from(document.querySelectorAll('#ovBody .k')).map((e) => e.textContent),
                        问自己一句: !!document.querySelector('#ovBody .ask-self'),
                        选单: Array.from(document.querySelectorAll('#ovBody .choice')).map((e) => e.textContent),
                        隐藏浮层数: document.querySelectorAll('#overlay:not([hidden])').length,
                        面板数: document.querySelectorAll('.ov-panel').length,
                      };
                      // 第 2 次点击：展开「依据」→ 理论 / 文献 / 语料例证 三层
                      const det = document.querySelector('#ovBody .evidence');
                      if (det) det.open = true;
                      第1.依据层 = Array.from(document.querySelectorAll('#ovBody .ev-l')).map((e) => e.textContent);
                      第1.文献按钮数 = document.querySelectorAll('#ovBody .ev-link').length;
                      第1.语料有内容 = /L3-/.test((document.querySelector('#ovBody .ev-body') || {}).textContent || '');
                      出.push(第1);
                      document.getElementById('ovClose').click();
                    }
                    // 只开一个：连点两个色块，面板数不能变成 2
                    if (bs.length > 1) {
                      bs[0].click();
                      bs[1].click();
                      出.push({
                        kicker: document.getElementById('ovKicker').textContent,
                        连点后面板数: document.querySelectorAll('.ov-panel').length,
                        连点后浮层数: document.querySelectorAll('#overlay:not([hidden])').length,
                      });
                      document.getElementById('ovClose').click();
                    }
                    return 出;
                  }""",
                                        号,
                                )
                        结果["浮层扫描"] = 浮层扫描

                        # 现场档：点一条问题 → 浮层四项（§8.5、§9.5）
                        pg.evaluate("() => window.LuCDA_UI.载入样例('demo-06', '')")
                        pg.wait_for_timeout(200)
                        现场 = pg.evaluate(
                                """() => {
                  const a = document.querySelectorAll('.turn');
                  const t = a[a.length - 1];
                  const q = t.querySelector('.q-item');
                  if (!q) return null;
                  q.click();
                  return {
                    kicker: document.getElementById('ovKicker').textContent,
                    k: Array.from(document.querySelectorAll('#ovBody .k')).map((e) => e.textContent),
                    v: Array.from(document.querySelectorAll('#ovBody .v')).map((e) => e.textContent.slice(0, 40)),
                  };
                }"""
                        )
                        结果["现场档浮层"] = 现场
                        pg.evaluate("() => document.getElementById('ovClose').click()")

                        # 说话人置信度低：在内存里把一份样例的置信度改成「低」，验显著提示 + 一键纠正
                        # （不落盘、不改 data/；只是把真实渲染路径跑一遍）
                        置信 = pg.evaluate(
                                """() => {
                  const U = window.LuCDA_UI;
                  const s = (U.状态.samples.样例 || []).filter((x) => x.id === 'demo-02')[0];
                  if (!s) return null;
                  const 原 = s.结果.判定.说话人置信度;
                  s.结果.判定.说话人置信度 = '低';
                  U.载入样例('demo-02', '');
                  const a = document.querySelectorAll('.turn');
                  const t = a[a.length - 1];
                  const w = t.querySelector('.warn');
                  const 按钮 = Array.from(t.querySelectorAll('.warn .choice')).map((b) => b.textContent);
                  const 提示 = w ? w.textContent.slice(0, 120) : '';
                  let 改后 = '';
                  if (w && w.querySelector('.choice')) {
                    w.querySelector('.choice').click();     // 一键纠正
                    const a2 = document.querySelectorAll('.turn');
                    const t2 = a2[a2.length - 1];
                    改后 = (t2.querySelector('.note') || {}).textContent || '';
                  }
                  s.结果.判定.说话人置信度 = 原;   // 复原
                  return {提示: 提示, 按钮: 按钮, 改后: 改后};
                }"""
                        )
                        结果["置信度低注入"] = 置信
                        pg.evaluate("() => document.getElementById('ovClose').click()")

                        # 语音入口：不给转写结果，只给诚实说明
                        语音 = pg.evaluate(
                                """() => {
                  const U = window.LuCDA_UI;
                  const 前 = U.状态.turns.length;
                  document.getElementById('micBtn').click();
                  const n = document.getElementById('composerNote');
                  return {
                    之前轮数: 前,
                    之后轮数: U.状态.turns.length,
                    提示: n && !n.hidden ? n.textContent : '',
                  };
                }"""
                        )
                        结果["语音入口"] = 语音

                        # 非聊天产品：不许有会话列表 / 头像 / 正在输入
                        聊天特征 = pg.evaluate(
                                """() => {
                  const 正文 = document.body.innerText;
                  return {
                    头像节点: document.querySelectorAll('.avatar, .bubble, .chat-head').length,
                    会话列表: document.querySelectorAll('.chat-list, .session-list, .conv-list').length,
                    正在输入: /正在输入|键入中|正在回复/.test(正文),
                  };
                }"""
                        )
                        结果["聊天特征"] = 聊天特征

                        # TTS：把 speechSynthesis.speak 换成计数器，点一下朗读看是不是真调了
                        TTS = pg.evaluate(
                                """() => {
                  const U = window.LuCDA_UI;
                  window.__lucda读了几次 = 0;
                  window.__lucda读的文 = '';
                  const sp = window.speechSynthesis;
                  if (sp) {
                    sp.speak = (u) => { window.__lucda读了几次++; window.__lucda读的文 = String(u && u.text); };
                  }
                  U.朗读('测试朗读。');
                  return {
                    有朗读接口: !!sp,
                    调用次数: window.__lucda读了几次,
                    读的文: window.__lucda读的文.slice(0, 30),
                  };
                }"""
                        )
                        结果["TTS"] = TTS

                        # 页面全文：不合规的推荐 / 可以买暗示 / 禁用词
                        全文 = pg.evaluate("() => document.body.innerText")
                        同类工具 = [
                                "国家反诈中心",
                                "反诈APP",
                                "腾讯手机管家",
                                "360卫士",
                                "猎豹",
                                "百度卫士",
                                "第三方工具",
                                "下载安装",
                                "推荐使用",
                        ]
                        结果["同类工具命中"] = [x for x in 同类工具 if x in 全文]
                        可以买暗示 = [
                                "可以买",
                                "放心买",
                                "推荐购买",
                                "值得买",
                                "买就对了",
                                "赶紧买",
                        ]
                        结果["可以买暗示命中"] = [x for x in 可以买暗示 if x in 全文]
                        禁用词 = [
                                "旨在",
                                "赋能",
                                "助力",
                                "深度融合",
                                "全方位",
                                "具有重要意义",
                                "打造",
                                "有效提升",
                                "不仅",
                                "我们",
                                "国内首个",
                                "填补空白",
                                "最强",
                                "最准",
                                "最权威",
                                "国家级",
                                "独家",
                                "权威AI",
                                "100%",
                                "绝对",
                                "保证",
                                "一定",
                                "肯定",
                        ]
                        结果["禁用词命中"] = [x for x in 禁用词 if x in 全文]
                        结果["页面全文长度"] = len(全文)

                        结果["首屏量测"] = 首屏
                        结果["回复量测"] = 回复态
                        结果["控制台报错"] = 控制台报错
                        结果["页面异常"] = 页面错误
                        br.close()
        finally:
                服务器.terminate()

        # ===== 判定 =====
        判定 = {}
        判定["首屏可点控件 ≤4"] = 首屏["首屏可点控件数"] <= 4
        判定["主按钮高 ≥88"] = 回复态["主按钮高"] >= 88
        判定["次按钮高 ≥64"] = 回复态["次按钮高"] >= 64
        判定["正文字号 ≥24"] = 回复态["正文字号"] >= 24
        判定["正文行高比 ≥1.8"] = 回复态["正文行高比"] >= 1.8
        判定["色块热区高 ≥64"] = 回复态["色块高"] >= 64
        判定["色块左侧竖条 4px"] = 回复态["色块竖条"] == "4px"
        判定["结论字号 ≥28"] = 回复态["结论字号"] >= 28
        判定["点 1 次出浮层"] = bool(结果["点1次出浮层"])
        判定["全程不换 URL"] = 结果["URL_首屏"] == 结果["URL_点浮层后"]
        判定["关掉浮层回到原处"] = bool(
                结果["关掉回原处"]
        )  # 正文不重排 + 滚动回位，见上方 前/开时/后
        判定["高风险有官方出口行"] = ("12315" in 结果["回复量测"]["官方出口文字"]) or (
                "96110" in 结果["回复量测"]["官方出口文字"]
        )
        判定["回复底部两行小字"] = 结果["回复量测"]["小字行数"] == 2
        判定["绿色给正常说法对照"] = "正常说法" in 结果["绿色档"]["normal"]
        判定["依据查询出文献与例证"] = "找到" in 结果["依据查询"]["结论"]
        判定["禁忌扫描 3 条全命中"] = all(x["命中"] for x in 结果["禁忌扫描用例"])
        判定["控制台无报错"] = len(控制台报错) == 0 and len(页面错误) == 0
        判定["无横向溢出"] = 回复态["文档宽度"] <= 回复态["视口宽度"]
        结果["判定"] = 判定

        输出 = {
                "截图目录": 临时目录,
                "判定": 判定,
                "量测": {
                        "首屏可点控件": 首屏["首屏可点控件"],
                        "回复态": {
                                k: 回复态[k]
                                for k in [
                                        "主按钮高",
                                        "次按钮高",
                                        "正文字号",
                                        "正文行高比",
                                        "色块高",
                                        "色块竖条",
                                        "结论字号",
                                        "色块数",
                                        "小字",
                                        "字体",
                                ]
                        },
                        "绿色档": 结果["绿色档"],
                        "关掉前后": 结果["关掉前后"],
                        "语音样例": 结果["语音样例"],
                        "依据查询": 结果["依据查询"],
                        "禁忌扫描用例": 结果["禁忌扫描用例"],
                        "禁忌扫描记录条数": 结果["禁忌扫描记录条数"],
                        "控制台报错": 控制台报错,
                        "页面异常": 页面错误,
                },
        }
        print(json.dumps(输出, ensure_ascii=False, indent=1))
        if not all(判定.values()):
                print(
                        "\n未通过的项："
                        + "、".join([k for k, v in 判定.items() if not v])
                )
                return 1
        print("\n全部判定通过。截图见：" + 临时目录)
        return 0


if __name__ == "__main__":
        sys.exit(main())
