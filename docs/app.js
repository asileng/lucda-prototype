/* web/app.js — LuCDA 唯一界面（执行指令 §8 + §9）
 *
 * 全产品只有一个界面，只有三块：
 *   ① 发出去的东西  ② AI 的回复（带色块，点开是浮层）  ③ 输入口（唯一的行动点）
 * 交互只有一件事：发东西给它。不做会话列表、不做头像气泡、不做「正在输入」。
 *
 * 规格落点（每一处都写明依据，溯源不出的一律不写）：
 *   §8.1  唯一界面 / 色块只编码风险 / 结论行 / 场景参数从用户说的话推断
 *   §8.2  P9 原位展开：浮层覆盖，不跳页、不挤压、只开一个、点空白或左上角关闭
 *   §8.3  老人档：不出现场景选择；浮层极简；结论与浮层可朗读
 *   §8.4  家属档：只在推断不出对抗者时问一次，系统先猜一个并高亮
 *   §8.5  现场档：单屏、超大字、输出为问题清单
 *   §8.6  离线演示模式：读 data/demo_samples.json，外观一致，断网可用
 *   §9.1  A 对质：6 个问题按序，挂「他可能怎么答」→「你再问」
 *   §9.2  B 帮劝：脚本分段 + 禁忌提示（第 ⑥ 栏必出）
 *   §9.3  C 自护：一句话 + 一个动作
 *   §9.4  绿色：主动输出「未发现操纵特征」+ 正常说法对照
 *   §9.5  浮层内容 = f(锚点类型, 用户, 对抗者)；点中「我自己的话」多一个模块
 *   §9.6  自我诊断：已生效的杠杆 / 被说到哪一步 / 给你一句
 *   §5.5  每一段输出在显示前过一遍禁忌扫描；命中的重写，重写不出就降级并记录
 *   §7.6  说话人置信度低 → 显著提示 + 一键纠正，不允许静默错判
 *   §6.7  依据三层；主动查询走本地检索 data/rag_index.json，不上向量库
 */
(() => {
  /* ================= 0. 配置与常量 ================= */

  var CFG = Object.assign({ API_BASE: "" }, window.LUCDA_CONFIG || {});
  var 出口地址 = String(CFG.API_BASE || "").trim();
  var 离线 = !出口地址;

  /* 图片演示样例的本地路径（data/demo_samples.json 的 demo-04 指向 worker/test_image.png）。
     载入失败时如实提示，不拿别的东西冒充。 */
  var 演示图片路径 = "../worker/test_image.png";

  /* 「问自己一句」的原话来自执行指令 §9.5 与 §9.6，不是自拟。 */
  var 自问句 = "如果他不卖东西，还会这样对我吗？";

  /* 契约字段 用户/对抗者 是 §4.2/§4.3 的取值；禁忌库生效条件用的是 §5.3 的用词。
     两套词不同，调用前按本表归一（§5.3 口径），否则组合禁忌会漏判。 */
  var 用户归一 = {
    老人本人: "老人",
    子女: "子女",
    社区工作者: "社区工作者",
    当事人: "当事人",
  };
  var 对抗者归一 = {
    "推销员（面谈）": "推销员",
    "推销员（电话）": "推销员",
    推销员: "推销员",
    广告: "广告",
    亲友: "父母",
    亲友即推销者: "父母",
    自己: "自己",
    平台客服: "平台",
    老人群体: "老人（群体）",
  };

  /* 三层各自回答什么（§6.1 原话缩短），色块里只用这个，不用杠杆名。 */
  var 层短名 = {
    事件层: "他在做什么",
    话语层: "话是怎么说的",
    说服杠杆层: "凭什么让你信",
  };

  /* 话语维度 → 理论层条目（data/rag_index.json 的 id）。 */
  var 维度理论 = {
    三维框架: "L1-three-dim",
    预设: "L1-presupposition",
    信息确定性: "L1-certainty",
    情绪引导: "L1-emotion",
  };
  var 杠杆理论 = "L1-six-levers";
  var 归属理论 = "L1-attribution";

  /* §8.4 的四个选项 → 一句用户自己的话（照 §8.1 推断表的例子写，组成一条可分析的新输入）。 */
  var 对抗者选项 = [
    {
      名: "推销员",
      词: ["推销", "卖", "上门", "店里", "电话", "催我", "让我买", "跟我说话"],
      句: "我要怎么跟他说",
    },
    {
      名: "广告",
      词: [
        "广告",
        "直播",
        "电视上",
        "包装",
        "传单",
        "海报",
        "视频里",
        "朋友圈",
      ],
      句: "这是广告上的话，没人跟我说话",
    },
    {
      名: "爸妈或亲友",
      词: [
        "爸妈",
        "我妈",
        "我爸",
        "爸妈",
        "亲戚",
        "朋友",
        "邻居",
        "家人",
        "子女",
      ],
      句: "我爸妈不信我",
    },
    {
      名: "我自己",
      词: ["我买了", "我投了", "我自己", "我信", "我吃过", "我已经付"],
      句: "我已经买了",
    },
  ];

  /* ================= 1. 状态 ================= */

  var S = {
    rag: null, // data/rag_index.json
    samples: null, // data/demo_samples.json
    turns: [], // 本页的轮次（发出去的东西 + 回复）
    corrections: [], // 说话人一键纠正：[{句子, 说话人}]
    scanLog: [], // 禁忌扫描记录（§5.5「并记录」）
    asked: false, // §8.4 只问一次
    dev: /(^|[?&])dev=1(&|$)/.test(location.search),
    busy: false,
    overlayTurn: null, // 当前浮层属于哪个轮次
    overlayKey: null,
  };

  /* ================= 2. DOM 小工具 ================= */

  function $(id) {
    return document.getElementById(id);
  }
  function h(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }
  function 加(父, 子) {
    if (子) 父.appendChild(子);
    return 父;
  }
  function 空(节点) {
    while (节点.firstChild) 节点.removeChild(节点.firstChild);
    return 节点;
  }

  var feed = $("feed");
  var overlay = $("overlay");
  var ovBody = $("ovBody");
  var ovKicker = $("ovKicker");
  var composerNote = $("composerNote");
  var pasteArea = $("pasteArea");
  var pasteInput = $("pasteInput");

  /* ================= 3. 禁忌扫描（§5.5） ================= */

  /* 每一段准备送达用户的叙述文字都过这里。扫不通就返回 null，调用方不许把这段显示出去。
     引文（色块里的原话）不扫——那是把用户的话原样引回去，口径同 data/demo_samples.json 的说明。
     策略.禁忌 也不扫——那一栏按设计就写着「绝不能说」的字面串（同口径）。 */
  function 扫描(text, ctx, 字段) {
    var s = text === null || text === undefined ? "" : String(text);
    if (!s.trim()) return s;
    var T = window.LuCDA && window.LuCDA.taboo;
    if (!T || typeof T.enforce !== "function") {
      S.scanLog.push({ 字段: 字段, 状态: "扫描器不可用", 原文: s });
      return s;
    }
    var r;
    try {
      r = T.enforce(s, { 用户: ctx.用户 || "", 对抗者: ctx.对抗者 || "" });
    } catch (e) {
      S.scanLog.push({
        字段: 字段,
        状态: "扫描报错",
        原文: s,
        错误: String((e && e.message) || e),
      });
      return s;
    }
    if (r.状态 === "降级为空" || r.状态 === "降级失败") {
      S.scanLog.push({
        字段: 字段,
        状态: r.状态,
        原文: s,
        命中: (r.命中 || []).map((x) => x.规则),
      });
      return null;
    }
    if (r.状态 !== "放行") {
      S.scanLog.push({
        字段: 字段,
        状态: r.状态,
        原文: s,
        重写后: r.文本,
        动作: (r.记录 || []).map((x) => x.动作 + " · " + (x.规则 || "")),
      });
    }
    return r.文本;
  }

  function 上下文(结果) {
    var u = 结果 && 结果.策略 ? 结果.策略.用户 : "";
    var o = 结果 && 结果.策略 ? 结果.策略.对抗者 : "";
    return { 用户: 用户归一[u] || "", 对抗者: 对抗者归一[o] || "" };
  }

  /* ================= 4. 依据（§6.7 / §9.5） ================= */

  function 取理论(id) {
    if (!S.rag || !id) return null;
    return (S.rag.理论层 || []).filter((x) => x.id === id)[0] || null;
  }
  function 取文献(id) {
    if (!S.rag || !id) return null;
    return (S.rag.文献层 || []).filter((x) => x.id === id)[0] || null;
  }
  function 取语料(id) {
    if (!S.rag || !id) return null;
    return (S.rag.语料层 || []).filter((x) => x.id === id)[0] || null;
  }

  /* 溯源[].文献 可能是字符串，也可能是 {标题,作者,年份,索引ID} 数组。 */
  function 文献列表(结果, 断言) {
    var 出 = [];
    (结果.溯源 || []).forEach((s) => {
      if (
        断言 &&
        s.断言 &&
        s.断言.indexOf(断言) === -1 &&
        断言.indexOf(s.断言) === -1
      )
        return;
      var lits = s.文献;
      if (typeof lits === "string") 出.push({ 标题: lits, 索引ID: "" });
      else if (Array.isArray(lits)) {
        lits.forEach((l) => {
          if (l && (l.标题 || l.索引ID))
            出.push({
              标题: l.标题 || "",
              作者: l.作者 || "",
              年份: l.年份 || "",
              索引ID: l.索引ID || "",
            });
        });
      }
    });
    var 去重 = [];
    出.forEach((x) => {
      var k = x.索引ID || x.标题;
      if (k && !去重.some((y) => (y.索引ID || y.标题) === k)) 去重.push(x);
    });
    return 去重;
  }

  /* 依据块：理论 → 文献 → 语料例证，三层都从 data/rag_index.json 里取，取不到就说取不到。 */
  function 依据块(锚, 结果, 折叠) {
    var 理论id = "";
    var 语料id = "";
    var 断言 = "";

    if (锚.层 === "说服杠杆层") {
      理论id = 锚.归属 === "已对我生效" ? 归属理论 : 杠杆理论;
      断言 = 锚.杠杆;
    } else if (锚.层 === "话语层") {
      理论id = 维度理论[锚.维度] || "";
      断言 = 锚.维度;
    } else {
      理论id = "L1-three-dim";
      断言 = "";
    }

    (结果.溯源 || []).forEach((s) => {
      if (
        !语料id &&
        s.语料例证 &&
        断言 &&
        s.断言 &&
        s.断言.indexOf(断言) !== -1
      )
        语料id = s.语料例证;
    });
    if (!语料id) {
      (结果.溯源 || []).forEach((s) => {
        if (!语料id && s.语料例证 && String(s.语料例证).startsWith("L3-"))
          语料id = s.语料例证;
      });
    }

    var t = 取理论(理论id);
    var lits = 文献列表(结果, 断言);
    if (!lits.length) {
      (结果.溯源 || []).forEach((s) => {
        if (lits.length) return;
        var ls = s.文献;
        if (typeof ls === "string") lits.push({ 标题: ls, 索引ID: "" });
        else if (Array.isArray(ls))
          ls.forEach((l) => {
            if (l && l.标题) lits.push(l);
          });
      });
    }
    var c = 取语料(语料id);

    var wrap = h("div", "evidence");
    var det = document.createElement("details");
    var sum = document.createElement("summary");
    加(sum, h("span", null, "依据 ▸ 理论 · 文献 · 语料例证"));
    det.appendChild(sum);
    var body = h("div", "ev-body");

    if (t) {
      加(body, h("div", "ev-l", "理论"));
      加(body, h("div", "ev-t", t.id + "｜" + t.名称 + "："));
      加(body, h("div", "ev-src", t.一句话));
      加(body, h("div", "ev-src", "来源：" + t.来源));
      加(body, h("div", "ev-src", "可核实性：" + t.可核实性));
    } else {
      加(
        body,
        h("div", "ev-src", "这条没有对得上的理论层条目。索引里没有，就不写。"),
      );
    }

    加(body, h("div", "ev-l", "文献"));
    if (lits.length) {
      lits.forEach((l) => {
        var btn = h("button", "ev-link", "打开出处：" + (l.标题 || l.索引ID));
        btn.type = "button";
        btn.addEventListener("click", () => {
          打开文献浮层(l);
        });
        var row = h(
          "div",
          "ev-t",
          [l.标题, l.作者, l.年份].filter(Boolean).join(" · ") || l.索引ID,
        );
        加(body, row);
        加(body, btn);
      });
    } else {
      加(
        body,
        h(
          "div",
          "ev-src",
          "这条没有挂文献。索引用的是输出里给的 索引ID，没给就不编。",
        ),
      );
    }

    加(body, h("div", "ev-l", "语料例证"));
    if (c) {
      加(body, h("div", "ev-t", "「" + c.片段 + "」"));
      加(
        body,
        h(
          "div",
          "ev-src",
          c.id + "｜线索「" + c.线索 + "」｜" + c.说话人 + " · " + c.归属,
        ),
      );
      加(
        body,
        h("div", "ev-src", "可核实性：" + c.可核实性 + "｜来源：" + c.来源),
      );
    } else {
      加(body, h("div", "ev-src", "这条没挂语料例证。"));
    }

    det.appendChild(body);
    if (折叠 === false) det.open = true;
    加(wrap, det);
    return wrap;
  }

  /* 文献详情浮层（第二次点击：色块 → 依据 → 文献出处） */
  function 打开文献浮层(l) {
    var r = l.索引ID ? 取文献(l.索引ID) : null;
    var 内容 = h("div");
    if (r) {
      加(内容, 描述行("标题", r.标题, "v big"));
      加(内容, 描述行("作者", r.作者, "v"));
      加(
        内容,
        描述行(
          "年份",
          String(r.年份 === null || r.年份 === undefined ? "未核实" : r.年份),
          "v",
        ),
      );
      加(内容, 描述行("出处", r.出处 || "未记录", "sub"));
      加(内容, 描述行("可核实性", r.可核实性, "sub"));
      加(内容, 描述行("核实方式", r.核实方式 || "未记录", "sub"));
      加(
        内容,
        描述行("支撑理论", (r.支撑理论 || []).join("、") || "未记录", "sub"),
      );
      加(内容, 描述行("对应文件", r.文件 || "无", "sub"));
    } else {
      加(内容, 描述行("文献", "索引里没有这条：" + (l.标题 || l.索引ID), "v"));
      加(
        内容,
        描述行(
          "说明",
          "data/rag_index.json 里查不到的内容，不当作已确认的出处引用。",
          "sub",
        ),
      );
    }
    加(
      内容,
      h("div", "note", "索引只记出处，不转述研究结论。要看结论，去读原文。"),
    );
    开浮层("文献出处", 内容);
  }

  /* ================= 5. 锚点：从结果里切出色块（§6.5 证据、§8.1 锚点） ================= */

  function 证据归位(证据, 原文, 模态) {
    if (证据 && typeof 证据 === "object") {
      return {
        位置: String(证据.位置 || ""),
        片段: String(证据.片段 || ""),
        观察: Array.isArray(证据.观察) ? 证据.观察.slice() : [],
      };
    }
    var s = String(证据 === null || 证据 === undefined ? "" : 证据).trim();
    var m = /^(\d+(?:\.\d+)?)\s*[-\u2013\u2014~\u301c]\s*(\d+(?:\.\d+)?)$/.exec(
      s,
    );
    if (!m) return { 位置: s, 片段: "", 观察: [] };
    var a = Number(m[1]);
    var b = Number(m[2]);
    if (模态 === "text") return { 位置: s, 片段: 原文.slice(a, b), 观察: [] };
    if (模态 === "audio")
      return { 位置: s, 片段: 时间轴取文(原文, a, b), 观察: [] };
    return { 位置: s, 片段: "", 观察: [] };
  }

  /* 语音：证据给的是起止秒，把落在区间里的转写行取出来当引文。 */
  function 时间轴取文(转写, a, b) {
    var 行 = String(转写 || "").split(/\r?\n/);
    var 出 = [];
    行.forEach((l) => {
      var m =
        /^\s*\[?\s*(\d+(?:\.\d+)?)\s*[-\u2013\u2014~]\s*(\d+(?:\.\d+)?)\s*\]?\s*(.*)$/.exec(
          l,
        );
      if (!m) return;
      var s = Number(m[1]);
      var e = Number(m[2]);
      if (e > a && s < b && m[3]) 出.push(m[3].trim());
    });
    return 出.join(" ");
  }

  /* 样例自带 色块锚点；联网结果没有，就从三层里派生。两路产出同一种形状。 */
  function 取锚点(结果, 原文, 模态, 样例锚点) {
    var 风险 = 结果 && 结果.判定 ? 结果.判定.风险 : "";
    var 出 = [];
    function 放(层, 标签, 说话人, 证据, 来源字段, 额外) {
      var 归 = 证据归位(证据, 原文, 模态);
      var o = {
        层: 层,
        标签: 标签,
        说话人: 说话人,
        位置: 归.位置,
        片段: 归.片段,
        观察: 归.观察,
        来源字段: 来源字段,
        色: 风险,
      };
      Object.keys(额外 || {}).forEach((k) => {
        o[k] = 额外[k];
      });
      出.push(o);
    }

    if (Array.isArray(样例锚点) && 样例锚点.length) {
      样例锚点.forEach((a, i) => {
        var 层 = /杠杆/.test(a.标签)
          ? "说服杠杆层"
          : /话语/.test(a.标签)
            ? "话语层"
            : "事件层";
        出.push({
          层: 层,
          标签: String(a.标签 || ""),
          说话人: a.说话人 || "",
          位置: String(a.位置 || ""),
          片段: String(a.片段 || ""),
          观察: Array.isArray(a.观察) ? a.观察.slice() : [],
          来源字段: a.来源字段 || "锚点[" + i + "]",
          色: a.色 || 风险,
        });
      });
      return 出;
    }

    if (!结果 || !结果.判定) return 出;

    (结果.事件层 || []).forEach((it, i) => {
      if (!it || !it.证据) return;
      放(
        "事件层",
        "事件层 · " + (it.语用目标 || ""),
        it.说话人,
        it.证据,
        "事件层[" + i + "]",
        {
          语用目标: it.语用目标 || "",
          人物关系: it.人物关系 || "",
        },
      );
    });
    (结果.话语层 || []).forEach((it, i) => {
      if (!it || !it.证据) return;
      var 值 = String(it.值 || "");
      放(
        "话语层",
        "话语层 · " + (it.维度 || "") + (值 ? "：" + 值 : ""),
        it.说话人,
        it.证据,
        "话语层[" + i + "]",
        {
          维度: it.维度 || "",
          值: 值,
        },
      );
    });
    (结果.说服杠杆层 || []).forEach((it, i) => {
      if (!it || !it.证据) return;
      放(
        "说服杠杆层",
        "说服杠杆层 · " +
          (it.杠杆 || "") +
          " · 强度 " +
          it.强度 +
          " · " +
          (it.归属 || ""),
        it.说话人,
        it.证据,
        "说服杠杆层[" + i + "]",
        { 杠杆: it.杠杆 || "", 强度: it.强度, 归属: it.归属 || "" },
      );
    });
    return 出;
  }

  /* 同一段原话上的多条标签合成一个色块（避免同位置重复堆叠）。 */
  function 分组(锚点) {
    var map = [];
    锚点.forEach((a) => {
      var k = a.位置 + "|" + a.片段;
      var g = map.filter((x) => x.key === k)[0];
      if (!g) {
        g = {
          key: k,
          位置: a.位置,
          片段: a.片段,
          色: a.色,
          labels: [],
          观察: [],
        };
        map.push(g);
      }
      g.labels.push(a);
      if (!g.色 && a.色) g.色 = a.色;
      (a.观察 || []).forEach((o) => {
        if (g.观察.indexOf(o) === -1) g.观察.push(o);
      });
    });
    return map;
  }

  /* §7.6 转述标记：他的话被我在话里转述出来，标明一下，免得看着像他当面说的。 */
  function 是转述(原文, 锚) {
    if (锚.说话人 === "我") return false;
    if (锚.层 === "事件层") return false;
    var 片段 = String(锚.片段 || "");
    if (/^.{0,3}(说|讲|告诉|问|念叨|宣称)/.test(片段)) return true;
    var m = /^(\d+)/.exec(String(锚.位置 || ""));
    if (!m) return false;
    var 前 = String(原文 || "").slice(
      Math.max(0, Number(m[1]) - 10),
      Number(m[1]),
    );
    return /(说|讲|告诉|问|念叨|宣称)/.test(前);
  }

  /* 说话人一键纠正（§7.6 第 2 道保险）：改的是归属，风险等级仍来自原分析，不假装重算过模型。 */
  function 纠正如有(锚) {
    var 片段 = String(锚.片段 || "");
    for (var i = 0; i < S.corrections.length; i++) {
      var c = S.corrections[i];
      var a = 片段.replace(/[\s，。！？；、,.!?;]/g, "");
      var b = String(c.句子 || "").replace(/[\s，。！？；、,.!?;]/g, "");
      if (!a || !b) continue;
      if (b.indexOf(a) !== -1 || a.indexOf(b) !== -1) return c.说话人;
    }
    return null;
  }

  function 应用纠正(锚点) {
    return 锚点.map((a) => {
      var 改 = 纠正如有(a);
      if (!改 || 改 === a.说话人) return a;
      var b = Object.assign({}, a, { 说话人: 改, 已纠正: true });
      if (a.层 === "说服杠杆层")
        b.归属 = 改 === "我" ? "已对我生效" : "正在施放";
      return b;
    });
  }

  function 已生效杠杆(锚点) {
    return 锚点.filter(
      (a) =>
        a.层 === "说服杠杆层" &&
        (a.归属 === "已对我生效" || (!a.归属 && a.说话人 === "我")),
    );
  }

  /* ================= 6. 说话人：老人档浮层①的机械口径 ================= */

  /* 老人档要「这句在干什么」≤12 字。只做机械改写，不新增断言：
     字段值照搬（杠杆 / 维度 / 语用目标），换个说法而已。 */
  function 干什么(a) {
    var 我 = a.说话人 === "我";
    var s = "";
    if (a.层 === "说服杠杆层")
      s = (我 ? "你说到了「" : "他说到了「") + (a.杠杆 || "") + "」";
    else if (a.层 === "话语层")
      s = (我 ? "你的话里藏着" : "他的话里藏着") + (a.维度 || "");
    else s = (我 ? "你在说" : "他想") + (a.语用目标 || "");
    if (s.replace(/[「」]/g, "").length > 12)
      s = a.杠杆 || a.维度 || a.语用目标 || "这一句被标了颜色";
    return s;
  }

  function 说话人词(sp) {
    if (sp === "我") return "我的话";
    if (sp === "第三人") return "旁人的话";
    return "他的话";
  }

  function 一句话给用户(结果, ctx) {
    var 输出 = (结果 && 结果.策略 && 结果.策略.输出) || [];
    var one = 输出.filter((o) => o.形态 === "一句话")[0] || 输出[0];
    if (!one) return null;
    return 扫描(one.内容, ctx, "策略.输出[0].内容");
  }

  /* ================= 7. 渲染：色块 ================= */

  function 色块列表(锚点, 原文, turn) {
    var 组 = 分组(锚点);
    var 包 = h("div", "blocks");
    组.forEach((g) => {
      var 色 = g.色 || "中性";
      var btn = h("button", "blk blk--" + 色);
      btn.type = "button";

      var 引 = String(g.片段 || "");
      if (!引) 引 = g.labels.map((l) => l.标签)[0] || "这一句";
      加(btn, h("div", "blk-quote", g.片段 ? "「" + 引 + "」" : 引));

      var meta = h("div", "blk-meta");
      var 已列 = {};
      g.labels.forEach((l) => {
        var k = "w:" + l.说话人;
        if (l.说话人 && !已列[k]) {
          已列[k] = 1;
          加(meta, h("span", "tag tag--who", 说话人词(l.说话人)));
        }
      });
      g.labels.forEach((l) => {
        var k = "l:" + l.层;
        if (!已列[k]) {
          已列[k] = 1;
          加(meta, h("span", "tag", 层短名[l.层] || l.层));
        }
        if (是转述(原文, l) && !已列["z"]) {
          已列["z"] = 1;
          加(meta, h("span", "tag", "你转述的话"));
        }
        if (l.已纠正 && !已列["c"]) {
          已列["c"] = 1;
          加(meta, h("span", "tag", "已按你的话改过"));
        }
      });
      if (turn.模态 !== "text" && g.位置)
        加(meta, h("span", "tag tag--ev", g.位置));
      加(btn, meta);
      if (g.观察.length)
        加(btn, h("div", "q-follow", "看到的：" + g.观察.join("；")));

      btn.addEventListener("click", () => {
        开色块浮层(g, turn);
      });
      加(包, btn);
    });
    return 包;
  }

  /* ================= 8. 浮层（§8.2 / §9.5） ================= */

  function 描述行(k, v, cls) {
    var s = h("div", "ov-sec");
    加(s, h("div", "k", k));
    加(s, h("div", cls || "v", v));
    return s;
  }
  function 节点行(k, 节点) {
    var s = h("div", "ov-sec");
    加(s, h("div", "k", k));
    var box = h("div", "ov-strong");
    加(box, 节点);
    加(s, box);
    return s;
  }

  function 朗读按钮(text) {
    var b = h("button", "ov-btn", "🔊 念一遍");
    b.type = "button";
    b.addEventListener("click", () => {
      朗读(text);
    });
    return b;
  }

  /* 点中「我自己的话」时多出来的模块（§9.5） */
  function 我的话模块(组, 结果) {
    var 我标 = 组.labels.filter((l) => l.说话人 === "我");
    if (!我标.length) return null;

    var 杠 = 我标.filter((l) => l.层 === "说服杠杆层");
    var 说明 = 杠.length
      ? "「" + 杠[0].杠杆 + "」已经对你生效"
      : 我标.map((l) => 干什么(l)).join("；");

    var 理论id = 杠.length
      ? 杠[0].归属 === "已对我生效"
        ? 归属理论
        : 杠杆理论
      : "L1-attribution";
    var t = 取理论(理论id);

    var box = h("div", "ov-sec");
    加(box, h("div", "k", "这句话说明什么"));
    加(box, h("div", "v big", 说明));

    加(box, h("div", "k", "为什么这是危险信号"));
    if (t) {
      加(box, h("div", "v", t.一句话));
      加(
        box,
        h(
          "div",
          "sub",
          t.id + "｜" + t.名称 + "（理论层，" + t.可核实性 + "）",
        ),
      );
    } else {
      加(box, h("div", "sub", "索引里没有对得上的理论条目，不补写。"));
    }

    加(box, h("div", "ask-self", 自问句));
    加(
      box,
      h(
        "div",
        "sub",
        "这句话出自执行指令 §9.5 / §9.6：不给结论，给一个自己能问自己的问题。",
      ),
    );

    var 依据 = 依据块(我标[0], 结果, true);
    加(box, 依据);
    return box;
  }

  /* 家属档：浮层六块（§9.5） */
  function 浮层家属(组, turn) {
    var 结果 = turn.结果;
    var ctx = turn.ctx;
    var box = h("div");

    加(
      box,
      描述行(
        "判定",
        (结果.判定.风险 || "") +
          "｜" +
          (扫描(结果.判定.一句话, ctx, "判定.一句话") ||
            "（结论没过禁忌扫描，已去掉）"),
        "v big",
      ),
    );

    var 杠 = 组.labels.filter((l) => l.层 === "说服杠杆层");
    if (杠.length) {
      加(
        box,
        描述行(
          "这是哪个杠杆",
          杠
            .map((l) => l.杠杆 + " · 强度 " + l.强度 + " · " + (l.归属 || ""))
            .join("；"),
          "v",
        ),
      );
    } else {
      加(box, 描述行("这是哪个杠杆", "这一段没有命中六杠杆。", "sub"));
    }

    var 多层 = h("div", "ov-sec");
    加(多层, h("div", "k", "为什么（理论 / 文献 / 语料例证）"));
    组.labels.forEach((l, i) => {
      var eb = 依据块(l, 结果, i === 0);
      加(多层, eb);
    });
    加(box, 多层);

    加(box, 节点行("前后文", 前后文节点(turn, 组)));
    加(box, 问题清单节点("可以问他什么", turn));
    加(box, 怎么说节点("可以怎么说", turn));

    var 我 = 我的话模块(组, 结果);
    if (我) 加(box, 我);
    return box;
  }

  /* 前后文：文本取字符区间两侧，语音取整段转写，图片给区域坐标。 */
  function 前后文节点(turn, 组) {
    var wrap = h("div");
    if (turn.模态 === "image") {
      if (turn.图片源) {
        var img = h("img");
        img.src = turn.图片源;
        img.alt = "你发的图";
        加(wrap, img);
      }
      加(wrap, h("div", "sub", "锚点在图上的区域：" + (组.位置 || "未给坐标")));
      return wrap;
    }
    if (turn.模态 === "audio") {
      加(wrap, h("div", null, turn.原文));
      加(wrap, h("div", "sub", "证据单位：时间轴（起止秒）"));
      return wrap;
    }
    var m = /^(\d+)\s*[-\u2013\u2014~]\s*(\d+)$/.exec(String(组.位置 || ""));
    if (!m) {
      加(wrap, h("div", "sub", "这条证据只给了位置，取不到前后文。"));
      return wrap;
    }
    var a = Number(m[1]);
    var b = Number(m[2]);
    var 原文 = String(turn.原文 || "");
    var 前 = 原文.slice(Math.max(0, a - 18), a);
    var 中 = 原文.slice(a, b);
    var 后 = 原文.slice(b, b + 18);
    var line = h("div", "ov-ctx");
    加(line, document.createTextNode(前));
    var mk = h("mark", null, 中);
    加(line, mk);
    加(line, document.createTextNode(后));
    加(wrap, line);
    加(
      wrap,
      h(
        "div",
        "sub",
        "黄色底就是这一段。证据单位：原文（字符区间 " + 组.位置 + "）。",
      ),
    );
    return wrap;
  }

  function 输出项(结果, 形态) {
    return ((结果.策略 && 结果.策略.输出) || []).filter((o) => o.形态 === 形态);
  }

  function 问题清单节点(k, turn) {
    var 问 = 输出项(turn.结果, "问题");
    var box = h("div");
    if (!问.length) {
      var 对 = turn.结果.策略 ? turn.结果.策略.对抗者 : "";
      加(box, h("div", "k", k));
      var 因 =
        对 === "广告"
          ? "对象是广告，没有交涉对象（执行指令 §4.3）。"
          : "这次没有给你问题清单。";
      加(box, h("div", "sub", 因));
      return box;
    }
    加(box, h("div", "k", k));
    var ul = h("ul", "ov-list");
    问
      .sort((x, y) => (x.序号 || 0) - (y.序号 || 0))
      .forEach((o) => {
        var t = 扫描(o.内容, turn.ctx, "策略.输出.问题");
        加(ul, h("li", null, t === null ? "（这条没过禁忌扫描，已去掉）" : t));
      });
    加(box, ul);
    return box;
  }

  function 怎么说节点(k, turn) {
    var 出 = 输出项(turn.结果, "脚本").concat(输出项(turn.结果, "一句话"));
    var box = h("div");
    加(box, h("div", "k", k));
    if (!出.length) {
      加(box, h("div", "sub", "这次没有给你可以照着说的话。"));
      return box;
    }
    var ul = h("ul", "ov-list");
    出.forEach((o) => {
      var t = 扫描(o.内容, turn.ctx, "策略.输出." + o.形态);
      加(ul, h("li", null, t === null ? "（这条没过禁忌扫描，已去掉）" : t));
    });
    加(box, ul);
    return box;
  }

  /* 老人档：只给两件事（§8.3） */
  function 浮层老人(组, turn) {
    var box = h("div");
    var 主 = 组.labels[0];
    加(box, 描述行("这句在干什么", 组.labels.map(干什么).join("／"), "v big"));
    var 该 = 一句话给用户(turn.结果, turn.ctx);
    加(box, 描述行("你该说什么", 该 || "这次没有生成给你说的话。", "v big"));
    var row = h("div", "ov-sec");
    加(row, 朗读按钮(组.labels.map(干什么).join("。") + "。" + (该 || "")));
    加(box, row);
    var 我 = 我的话模块(组, turn.结果);
    if (我) 加(box, 我);
    else 加(box, 依据块(主, turn.结果, true));
    加(box, 纠正节点(组, turn));
    return box;
  }

  /* 现场档：浮层就是这四个问题（§8.5、§9.5） */
  function 浮层现场问题(o, 序, 总, turn) {
    var box = h("div");
    加(
      box,
      描述行("这是第几个问题", "第 " + 序 + " 个（共 " + 总 + " 个）", "v"),
    );
    加(
      box,
      描述行(
        "该问什么",
        扫描(o.内容, turn.ctx, "策略.输出.问题") ||
          "（这条没过禁忌扫描，已去掉）",
        "v big",
      ),
    );
    加(
      box,
      描述行(
        "他可能怎么答",
        扫描(o.他可能怎么答, turn.ctx, "策略.输出.他可能怎么答") ||
          "这次没给这一条。",
        "v",
      ),
    );
    加(
      box,
      描述行(
        "你再问",
        扫描(o.你再问, turn.ctx, "策略.输出.你再问") || "这次没给这一条。",
        "v",
      ),
    );
    加(box, 发现行(turn.结果, turn.ctx));
    return box;
  }

  /* 说话人不对？一键纠正（§7.6 第 2 道保险） */
  function 纠正节点(组, turn) {
    var box = h("div", "ov-sec");
    加(box, h("div", "k", "说话人不对？"));
    var 谁 = 组.labels[0].说话人 === "我" ? "推销者" : "我";
    var b = h(
      "button",
      "choice",
      "改成：" + (谁 === "我" ? "这句是我说的" : "这句是他说的"),
    );
    b.type = "button";
    b.addEventListener("click", () => {
      S.corrections.push({ 句子: 组.片段, 说话人: 谁 });
      重建轮次(turn);
      开色块浮层(turn.组缓存[组.key], turn);
    });
    加(box, b);
    return box;
  }

  function 发现行(结果, ctx) {
    var box = h("div", "ov-sec");
    加(box, h("div", "k", "这轮是怎么判的"));
    加(
      box,
      h(
        "div",
        "sub",
        扫描(结果.判定 && 结果.判定.触发规则, ctx, "判定.触发规则") ||
          "结果里没给触发规则。",
      ),
    );
    if (结果.判定 && 结果.判定.官方出口 && 结果.判定.官方出口.length) {
      加(box, h("div", "sub", "官方出口：" + 结果.判定.官方出口.join(" / ")));
    }
    return box;
  }

  function 开色块浮层(组, turn) {
    var 内 = h("div");
    var 档 = turn.档 || 档位(turn.结果);
    if (档 === "家属") 加(内, 浮层家属(组, turn));
    else 加(内, 浮层老人(组, turn));
    if (档 === "现场") 加(内, k_现场注记());
    S.overlayTurn = turn;
    S.overlayKey = 组.key;
    开浮层("色块 · " + (组.色 || "中性") + "色", 内);
  }

  function k_现场注记() {
    var box = h("div", "note");
    加(box, h("span", "nt", "现场档"));
    加(
      box,
      h("span", null, "：要问的那几个问题在下面按顺序列着，点一条看怎么接。"),
    );
    return box;
  }

  /* 浮层的开关：只开一个，开新的自动关旧的；点空白或左上角关闭（§8.2）。
     开的时候把当前滚动位置记下来，关的时候楜回去 —— 「关掉即回到原处，位置不丢」（P9）。
     同时锁住背后页面的滚动，免得看浮层的时候页面被指头带跑。 */
  var 浮层前滚动 = null;

  function 开浮层(kicker, 内容) {
    if (overlay.hidden) 浮层前滚动 = window.scrollY || 0;
    ovKicker.textContent = kicker || "浮层";
    空(ovBody);
    加(ovBody, 内容);
    ovBody.scrollTop = 0;
    overlay.hidden = false;
    document.body.classList.add("ov-open");
  }
  function 关浮层() {
    var 回 = 浮层前滚动;
    浮层前滚动 = null;
    overlay.hidden = true;
    document.body.classList.remove("ov-open");
    空(ovBody);
    S.overlayTurn = null;
    S.overlayKey = null;
    if (回 !== null && 回 !== undefined) {
      try {
        window.scrollTo(0, 回);
      } catch {}
    }
  }
  $("ovClose").addEventListener("click", 关浮层);
  overlay.addEventListener("click", (e) => {
    if (
      e.target &&
      e.target.getAttribute &&
      e.target.getAttribute("data-close") === "1"
    )
      关浮层();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !overlay.hidden) 关浮层();
  });

  /* ================= 9. 渲染：回复 ================= */

  function 档位(结果) {
    var u = 结果 && 结果.策略 ? 结果.策略.用户 : "";
    if (u === "当事人") return "现场";
    if (u === "子女" || u === "社区工作者") return "家属";
    return "老人"; // 默认老人档（§8.3）
  }

  function 两行小字() {
    var n = h("div", "notice");
    加(n, h("p", null, "分析基于 AI，供参考，不构成法律意见。"));
    加(n, h("p", null, "LuCDA 只分析话术怎么骗人，不判断产品真假。"));
    return n;
  }

  function 输出块(turn) {
    var 结果 = turn.结果;
    var ctx = turn.ctx;
    var 档 = turn.档 || 档位(结果);
    var 问 = 输出项(结果, "问题");
    var 脚 = 输出项(结果, "脚本");
    var 句 = 输出项(结果, "一句话");
    if (!问.length && !脚.length && !句.length) return null;
    var 包 = h("div", "output");

    if (问.length) {
      问.sort((x, y) => (x.序号 || 0) - (y.序号 || 0));
      加(
        包,
        h(
          "h3",
          null,
          "按顺序问这 " +
            问.length +
            " 个" +
            (问.length === 6 ? "" : "（§9.1 要求 6 个）"),
        ),
      );
      问.forEach((o, i) => {
        var b = h("button", "q-item");
        b.type = "button";
        加(b, h("div", "q-no", "第 " + (o.序号 || i + 1) + " 个"));
        var t = 扫描(o.内容, ctx, "策略.输出[" + i + "].内容");
        加(
          b,
          h("div", "q-ask", t === null ? "（这条没过禁忌扫描，已去掉）" : t),
        );
        var 答 = 扫描(o.他可能怎么答, ctx, "策略.输出[" + i + "].他可能怎么答");
        var 再 = 扫描(o.你再问, ctx, "策略.输出[" + i + "].你再问");
        if (答) 加(b, h("div", "q-follow", "他可能怎么答：" + 答));
        if (再) 加(b, h("div", "q-follow", "你再问：" + 再));
        b.addEventListener("click", () => {
          开浮层(
            "现场档 · 问题",
            浮层现场问题(o, o.序号 || i + 1, 问.length, turn),
          );
        });
        加(包, b);
      });
    }

    if (脚.length) {
      加(包, h("h3", null, "就这样跟他说"));
      脚.forEach((o, i) => {
        var seg = h("div", "script-seg");
        加(seg, h("div", "seg-no", "第 " + (i + 1) + " 段"));
        var t = 扫描(o.内容, ctx, "策略.输出·脚本[" + i + "]");
        加(
          seg,
          h("div", "seg-body", t === null ? "（这段没过禁忌扫描，已去掉）" : t),
        );
        加(包, seg);
      });
    }

    if (句.length) {
      加(包, h("h3", null, 档 === "现场" ? "照着念" : "你就说这一句"));
      句.forEach((o, i) => {
        var one = h("div", "oneline");
        var t = 扫描(o.内容, ctx, "策略.输出·一句话[" + i + "]");
        加(
          one,
          h("div", "one-body", t === null ? "（这句没过禁忌扫描，已去掉）" : t),
        );
        加(包, one);
      });
      var row = h("div", "ov-sec");
      加(row, 朗读按钮(句.map((o) => o.内容).join("。")));
      加(包, row);
    }

    var 禁忌 = (结果.策略 && 结果.策略.禁忌) || [];
    if (禁忌.length) {
      var f = h("div", "forbid");
      加(f, h("div", "fh", "这些话别说（第 ⑥ 栏）"));
      var ul = h("ul");
      禁忌.forEach((x) => {
        加(ul, h("li", null, x));
      });
      加(f, ul);
      加(f, h("div", "fh", "扫描时按字面串比对。"));
      加(包, f);
    }
    return 包;
  }

  function 组缓存(turn) {
    turn.组缓存 = turn.组缓存 || {};
    turn.锚点 = 应用纠正(
      取锚点(turn.结果, turn.原文, turn.模态, turn.样例锚点),
    );
    turn.分组结果 = 分组(turn.锚点);
    turn.分组结果.forEach((g) => {
      turn.组缓存[g.key] = g;
    });
    return turn.分组结果;
  }

  function 渲染回复(turn) {
    var 结果 = turn.结果;
    var ctx = turn.ctx;
    var box = h("div", "reply");

    if (turn.样例标记) {
      var tag = h("div", "sample-tag");
      加(
        tag,
        h(
          "span",
          null,
          "演示样例：" +
            turn.样例标记.标题 +
            (turn.样例标记.期望 ? "（" + turn.样例标记.期望 + "）" : ""),
        ),
      );
      if (turn.样例标记.说明) 加(tag, h("div", null, turn.样例标记.说明));
      if (turn.模态 === "audio")
        加(tag, h("div", null, "这里的语音是人工转写的文本，没有做实时识别。"));
      加(box, tag);
    }

    if (turn.本地已纠正) {
      var cn = h("div", "note");
      加(cn, h("span", "nt", "已按你的话改了说话人"));
      加(
        cn,
        h(
          "span",
          null,
          "。只重算了说话人归属与诊断，风险等级仍来自第一次分析。",
        ),
      );
      加(box, cn);
    }

    if (turn.降级) {
      加(box, turn.降级);
      加(
        box,
        h(
          "div",
          "note",
          "降级时不给判定。校验不过就承认没分析出来，不拿一个「绿」冒充结论。",
        ),
      );
      加(box, 两行小字());
      return box;
    }

    组缓存(turn);

    /* §7.6：置信度低必须显著提示 + 一键纠正，不允许静默错判 */
    if (结果.判定 && 结果.判定.说话人置信度 === "低" && !turn.本地已纠正) {
      加(box, 说话人提示(turn));
    }

    加(box, 色块列表(turn.锚点, turn.原文, turn));

    var 出 = 输出块(turn);
    if (出) 加(box, 出);

    var 自查 = 自查块(turn);
    if (自查) 加(box, 自查);

    加(box, h("hr", "rule"));
    var 结论 = 扫描(结果.判定 && 结果.判定.一句话, ctx, "判定.一句话");
    加(box, h("div", "conclusion", 结论 || "这次没给出一句话结论。"));

    if (结果.判定 && 结果.判定.官方出口 && 结果.判定.官方出口.length) {
      var off = h("div", "official");
      加(off, h("b", null, "有事打官方电话："));
      var sp = h("span", null, 结果.判定.官方出口.join(" / "));
      加(off, sp);
      加(box, off);
    } else if (结果.判定 && 结果.判定.风险 === "红") {
      加(
        box,
        h(
          "div",
          "note",
          "红色判定必须有官方出口行（验收 7），这一条结果里没有，按缺字段处理。",
        ),
      );
    }

    if (结果.判定 && 结果.判定.正常说法对照) {
      var nor = h("div", "normal");
      加(nor, h("b", null, "未发现操纵特征。正常说法是这样："));
      加(
        nor,
        h(
          "span",
          null,
          扫描(结果.判定.正常说法对照, ctx, "判定.正常说法对照") ||
            "（对照没过禁忌扫描，已去掉）",
        ),
      );
      加(box, h("div", "note", "这只表示没发现操纵特征，不对产品作任何背书。"));
      加(box, nor);
    } else if (结果.判定 && 结果.判定.风险 === "绿") {
      加(
        box,
        h(
          "div",
          "note",
          "绿色判定必须附「正常说法」对照（验收 12），这一条结果里没有，按缺字段处理。",
        ),
      );
    }

    var 问 = 询问对抗者(turn);
    if (问) 加(box, 问);

    加(box, 依据总览(turn));
    加(box, 两行小字());
    return box;
  }

  /* §9.6 自我诊断：从老人自己说的话里读出生效的杠杆与被说到哪一步 */
  function 自查块(turn) {
    var 结果 = turn.结果;
    var ctx = turn.ctx;
    var 生效 = 已生效杠杆(turn.锚点);
    var 对 = 结果.策略 ? 结果.策略.对抗者 : "";
    if (!生效.length && 对 !== "自己") return null;

    var box = h("div", "selfcheck");
    加(box, h("h3", null, "你被说到哪一步了"));
    if (结果.诊断) {
      加(
        box,
        h(
          "div",
          "step",
          扫描(结果.诊断.被说到哪一步, ctx, "诊断.被说到哪一步") ||
            "诊断没过禁忌扫描。",
        ),
      );
      加(
        box,
        h(
          "div",
          "why",
          "依据：" + (扫描(结果.诊断.依据, ctx, "诊断.依据") || "未知"),
        ),
      );
    }
    if (生效.length) {
      加(box, h("div", "why", "你自己说的话里，已经看出这些杠杆生效了："));
      var ul = h("ul");
      生效.forEach((a) => {
        加(ul, h("li", null, a.杠杆 + "（" + a.片段 + "）"));
      });
      加(box, ul);
    } else {
      加(box, h("div", "why", "你自己的话里没有出现已生效的杠杆。"));
    }
    加(box, h("div", "ask-self", 自问句));
    加(
      box,
      h(
        "div",
        "why",
        "这句是执行指令 §9.5 / §9.6 的原话：不给结论，给一个自己能问自己的问题。",
      ),
    );
    return box;
  }

  /* §7.6 说话人提示：显著提示 + 一句一键纠正 */
  function 说话人提示(turn) {
    var box = h("div", "warn");
    加(box, h("div", "warn-head", "我不确定哪句是你说的"));
    加(box, h("div", "warn-sub", "分错说话人会把结论弄反。点一下就能改。"));
    var fix = h("div", "warn-fix");
    拆分句子(turn.原文).forEach((句) => {
      var row = h("div", "fix-row");
      加(row, h("div", "fix-text", "「" + 句 + "」"));
      var b1 = h("button", "choice", "这句是我说的");
      b1.type = "button";
      b1.addEventListener("click", () => {
        S.corrections.push({ 句子: 句, 说话人: "我" });
        turn.本地已纠正 = true;
        重建轮次(turn);
      });
      var b2 = h("button", "choice", "这句是他说的");
      b2.type = "button";
      b2.addEventListener("click", () => {
        S.corrections.push({ 句子: 句, 说话人: "推销者" });
        turn.本地已纠正 = true;
        重建轮次(turn);
      });
      加(row, b1);
      加(row, b2);
      加(fix, row);
    });
    加(box, fix);
    加(
      box,
      h(
        "div",
        "warn-sub",
        "改的是说话人归属与诊断；风险等级仍来自第一次分析。",
      ),
    );
    return box;
  }

  function 拆分句子(原文) {
    var 出 = [];
    String(原文 || "")
      .split(/[。！？；\n]+/)
      .forEach((s) => {
        var t = s.replace(/^[\s，、,]+|[\s，、,]+$/g, "");
        if (t.length >= 2) 出.push(t);
      });
    if (出.length > 8) 出 = 出.slice(0, 8);
    return 出;
  }

  /* §8.4：只在推断不出对抗者时问一次；系统先猜一个并高亮 */
  function 询问对抗者(turn) {
    if (S.asked || turn.已问过) return null;
    var 结果 = turn.结果;
    var 对 = 结果.策略 ? 结果.策略.对抗者 : "";
    var 置信 = 结果.判定 ? 结果.判定.说话人置信度 : "";
    if (对 && 置信 !== "低") return null;

    var 猜 = 猜对抗者(turn.原文, 对);
    var box = h("div", "ask");
    加(box, h("h3", null, "你要跟谁说？"));
    加(
      box,
      h(
        "div",
        "ask-sub",
        "先按「" +
          猜.名 +
          "」猜的" +
          (猜.怎么来的 ? "（" + 猜.怎么来的 + "）" : "") +
          "。只用点一下，也可以改成别的。",
      ),
    );
    var list = h("div", "choices");
    对抗者选项.forEach((o) => {
      var b = h("button", "choice");
      b.type = "button";
      b.setAttribute("aria-pressed", o.名 === 猜.名 ? "true" : "false");
      b.textContent = o.名;
      if (o.名 === 猜.名) 加(b, h("small", null, "系统猜的是这个"));
      b.addEventListener("click", () => {
        turn.已问过 = true;
        S.asked = true;
        发送文字(turn.原文 + "\n" + o.句);
      });
      加(list, b);
    });
    var 不改 = h("button", "choice", "不用改");
    不改.type = "button";
    不改.addEventListener("click", () => {
      turn.已问过 = true;
      S.asked = true;
      重建轮次(turn);
    });
    加(list, 不改);
    加(box, list);
    return box;
  }

  function 猜对抗者(原文, 模型给的) {
    if (模型给的 && 对抗者选项.some((o) => o.名 === 模型给的)) {
      return { 名: 模型给的, 怎么来的: "分析结果里给的对象" };
    }
    var t = String(原文 || "");
    for (var i = 0; i < 对抗者选项.length; i++) {
      var o = 对抗者选项[i];
      for (var j = 0; j < o.词.length; j++) {
        if (t.indexOf(o.词[j]) !== -1)
          return { 名: o.名, 怎么来的: "你这句话里有「" + o.词[j] + "」" };
      }
    }
    return { 名: "推销员", 怎么来的: "没有线索，先按最常见的猜" };
  }

  /* 依据总览：这轮断言的出处，一次点击打开（§11 验收 3） */
  function 依据总览(turn) {
    var 源 = (turn.结果.溯源 || []).filter((s) => s && s.断言);
    var box = h("div", "evidence");
    var det = document.createElement("details");
    var sum = document.createElement("summary");
    加(sum, h("span", null, "这轮的依据 ▸ 共 " + 源.length + " 条"));
    det.appendChild(sum);
    var body = h("div", "ev-body");
    if (!源.length) {
      加(body, h("div", "ev-src", "这轮没给溯源条目。没依据的断言不显示。"));
    }
    源.forEach((s) => {
      加(body, h("div", "ev-l", "断言"));
      加(
        body,
        h(
          "div",
          "ev-t",
          扫描(s.断言, turn.ctx, "溯源.断言") || "（断言没过禁忌扫描，已去掉）",
        ),
      );
      var lits = 文献列表({ 溯源: [s] });
      lits.forEach((l) => {
        var b = h("button", "ev-link", "打开出处：" + (l.标题 || l.索引ID));
        b.type = "button";
        b.addEventListener("click", () => {
          打开文献浮层(l);
        });
        加(body, b);
      });
      if (typeof s.语料例证 === "string" && s.语料例证) {
        加(body, h("div", "ev-src", "语料例证：" + s.语料例证));
      }
    });
    det.appendChild(body);
    加(box, det);
    return box;
  }

  /* ================= 10. 渲染：轮次 ================= */

  function 建轮次(turn) {
    turn.id =
      turn.id ||
      "t" + (S.turns.length + 1) + "_" + Math.random().toString(36).slice(2, 7);
    var art = h("article", "turn");
    art.setAttribute("data-turn", turn.id);

    var sent = h("div", "sent");
    加(sent, h("div", "sent-kicker", turn.输入说明 || "你发的"));
    if (turn.模态 === "image") {
      if (turn.图片源) {
        var img = h("img");
        img.src = turn.图片源;
        img.alt = "你发的图";
        img.addEventListener("error", () => {
          加(
            sent,
            h(
              "div",
              "sent-missing",
              "本地没找到这张图（" +
                演示图片路径 +
                "）。结果里的区域坐标仍按样例里的记录显示。",
            ),
          );
        });
        加(sent, img);
      }
      加(sent, h("div", "sent-body", turn.转写 || "（图片）"));
    } else {
      加(sent, h("div", "sent-body", turn.原文));
    }
    加(art, sent);
    加(art, 渲染回复(turn));
    turn.节点 = art;
    return art;
  }

  function 渲染轮次(turn) {
    feed.appendChild(建轮次(turn));
    S.turns.push(turn);
    滚动到底();
  }

  function 重建轮次(turn) {
    // 先把旧节点捉住：建轮次() 内部会把 turn.节点 重新赋成尚未挂载的新节点，
    // 所以不能在建轮次() 之后再读 turn.节点.parentNode（那时它已经是 null）。
    var 旧 = turn.节点;
    if (!旧 || !旧.parentNode) return;
    var 新 = 建轮次(turn);
    旧.parentNode.replaceChild(新, 旧);
  }

  function 滚动到底() {
    try {
      var y =
        feed.getBoundingClientRect().bottom +
        window.scrollY -
        window.innerHeight +
        240;
      window.scrollTo(0, Math.max(0, y));
    } catch {}
  }

  /* ================= 11. 依据查询（§6.7 主动查询入口） ================= */

  function 是依据查询(文本) {
    var t = String(文本 || "");
    if (!/(研究|文献|出处|依据|来源|说法)/.test(t)) return null;
    if (!/(有什么|有哪些|有没有|是什么|怎么说|算不算|吗|？|\?)/.test(t))
      return null;
    var 命中 = 检索线索(t);
    return 命中.length ? 命中 : null;
  }

  function 检索线索(文本) {
    if (!S.rag) return [];
    var t = String(文本 || "");
    var 出 = [];
    (S.rag.线索索引 || []).forEach((c) => {
      var 名 = [c.线索].concat(c.别名 || []);
      var 中 = 名.filter((x) => x && t.indexOf(x) !== -1);
      if (!中.length) return;
      出.push({ 条目: c, 中: 中[0] });
    });
    return 出;
  }

  function 建查询轮次(文本, 命中) {
    var turn = {
      模态: "text",
      原文: 文本,
      输入说明: "你问的话",
      结果: null,
      查询: 命中,
      锚点: [],
      档: "老人",
    };
    var art = h("article", "turn");
    var sent = h("div", "sent");
    加(sent, h("div", "sent-kicker", "你问的话"));
    加(sent, h("div", "sent-body", 文本));
    加(art, sent);

    var box = h("div", "reply");
    命中.forEach((m) => {
      var blk = h("div", "blk blk--中性");
      加(blk, h("div", "blk-quote", "「" + m.中 + "」"));
      var meta = h("div", "blk-meta");
      加(meta, h("span", "tag", "依据查询（不是风险判定）"));
      加(blk, meta);
      加(box, blk);

      var 理 = (m.条目.理论 || []).map((id) => {
        var t = 取理论(id);
        return t
          ? t.id +
              "｜" +
              t.名称 +
              "：" +
              t.一句话 +
              "（" +
              t.来源 +
              "；" +
              t.可核实性 +
              "）"
          : id;
      });
      var 文 = (m.条目.文献 || []).map((id) => {
        var l = 取文献(id);
        return l
          ? {
              标题: l.标题,
              作者: l.作者,
              年份: l.年份,
              索引ID: l.id,
              可核实性: l.可核实性,
              核实方式: l.核实方式,
              出处: l.出处,
            }
          : { 标题: id, 索引ID: id };
      });
      var 语 = (m.条目.语料例证 || []).map((id) => {
        var c = 取语料(id);
        return c
          ? c.id + "｜「" + c.片段 + "」｜" + c.可核实性 + "｜" + c.来源
          : id;
      });

      var sec = h("div", "ov-sec");
      加(sec, h("div", "k", "理论"));
      if (理.length)
        理.forEach((x) => {
          加(sec, h("div", "v", x));
        });
      else 加(sec, h("div", "sub", "索引里没给理论层条目。"));
      加(box, sec);

      var sec2 = h("div", "ov-sec");
      加(sec2, h("div", "k", "文献"));
      if (文.length) {
        文.forEach((l) => {
          加(
            sec2,
            h(
              "div",
              "v",
              [l.标题, l.作者, l.年份].filter(Boolean).join(" · ") +
                (l.可核实性 ? "（" + l.可核实性 + "）" : ""),
            ),
          );
          var b = h("button", "ev-link", "打开出处：" + l.标题);
          b.type = "button";
          b.addEventListener("click", () => {
            打开文献浮层(l);
          });
          加(sec2, b);
        });
      } else 加(sec2, h("div", "sub", "这条线索没挂文献。"));
      加(box, sec2);

      var sec3 = h("div", "ov-sec");
      加(sec3, h("div", "k", "语料例证"));
      if (语.length)
        语.forEach((x) => {
          加(sec3, h("div", "v", x));
        });
      else 加(sec3, h("div", "sub", "这条线索没挂语料例证。"));
      加(box, sec3);
    });

    加(box, h("hr", "rule"));
    var 统计 = 命中.reduce(
      (a, m) => {
        a.理论 += (m.条目.理论 || []).length;
        a.文献 += (m.条目.文献 || []).length;
        a.语料 += (m.条目.语料例证 || []).length;
        return a;
      },
      { 理论: 0, 文献: 0, 语料: 0 },
    );
    加(
      box,
      h(
        "div",
        "conclusion",
        "找到 " +
          命中.length +
          " 组依据：理论 " +
          统计.理论 +
          " · 文献 " +
          统计.文献 +
          " · 语料 " +
          统计.语料,
      ),
    );
    加(
      box,
      h(
        "div",
        "note",
        "本地检索 data/rag_index.json，不上向量库（执行指令 §6.7）。文献只记出处，不转述研究结论。",
      ),
    );

    var 待核 = h("div", "note");
    加(待核, h("span", "nt", "可核实性"));
    加(
      待核,
      h(
        "span",
        null,
        "：标「待核实」的条目尚未逐条核对，不当作已确认的出处。语料层当前是自建样例，语料加工完成后替换。",
      ),
    );
    加(box, 待核);

    加(box, 两行小字());
    加(art, box);
    turn.节点 = art;
    feed.appendChild(art);
    S.turns.push(turn);
    滚动到底();
  }

  /* ================= 12. 提交与交互 ================= */

  function 提示(text, 警告) {
    if (!text) {
      composerNote.hidden = true;
      composerNote.textContent = "";
      composerNote.className = "composer-note";
      return;
    }
    composerNote.hidden = false;
    composerNote.textContent = text;
    composerNote.className = "composer-note" + (警告 ? " warnn" : "");
  }

  function 找同样例(文本) {
    if (!S.samples) return null;
    var t = String(文本 || "").trim();
    var hit = (S.samples.样例 || []).filter(
      (s) => String((s.输入 && s.输入.内容) || "").trim() === t,
    )[0];
    return hit || null;
  }

  function 发送文字(文本) {
    var t = String(文本 || "").trim();
    if (!t) {
      提示("先粘一句话进来。", true);
      return;
    }
    if (t.length > 8000) {
      提示("文字最多 8000 字，这次 " + t.length + " 字。", true);
      return;
    }
    收起粘贴();
    提示("");

    var 查询 = 是依据查询(t);
    if (查询) {
      建查询轮次(t, 查询);
      return;
    }

    if (离线) {
      var 样 = 找同样例(t);
      if (样) {
        载入样例(样.id, "这条和演示样例一样，直接用它的结果。");
        return;
      }
      中性回复(
        t,
        "text",
        "离线演示模式：这个页面不联网，所以不做分析。",
        "要看效果，点右上角「演示样例」，那里有 5 条真实调用出来的结果；要把出口地址填进 web/config.js 的 API_BASE，才走联网分析。",
      );
      return;
    }
    提交联网(t, "text");
  }

  function 中性回复(原文, 模态, 标题, 正文) {
    var turn = { 模态: 模态, 原文: 原文, 结果: null, 锚点: [], 档: "老人" };
    var art = h("article", "turn");
    var sent = h("div", "sent");
    加(sent, h("div", "sent-kicker", "你发的"));
    if (模态 === "image" && 原文.indexOf("data:") === 0) {
      var img = h("img");
      img.src = 原文;
      img.alt = "你发的图";
      加(sent, img);
      加(sent, h("div", "sent-body", "（一张图片）"));
    } else {
      加(sent, h("div", "sent-body", 原文));
    }
    加(art, sent);
    var box = h("div", "reply");
    var n = h("div", "note");
    加(n, h("span", "nt", 标题));
    加(n, h("span", null, 正文));
    加(box, n);
    加(box, 两行小字());
    加(art, box);
    turn.节点 = art;
    feed.appendChild(art);
    S.turns.push(turn);
    滚动到底();
  }

  function 提交联网(内容, 模态) {
    if (S.busy) return;
    S.busy = true;
    提示("分析中…", false);
    var ctl = null;
    var timer = null;
    try {
      ctl = new AbortController();
      timer = setTimeout(() => {
        try {
          ctl.abort();
        } catch {}
      }, 120000);
    } catch {
      ctl = null;
    }
    fetch(出口地址.replace(/\/+$/, "") + "/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 模态: 模态, 内容: 内容 }),
      signal: ctl ? ctl.signal : undefined,
    })
      .then((res) =>
        res.text().then((t) => {
          var j = null;
          try {
            j = JSON.parse(t);
          } catch {}
          return { res: res, json: j, text: t };
        }),
      )
      .then((r) => {
        if (timer) clearTimeout(timer);
        S.busy = false;
        提示("");
        if (r.res.ok && r.json && !r.json.状态) {
          渲染结果轮次(内容, 模态, r.json);
          return;
        }
        if (r.res.ok && r.json && r.json.状态 === "降级") {
          渲染降级轮次(内容, 模态, r.json);
          return;
        }
        中性回复(
          模态 === "image" ? "（一张图片）" : 内容,
          模态,
          "出口没给出结果：HTTP " + r.res.status + "。",
          (r.json && ((r.json.错误 && r.json.错误.说明) || r.json.提示)) ||
            String(r.text || "").slice(0, 200) ||
            "没有更多信息。",
        );
      })
      .catch((e) => {
        if (timer) clearTimeout(timer);
        S.busy = false;
        提示("没连上出口。", true);
        中性回复(
          模态 === "image" ? "（一张图片）" : 内容,
          模态,
          "没连上出口（" + ((e && e.message) || "网络错误") + "）。",
          "先看右上角「演示样例」，那里是本地结果，断网也能用。",
        );
      });
  }

  function 渲染结果轮次(内容, 模态, 结果) {
    var turn = {
      模态: 模态,
      原文: 内容,
      转写: 模态 === "audio" ? 内容 : "",
      输入说明: "你发的",
      结果: 结果,
      锚点: [],
      档: 档位(结果),
      ctx: 上下文(结果),
    };
    渲染轮次(turn);
    提示("");
  }

  function 渲染降级轮次(内容, 模态, json) {
    var turn = {
      模态: 模态,
      原文: content_or(内容),
      输入说明: "你发的",
      结果: json,
      锚点: [],
      档: "老人",
      ctx: { 用户: "", 对抗者: "" },
    };
    var box = h("div", "note");
    加(box, h("span", "nt", "这次没通过契约校验，所以不给判定。"));
    加(box, h("span", null, (json.错误 && json.错误.说明) || json.提示 || ""));
    turn.降级 = box;
    渲染轮次(turn);
  }

  function content_or(x) {
    return x && x.indexOf("data:") === 0 ? "（一张图片）" : x;
  }

  /* ================= 13. 演示样例（§8.6 离线演示模式） ================= */

  function 载入样例(id, 说明) {
    if (!S.samples) return;
    提示("");
    var s = (S.samples.样例 || []).filter((x) => x.id === id)[0];
    if (!s) return;
    var 模态 = s.输入.模态;
    var turn = {
      模态: 模态,
      原文: s.输入.内容,
      转写:
        模态 === "audio"
          ? s.输入.内容
          : 模态 === "image"
            ? "（演示用的虚构包装图）"
            : "",
      图片源: 模态 === "image" ? 演示图片路径 : "",
      输入说明:
        模态 === "text"
          ? "你发的文字"
          : 模态 === "image"
            ? "你发的图片"
            : "你发的语音（人工转写，不是实时识别）",
      结果: s.结果,
      样例锚点: s.色块锚点,
      锚点: [],
      档: 档位(s.结果),
      ctx: 上下文(s.结果),
      样例标记: { 标题: s.标题, 期望: s.期望, 说明: s.说明 },
    };
    渲染轮次(turn);
    if (说明) 提示(说明, false);
    关浮层();
  }

  function 演示样例浮层() {
    var box = h("div");
    if (!S.samples) {
      加(
        box,
        h(
          "div",
          "note",
          "还没有读到 data/demo_samples.json。用本机静态服务器打开这个页面，不要双击 html 文件。",
        ),
      );
      开浮层("演示样例", box);
      return;
    }
    加(
      box,
      h(
        "div",
        "note",
        (S.samples.样例 || []).length +
          " 条都来自真实调用，本地存着，断网可用。外观与联网模式一致（执行指令 §8.6）。",
      ),
    );
    var list = h("div", "sample-list");
    (S.samples.样例 || []).forEach((s) => {
      var b = h("button", "sample-item");
      b.type = "button";
      var 风险 = s.结果 && s.结果.判定 ? s.结果.判定.风险 : "";
      加(b, h("span", "risk-" + 风险, "[" + (风险 || "?") + "] "));
      加(b, h("span", null, s.标题));
      加(
        b,
        h(
          "small",
          null,
          s.id + " ｜ 模态 " + s.输入.模态 + " ｜ " + (s.输入.说明 || ""),
        ),
      );
      b.addEventListener("click", () => {
        载入样例(s.id, "这是演示样例：" + s.标题 + "。");
      });
      加(list, b);
    });
    加(box, list);

    var 状态 = h("div", "note");
    加(状态, h("span", "nt", 离线 ? "离线演示模式" : "联网模式"));
    加(
      状态,
      h(
        "span",
        null,
        离线
          ? "：API_BASE 是空字符串，页面不发任何网络请求。填上出口地址即可联网。"
          : "：API_BASE 已填，发东西会走 " + 出口地址 + "。",
      ),
    );
    加(box, 状态);

    var dev = h("div", "dev-log");
    var det = document.createElement("details");
    var sum = document.createElement("summary");
    sum.textContent = "禁忌扫描记录（§5.5 记录）共 " + S.scanLog.length + " 条";
    det.appendChild(sum);
    var pre = h(
      "pre",
      null,
      S.scanLog.length
        ? JSON.stringify(S.scanLog, null, 1)
        : "这次还没有命中。",
    );
    det.appendChild(pre);
    加(dev, det);
    加(box, dev);
    开浮层("演示样例", box);
  }

  /* ================= 14. TTS（结论与浮层可朗读） ================= */

  function 朗读(text) {
    var t = String(text || "").trim();
    if (!t) return;
    if (
      !("speechSynthesis" in window) ||
      typeof window.SpeechSynthesisUtterance !== "function"
    ) {
      提示("这台设备不支持朗读。", true);
      return;
    }
    try {
      window.speechSynthesis.cancel();
      var u = new window.SpeechSynthesisUtterance(t);
      u.lang = "zh-CN";
      u.rate = 0.9;
      window.speechSynthesis.speak(u);
    } catch {
      提示("朗读没起来。", true);
    }
  }

  /* ================= 15. 输入口 ================= */

  function 展开粘贴() {
    pasteArea.hidden = false;
    document.body.classList.add("paste-open");
    try {
      pasteInput.focus();
    } catch {}
  }
  function 收起粘贴() {
    pasteArea.hidden = true;
    document.body.classList.remove("paste-open");
  }

  $("pasteBtn").addEventListener("click", () => {
    提示("");
    if (pasteArea.hidden) 展开粘贴();
    else 收起粘贴();
  });
  $("closePasteBtn").addEventListener("click", () => {
    收起粘贴();
    提示("");
  });
  $("sendBtn").addEventListener("click", () => {
    var t = pasteInput.value;
    if (!String(t || "").trim()) {
      提示("先粘一句话进来。", true);
      return;
    }
    pasteInput.value = "";
    发送文字(t);
  });
  pasteInput.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") $("sendBtn").click();
  });

  $("camBtn").addEventListener("click", () => {
    提示("");
    $("fileInput").click();
  });
  $("fileInput").addEventListener("change", () => {
    var f = $("fileInput").files && $("fileInput").files[0];
    $("fileInput").value = "";
    if (!f) return;
    if (离线) {
      中性回复(
        "（一张图片）",
        "image",
        "离线演示模式：不联网，所以不做分析。",
        "图片这一路要看演示样例第 4 条（虚构包装图）。要把出口地址填进 web/config.js 才走联网分析。",
      );
      return;
    }
    var fr = new FileReader();
    fr.onload = () => {
      提交联网(String(fr.result), "image");
    };
    fr.onerror = () => {
      提示("这张图读不出来。", true);
    };
    fr.readAsDataURL(f);
  });

  $("micBtn").addEventListener("click", () => {
    提示("");
    /* 语音不做真实现（用户 2026-10-01 定向决定）：不录音、不生成转写。
       离线演示模式下只展示明示的演示样例，不假装成实时结果。 */
    if (离线) {
      var 有 =
        S.samples &&
        (S.samples.样例 || []).some((s) => s.输入.模态 === "audio");
      if (有) {
        载入样例(
          "demo-05",
          "演示样例：语音。这条用的是人工转写的时间轴文本，产品不做实时识别。",
        );
      } else {
        提示("语音识别还没做。先用「粘贴文字」。", true);
      }
      return;
    }
    提示("语音识别还没做，放到后面开发。先用「📋 粘贴文字」。", true);
    展开粘贴();
  });

  $("demoBtn").addEventListener("click", 演示样例浮层);

  /* ================= 16. 启动 ================= */

  /* 读运行时数据。同一份前端源码要同时跑在两种布局下：
       · docs/index.html 与 docs/data/ 同级（GitHub Pages 发布产物）
       · web/index.html 而 data/ 在上一级（本机开发、tools/shot_web.py）
     按页面自己的路径算出来，两种布局都直接命中，不产生多余的 404。
     算错了才退到另一个候选（只有非标准布局会走到这里）。 */
  var 数据基 = (() => {
    var 页 = location.pathname || "/";
    var 目录 = 页.slice(0, 页.lastIndexOf("/") + 1);
    var 源码布局 = /\/web\/$/.test(目录);
    return {
      主: 源码布局 ? 目录 + "../data/" : 目录 + "data/",
      备: 源码布局 ? 目录 + "data/" : 目录 + "../data/",
    };
  })();

  function 读JSON(名) {
    var 候选 = [数据基.主, 数据基.备];
    function 试(i) {
      if (i >= 候选.length) return Promise.reject(new Error("读不到 " + 名));
      return fetch(候选[i] + 名, { cache: "no-store" })
        .then((r) => {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        })
        .catch(() => 试(i + 1));
    }
    return 试(0);
  }

  function 启动() {
    var T = window.LuCDA && window.LuCDA.taboo;
    if (T && typeof T.loadRules === "function") {
      读JSON("taboos.json")
        .then((rules) => {
          T.loadRules(rules);
        })
        .catch(
          () => {},
        ); /* 读不到就用 web/taboos.js 里的兜底副本，离线仍然能扫 */
    }
    读JSON("rag_index.json")
      .then((j) => {
        S.rag = j;
      })
      .catch(() => {
        S.rag = null;
      });
    读JSON("demo_samples.json")
      .then((j) => {
        S.samples = j;
        if (离线) 提示("离线演示模式：看右上角「演示样例」。", false);
      })
      .catch(() => {
        提示(
          "没读到 data/demo_samples.json。请用本机静态服务器打开这个页面。",
          true,
        );
      });
    window.LuCDA_UI = {
      状态: S,
      发送文字: 发送文字,
      载入样例: 载入样例,
      打开浮层: 开浮层,
      关浮层: 关浮层,
      朗读: 朗读,
      扫描: 扫描,
    };
  }

  启动();
})();
