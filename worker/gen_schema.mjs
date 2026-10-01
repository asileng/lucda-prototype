/* worker/gen_schema.mjs — 由 schema/annotation.schema.json 生成 worker/schema.js
 *
 * 契约的唯一真源是 schema/annotation.schema.json。本脚本只做复制，不做任何改写。
 * 用法：node worker/gen_schema.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const src = path.join(here, "..", "schema", "annotation.schema.json");
const dst = path.join(here, "schema.js");

function 读JSON(文件) {
 let 文本 = "";
 try {
  文本 = fs.readFileSync(文件, "utf8");
 } catch (e) {
  throw new Error(`读不到 ${文件}：${String(e?.message || e)}`);
 }
 try {
  return JSON.parse(文本);
 } catch (e) {
  throw new Error(`${文件} 不是合法 JSON：${String(e?.message || e)}`);
 }
}

const obj = 读JSON(src);

const header =
 "/* worker/schema.js — 输出契约的运行时副本（由 schema/annotation.schema.json 生成）\n" +
 " *\n" +
 " * 为什么复制一份：Cloudflare Workers 运行时不能读仓库文件，JSON 模块导入在 node 与\n" +
 " * esbuild 两边都要额外开关。生成一份 JS 对象最省事，两边行为一致。\n" +
 " *\n" +
 " * 唯一真源仍是 schema/annotation.schema.json。改契约请改原文件，然后重跑生成：\n" +
 " *   node worker/gen_schema.mjs\n" +
 " * tools/worker_test.mjs 每次运行都会比对两份是否一致，不一致直接判失败。\n" +
 " */\n\n" +
 "export const SCHEMA_SOURCE = " +
 JSON.stringify("schema/annotation.schema.json") +
 ";\n\n" +
 "export const ANNOTATION_SCHEMA = " +
 JSON.stringify(obj, null, 2) +
 ";\n";

fs.writeFileSync(dst, header);
console.log(
 "已生成 " + path.relative(process.cwd(), dst) + "，" + header.length + " 字节",
);
