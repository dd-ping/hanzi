# -*- coding: utf-8 -*-
"""
从 npmmirror（阿里云国内镜像）下载 hanzi-writer-data 完整字库包（9575字），
解压转换为码点命名，写入离线库 hanzi_data。
"""
import io
import json
import os
import tarfile
import urllib.request

TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hanzi_data")
URL = "https://registry.npmmirror.com/hanzi-writer-data/-/hanzi-writer-data-2.0.1.tgz"


def main():
    print("从 npmmirror 下载完整字库包...")
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req, timeout=120).read()
    print(f"下载完成 {len(data)//1024} KB")

    os.makedirs(TARGET, exist_ok=True)
    tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")
    count = 0
    skip = 0
    for m in tf.getmembers():
        if not m.isfile() or not m.name.endswith(".json"):
            continue
        base = os.path.basename(m.name)          # 堂.json
        ch_name = base[:-5]
        if len(ch_name) != 1 or not ('\u4e00' <= ch_name <= '\u9fff'):
            skip += 1
            continue
        try:
            content = tf.extractfile(m).read()
            json.loads(content)                  # 校验合法 JSON
        except Exception:
            skip += 1
            continue
        out = os.path.join(TARGET, f"{ord(ch_name):04x}.json")
        with open(out, "wb") as f:
            f.write(content)
        count += 1
    print(f"写入离线库: {count} 个字, 跳过 {skip} 项")
    files = len([f for f in os.listdir(TARGET) if f.endswith(".json")])
    print(f"hanzi_data 总文件数: {files}")


if __name__ == "__main__":
    main()
