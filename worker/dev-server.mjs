/* worker/dev-server.mjs — 本机答辩用同构代理
 *
 * 为什么要有它：GitHub Pages 是纯静态站，藏不住 key；答辩现场又不能保证能连上
 * Cloudflare。于是本机跑一个代理，路由与响应格式同 worker.js，前端把 API_BASE 指到
 * 本机地址即可（执行指令 §10.2、§6 铁律 12）。
 *
 * 与 worker.js 的关系：本文件不重复实现任何逻辑，直接 import worker.js 的路由表。
 * 两边跑的是同一份提示词、同一份契约、同一条降级路径。
 *
 * 用法：
 *   node worker/dev-server.mjs           # 默认 8787
 *   PORT=8899 node worker/dev-server.mjs
 *
 * 密钥：只从 process.env.DEEPSEEK_API_KEY 读，不打印、不落盘、不回显。
 * 语音：audio 分支与 worker 一致，返回明确的「未实现」，不伪造转写结果。
 */

import http from "node:http";
import { 路由, 造限流器, 跨域头, 默认上限 } from "./worker.js";

const 端口 = Number(process.env.PORT) > 0 ? Number(process.env.PORT) : 8787;
const 主机 = process.env.HOST || "127.0.0.1";

// 只把需要的变量显式传下去；不打印值。
const env = {
  DEEPSEEK_API_KEY: process.env.DEEPSEEK_API_KEY,
  ALLOWED_ORIGIN: process.env.ALLOWED_ORIGIN,
  RATE_LIMIT_PER_MINUTE: process.env.RATE_LIMIT_PER_MINUTE,
  UPSTREAM_TIMEOUT_MS: process.env.UPSTREAM_TIMEOUT_MS,
  MAX_OUTPUT_TOKENS: process.env.MAX_OUTPUT_TOKENS,
};

const 每分钟 =
  Number(env.RATE_LIMIT_PER_MINUTE) > 0
    ? Number(env.RATE_LIMIT_PER_MINUTE)
    : 默认上限.每分钟请求数;
const limiter = 造限流器({ 上限: 每分钟, 窗口毫秒: 默认上限.限流窗口毫秒 });

const 读请求体 = (req) =>
  new Promise((resolve, reject) => {
    const 块 = [];
    let 长度 = 0;
    req.on("data", (c) => {
      长度 += c.length;
      if (长度 > 默认上限.请求体字符 * 4) {
        reject(new Error("BODY_TOO_LARGE"));
        req.destroy();
        return;
      }
      块.push(c);
    });
    req.on("end", () => resolve(Buffer.concat(块).toString("utf8")));
    req.on("error", reject);
  });

const 服务器 = http.createServer(async (req, res) => {
  const 头 = 跨域头(env);
  const 路径 = (req.url || "/").split("?")[0];

  if (req.method === "OPTIONS") {
    res.writeHead(204, 头);
    res.end();
    return;
  }

  let bodyText = "";
  try {
    if (req.method === "POST") bodyText = await 读请求体(req);
  } catch (e) {
    const 说明 =
      e?.message === "BODY_TOO_LARGE"
        ? `请求体超过 ${默认上限.请求体字符} 字符。`
        : `读取请求体失败：${String(e?.message || e)}`;
    res.writeHead(e?.message === "BODY_TOO_LARGE" ? 413 : 400, {
      ...头,
      "content-type": "application/json; charset=utf-8",
    });
    res.end(
      JSON.stringify({
        状态: "拒绝",
        错误: {
          标记:
            e?.message === "BODY_TOO_LARGE"
              ? "BODY_TOO_LARGE"
              : "BODY_READ_ERROR",
          说明,
        },
      }),
    );
    return;
  }

  const 来源 = req.socket.remoteAddress || "unknown";
  const r = await 路由({
    method: req.method === "GET" ? "GET" : "POST",
    pathname: 路径,
    bodyText,
    env,
    clientIp: 来源,
    limiter,
    // 日志只记模态、长度、校验结果，不记用户输入（隐私）
    logger: (记) => console.log(JSON.stringify({ ...记, 来源: "dev-server" })),
  });

  res.writeHead(r.状态码, {
    ...头,
    "content-type": "application/json; charset=utf-8",
  });
  res.end(JSON.stringify(r.对象));
});

服务器.listen(端口, 主机, () => {
  const 有密钥 = Boolean(
    env.DEEPSEEK_API_KEY && String(env.DEEPSEEK_API_KEY).trim(),
  );
  console.log("LuCDA 本机答辩代理");
  console.log(`地址：http://${主机}:${端口}`);
  console.log("路由：POST /api/analyze ｜ GET /health");
  console.log(`限流：每 60 秒最多 ${每分钟} 次（按来源，进程内计数）`);
  console.log(
    有密钥
      ? "密钥：已从环境变量 DEEPSEEK_API_KEY 读取（值不打印）"
      : "密钥：没读到 DEEPSEEK_API_KEY —— /api/analyze 会返回 降级（NO_API_KEY），不会给判定",
  );
  console.log(
    "契约：schema/annotation.schema.json（模型返回必须过校验，否则降级）",
  );
  console.log("语音：audio 返回「未实现」，不伪造转写结果");
});
