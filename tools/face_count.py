"""数一张舞台页截图里有几张脸（判断"画面叠了两份"）。

用法: .venv\\Scripts\\python.exe tools/face_count.py shots\\_user_shot2.png
输出: 检出的人脸框坐标 + 数量；>1 基本可以确认画面里有两份人像。
"""
from __future__ import annotations

import os
import sys

import cv2


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: face_count.py <图片路径>")
        return 2
    path = sys.argv[1]
    if not os.path.exists(path):
        print("找不到:", path)
        return 2

    img = cv2.imread(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    print(f"图像 {img.shape[1]}x{img.shape[0]}")

    cas = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
    found = []
    for scale in (1.05, 1.08, 1.12, 1.16):
        faces = cas.detectMultiScale(gray, scaleFactor=scale, minNeighbors=5,
                                     minSize=(40, 40), maxSize=(500, 500))
        faces = [tuple(int(v) for v in f) for f in faces]
        print(f"  scaleFactor={scale}: {len(faces)} 张 → {faces}")
        if len(faces) > len(found):
            found = faces
        if len(found) >= 2:
            break

    # 侧面脸补测（正脸分类器对侧脸常失效）
    cas2 = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, "haarcascade_profileface.xml"))
    prof = [tuple(int(v) for v in f) for f in
            cas2.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=5, minSize=(40, 40))]
    print(f"  侧脸: {len(prof)} 张 → {prof}")

    n = max(len(found), len(prof))
    print(f"\n结论: 正脸最多 {len(found)} 张，侧脸 {len(prof)} 张 → 人脸总数 {n}")
    print("判定:", "画面里有两份人像（叠影/复制）" if n >= 2 else "只检出一张脸（未发现复制人像）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
