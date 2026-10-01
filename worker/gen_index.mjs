/* worker/gen_index.mjs — 由 data/rag_index.json 生成 worker/rag_index.js（给提示词用的依据清单）
 *
 * 为什么要有它：提示词要求「文献只能引用给定索引里的条目」「溯源不出的内容删掉」。
 * 索引必须真的喂给模型，否则模型只能留空 溯源（实测第一版就是这样，校验直接不过）。
 *
 * 处理口径：
 *   · 文献层只放 可核实性 = 已核实 的条目；待核实的不喂给模型，避免被当成已确认出处引用
 *   · 线索索引里指向被排除文献的引用一并去掉
 *   · 语料层全部是自建样例，原样带上，并要求模型在 语料例证 里注明「自建样例（语料加工未完成）」
 *
 * 用法：node worker/gen_index.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const src = path.join(here, "..", "data", "rag_index.json");
const dst = path.join(here, "rag_index.js");

function 读索引(文件) {
 try {
  return JSON.parse(fs.readFileSync(文件, "utf8"));
 } catch (e) {
  throw new Error(`读不到 ${文件}：${String(e?.message || e)}`);
 }
}

const 索引 = 读索引(src);

const 已核实 = new Set(
 索引.文献层.filter((w) => w.可核实性 === "已核实").map((w) => w.id),
);
const 待核实 = 索引.文献层
 .filter((w) => w.可核实性 !== "已核实")
 .map((w) => w.id);

const 文献层 = 索引.文献层
 .filter((w) => 已核实.has(w.id))
 .map((w) => ({ 索引ID: w.id, 标题: w.标题, 作者: w.作者, 年份: w.年份 }));

const 线索索引 = 索引.线索索引.map((c) => ({
 线索: c.线索,
 别名: c.别名 || [],
 理论: c.理论 || [],
 文献: (c.文献 || []).filter((id) => 已核实.has(id)),
 语料例证: c.语料例证 || [],
}));

const 理论层 = 索引.理论层.map((t) => ({
 索引ID: t.id,
 名称: t.名称,
 一句话: t.一句话,
}));

const 语料层 = 索引.语料层.map((t) => ({
 索引ID: t.id,
 线索: t.线索,
 片段: t.片段,
 说话人: t.说话人,
 归属: t.归属,
 来源: t.来源,
}));

const payload = {
 理论层,
 文献层,
 语料层,
 线索索引,
 未收录: 待核实,
 说明:
  "本清单只收录可核实性为「已核实」的文献；未收录条目不得出现在任何输出里。",
};

const header =
 "/* worker/rag_index.js — 依据清单的运行时副本（由 data/rag_index.json 生成）\n" +
 " *\n" +
 " * 唯一真源是 data/rag_index.json。改索引请改原文件，然后重跑：node worker/gen_index.mjs\n" +
 " * 生成时只保留 可核实性 = 已核实 的文献条目，见 worker/gen_index.mjs 的处理口径。\n" +
 " */\n\n" +
 "export const 依据索引 = " +
 JSON.stringify(payload, null, 2) +
 ";\n\n" +
 "/** 渲染成提示词里的一段清单文本。只做排版，不改内容。 */\n" +
 "export function 索引清单文本() {\n" +
 "  const 行 = [];\n" +
 '  行.push("【理论层：溯源[].理论 只能从这里取】");\n' +
 "  for (const t of 依据索引.理论层) 行.push(`${t.索引ID}｜${t.名称}｜${t.一句话}`);\n" +
 '  行.push("");\n' +
 '  行.push("【文献层：溯源[].文献 只能从这里取，写 标题/作者/年份/索引ID】");\n' +
 "  for (const w of 依据索引.文献层) 行.push(`${w.索引ID}｜${w.标题}｜${w.作者}｜${w.年份}`);\n" +
 '  行.push("");\n' +
 '  行.push("【语料层：溯源[].语料例证 只能从这里取，并注明「自建样例（语料加工未完成）」】");\n' +
 "  for (const c of 依据索引.语料层) 行.push(`${c.索引ID}｜${c.线索}｜${c.片段}`);\n" +
 '  行.push("");\n' +
 '  行.push("【线索索引：先按线索或别名找，再用它给出的理论/文献/语料】");\n' +
 "  for (const c of 依据索引.线索索引) {\n" +
 '    const 别名 = c.别名.length ? `（也叫：${c.别名.join("、")}）` : "";\n' +
 "    行.push(\n" +
 '      `${c.线索}${别名}｜理论：${c.理论.join(",") || "无"}｜文献：${c.文献.join(",") || "无"}｜语料：${c.语料例证.join(",") || "无"}`\n' +
 "    );\n" +
 "  }\n" +
 '  行.push("");\n' +
 '  行.push(`【本清单未收录、不得引用】${依据索引.未收录.join("、") || "无"}`);\n' +
 '  行.push("清单里找不到对应条目的判断，就不要写进 溯源；宁少写，不编。溯源 至少要有一条。");\n' +
 '  return 行.join("\\n");\n' +
 "}\n";

fs.writeFileSync(dst, header);
console.log(
 `已生成 worker/rag_index.js：理论 ${理论层.length} 条｜文献 ${文献层.length} 条｜语料 ${语料层.length} 条｜线索 ${线索索引.length} 条｜排除待核实 ${待核实.length} 条`,
);
