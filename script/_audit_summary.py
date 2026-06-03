"""临时小脚本：对 single_en_audit.jsonl 做一份 Top-N 频次 + 上下文摘要。

人工审计时建议：1) 看高频字母段是否有合法搭配（A 股 / B 超 / T 台 / K 线）；
2) 把这些字母连同左右汉字 token 一起记下来作为白名单，再决定怎么放回主流程。
"""
import json
from collections import Counter
from pathlib import Path

from project_dirs import REPORTS_DIR

ROOT = Path(__file__).resolve().parent.parent
AUDIT = REPORTS_DIR / "single_en_audit.jsonl"

n_records = 0
n_matches = 0
letter_freq: Counter = Counter()
right_neighbor: dict[str, Counter] = {}
samples_by_letter: dict[str, list[str]] = {}

with AUDIT.open(encoding="utf-8") as f:
    for line in f:
        rec = json.loads(line)
        n_records += 1
        for m in rec["matches"]:
            n_matches += 1
            letters = m["letters"]
            letter_freq[letters] += 1
            right = m["right"][:1]
            right_neighbor.setdefault(letters, Counter())[right] += 1
            if letters not in samples_by_letter:
                samples_by_letter[letters] = []
            if len(samples_by_letter[letters]) < 3:
                samples_by_letter[letters].append(
                    f"...{m['left']}「{letters}」{m['right']}..."
                )

print(f"audit 文件: {AUDIT.relative_to(ROOT)}")
print(f"记录数:    {n_records} 条 (即 {n_records} 个 record × field)")
print(f"剥离处数:  {n_matches} 处")
print()
print(f"出现 ≥10 次的字母段 (共 {sum(1 for _, c in letter_freq.items() if c >= 10)} 个):")
print()
for letters, cnt in letter_freq.most_common():
    if cnt < 10:
        break
    top_neighbors = ", ".join(
        f"{ch!r}×{c}" for ch, c in right_neighbor[letters].most_common(5) if ch
    )
    print(f"  [{cnt:>4}x] {letters!r}    紧随汉字 Top: {top_neighbors}")
    for s in samples_by_letter[letters]:
        print(f"         {s}")
    print()
