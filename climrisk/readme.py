"""
readme.py | Keep the README's highlight numbers in sync with the latest run.

The README contains a block between <!-- NAME:START --> and <!-- NAME:END -->; update_block()
replaces only that block, so the prose around it is never touched.
"""
from __future__ import annotations

import re
from pathlib import Path


def update_block(readme, name: str, markdown: str) -> bool:
    p = Path(readme)
    if not p.exists():
        return False
    text = p.read_text(encoding="utf-8")
    pat = re.compile(rf"(<!-- {name}:START -->)(.*?)(<!-- {name}:END -->)", re.S)
    if not pat.search(text):
        return False
    p.write_text(pat.sub(lambda m: f"{m.group(1)}\n{markdown.strip()}\n{m.group(3)}", text), encoding="utf-8")
    return True


def md_table(rows, header=("Result", "Value")) -> str:
    out = [f"| {header[0]} | {header[1]} |", "|---|---|"]
    out += [f"| {a} | {b} |" for a, b in rows]
    return "\n".join(out)
