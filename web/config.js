/* web/config.js — LuCDA 前端配置（执行指令 §10.2）
 *
 * 只放一个字段：出口地址。**这里绝对不放任何 key。**
 * GitHub Pages 是纯静态站，藏不住 key，所以公开站默认走离线演示模式（执行指令 §8.6）。
 *
 * 联网要做什么：
 *   1. 部署 worker/（Cloudflare Workers 或本机 node worker/dev-server.mjs）；
 *   2. 把它的地址填到下面 API_BASE，例如
 *        window.LUCDA_CONFIG = { API_BASE: "https://lucda-prototype.<你的账号>.workers.dev" };
 *      本机答辩填 http://127.0.0.1:8787 也可以；
 *   3. 留空字符串 = 离线演示模式：读 data/demo_samples.json，不发任何网络请求。
 *
 * key 只存在于 Worker 的环境变量里（wrangler secret put DEEPSEEK_API_KEY / 本机环境变量），
 * 前端拿不到、也不该拿到。
 */
window.LUCDA_CONFIG = { API_BASE: "" };
