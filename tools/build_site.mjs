// tools/build_site.mjs
// 把 web/ 构建成 GitHub Pages 的发布产物 docs/。
//
// 为什么要有这一步：
//   · 执行指令 §14 规定前端源码在 web/，不能改名；
//   · GitHub Pages 只能从仓库根或 /docs 发布；
//   · 本机 gh token 无 workflow scope，不能用 Actions（.github/workflows 会被拒）。
//   所以 web/ 是源码，docs/ 是产物 —— 这一步把前者复制成后者。
//
// 为什么要复制 data/：
//   web/app.js 里 fetch 的是相对路径 "data/xxx.json"，即假设 index.html 与 data/ 同级。
//   发布产物里 docs/index.html 与 docs/data/ 同级，路径才成立。
//
// 用法：node tools/build_site.mjs

import {
  cp,
  mkdir,
  readdir,
  rm,
  readFile,
  stat,
  writeFile,
} from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const WEB = path.join(ROOT, "web");
const DATA = path.join(ROOT, "data");
const DOCS = path.join(ROOT, "docs");

// 前端运行时真正会 fetch 的三个文件。少一个离线演示就会瘸。
const RUNTIME_DATA = ["demo_samples.json", "rag_index.json", "taboos.json"];

function kb(n) {
  return (n / 1024).toFixed(1) + " KB";
}

async function listFiles(dir, base = "") {
  const out = [];
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const rel = base ? base + "/" + e.name : e.name;
    if (e.isDirectory())
      out.push(...(await listFiles(path.join(dir, e.name), rel)));
    else out.push(rel);
  }
  return out;
}

async function main() {
  console.log("构建发布产物 docs/");
  console.log("  源  web/   →  " + DOCS);
  console.log("  源  data/  →  docs/data/");
  console.log("");

  if (!existsSync(path.join(WEB, "index.html"))) {
    console.error("✗ web/index.html 不存在，无法构建");
    process.exit(1);
  }

  // 清空 docs/ 的**内容**，但保留 docs/ 目录自身。
  // 为什么不用 rm(DOCS)：Windows 上如果有别的进程（编辑器、文件监视、残留的
  // 静态服务器）开着 docs/ 里的文件或把 docs/ 当工作目录，rmdir 会 EBUSY，
  // 整个构建就白跑。逐个删文件能把失败范围缩到单个文件，而且能重试。
  await mkdir(DOCS, { recursive: true });
  for (const e of await readdir(DOCS)) {
    await rm(path.join(DOCS, e), {
      recursive: true,
      force: true,
      maxRetries: 5,
      retryDelay: 200,
    });
  }

  // 1. web/ → docs/
  await cp(WEB, DOCS, { recursive: true });

  // 2. 前端运行时数据 → docs/data/
  await mkdir(path.join(DOCS, "data"), { recursive: true });
  const missing = [];
  for (const f of RUNTIME_DATA) {
    const src = path.join(DATA, f);
    if (!existsSync(src)) {
      missing.push(f);
      continue;
    }
    await cp(src, path.join(DOCS, "data", f));
  }
  if (missing.length) {
    console.error("✗ 缺少前端运行时数据：" + missing.join(", "));
    console.error("  离线演示模式会失效，构建中止。");
    process.exit(1);
  }

  // 3. 校验 index.html 引用的每个相对路径都能在 docs/ 里解析到
  const html = await readFile(path.join(DOCS, "index.html"), "utf8");
  const refs = [...html.matchAll(/(?:src|href)="([^"]+)"/g)]
    .map((m) => m[1])
    .filter(
      (u) =>
        !/^(https?:)?\/\//.test(u) &&
        !u.startsWith("data:") &&
        !u.startsWith("#"),
    );

  const broken = [];
  for (const r of refs) {
    const p = path.join(DOCS, r.replace(/^\.\//, ""));
    if (!existsSync(p)) broken.push(r);
  }
  if (broken.length) {
    console.error("✗ docs/index.html 引用了不存在的路径：" + broken.join(", "));
    process.exit(1);
  }

  // 4. 校验 app.js 里 fetch 的相对路径也能解析到
  const appjs = await readFile(path.join(DOCS, "app.js"), "utf8");
  const fetches = [...appjs.matchAll(/fetch\(\s*['"]([^'"]+)['"]/g)].map(
    (m) => m[1],
  );
  const brokenFetch = [];
  for (const f of fetches) {
    if (/^https?:/.test(f)) continue;
    if (!existsSync(path.join(DOCS, f.replace(/^\.\//, ""))))
      brokenFetch.push(f);
  }
  if (brokenFetch.length) {
    console.error(
      "✗ docs/app.js fetch 的路径在 docs/ 里不存在：" + brokenFetch.join(", "),
    );
    process.exit(1);
  }

  // 5. 清单
  const files = await listFiles(DOCS);
  console.log("产物清单（" + files.length + " 个文件）：");
  let total = 0;
  for (const f of files.sort()) {
    const s = (await stat(path.join(DOCS, f))).size;
    total += s;
    console.log(
      "  " + String(s).padStart(9) + "  " + kb(s).padStart(9) + "  docs/" + f,
    );
  }
  console.log("");
  console.log("合计 " + kb(total));
  console.log(
    "校验通过：index.html 引用 " +
      refs.length +
      " 条、app.js fetch " +
      fetches.length +
      " 条，全部可解析。",
  );
  console.log("✓ 构建完成 —— 可用 npm run serve 预览 docs/");
}

main().catch((e) => {
  console.error("构建失败：" + (e && e.stack ? e.stack : e));
  process.exit(1);
});
