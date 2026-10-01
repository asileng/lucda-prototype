"""worker/make_test_image.py — 造一张假的保健品包装图，供图片模态联调与离线样例使用。

为什么要有它：图片模态要真跑 VLM，就必须有一张可复现的输入图。凭空找一张真图既不合规
也不可复现，所以用 PIL 现画一张。图中文字全部是自拟的，不对应任何真实产品。

图里刻意包含（执行指令 §7.3 让 VLM 去观察的那几项）：
  · 承诺强度：声称对 3 种病有改善作用
  · 资质表述：全图没有任何批准文号 / 生产许可 / 备案编号一类的字（故意的，用来验证
    「材料里没有找到 X」这类观察，而不是「X 是假的」这类核查，§1.3）
  · 专家形象元素：白大褂人形 + 荣誉证书墙
  · 价格牌与赠品：买三盒送一盒
  · 社会认同：已有 3800 位老客户
  · 稀缺：今天最后一天

用法：
  "D:/anaconda/miniconda3/python.exe" worker/make_test_image.py [输出路径]
默认输出：worker/test_image.png
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFont

FONT_PATH = r"C:/Windows/Fonts/msyh.ttc"


def font(size):
  return ImageFont.truetype(FONT_PATH, size, index=0)


W, H = 1000, 1400
BG = (250, 248, 243)
INK = (28, 32, 38)
RED = (176, 42, 42)
GRAY = (120, 124, 130)


def text(d, xy, s, f, fill=INK, anchor="la"):
  d.text(xy, s, font=f, fill=fill, anchor=anchor)


def box(d, xy, radius=10, outline=(196, 190, 178), width=3, fill=None):
  d.rounded_rectangle(xy, radius=radius, outline=outline, width=width, fill=fill)


def white_coat_expert(d, x, y):
  """白大褂人形：一个圆头 + 一件白大褂 + 一条听诊器线。"""
  # 头
  d.ellipse((x + 42, y, x + 118, y + 76), fill=(226, 205, 184), outline=GRAY, width=3)
  # 白大褂
  d.rounded_rectangle(
    (x + 18, y + 82, x + 142, y + 226),
    radius=16,
    fill=(255, 255, 255),
    outline=GRAY,
    width=3,
  )
  # 衣襟
  d.line((x + 80, y + 92, x + 80, y + 222), fill=(210, 210, 210), width=3)
  # 听诊器
  d.line((x + 56, y + 108, x + 56, y + 150), fill=GRAY, width=4)
  d.line((x + 104, y + 108, x + 104, y + 150), fill=GRAY, width=4)
  d.ellipse((x + 40, y + 146, x + 120, y + 168), outline=GRAY, width=4)
  d.ellipse((x + 100, y + 158, x + 118, y + 176), fill=GRAY)


def cert_wall(d, x, y):
  """荣誉证书墙：三张并排的证书框。"""
  for i in range(3):
    bx = x + i * 96
    box(
      d, (bx, y, bx + 80, y + 62), radius=6, outline=RED, width=3, fill=(255, 253, 246)
    )
    text(d, (bx + 40, y + 10), "荣誉", font(20), fill=RED, anchor="ma")
    text(d, (bx + 40, y + 36), "证书", font(20), fill=RED, anchor="ma")


def main():
  out = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_image.png")
  )

  img = Image.new("RGB", (W, H), BG)
  d = ImageDraw.Draw(img)

  # 外框
  box(d, (16, 16, W - 16, H - 16), radius=18, outline=(206, 198, 184), width=4)

  # 品名与规格
  text(d, (56, 56), "康寿源", font(46), fill=RED)
  text(d, (56, 118), "灵芝孢子粉胶囊", font(58))
  text(d, (56, 196), "规格：0.45g × 60 粒 / 盒", font(28), fill=GRAY)

  d.line((56, 250, W - 56, 250), fill=(212, 204, 190), width=3)

  # 承诺强度：三种病
  box(
    d,
    (56, 282, W - 56, 486),
    radius=12,
    outline=(206, 198, 184),
    width=3,
    fill=(255, 255, 255),
  )
  text(d, (84, 306), "适用人群", font(34), fill=RED)
  text(d, (84, 364), "对糖尿病、高血压、失眠有改善作用", font(36))
  text(d, (84, 424), "每日两粒，四十天为一个周期", font(28), fill=GRAY)

  # 专家形象 + 证书墙
  white_coat_expert(d, 74, 528)
  text(d, (232, 540), "专家组推荐配方", font(40))
  text(d, (232, 600), "由保健品行业协会", font(26), fill=GRAY)
  text(d, (232, 636), "组织专家评审", font(26), fill=GRAY)
  cert_wall(d, 232, 682)

  # 社会认同 + 稀缺
  box(
    d,
    (56, 940, W - 56, 1068),
    radius=12,
    outline=(222, 176, 96),
    width=3,
    fill=(255, 251, 240),
  )
  text(d, (84, 964), "已有 3800 位老客户在用", font(36))
  text(d, (84, 1018), "今天最后一天，明日恢复原价", font(34), fill=RED)

  # 价格牌与赠品
  box(
    d,
    (56, 1100, W - 56, 1210),
    radius=12,
    outline=(206, 198, 184),
    width=3,
    fill=(255, 255, 255),
  )
  text(d, (84, 1124), "买三盒送一盒", font(40), fill=RED)
  text(d, (84, 1176), "每盒 298 元", font(32), fill=GRAY)

  # 底部：只有电话，没有任何资质表述
  text(d, (56, 1256), "咨询电话：138-0000-0000", font(30), fill=GRAY)
  text(
    d, (56, 1300), "本图为演示用虚构包装，非真实商品", font(24), fill=(160, 160, 160)
  )

  img.save(out, "PNG")
  print(
    "已生成 " + out + " " + str(img.size) + " " + str(os.path.getsize(out)) + " 字节"
  )


if __name__ == "__main__":
  main()
