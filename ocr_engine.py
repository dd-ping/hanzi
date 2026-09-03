# -*- coding: utf-8 -*-
"""
OCR 图片识字模块
- 使用 rapidocr_onnxruntime（纯 onnxruntime，无需系统级依赖，支持中英文）
- 首次调用会加载模型（约需几秒），之后复用全局引擎
"""
import threading
from rapidocr_onnxruntime import RapidOCR

_engine = None
_engine_lock = threading.Lock()
_is_loading = False


def get_engine():
    """获取（或懒加载）全局 OCR 引擎"""
    global _engine, _is_loading
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _is_loading = True
                try:
                    _engine = RapidOCR()
                finally:
                    _is_loading = False
    return _engine


def engine_loading():
    return _is_loading


def ocr_image(image_path, min_conf=0.4):
    """
    识别图片中的文字。
    返回 [(文本, 置信度), ...]，按识别顺序排列。
    """
    engine = get_engine()
    result, _ = engine(image_path)
    lines = []
    for item in (result or []):
        # rapidocr 结果项: [box(4点), text, score]
        text = str(item[1])
        try:
            conf = float(item[2])
        except (TypeError, ValueError):
            conf = 0.0
        if conf >= min_conf:
            lines.append((text, conf))
    return lines


def extract_hanzi(image_path, dedup=True, min_conf=0.4):
    """
    识别图片并提取汉字，返回 (汉字列表, 全部识别行)。
    - dedup=True 时按出现顺序去重（适合字帖/生字表，每个字只保留一次）
    """
    lines = ocr_image(image_path, min_conf=min_conf)
    out = []
    seen = set()
    for text, _conf in lines:
        for ch in text:
            if '\u4e00' <= ch <= '\u9fff':
                if dedup and ch in seen:
                    continue
                seen.add(ch)
                out.append(ch)
    return out, lines


if __name__ == "__main__":
    # 命令行测试
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else r"..\ocr_test.png"
    chars, lines = extract_hanzi(p)
    print("识别行:", lines)
    print("提取汉字:", "".join(chars))
