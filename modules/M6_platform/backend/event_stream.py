"""LLM 教学演示输出的增量解析与 SSE 编码。

把 pipeline._parse_demo_response 的按行解析改造成可增量调用的形态，
供 /api/v1/chat/<tid>/demo/stream 在 DeepSeek 流式生成过程中边收边解析。
pipeline._parse_demo_response 仍保留原签名（course.py 等离线调用方不变），
内部委托给本模块，两套实现必须逐事件等价（见 test_event_stream.py）。
"""
import json
import re


# 常见 LaTeX 命令 → 中文口播替换表
_LATEX_SUBS = [
    (r'\\frac\s*\{([^}]*)\}\s*\{([^}]*)\}', r'\1 分之 \2'),
    (r'\\sqrt\s*\{([^}]*)\}', r'根号 \1'),
    (r'\\sqrt\[([^\]]*)\]\s*\{([^}]*)\}', r'\1 次根号 \2'),
    (r'\\hat\s*\{([^}]*)\}', r'\1 估计值'),
    (r'\\sum', '求和'),
    (r'\\int', '积分'),
    (r'\\infty', '无穷大'),
    (r'\\pi', '派'),
    (r'\\alpha', '阿尔法'),
    (r'\\beta', '贝塔'),
    (r'\\gamma', '伽马'),
    (r'\\theta', '西塔'),
    (r'\\sigma', '西格玛'),
    (r'\\mu', '缪'),
    (r'\\lambda', '拉姆达'),
    (r'\\Delta', '德尔塔'),
    (r'\\rightarrow', '到'),
    (r'\\Rightarrow', '得到'),
    (r'\\approx', '约等于'),
    (r'\\neq', '不等于'),
    (r'\\leq', '小于等于'),
    (r'\\geq', '大于等于'),
    (r'\\cdot', '点乘'),
    (r'\\times', '乘'),
    (r'\\div', '除以'),
    (r'\\pm', '正负'),
    (r'\\partial', '偏'),
    (r'\\mathbb\{([^}]*)\}', r'\1'),
    (r'\\mathrm\{([^}]*)\}', r'\1'),
    (r'\\text\{([^}]*)\}', r'\1'),
]


def _latex_symbols_to_spoken(tex: str) -> str:
    """LaTeX 片段 → 中文口播（去定界符/命令/花括号，常见符号转中文）。无前缀、不截断。"""
    text = tex.replace("$$", " ").replace("$", " ")
    for pat, repl in _LATEX_SUBS:
        text = re.sub(pat, repl, text)
    text = re.sub(r'\\([a-zA-Z]+)', '', text)   # 去掉剩余的 \xxx 命令
    text = re.sub(r'[{}]', '', text)            # 去掉花括号
    return " ".join(text.split()).strip()       # 压缩空白


# 口播文本里残留的 markdown 粗体与内嵌公式定界符（AI 偶尔不遵守「speak 纯口语」约定，
# 写成 **均值 μ** 或 $\sigma^2$，TTS 会把符号念出来，需在送 TTS 前清洗）
_MD_BOLD = re.compile(r'\*\*(.+?)\*\*')
_INLINE_MATH = re.compile(
    r'\$\$(.+?)\$\$|\\\[(.+?)\\\]|\$([^$\n]+?)\$|\\\((.+?)\\\)',
    re.S,
)


def _clean_speak_text(text: str) -> str:
    """口播文本清洗：去 markdown 粗体标记、把内嵌 $...$/\\(...\\) 公式转中文口播，
    确保 TTS 念得干净（与前端字幕 renderMath 对应，但这里是给音频用的纯文本）。"""
    if not text:
        return text
    text = _MD_BOLD.sub(r'\1', text)            # **粗体** → 粗体（保留内容）

    def _sub_math(m):
        inner = next((g for g in m.groups() if g is not None), "")
        return _latex_symbols_to_spoken(inner) or " "

    text = _INLINE_MATH.sub(_sub_math, text)
    text = text.replace("**", "")               # 清掉残留的孤立 ** 标记
    cleaned = " ".join(text.split()).strip()
    return cleaned or text

# AI 常输出系统外的板书类型，映射到支持的类型，避免被丢弃
BOARD_ACTION_ALIAS = {
    "write_definition": "write_subtitle",
    "definition": "write_subtitle",
    "write_highlight": "write_bullets",
    "write_note": "write_bullets",
    "note": "write_bullets",
}


class LineAssembler:
    """token 流 → 完整行。LLM chunk 可能切在行中间，这里按 \\n 重组。"""

    def __init__(self):
        self._buf = ""

    def feed(self, chunk: str) -> list:
        """喂入一个文本块，返回新凑齐的完整行（不含换行符）。"""
        self._buf += chunk
        if "\n" not in self._buf:
            return []
        parts = self._buf.split("\n")
        self._buf = parts[-1]
        return parts[:-1]

    def flush(self) -> str:
        """流结束时返回残余的最后一行（可能为空串，也要喂给解析器，
        保证行序列与 text.split('\\n') 严格一致）。"""
        rest, self._buf = self._buf, ""
        return rest


class DemoEventParser:
    """_parse_demo_response 的增量形态：feed_line 喂一行，返回 0~2 个事件。

    [formula] 是唯一的跨行状态：收集中遇到不以 '[' 开头的行（含空行）
    全部吞进公式 buffer，遇到新标签行先 flush 公式再解析该行——
    这正是原全文解析的行为，空行判断必须放在公式态处理之后。

    image_catalog: {image_id: {"src", "media_type", "caption"}}，即本次注入
    prompt 的候选插图集合（见 media_library.build_catalog）。[image] 行的 ID
    必须命中该集合才产出事件——LLM 编造的 ID 静默丢弃且不耗 seq（与空内容
    board 行同语义），这是插图链路的防幻觉闸门。不传则丢弃一切 [image] 行。
    """

    def __init__(self, image_catalog=None):
        self._seq = 0
        self._formula_buf = None  # None=非收集态；str=已收集的公式文本
        self._image_catalog = image_catalog or {}

    def feed_line(self, raw_line: str) -> list:
        events = []
        if self._formula_buf is not None:
            if not raw_line.lstrip().startswith('['):
                self._formula_buf += "\n" + raw_line  # 续行保留原始空白
                return events
            events.extend(self._flush_formula())

        line = raw_line.strip()
        if not line:
            return events

        m = re.match(r'\[speak\]\s*(.+)', line, re.IGNORECASE)
        if m:
            text = _clean_speak_text(m.group(1).strip())  # 去 markdown/内嵌公式，保证 TTS 干净
            if text:  # 清洗后为空（整行仅符号）则不产事件、不耗 seq
                self._seq += 1
                events.append({"seq": self._seq, "type": "speak", "text": text})
            return events

        m = re.match(r'\[board:(\w+)\]\s*(.*)', line, re.IGNORECASE)
        if m:
            content = m.group(2).strip()
            if content:  # 空内容不产事件、不耗 seq
                self._seq += 1
                action = m.group(1).lower()
                action = BOARD_ACTION_ALIAS.get(action, action)
                events.append({"seq": self._seq, "type": "board", "action": action, "content": content})
            return events

        m = re.match(r'\[board\]\s*(.+)', line, re.IGNORECASE)
        if m:
            self._seq += 1
            events.append({"seq": self._seq, "type": "board", "action": "write_bullets",
                           "content": m.group(1).strip()})
            return events

        m = re.match(r'\[formula\]\s*(.*)', line, re.IGNORECASE)
        if m:
            self._formula_buf = m.group(1)  # 进入收集态，事件在 flush 时产出
            return events

        m = re.match(r'\[table\]\s*(.+)', line, re.IGNORECASE)
        if m:
            parts = [p.strip() for p in m.group(1).split('|') if p.strip()]
            if len(parts) >= 2:
                self._seq += 1
                events.append({
                    "seq": self._seq, "type": "table",
                    "title": parts[0],
                    "columns": [c.strip() for c in parts[1].split(',')],
                    "rows": [[c.strip() for c in r.split(',')] for r in parts[2:]],
                })
            return events

        m = re.match(r'\[image\]\s*(.+)', line, re.IGNORECASE)
        if m:
            parts = [p.strip() for p in m.group(1).split('|')]
            meta = self._image_catalog.get(parts[0])
            if meta:  # 候选集外的 ID 不产事件、不耗 seq
                self._seq += 1
                events.append({
                    "seq": self._seq, "type": "image",
                    "image_id": parts[0],
                    "src": meta.get("src", ""),
                    "media_type": meta.get("media_type", "static"),
                    "caption": parts[1] if len(parts) > 1 and parts[1] else meta.get("caption", ""),
                })
            return events

        if re.match(r'\[pause\]', line, re.IGNORECASE):
            self._seq += 1
            events.append({"seq": self._seq, "type": "pause", "duration_sec": 1.5})
            return events

        return events

    def finish(self) -> list:
        """流结束：flush 可能仍在收集中的公式（max_tokens 截断场景）。"""
        if self._formula_buf is not None:
            return self._flush_formula()
        return []

    def _flush_formula(self) -> list:
        buf, self._formula_buf = self._formula_buf, None
        buf = buf.strip()
        if not buf:
            return []
        has_block = "$$" in buf
        display_mode = "block" if has_block else "inline"
        # 不再机器朗读公式：旧的逐符号转中文对 \lim、上下标 _{} ^{} 等复杂式只会产出
        # 乱码（如「f'(x_0) = _德尔塔 x 0 ... 分之」），且与紧随其后的 [speak] 自然语言
        # 讲解重复。现在 prompt 强制「先上公式、紧接着 [speak] 讲解」，公式静默上板、由
        # 它后面那条讲解配音即可，不需要再合成一段念不通的公式音。
        self._seq += 1
        return [{"seq": self._seq, "type": "formula", "latex": buf, "display_mode": display_mode}]


def parse_demo_text(text: str, image_catalog=None) -> list:
    """全文一次性解析（增量解析器的便捷包装，与原 _parse_demo_response 等价）。"""
    parser = DemoEventParser(image_catalog=image_catalog)
    events = []
    for line in text.split("\n"):
        events.extend(parser.feed_line(line))
    events.extend(parser.finish())
    return events


def _merge_speaks(events: list) -> list:
    """合并相邻的 speak 事件成一条（短文本+长文本一起合成，GPT-SoVITS 有足够上下文）。"""
    if not events:
        return events
    merged = []
    buf = None
    for e in events:
        if e["type"] == "speak":
            if buf is None:
                buf = dict(e)
            else:
                buf["text"] += e["text"]
                buf["seq"] = e["seq"]
        else:
            if buf is not None:
                merged.append(buf)
                buf = None
            merged.append(e)
    if buf is not None:
        merged.append(buf)
    return merged


def parse_demo_text_merged(text: str, image_catalog=None) -> list:
    """解析+合并相邻 speak 事件（推荐入口，消除短句合成问题）。"""
    return _merge_speaks(parse_demo_text(text, image_catalog=image_catalog))


def sse_frame(event: str, data: dict) -> str:
    """编码一个 SSE 帧。data 序列化为单行 JSON。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


SSE_PING = ": ping\n\n"
