/* worker/gen_prompt.mjs — 把 schema/prompt_contract.md §1 的 system prompt 逐字注入 worker.js
 *
 * 为什么用脚本注入：system prompt 是 3KB 左右的中文长文，手工复制粘贴必然出偏差。
 * 本脚本按契约文件里的围栏代码块抽取，逐字写入 worker.js 的两个标记之间，可反复重跑。
 * 抽取结果会打印长度与哈希，便于核对「注入的确实是契约原文」。
 *
 * 用法：node worker/gen_prompt.mjs
 */
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const contractPath = path.join(here, "..", "schema", "prompt_contract.md");
const workerPath = path.join(here, "worker.js");

export function extractSystemPrompt(md) {
 const start = md.indexOf("\n````text\n");
 if (start < 0)
  throw new Error("在 prompt_contract.md 里没有找到 `````text 围栏（§1）");
 const body = md.slice(start + "\n````text\n".length);
 const end = body.indexOf("\n````");
 if (end < 0) throw new Error("在 prompt_contract.md 里没有找到围栏结尾");
 const text = body.slice(0, end);
 const first = text.split("\n")[0].trim();
 const last = text.trimEnd().split("\n").pop().trim();
 if (!first.startsWith("你是一个"))
  throw new Error("抽取到的内容开头不对：" + first);
 if (last !== "自查完毕再输出。")
  throw new Error("抽取到的内容结尾不对：" + last);
 if (text.includes("`"))
  throw new Error(
   "prompt 正文里出现反引号，模板字符串不安全，需改用 JSON 注入",
  );
 if (text.includes("${"))
  throw new Error("prompt 正文里出现 ${，模板字符串不安全，需改用 JSON 注入");
 return text;
}

export function injectPrompt(workerSrc, prompt) {
 const 语句 =
  "/* 注入标记：下面这一条由 worker/gen_prompt.mjs 覆盖，内容取自 schema/prompt_contract.md §1 */\n" +
  "/* <<<PROMPT_CONTRACT_BEGIN>>> */\n" +
  "export const SYSTEM_PROMPT = String.raw`" +
  prompt +
  "`;\n" +
  "/* <<<PROMPT_CONTRACT_END>>> */";

 const 规范形态 =
  /\/\* <<<PROMPT_CONTRACT_BEGIN>>> \*\/[\s\S]*?\/\* <<<PROMPT_CONTRACT_END>>> \*\//;
 if (规范形态.test(workerSrc)) return workerSrc.replace(规范形态, 语句);

 // 兼容早期形态：标记夹在模板字符串里面
 const 旧形态 =
  /export const SYSTEM_PROMPT = String\.raw`<<<PROMPT_CONTRACT_BEGIN>>>[\s\S]*?<<<PROMPT_CONTRACT_END>>>`;/;
 if (旧形态.test(workerSrc)) return workerSrc.replace(旧形态, 语句);

 throw new Error("worker.js 里没有找到注入标记");
}

function main() {
 const md = fs.readFileSync(contractPath, "utf8");
 const prompt = extractSystemPrompt(md);
 const src = fs.readFileSync(workerPath, "utf8");
 const next = injectPrompt(src, prompt);
 fs.writeFileSync(workerPath, next);
 const hash = crypto
  .createHash("sha256")
  .update(prompt, "utf8")
  .digest("hex")
  .slice(0, 16);
 console.log(
  "已注入 system prompt：字数 " +
   prompt.length +
   "｜行数 " +
   prompt.split("\n").length +
   "｜sha256(前16) " +
   hash,
 );
}

if (
 process.argv[1] &&
 path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))
) {
 main();
}
