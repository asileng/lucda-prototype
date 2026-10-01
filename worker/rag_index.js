/* worker/rag_index.js — 依据清单的运行时副本（由 data/rag_index.json 生成）
 *
 * 唯一真源是 data/rag_index.json。改索引请改原文件，然后重跑：node worker/gen_index.mjs
 * 生成时只保留 可核实性 = 已核实 的文献条目，见 worker/gen_index.mjs 的处理口径。
 */

export const 依据索引 = {
  理论层: [
    {
      索引ID: "L1-three-dim",
      名称: "三维框架",
      一句话:
        "看一段话怎么给事件命名、怎么定性、怎么评价——命名方式本身就在做完形填空。",
    },
    {
      索引ID: "L1-presupposition",
      名称: "预设",
      一句话: "没被说出口、却被当成前提的内容；反驳对方要先反驳那个前提。",
    },
    {
      索引ID: "L1-certainty",
      名称: "信息确定性",
      一句话: "用不留余地的断然表述替代概率表述，把「可能」说成「就是」。",
    },
    {
      索引ID: "L1-emotion",
      名称: "情绪引导",
      一句话: "用恐惧、内疚、希望、归属感推动决定，让人来不及核对内容。",
    },
    {
      索引ID: "L1-elaboration",
      名称: "说服的加工路径（中心 / 边缘）",
      一句话:
        "中心路径靠理据，需要对方有动机有能力加工；边缘路径靠情感、紧迫、从众、人际线索。推销者对老人全用边缘路径。",
    },
    {
      索引ID: "L1-six-levers",
      名称: "六杠杆",
      一句话: "权威、稀缺、社会认同、承诺一致、互惠、喜好——凭什么让你信。",
    },
    {
      索引ID: "L1-attribution",
      名称: "归属（正在施放 / 已对我生效）",
      一句话:
        "同一个杠杆，话是推销者说的还是我说的，意思相反：前者是「他在做什么」，后者是「我被说到哪一步」。",
    },
  ],
  文献层: [
    {
      索引ID: "L2-cialdini-1984",
      标题: "Influence: The Psychology of Persuasion",
      作者: "Robert B. Cialdini",
      年份: 1984,
    },
    {
      索引ID: "L2-petty-cacioppo-1986",
      标题: "The Elaboration Likelihood Model of Persuasion",
      作者: "Richard E. Petty, John T. Cacioppo",
      年份: 1986,
    },
    {
      索引ID: "L2-levinson-1983",
      标题: "Pragmatics（第 4 章 Presupposition）",
      作者: "Stephen C. Levinson",
      年份: 1983,
    },
    {
      索引ID: "L2-witte-1992",
      标题: "Putting the fear back into fear appeals: The extended parallel process model",
      作者: "Kim Witte",
      年份: 1992,
    },
    {
      索引ID: "L2-hyland-1998",
      标题: "Hedging in Scientific Research Articles",
      作者: "Ken Hyland",
      年份: 1998,
    },
    {
      索引ID: "L2-fairclough-1993",
      标题: "Critical discourse analysis and the marketization of public discourse: the universities",
      作者: "Norman Fairclough",
      年份: 1993,
    },
    {
      索引ID: "L2-vandijk-1980",
      标题: "Macrostructures: An Interdisciplinary Study of Global Structures in Discourse, Interaction, and Cognition",
      作者: "Teun A. van Dijk",
      年份: 1980,
    },
    {
      索引ID: "L2-leixiaoyan-2022",
      标题: "数字时代中国老年人被诈骗研究——互联网与数字普惠金融的作用",
      作者: "雷晓燕、沈艳、杨玲",
      年份: 2022,
    },
    {
      索引ID: "L2-wangziwei-2025",
      标题: "健康类谣言文章与科普文章的话语特征对比研究",
      作者: "王梓维",
      年份: 2025,
    },
    {
      索引ID: "L2-fengyajun-2022",
      标题: "微信健康类谣言传播的话语特征与影响路径研究",
      作者: "冯亚军",
      年份: 2022,
    },
    {
      索引ID: "L2-luozhengfeng-2017",
      标题: "微信健康类谣言的框架特征及其心理动力机制探析",
      作者: "罗政锋、韩隽",
      年份: 2017,
    },
    {
      索引ID: "L2-diaohe-2019",
      标题: "互联网环境中养生健康「误传播」现象研究",
      作者: "刁鹤",
      年份: 2019,
    },
    {
      索引ID: "L2-anter-2025",
      标题: "Older Adults' Information Use on Social Media: The Role of Psychological Needs and Personality Traits",
      作者: "Luise Anter, Martin Fischer, Anna Sophie Kümpel",
      年份: 2025,
    },
    {
      索引ID: "L2-dingxing-2025",
      标题: "Trust in AI vs. human doctors: The roles of subjective understanding, perceived epistemic authority and social proof",
      作者: "Xiaotong Ding, Cai Xing",
      年份: 2025,
    },
    {
      索引ID: "L2-milella-2026",
      标题: "Perceiving AI as an Epistemic Authority or Algority: A User Study on the Human Attribution of Authority to AI",
      作者: "Frida Milella, Federico Cabitza",
      年份: 2026,
    },
    {
      索引ID: "L2-nickel-2022",
      标题: "Trust in medical artificial intelligence: a discretionary account",
      作者: "Philip J. Nickel",
      年份: 2022,
    },
    {
      索引ID: "L2-lizhaoxue-2026",
      标题: "Algorithm-associated digital addiction among older adults: mechanisms and public health implications for healthy aging",
      作者: "Zhaoxue Li, Xiaoyong Yu, Kan Tian",
      年份: 2026,
    },
    {
      索引ID: "L2-vines-2015",
      标题: "An Age-Old Problem: Examining the Discourses of Ageing in HCI and Strategies for Future Research",
      作者: "John Vines, Gary Pritchard, Peter Wright, Patrick Olivier, Katie Brittain",
      年份: 2015,
    },
  ],
  语料层: [
    {
      索引ID: "L3-s-01",
      线索: "最后三盒",
      片段: "这个我先给您留三盒，今天不定就给别人了。",
      说话人: "推销者",
      归属: "正在施放",
      来源: "自建样例（语料加工未完成）",
    },
    {
      索引ID: "L3-s-02",
      线索: "今天截止",
      片段: "这个价就今天，明天就恢复原价了。",
      说话人: "推销者",
      归属: "正在施放",
      来源: "自建样例（语料加工未完成）",
    },
    {
      索引ID: "L3-s-03",
      线索: "都在买",
      片段: "您看这儿，来的人都在买，一回都是好几盒。",
      说话人: "推销者",
      归属: "正在施放",
      来源: "自建样例（语料加工未完成）",
    },
    {
      索引ID: "L3-s-04",
      线索: "专家推荐",
      片段: "这个是院士那边研发的，专家推荐的配方。",
      说话人: "推销者",
      归属: "正在施放",
      来源: "自建样例（语料加工未完成）",
    },
    {
      索引ID: "L3-s-05",
      线索: "免费体验",
      片段: "先免费体验一次，觉得好您再说。",
      说话人: "推销者",
      归属: "正在施放",
      来源: "自建样例（语料加工未完成）",
    },
    {
      索引ID: "L3-s-06",
      线索: "送鸡蛋",
      片段: "来听就给十个鸡蛋，不要钱。",
      说话人: "推销者",
      归属: "正在施放",
      来源: "自建样例（语料加工未完成）",
    },
    {
      索引ID: "L3-s-07",
      线索: "阿姨您就像我亲妈",
      片段: "阿姨您就像我亲妈一样，我能害您吗。",
      说话人: "推销者",
      归属: "正在施放",
      来源: "自建样例（语料加工未完成）",
    },
    {
      索引ID: "L3-s-08",
      线索: "我很信任他",
      片段: "小李对我挺好的，我信他。",
      说话人: "我",
      归属: "已对我生效",
      来源: "自建样例（语料加工未完成）",
    },
    {
      索引ID: "L3-s-09",
      线索: "这个能治糖尿病",
      片段: "这个能治糖尿病，吃三个疗程就好了。",
      说话人: "推销者",
      归属: "正在施放",
      来源: "自建样例（语料加工未完成）",
    },
    {
      索引ID: "L3-s-10",
      线索: "不吃就晚了",
      片段: "您现在不吃，等严重了花的钱更多。",
      说话人: "推销者",
      归属: "正在施放",
      来源: "自建样例（语料加工未完成）",
    },
  ],
  线索索引: [
    {
      线索: "最后三盒",
      别名: ["只剩三盒", "不多了", "没几盒了"],
      理论: ["L1-six-levers"],
      文献: ["L2-cialdini-1984", "L2-leixiaoyan-2022"],
      语料例证: ["L3-s-01"],
    },
    {
      线索: "今天截止",
      别名: ["最后一天", "仅限今天", "今天不定就没了"],
      理论: ["L1-six-levers"],
      文献: ["L2-cialdini-1984"],
      语料例证: ["L3-s-02"],
    },
    {
      线索: "都在买",
      别名: ["邻居都用了", "买过的都说好", "好多人都买了"],
      理论: ["L1-six-levers"],
      文献: ["L2-cialdini-1984", "L2-dingxing-2025"],
      语料例证: ["L3-s-03"],
    },
    {
      线索: "专家推荐",
      别名: ["院士", "祖传", "AI 诊断", "教授", "研发"],
      理论: ["L1-six-levers"],
      文献: ["L2-dingxing-2025", "L2-milella-2026", "L2-nickel-2022"],
      语料例证: ["L3-s-04"],
    },
    {
      线索: "免费体验",
      别名: ["先尝一口", "不要钱试试", "先体验一次"],
      理论: ["L1-six-levers"],
      文献: ["L2-cialdini-1984"],
      语料例证: ["L3-s-05"],
    },
    {
      线索: "送鸡蛋",
      别名: ["送小礼品", "来听就给", "先拿点东西回去"],
      理论: ["L1-six-levers"],
      文献: ["L2-cialdini-1984"],
      语料例证: ["L3-s-06"],
    },
    {
      线索: "阿姨您就像我亲妈",
      别名: ["干女儿", "家人", "阿姨", "叔叔", "我一直惦记着您"],
      理论: ["L1-six-levers", "L1-emotion"],
      文献: ["L2-cialdini-1984"],
      语料例证: ["L3-s-07"],
    },
    {
      线索: "我很信任他",
      别名: ["我信他", "他对我挺好的", "我把他当自家人"],
      理论: ["L1-attribution", "L1-six-levers"],
      文献: ["L2-cialdini-1984"],
      语料例证: ["L3-s-08"],
    },
    {
      线索: "这个能治糖尿病",
      别名: ["能治好", "能治我的病", "吃几个疗程就好"],
      理论: ["L1-presupposition", "L1-certainty"],
      文献: ["L2-levinson-1983", "L2-hyland-1998", "L2-wangziwei-2025"],
      语料例证: ["L3-s-09"],
    },
    {
      线索: "不吃就晚了",
      别名: ["等严重了花钱更多", "再拖就没办法了", "你这个病拖不得"],
      理论: ["L1-emotion", "L1-six-levers"],
      文献: ["L2-witte-1992", "L2-luozhengfeng-2017", "L2-lizhaoxue-2026"],
      语料例证: ["L3-s-10", "L3-s-02"],
    },
    {
      线索: "健康类谣言的话语特征",
      别名: ["养生文章", "科普文章", "朋友圈转发"],
      理论: ["L1-three-dim", "L1-certainty"],
      文献: [
        "L2-wangziwei-2025",
        "L2-fengyajun-2022",
        "L2-luozhengfeng-2017",
        "L2-diaohe-2019",
        "L2-vandijk-1980",
      ],
      语料例证: [],
    },
    {
      线索: "老年人为什么更容易信",
      别名: ["老人好骗", "老人容易信", "老年人受骗"],
      理论: ["L1-elaboration", "L1-emotion"],
      文献: [
        "L2-leixiaoyan-2022",
        "L2-anter-2025",
        "L2-lizhaoxue-2026",
        "L2-vines-2015",
      ],
      语料例证: [],
    },
    {
      线索: "AI 说的话为什么更容易被信",
      别名: ["AI 诊断", "人工智能判断", "机器说的"],
      理论: ["L1-six-levers", "L1-elaboration"],
      文献: ["L2-dingxing-2025", "L2-milella-2026", "L2-nickel-2022"],
      语料例证: [],
    },
  ],
  未收录: ["L2-liulu", "L2-kerasidou-2026"],
  说明: "本清单只收录可核实性为「已核实」的文献；未收录条目不得出现在任何输出里。",
};

/** 渲染成提示词里的一段清单文本。只做排版，不改内容。 */
export function 索引清单文本() {
  const 行 = [];
  行.push("【理论层：溯源[].理论 只能从这里取】");
  for (const t of 依据索引.理论层)
    行.push(`${t.索引ID}｜${t.名称}｜${t.一句话}`);
  行.push("");
  行.push("【文献层：溯源[].文献 只能从这里取，写 标题/作者/年份/索引ID】");
  for (const w of 依据索引.文献层)
    行.push(`${w.索引ID}｜${w.标题}｜${w.作者}｜${w.年份}`);
  行.push("");
  行.push(
    "【语料层：溯源[].语料例证 只能从这里取，并注明「自建样例（语料加工未完成）」】",
  );
  for (const c of 依据索引.语料层) 行.push(`${c.索引ID}｜${c.线索}｜${c.片段}`);
  行.push("");
  行.push("【线索索引：先按线索或别名找，再用它给出的理论/文献/语料】");
  for (const c of 依据索引.线索索引) {
    const 别名 = c.别名.length ? `（也叫：${c.别名.join("、")}）` : "";
    行.push(
      `${c.线索}${别名}｜理论：${c.理论.join(",") || "无"}｜文献：${c.文献.join(",") || "无"}｜语料：${c.语料例证.join(",") || "无"}`,
    );
  }
  行.push("");
  行.push(`【本清单未收录、不得引用】${依据索引.未收录.join("、") || "无"}`);
  行.push(
    "清单里找不到对应条目的判断，就不要写进 溯源；宁少写，不编。溯源 至少要有一条。",
  );
  return 行.join("\n");
}
