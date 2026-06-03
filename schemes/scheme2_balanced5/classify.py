#!/usr/bin/env python3
"""方案2：暴力色情 / 发票营销 / 商业广告 / 钓鱼邮件 / 学术营销。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "script"))

from rule_classify import SchemeConfig, run_scheme  # noqa: E402

SCHEME_DIR = Path(__file__).resolve().parent

CFG = SchemeConfig(
    name="方案2 · 均衡五类",
    rule_categories=("暴力色情", "发票营销", "商业广告", "钓鱼邮件", "学术营销"),
    rule_priority={
        "暴力色情": 0,
        "钓鱼邮件": 1,
        "发票营销": 2,
        "学术营销": 3,
        "商业广告": 4,
    },
    category_id={
        "暴力色情": 0,
        "发票营销": 1,
        "商业广告": 2,
        "钓鱼邮件": 3,
        "学术营销": 4,
    },
    taxonomy_path=SCHEME_DIR / "category_taxonomy.json",
    output_dir=SCHEME_DIR / "outputs",
)


def main() -> None:
    dist = run_scheme(CFG)
    total = sum(dist.values())
    print(f"\n{CFG.name} 完成 → {CFG.output_dir}")
    for cat, cnt in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {cnt} ({cnt/total*100:.1f}%)")


if __name__ == "__main__":
    main()
