# -*- coding: utf-8 -*-
"""生成离线拼音字典 pinyin.json（字 -> 带声调拼音，多音字取常用读音）"""
import json
import os

from pypinyin import pinyin, Style

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pinyin.json")


def main():
    data = {}
    # 覆盖 CJK 基本区 + 扩展A区常用字
    ranges = [(0x4E00, 0x9FFF), (0x3400, 0x4DBF)]
    for lo, hi in ranges:
        for cp in range(lo, hi + 1):
            ch = chr(cp)
            try:
                py = pinyin(ch, style=Style.TONE)[0][0]
            except Exception:
                py = ""
            # pypinyin 转换失败的会返回原字本身，剔除
            if py and py != ch:
                data[ch] = py
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"生成拼音条目: {len(data)} 个 -> {OUT}")
    print("样例:", {c: data.get(c, "") for c in "堂表兄弟姐妹擦晚"})
    print("文件大小:", os.path.getsize(OUT) // 1024, "KB")


if __name__ == "__main__":
    main()
