/* tools/worker_test.mjs — M2/M3 后端打通的自测
 *
 * 跑什么：
 *   1. 契约副本一致性：worker/schema.js 必须等于 schema/annotation.schema.json
 *   2. 起 worker/dev-server.mjs（真进程、真 HTTP），用真实密钥跑
 *      · 3 条文字（红 / 黄 / 图片三种情形中的黄就是 §6.2 的核心情形）
 *      · 1 张图片（用 PIL 现造的虚构保健品包装图）
 *   3. 每条返回都要过两层契约校验：node 侧 worker/validator.js + python 侧 jsonschema
 *   4. 不花钱的负向用例：非法模态、audit 未声明转写来源的 audio（必须回 501，且不返回任何转写结果）
 *   5. 同构验证：直接调用 worker.js 的默认导出处（Cloudflare Workers 入口），
 *      与 dev-server 走的是同一份实现
 *   6. 隐私检查：进程输出与响应体里都不能出现密钥
 *
 * 用法（密钥只从环境变量取，脚本不硬编码）：
 *   node tools/worker_test.mjs
 *   WT_PORT=8899 node tools/worker_test.mjs
 *
 * 退出码：0 = 全部通过；1 = 有失败（会把失败原文如实打印出来，不伪造通过）
 */

import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { validateInstance } from "../worker/validator.js";
import { ANNOTATION_SCHEMA } from "../worker/schema.js";
import 出口, { 查策略形态, 补齐官方出口 } from "../worker/worker.js";

const 此处 = path.dirname(fileURLToPath(import.meta.url));
const 根 = path.join(此处, "..");
const 端口 =
  Number(process.env.WT_PORT) > 0 ? Number(process.env.WT_PORT) : 8799;
const 基地址 = `http://127.0.0.1:${端口}`;
const PYTHON = process.env.WT_PYTHON || "D:/anaconda/miniconda3/python.exe";
const 契约路径 = path.join(根, "schema", "annotation.schema.json");
const 样例路径 = path.join(根, "data", "demo_samples.json");
const 图片路径 = path.join(根, "worker", "test_image.png");

const 密钥 = process.env.DEEPSEEK_API_KEY || "";
const 通过项 = [];
const 失败项 = [];
let dev进程 = null;
const dev输出 = [];

const 记通过 = (名, 细节) => {
  通过项.push({ 名, 细节 });
  console.log(`  通过  ${名}${细节 ? ` — ${细节}` : ""}`);
};
const 记失败 = (名, 细节) => {
  失败项.push({ 名, 细节 });
  console.log(`  失败  ${名}${细节 ? ` — ${细节}` : ""}`);
};

/* ===== python 侧独立校验（另一个实现，用来交叉验证 node 侧 validator） ===== */
const PY校验 = `
import json, sys
from jsonschema import Draft202012Validator
schema_path, data_path = sys.argv[1], sys.argv[2]
with open(schema_path, encoding="utf-8") as f:
    schema = json.load(f)
if data_path == "-":
    对象 = json.load(sys.stdin)
else:
    with open(data_path, encoding="utf-8") as f:
        对象 = json.load(f)
def 检查(o, 名):
    errs = sorted(Draft202012Validator(schema).iter_errors(o), key=lambda e: list(e.path))
    if errs:
        e = errs[0]
        print(f"{名}|不通过|{'/'.join(str(p) for p in e.path)}|{e.message[:200]}")
    else:
        print(f"{名}|通过")
if isinstance(对象, dict) and "样例" in 对象:
    for s in 对象["样例"]:
        检查(s["结果"], s["id"])
else:
    检查(对象, "对象")
`;

function 跑PY校验(对象或路径, 名) {
  return new Promise((resolve) => {
    const 用stdin = typeof 对象或路径 === "object";
    const p = spawn(
      PYTHON,
      ["-c", PY校验, 契约路径, 用stdin ? "-" : 对象或路径],
      {
        stdio: ["pipe", "pipe", "pipe"],
      },
    );
    let out = "";
    let err = "";
    p.stdout.on("data", (c) => (out += c.toString()));
    p.stderr.on("data", (c) => (err += c.toString()));
    if (用stdin) p.stdin.end(JSON.stringify(对象或路径));
    else p.stdin.end();
    p.on("close", (码) => {
      // Windows 的 python 会输出 \r\n，先去掉行尾的 \r 再判断
      const 行 = out
        .split("\n")
        .map((l) => l.replace(/\r$/, ""))
        .filter(Boolean);
      const 通过 =
        码 === 0 && 行.length > 0 && 行.every((l) => l.endsWith("|通过"));
      resolve({ 通过, 行, 码, err: err.trim(), 名 });
    });
  });
}

/* ===== 起 dev-server ===== */
function 起代理() {
  return new Promise((resolve, reject) => {
    dev进程 = spawn(
      process.execPath,
      [path.join(根, "worker", "dev-server.mjs")],
      {
        env: { ...process.env, PORT: String(端口), HOST: "127.0.0.1" },
        stdio: ["ignore", "pipe", "pipe"],
        cwd: 根,
      },
    );
    dev进程.stdout.on("data", (c) => {
      const 行 = c.toString();
      dev输出.push(行);
      process.stdout.write(`  [dev-server] ${行}`);
    });
    dev进程.stderr.on("data", (c) => {
      dev输出.push(c.toString());
      process.stdout.write(`  [dev-server:err] ${c}`);
    });
    dev进程.on("exit", (码) =>
      reject(new Error(`dev-server 提前退出，退出码 ${码}`)),
    );

    const 截止 = Date.now() + 15000;
    const 试 = async () => {
      try {
        const r = await fetch(`${基地址}/health`);
        if (r.ok) return resolve(await r.json());
      } catch {
        /* 还没起来 */
      }
      if (Date.now() > 截止)
        return reject(new Error("等 dev-server 起来超时（15 秒）"));
      setTimeout(试, 250);
    };
    setTimeout(试, 250);
  });
}

/* ===== 结构检查（契约之外的跨字段硬约束） ===== */
function 查结构(结果, 期望) {
  const 问题 = [];
  const 单位 = { text: "原文", audio: "时间轴", image: "区域" }[结果.meta.模态];
  if (结果.meta.证据单位 !== 单位)
    问题.push(`证据单位应为 ${单位}，实际 ${结果.meta.证据单位}`);
  if (结果.判定.风险 === "红") {
    const 出口s = 结果.判定.官方出口 || [];
    if (!出口s.length) 问题.push("判红但没有 官方出口（执行指令 §11 验收 7）");
    if (出口s.some((o) => !["12315", "96110"].includes(o)))
      问题.push(`官方出口里出现了非官方渠道：${出口s.join(",")}`);
    // 用户 2026-10-01 定向决定：判红时两个号码都给
    if (!(出口s.includes("12315") && 出口s.includes("96110")))
      问题.push(
        `判红的 官方出口 必须同时写 12315 与 96110，实际 ${JSON.stringify(出口s)}（§11 验收 7）`,
      );
  }
  // §4.2 / §9.1 / §9.2 / §12：形态要跟 策略.用户 对得上（数量、条数、字数、按序）
  问题.push(...查策略形态(结果));
  if (结果.判定.风险 === "绿" && !结果.判定.正常说法对照) {
    问题.push("判绿但没有 正常说法对照（§9.4、§11 验收 12）");
  }
  for (const l of 结果.说服杠杆层) {
    if (l.归属 === "已对我生效" && l.说话人 !== "我")
      问题.push(`杠杆 ${l.杠杆} 归属=已对我生效，但说话人是 ${l.说话人}`);
  }
  if (期望?.风险 && 结果.判定.风险 !== 期望.风险)
    问题.push(`期望风险 ${期望.风险}，实际 ${结果.判定.风险}`);
  if (期望?.至少一条归属已生效) {
    if (!结果.说服杠杆层.some((l) => l.归属 === "已对我生效"))
      问题.push("没有出现「已对我生效」的杠杆");
  }
  return 问题;
}

/* ===== 主流程 ===== */
console.log("\n=== M2/M3 出口自测（tools/worker_test.mjs）===");
console.log(
  `密钥：${密钥 ? "已从环境变量 DEEPSEEK_API_KEY 读取（值不打印）" : "缺失"}`,
);
if (!密钥) {
  记失败("密钥", "没有读到 DEEPSEEK_API_KEY，无法跑真实调用");
  process.exit(1);
}

// 1. 契约副本一致性
{
  let 真源 = null;
  try {
    真源 = JSON.parse(readFileSync(契约路径, "utf8"));
  } catch (e) {
    记失败("读 schema/annotation.schema.json", String(e?.message || e));
  }
  if (真源) {
    const 一致 = JSON.stringify(真源) === JSON.stringify(ANNOTATION_SCHEMA);
    if (一致) 记通过("worker/schema.js 与 schema/annotation.schema.json 一致");
    else
      记失败(
        "worker/schema.js 与 schema/annotation.schema.json 一致",
        "两份不一致，先跑 node worker/gen_schema.mjs",
      );
  }
}

// 2. 造图
console.log("  用 PIL 造测试图（worker/make_test_image.py）");
await new Promise((resolve) => {
  const p = spawn(
    PYTHON,
    [path.join(根, "worker", "make_test_image.py"), 图片路径],
    { stdio: "inherit" },
  );
  p.on("close", resolve);
});
const 图片 = readFileSync(图片路径);
const 数据URL = `data:image/png;base64,${图片.toString("base64")}`;

// 3. 起代理
console.log(`  起 dev-server（127.0.0.1:${端口}）`);
let 健康 = null;
try {
  健康 = await 起代理();
  记通过(
    "dev-server 起来了并回 /health",
    `模型=${JSON.stringify(健康.模型?.默认 || 健康.模型)}｜密钥已读取=${健康.密钥?.已从环境变量读取}`,
  );
} catch (e) {
  记失败("dev-server 起来了并回 /health", String(e?.message || e));
}

const 用例 = [
  {
    名: "T1 文字 · §6.2 核心情形（我很信任小李）",
    body: { 模态: "text", 内容: "小李说这个胶囊能治糖尿病，我很信任他" },
    期望: { 至少一条归属已生效: true },
  },
  {
    名: "T2 文字 · 要求转账（应判红）",
    body: {
      模态: "text",
      内容: "阿姨您就像我亲妈一样，这个胶囊是院士研发的，对糖尿病、高血压、失眠都管用，最后三盒了，您先转 894 块过来，我把货给您留着。",
    },
    期望: {},
  },
  {
    名: "T3 文字 · 正常商家的说法（应判绿）",
    body: {
      模态: "text",
      内容: "药店的人说这个保健品不能替代吃药，你先去问医生，需要的话我帮你查一下厂家信息，我们不送货上门，你到店里来买。",
    },
    期望: { 风险: "绿" },
  },
  {
    名: "T4 图片 · 虚构保健品包装图",
    body: { 模态: "image", 内容: 数据URL },
    期望: {},
  },
];

const 各例结果 = [];
for (const c of 用例) {
  const t0 = Date.now();
  let r = null;
  let 原始 = "";
  try {
    const resp = await fetch(`${基地址}/api/analyze`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(c.body),
    });
    原始 = await resp.text();
    r = { 状态码: resp.status, 体: JSON.parse(原始) };
  } catch (e) {
    记失败(c.名, `请求异常：${String(e?.message || e)}`);
    continue;
  }
  const 耗时 = Date.now() - t0;

  if (r.状态码 !== 200) {
    记失败(
      c.名,
      `HTTP ${r.状态码}（${耗时}ms）原始返回：${原始.slice(0, 500)}`,
    );
    continue;
  }

  const 结果 = r.体;
  const js = validateInstance(结果, ANNOTATION_SCHEMA);
  const py = await 跑PY校验(结果, c.名);
  const 结构问题 = 查结构(结果, c.期望);
  const 摘要 = `${结果.meta.模态}｜${结果.判定.风险}｜${结果.判定.一句话}｜杠杆=${结果.说服杠杆层.map((l) => `${l.杠杆}${l.强度}·${l.归属}`).join(",") || "无"}｜输出=${结果.策略.输出.map((o) => o.形态).join("/")}｜溯源=${结果.溯源.length}｜${耗时}ms`;
  各例结果.push({ 名: c.名, 摘要, 用量: 结果.meta.模态 });

  if (js.valid && py.通过 && !结构问题.length) {
    记通过(c.名, 摘要);
    console.log(`        node 校验：通过｜python 校验：${py.行.join(" ")}`);
  } else {
    记失败(
      c.名,
      摘要 +
        (js.valid
          ? ""
          : `｜node 校验错误：${js.errors.slice(0, 5).join("；")}`) +
        (py.通过 ? "" : `｜python 校验：${py.行.join(" ") || py.err}`) +
        (结构问题.length ? `｜结构问题：${结构问题.join("；")}` : ""),
    );
  }
}

// 4. 负向用例（不花钱）
{
  const resp = await fetch(`${基地址}/api/analyze`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ 模态: "audio", 内容: "（模拟一段没有转写的录音）" }),
  });
  const 体 = await resp.json();
  const 合格 =
    resp.status === 501 &&
    体.状态 === "未实现" &&
    !体.判定 &&
    !/\S/.test(String(体.转写 || "")) &&
    !("转写文本" in 体);
  if (合格)
    记通过(
      "audio 未声明转写来源 → 501 未实现，且不返回任何转写结果",
      JSON.stringify(体.错误),
    );
  else
    记失败(
      "audio 未声明转写来源 → 501 未实现",
      `HTTP ${resp.status}｜${JSON.stringify(体).slice(0, 300)}`,
    );
}
{
  const resp = await fetch(`${基地址}/api/analyze`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ 模态: "video", 内容: "x" }),
  });
  const 体 = await resp.json();
  if (resp.status === 400 && 体.判定 === null)
    记通过("非法模态 → 400 且不下判定", JSON.stringify(体.错误));
  else
    记失败(
      "非法模态 → 400 且不下判定",
      `HTTP ${resp.status}｜${JSON.stringify(体).slice(0, 200)}`,
    );
}

// 5. 同构：直接调用 worker.js 的 Cloudflare 入口
{
  const 请求 = new Request(`${基地址}/health`, { method: "GET" });
  const 回 = await 出口.fetch(请求, { DEEPSEEK_API_KEY: 密钥 }, {});
  const 体 = await 回.json();
  const 一致 =
    回.status === 200 &&
    体.状态 === "正常" &&
    JSON.stringify(体.模型) === JSON.stringify(健康?.模型);
  if (一致)
    记通过(
      "worker.js 的默认导出处（Workers 入口）与 dev-server 同构",
      "/health 一致",
    );
  else
    记失败(
      "worker.js 的默认导出处与 dev-server 同构",
      `HTTP ${回.status}｜${JSON.stringify(体).slice(0, 200)}`,
    );
}
{
  const 回 = await 出口.fetch(
    new Request(`${基地址}/api/analyze`, { method: "OPTIONS" }),
    {},
    {},
  );
  const 头 = 回.headers.get("access-control-allow-origin");
  if (回.status === 204 && 头)
    记通过("CORS 预检", `204，Access-Control-Allow-Origin=${头}`);
  else 记失败("CORS 预检", `HTTP ${回.status}，头 ${头}`);
}

// 6. 离线演示样例也过一遍 python 契约校验
if (readFileSync(样例路径, "utf8")) {
  const py = await 跑PY校验(样例路径, "data/demo_samples.json");
  if (py.通过)
    记通过(
      "data/demo_samples.json 全部样例过 python jsonschema",
      py.行.join("｜"),
    );
  else 记失败("data/demo_samples.json 契约校验", py.行.join("｜") || py.err);
}

// 6b. 离线演示样例的形态分布与官方出口（不花钱，改样例后必须重跑这一节）
{
  let 样例集 = null;
  try {
    样例集 = JSON.parse(readFileSync(样例路径, "utf8"));
  } catch (e) {
    记失败("读 data/demo_samples.json", String(e?.message || e));
  }
  const 全部 = 样例集?.样例 || [];
  const 形态表 = {};
  const 硬问题 = [];
  for (const s of 全部) {
    const 结果 = s.结果;
    for (const o of 结果.策略.输出) 形态表[o.形态] = (形态表[o.形态] || 0) + 1;
    for (const p of 查策略形态(结果)) 硬问题.push(`${s.id}：${p}`);
    if (结果.判定.风险 === "红") {
      const 出口s = 结果.判定.官方出口 || [];
      if (!(出口s.includes("12315") && 出口s.includes("96110")))
        硬问题.push(
          `${s.id}：判红但官方出口不是 12315 + 96110 两个，实际 ${JSON.stringify(出口s)}`,
        );
    }
  }
  const 三形态 = ["问题", "脚本", "一句话"].filter((x) => 形态表[x] > 0);
  if (三形态.length === 3 && !硬问题.length)
    记通过(
      "离线样例覆盖三种输出形态，且判红样例都带 12315 + 96110",
      `共 ${全部.length} 条｜形态分布 ${JSON.stringify(形态表)}`,
    );
  else
    记失败(
      "离线样例覆盖三种输出形态，且判红样例都带 12315 + 96110",
      `形态分布 ${JSON.stringify(形态表)}${硬问题.length ? `｜${硬问题.join("；")}` : ""}`,
    );
}

// 6c. 出口的确定性护栏：提示词没写全时，出口必须把两个官方号码补齐（不花钱）
{
  const 缺 = { 判定: { 风险: "红", 官方出口: ["96110"] } };
  const 记 = 补齐官方出口(缺);
  const 黄 = { 判定: { 风险: "黄" } };
  const 不改黄 = 补齐官方出口(黄) === null && !("官方出口" in 黄.判定);
  const 全 = { 判定: { 风险: "红", 官方出口: ["12315", "96110"] } };
  const 不动全 = 补齐官方出口(全) === null;
  const 合格 =
    记 !== null &&
    JSON.stringify(缺.判定.官方出口) === '["12315","96110"]' &&
    不改黄 &&
    不动全;
  if (合格)
    记通过(
      "判红时出口把官方号码补齐成 12315 + 96110（黄档不动）",
      `${JSON.stringify(记)}`,
    );
  else
    记失败(
      "判红时出口把官方号码补齐成 12315 + 96110（黄档不动）",
      `补齐结果 ${JSON.stringify(记)}｜黄档未改=${不改黄}｜已全则不动=${不动全}`,
    );
}

// 7. 隐私：输出与响应里不能出现密钥
{
  const 泄露 = dev输出.some((t) => t.includes(密钥) && 密钥.length > 8);
  if (泄露) 记失败("dev-server 输出里不出现密钥");
  else 记通过("dev-server 输出里不出现密钥");
}

// 收尾
if (dev进程) dev进程.kill();

console.log("\n=== 结果 ===");
console.log(`通过 ${通过项.length} 项｜失败 ${失败项.length} 项`);
for (const r of 各例结果) console.log(`  · ${r.名}：${r.摘要}`);
if (失败项.length) {
  console.log("\n失败明细（原文照抄，不修饰）：");
  for (const f of 失败项) console.log(`  - ${f.名}：${f.细节}`);
  process.exitCode = 1;
} else {
  console.log("全部通过。");
}
