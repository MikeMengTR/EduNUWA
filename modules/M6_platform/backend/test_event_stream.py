# -*- coding: utf-8 -*-
"""event_stream 增量解析器与原 _parse_demo_response 的等价性测试。

三方对比：原实现冻结副本 ≡ parse_demo_text 全文解析 ≡ 随机 chunk 切片经
LineAssembler 增量喂入。任何一处不等价都说明重构破坏了 course.py 等调用方。

运行: D:\\anaconda3\\envs\\edu\\python.exe modules\\M6_platform\\backend\\test_event_stream.py
"""
import random
import re
import sys

from event_stream import LineAssembler, DemoEventParser, parse_demo_text


# ---------------- 原实现冻结副本（来自 pipeline.py，重构前逐字拷贝） ----------------

_BOARD_ACTION_ALIAS = {
    "write_definition": "write_subtitle",
    "definition": "write_subtitle",
    "write_highlight": "write_bullets",
    "write_note": "write_bullets",
    "note": "write_bullets",
}


def _parse_demo_response_reference(text):
    events = []
    seq = 0
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        m = re.match(r'\[speak\]\s*(.+)', line, re.IGNORECASE)
        if m:
            seq += 1
            events.append({"seq": seq, "type": "speak", "text": m.group(1).strip()})
            continue
        m = re.match(r'\[board:(\w+)\]\s*(.*)', line, re.IGNORECASE)
        if m:
            content = m.group(2).strip()
            if content:
                seq += 1
                action = m.group(1).lower()
                action = _BOARD_ACTION_ALIAS.get(action, action)
                events.append({"seq": seq, "type": "board", "action": action, "content": content})
            continue
        m = re.match(r'\[board\]\s*(.+)', line, re.IGNORECASE)
        if m:
            seq += 1
            events.append({"seq": seq, "type": "board", "action": "write_bullets", "content": m.group(1).strip()})
            continue
        m = re.match(r'\[formula\]\s*(.*)', line, re.IGNORECASE)
        if m:
            buf = m.group(1)
            while i < len(lines) and not lines[i].lstrip().startswith('['):
                buf += "\n" + lines[i]
                i += 1
            latex = " ".join(buf.replace("$$", " ").replace("$", " ").split()).strip()
            if latex:
                seq += 1
                events.append({"seq": seq, "type": "formula", "latex": latex, "display_mode": True})
            continue
        m = re.match(r'\[table\]\s*(.+)', line, re.IGNORECASE)
        if m:
            parts = [p.strip() for p in m.group(1).split('|') if p.strip()]
            if len(parts) >= 2:
                seq += 1
                events.append({
                    "seq": seq, "type": "table",
                    "title": parts[0],
                    "columns": [c.strip() for c in parts[1].split(',')],
                    "rows": [[c.strip() for c in r.split(',')] for r in parts[2:]],
                })
            continue
        if re.match(r'\[pause\]', line, re.IGNORECASE):
            seq += 1
            events.append({"seq": seq, "type": "pause", "duration_sec": 1.5})
            continue
    return events


# ---------------- 测试样本 ----------------

SAMPLES = {
    "典型完整输出": """[speak] 同学们好，今天我们来学习正态分布。
[board:write_title] 正态分布
[speak] 它的概率密度函数请看黑板。
[formula] $$f(x)=\\frac{1}{\\sqrt{2\\pi}\\sigma}e^{-\\frac{(x-\\mu)^2}{2\\sigma^2}}$$
[board:write_bullets] 均值 μ 决定分布中心 | 标准差 σ 决定离散程度
[table] 常见分布对比 | 分布,均值,方差 | 正态分布,μ,σ² | 均匀分布,(a+b)/2,(b-a)²/12
[pause]
[speak] 以上就是本节的核心内容。""",

    "多行公式夹空行": """[speak] 看这个分段函数。
[formula] $$f(x) = \\begin{cases}

x^2 & x > 0 \\\\
0 & x \\le 0
\\end{cases}$$

[speak] 注意分界点。""",

    "公式收尾被截断": """[speak] 推导如下。
[formula] $$\\int_0^1 x\\,dx
= \\frac{1}{2}""",

    "非标准板书类型与空内容": """[board:write_definition] 期望的定义
[board:note] 这是注记
[board:write_steps]
[board] 默认要点
[BOARD:WRITE_TITLE] 大小写混合""",

    "空公式与连续公式": """[formula] $$$$
[formula] $$a+b$$
[formula]
[speak] 完。""",

    "table 边界": """[table] 只有标题
[table] 标题 | 列1,列2
[table] 标题 | 列1,列2 | a,b | c,d""",

    "正文混入无标签行": """这是一段没有标签的闲聊。
[speak] 正式开始。
继续闲聊，应被忽略。
[board:write_title] 标题""",

    "image无catalog全丢弃": """[speak] 看这张图。
[image] IMG_math_0001 | 注意切线
[board:write_title] 导数
[image] IMG_fake_9999
[speak] 完。""",

    "尾部无换行截断半行": "[speak] 第一句。\n[speak] 第二句没有结",

    "空输入": "",

    "只有空白": "\n  \n\t\n",
}


def random_chunks(text, rng):
    """把文本随机切成 1~8 字符的小块，模拟 LLM 流式输出。"""
    chunks = []
    i = 0
    while i < len(text):
        n = rng.randint(1, 8)
        chunks.append(text[i:i + n])
        i += n
    return chunks


def parse_streamed(text, rng):
    asm = LineAssembler()
    parser = DemoEventParser()
    events = []
    for chunk in random_chunks(text, rng):
        for line in asm.feed(chunk):
            events.extend(parser.feed_line(line))
    events.extend(parser.feed_line(asm.flush()))
    events.extend(parser.finish())
    return events


def main():
    rng = random.Random(20260610)
    failures = 0
    for name, text in SAMPLES.items():
        ref = _parse_demo_response_reference(text)
        full = parse_demo_text(text)
        ok_full = full == ref
        ok_stream = True
        for trial in range(20):  # 多轮随机切片
            streamed = parse_streamed(text, rng)
            if streamed != ref:
                ok_stream = False
                print(f"  [stream-mismatch trial={trial}]\n    ref={ref}\n    got={streamed}")
                break
        status = "PASS" if (ok_full and ok_stream) else "FAIL"
        if status == "FAIL":
            failures += 1
            if not ok_full:
                print(f"  [full-mismatch]\n    ref={ref}\n    got={full}")
        print(f"[{status}] {name}: {len(ref)} events")

    # ---- [image] 专项测试（参考实现不认识 [image]，不参与三方等价对比） ----
    catalog = {
        "IMG_math_0001": {"src": "/api/v1/media/math/IMG_math_0001.png",
                          "media_type": "static", "caption": "默认说明"},
    }
    image_text = """[speak] 看这张图。
[image] IMG_math_0001 | 注意切线只碰曲线一个点
[image] IMG_fake_9999 | 编造的ID应被丢弃
[image] IMG_math_0001
[board:write_title] 导数
[speak] 完。"""
    expected_image = [
        {"seq": 1, "type": "speak", "text": "看这张图。"},
        {"seq": 2, "type": "image", "image_id": "IMG_math_0001",
         "src": "/api/v1/media/math/IMG_math_0001.png", "media_type": "static",
         "caption": "注意切线只碰曲线一个点"},
        # IMG_fake_9999 被丢弃且不耗 seq
        {"seq": 3, "type": "image", "image_id": "IMG_math_0001",
         "src": "/api/v1/media/math/IMG_math_0001.png", "media_type": "static",
         "caption": "默认说明"},  # 无竖线说明 → 回退 catalog caption
        {"seq": 4, "type": "board", "action": "write_title", "content": "导数"},
        {"seq": 5, "type": "speak", "text": "完。"},
    ]
    got_full = parse_demo_text(image_text, image_catalog=catalog)
    ok_img_full = got_full == expected_image
    ok_img_stream = True
    for trial in range(20):
        asm2 = LineAssembler()
        p2 = DemoEventParser(image_catalog=catalog)
        got = []
        for chunk in random_chunks(image_text, rng):
            for line in asm2.feed(chunk):
                got.extend(p2.feed_line(line))
        got.extend(p2.feed_line(asm2.flush()))
        got.extend(p2.finish())
        if got != expected_image:
            ok_img_stream = False
            print(f"  [image-stream-mismatch trial={trial}]\n    exp={expected_image}\n    got={got}")
            break
    # 无 catalog：一切 [image] 行被丢弃（向后兼容默认）
    no_catalog = parse_demo_text(image_text)
    ok_img_drop = all(e["type"] != "image" for e in no_catalog) and len(no_catalog) == 3
    status = "PASS" if (ok_img_full and ok_img_stream and ok_img_drop) else "FAIL"
    if status == "FAIL":
        failures += 1
        if not ok_img_full:
            print(f"  [image-full-mismatch]\n    exp={expected_image}\n    got={got_full}")
        if not ok_img_drop:
            print(f"  [image-drop-mismatch] got={no_catalog}")
    print(f"[{status}] image catalog 解析: full={ok_img_full} stream={ok_img_stream} drop={ok_img_drop}")

    # 附加：用仓库里真实 demo events 的逆向文本不可得，改用大样本随机模糊
    fuzz_tags = ["[speak] ", "[board:write_title] ", "[board:bogus_type] ", "[board] ",
                 "[formula] $$", "[table] t | a,b | 1,2", "[pause]", "[image] IMG_x | c",
                 "", "  ", "plain"]
    for trial in range(200):
        n = rng.randint(0, 30)
        text = "\n".join(rng.choice(fuzz_tags) + ("x" * rng.randint(0, 5)) for _ in range(n))
        ref = _parse_demo_response_reference(text)
        if parse_demo_text(text) != ref or parse_streamed(text, rng) != ref:
            failures += 1
            print(f"[FAIL] fuzz trial={trial}\n  text={text!r}\n  ref={ref}")
            break
    else:
        print(f"[PASS] fuzz 200 trials")

    if failures:
        print(f"\n{failures} 处不等价，重构有问题")
        return 1
    print("\n全部等价 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
