/* worker/validator.js — LuCDA 输出契约校验器（JSON Schema 子集，零依赖）
 *
 * 为什么自己写：Cloudflare Workers 运行时不能装依赖；Node 侧测试要能复用同一份代码。
 * 覆盖 schema/annotation.schema.json 实际用到的关键字：
 *   $ref / $defs / type / enum / const / required / properties / additionalProperties /
 *   items / minItems / maxItems / minLength / minimum / maximum / allOf / oneOf / not / if-then-else
 *
 * 边界：这是校验器，不是判定器。它只回答「这份 JSON 是否合契约」（执行指令 §6.6），
 * 不判断任何内容真假（执行指令 §1.3）。
 *
 * 用法：
 *   import { validateInstance } from "./validator.js";
 *   const r = validateInstance(结果, ANNOTATION_SCHEMA);
 *   // r = { valid: boolean, errors: ["判定.官方出口：…", …] }
 */

const MAX_DEPTH = 60;

function kindOf(v) {
  if (v === null) return "null";
  if (Array.isArray(v)) return "array";
  if (typeof v === "number") return Number.isInteger(v) ? "integer" : "number";
  return typeof v; // string | boolean | object | undefined
}

function typeMatches(expected, actual) {
  if (expected === "integer") return actual === "integer";
  if (expected === "number") return actual === "integer" || actual === "number";
  return expected === actual;
}

function short(v) {
  let s;
  try {
    s = typeof v === "string" ? v : JSON.stringify(v);
  } catch {
    s = String(v);
  }
  if (s === undefined) s = String(v);
  if (s.length > 60) s = s.slice(0, 60) + "…";
  return s;
}

function join(path, key) {
  return path ? path + "." + key : key;
}

function index(path, i) {
  return path + "[" + i + "]";
}

/** 只支持内部引用 #/$defs/xxx —— 本契约只用这一种。 */
function resolveRef(ref, root) {
  const m = /^#\/(\$defs)\/(.+)$/.exec(String(ref));
  if (!m) return null;
  const defs = root && root.$defs;
  if (!defs || !Object.hasOwn(defs, m[2])) return null;
  return { schema: defs[m[2]], path: "$defs." + m[2] };
}

function test(instance, schema, root) {
  const errs = [];
  walk(instance, schema, "", root, errs, 0);
  return { valid: errs.length === 0, errors: errs };
}

function walk(instance, schema, path, root, errs, depth) {
  if (depth > MAX_DEPTH) {
    errs.push((path || "根") + "：嵌套过深，校验中止");
    return;
  }
  if (schema === true || schema === undefined || schema === null) return;
  if (schema === false) {
    errs.push((path || "根") + "：契约禁止该字段");
    return;
  }
  if (typeof schema !== "object" || Array.isArray(schema)) return;

  if (schema.$ref) {
    const r = resolveRef(schema.$ref, root);
    if (!r) {
      errs.push(join(path, "$ref") + "：无法解析引用 " + short(schema.$ref));
      return;
    }
    walk(instance, r.schema, path, root, errs, depth + 1);
    return;
  }

  // if / then / else（判定层与 meta 层用它表达跨字段约束）
  if (Object.hasOwn(schema, "if")) {
    const cond = test(instance, schema.if, root);
    if (cond.valid && schema.then)
      walk(instance, schema.then, path, root, errs, depth + 1);
    else if (!cond.valid && schema.else)
      walk(instance, schema.else, path, root, errs, depth + 1);
    if (!Object.hasOwn(schema, "then") && !schema.else) {
      // 只有 if 没有 then：不做任何约束
    }
  }

  if (Array.isArray(schema.allOf)) {
    for (const sub of schema.allOf)
      walk(instance, sub, path, root, errs, depth + 1);
  }

  if (Array.isArray(schema.oneOf) || Array.isArray(schema.anyOf)) {
    const branches = schema.oneOf || schema.anyOf;
    const results = branches.map((b) => test(instance, b, root));
    const okCount = results.filter((r) => r.valid).length;
    if (okCount === 0) {
      const best = results
        .slice()
        .sort((a, b) => a.errors.length - b.errors.length)[0];
      errs.push(
        (path || "根") +
          "：不符合契约给出的任何一种写法。最接近的写法差在 —— " +
          (best && best.errors.length ? best.errors.join("；") : "无可读差异"),
      );
    } else if (okCount > 1) {
      errs.push((path || "根") + "：同时符合契约的多种写法，写法必须唯一");
    }
  }

  if (Object.hasOwn(schema, "not")) {
    const r = test(instance, schema.not, root);
    if (r.valid) errs.push((path || "根") + "：命中了契约明确禁止的写法");
  }

  if (schema.const !== undefined) {
    if (instance !== schema.const) {
      errs.push(
        (path || "根") +
          "：取值必须为「" +
          short(schema.const) +
          "」，实际为「" +
          short(instance) +
          "」",
      );
    }
  }

  if (Array.isArray(schema.enum)) {
    if (!schema.enum.some((v) => v === instance)) {
      errs.push(
        (path || "根") +
          "：取值必须是 " +
          schema.enum.map((v) => "「" + short(v) + "」").join(" / ") +
          " 之一，实际为「" +
          short(instance) +
          "」",
      );
    }
  }

  const actual = kindOf(instance);

  if (schema.type !== undefined) {
    const want = Array.isArray(schema.type) ? schema.type : [schema.type];
    if (!want.some((t) => typeMatches(t, actual, instance))) {
      errs.push(
        (path || "根") +
          "：类型应为 " +
          want.join(" / ") +
          "，实际为 " +
          actual,
      );
      return; // 类型不符时后面的关键字必然连带失败，不重复报
    }
  }

  if (typeof instance === "string") {
    if (
      typeof schema.minLength === "number" &&
      instance.length < schema.minLength
    ) {
      errs.push(
        (path || "根") +
          "：至少要 " +
          schema.minLength +
          " 个字符，实际 " +
          instance.length +
          " 个",
      );
    }
    if (
      typeof schema.maxLength === "number" &&
      instance.length > schema.maxLength
    ) {
      errs.push(
        (path || "根") +
          "：最多 " +
          schema.maxLength +
          " 个字符，实际 " +
          instance.length +
          " 个",
      );
    }
    if (
      typeof schema.pattern === "string" &&
      !new RegExp(schema.pattern).test(instance)
    ) {
      errs.push((path || "根") + "：不符合要求的写法");
    }
  }

  if (typeof instance === "number") {
    if (typeof schema.minimum === "number" && instance < schema.minimum) {
      errs.push(
        (path || "根") + "：不能小于 " + schema.minimum + "，实际 " + instance,
      );
    }
    if (typeof schema.maximum === "number" && instance > schema.maximum) {
      errs.push(
        (path || "根") + "：不能大于 " + schema.maximum + "，实际 " + instance,
      );
    }
  }

  if (Array.isArray(instance)) {
    if (
      typeof schema.minItems === "number" &&
      instance.length < schema.minItems
    ) {
      errs.push(
        (path || "根") +
          "：至少要有 " +
          schema.minItems +
          " 项，实际 " +
          instance.length +
          " 项",
      );
    }
    if (
      typeof schema.maxItems === "number" &&
      instance.length > schema.maxItems
    ) {
      errs.push(
        (path || "根") +
          "：最多只能有 " +
          schema.maxItems +
          " 项，实际 " +
          instance.length +
          " 项",
      );
    }
    if (schema.items && !Array.isArray(schema.items)) {
      for (let i = 0; i < instance.length; i++) {
        walk(instance[i], schema.items, index(path, i), root, errs, depth + 1);
      }
    }
  }

  if (schema.properties && actual === "object") {
    for (const key of Object.keys(schema.properties)) {
      if (Object.hasOwn(instance, key)) {
        walk(
          instance[key],
          schema.properties[key],
          join(path, key),
          root,
          errs,
          depth + 1,
        );
      }
    }
  }

  if (Array.isArray(schema.required) && actual === "object") {
    for (const key of schema.required) {
      if (!Object.hasOwn(instance, key)) {
        errs.push((path || "根") + "：缺少必填字段 " + key);
      }
    }
  }

  if (actual === "object") {
    const props = schema.properties || {};
    if (schema.additionalProperties === false) {
      for (const key of Object.keys(instance)) {
        if (!Object.hasOwn(props, key)) {
          errs.push((path || "根") + "：出现契约未定义的字段 " + key);
        }
      }
    } else if (
      schema.additionalProperties &&
      typeof schema.additionalProperties === "object"
    ) {
      for (const key of Object.keys(instance)) {
        if (!Object.hasOwn(props, key)) {
          walk(
            instance[key],
            schema.additionalProperties,
            join(path, key),
            root,
            errs,
            depth + 1,
          );
        }
      }
    }
  }
}

/**
 * @param {unknown} instance 待校验的对象
 * @param {object} schema 契约（默认由调用方传入 worker/schema.js 的 ANNOTATION_SCHEMA）
 * @returns {{valid: boolean, errors: string[]}}
 */
export function validateInstance(instance, schema) {
  const errs = [];
  const root = schema && typeof schema === "object" ? schema : {};
  walk(instance, root, "", root, errs, 0);
  return { valid: errs.length === 0, errors: errs };
}
