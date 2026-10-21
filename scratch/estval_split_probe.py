"""Probe: split estval into <value expression> + <disposition> without
enumerating disposition phrases.

Idea: the disposition vocabulary is open-ended (260+ variants and growing), but
the *value* vocabulary is closed -- money amounts, a handful of quantity words,
and punctuation. So describe the value side and treat whatever is left as
disposition.
"""

import glob
import re
import collections

import pandas as pd

MONEY = r"\$?\s?\d[\d,]*(?:\.\d+)?"

# One token of a value expression. Connector words ("to", "and", "over") only
# count as value tokens when a number follows, so a disposition that starts
# with such a word ("To be retained for official display") is not swallowed.
VALUE_TOKEN = re.compile(
    rf"""
      \s+
    | {MONEY}
    | \$
    | not\s+submitted
    | awaiting\s+appraisal
    | more\s+than\s+minimal\s+value
    | minimal\s+value
    | (?:unknown|undetermined|unspecified|n/a|none)\b
    | (?:each|ea\.?|apiece|respectively|aggregately|aggragately|combined
        |total\s+value|total)\b
    | (?:over|above|about|approximately|approx\.?|exceeds|more\s+than
        |less\s+than|up\s+to|to|and|&|or|plus)
        \s*(?=\$|\d)
    | [-–—,.;:()\[\]/+*=]
    """,
    re.I | re.X,
)

LABEL = re.compile(r"^\s*est(?:imated)?\.?\s*value\s*[—:\-]?\s*", re.I)
LEADING_SEP = re.compile(r"^[-–—,.;:/)\s]+")


def split_value(text):
    """Return (value_expression, disposition_text)."""
    text = LABEL.sub("", text.strip())
    pos = 0
    while pos < len(text):
        m = VALUE_TOKEN.match(text, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
    return text[:pos].strip(), LEADING_SEP.sub("", text[pos:]).strip()


raw = pd.concat(
    [pd.read_csv(f, encoding="utf-8-sig") for f in sorted(glob.glob("raw/*.csv"))],
    ignore_index=True,
)
item = raw["item"].dropna().astype(str)
est = item.str.extract(r"(.+)(Est.+$)", flags=re.M)[1].dropna()

no_value, with_disp, clean_value = 0, 0, 0
suspicious = []
disp_counts = collections.Counter()
value_shapes = collections.Counter()

for seg in est:
    value, disp = split_value(seg)
    if not value:
        no_value += 1
        suspicious.append(("NO VALUE", seg))
        continue
    if disp:
        with_disp += 1
        disp_counts[disp] += 1
    else:
        clean_value += 1
    value_shapes[re.sub(r"\d[\d,]*(?:\.\d+)?", "N", value)] += 1
    # A value expression with no digit at all is a parse failure worth eyeing.
    if not re.search(r"\d", value):
        suspicious.append(("NO DIGITS", seg))

print(f"Est segments analysed:        {len(est)}")
print(f"  value only, no disposition: {clean_value}")
print(f"  value + disposition split:  {with_disp}")
print(f"  no value found at all:      {no_value}")
print()
print("=== 25 most common value shapes (digits -> N) ===")
for shape, n in value_shapes.most_common(25):
    print(f"  {n:5d}  {shape!r}")
print()
print(f"=== distinct dispositions recovered: {len(disp_counts)} ===")
for d, n in disp_counts.most_common(15):
    print(f"  {n:5d}  {d!r}")
print()
print(f"=== suspicious ({len(suspicious)}), first 30 ===")
for why, seg in suspicious[:30]:
    print(f"  [{why}] {seg!r}")
