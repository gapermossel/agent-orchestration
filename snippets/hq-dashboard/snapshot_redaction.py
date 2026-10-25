"""Fail-closed redaction for a read-only status-dashboard snapshot.

Excerpt from the snapshot builder of an internal operations dashboard
(Python stdlib only; a vanilla-JS page reads the JSON it writes). Shown here
as a self-contained excerpt.

Design rules:
* Credential-shaped strings are replaced with [REDACTED] before any text is
  copied into the snapshot. The assignment word list lives in the rules file
  next to the builder, not in code.
* Customer names are matched by SHA-256 of a lowercased word, or of two
  adjacent words joined ("ab cd" -> "abcd"), so the config never holds the
  names themselves. Hits become "a customer" in prose, "CUSTOMER" in file names.
* Fail closed: after redaction the whole output is scanned again; if any
  name survives, nothing is written and the builder exits with status 2.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys

# Vendor-prefixed credentials (GitHub, Slack, AWS style). Assignment words come from the rules file.
BUILTIN_PATTERNS = [
    re.compile(r"\b(ghp|gho|ghs|github_pat|sk|xox[bap]|AKIA)[-_][A-Za-z0-9_]{16,}\b"),
]


def load_rules(path: str) -> tuple[list[re.Pattern], dict[str, bool]]:
    """rules.json: {"assignment_words": [...], "block_patterns": [...], "name_sha256": [{"sha256", "withhold"}]}"""
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    words = "|".join(re.escape(w) for w in cfg.get("assignment_words", []))
    pats = list(BUILTIN_PATTERNS)
    if words:
        pats.insert(0, re.compile(rf"(?i)\b({words})\b(\s*[:=]\s*)(?!\s*$)([^\s`'\"|,;]{{6,}})"))
    pats += [re.compile(p) for p in cfg.get("block_patterns", [])]
    names = {c["sha256"]: bool(c.get("withhold")) for c in cfg.get("name_sha256", [])}
    return pats, names


def redact(text: str, patterns: list[re.Pattern], stats: dict) -> str:
    def sub(m):
        stats["redactions"] = stats.get("redactions", 0) + 1
        return (m.group(1) + m.group(2) + "[REDACTED]") if m.re.groups >= 3 else "[REDACTED]"
    for r in patterns:
        text = r.sub(sub, text)
    return text


_WORD = re.compile(r"[A-Za-z]+")
_SUFFIX = re.compile(r"(?:[ ]+(?:Investments?|Holdings|Trust|Group|\(Pty\)|Pty|Ltd|Inc|CC)(?![A-Za-z])\.?)+")


def _h(w: str) -> str:
    return hashlib.sha256(w.lower().encode()).hexdigest()


def name_spans(text: str, names: dict[str, bool]) -> list[tuple[int, int, bool]]:
    """[(start, end, withhold)] for every name hit (single word or two-word bigram)."""
    if not names or not text:
        return []
    ws = list(_WORD.finditer(text))
    out, i = [], 0
    while i < len(ws):
        a = ws[i]
        if i + 1 < len(ws) and text[a.end():ws[i + 1].start()] == " ":
            pair = _h(a.group() + ws[i + 1].group())
            if pair in names:
                out.append((a.start(), ws[i + 1].end(), names[pair])); i += 2; continue
        if _h(a.group()) in names:
            out.append((a.start(), a.end(), names[_h(a.group())]))
        i += 1
    return out


def scrub_names(text, names: dict[str, bool]):
    """Replace each name: 'CUSTOMER' inside file names/paths, 'a customer' in prose."""
    if not isinstance(text, str):
        return text
    spans = name_spans(text, names)
    res, last = [], 0
    for s, e, _ in spans:
        if s < last:
            continue
        before = text[s - 1] if s else " "
        after = text[e] if e < len(text) else " "
        if before in "-_/" or (after in "-_.*" and before not in " (["):
            res.append(text[last:s]); res.append("CUSTOMER")
        else:
            m = _SUFFIX.match(text, e)
            e = m.end() if m else e
            pre = text[last:s]
            pm = re.search(r"(?i)\b(the|a|an)\s+$", pre)
            if pm:
                pre = pre[:pm.start()]
            res.append(pre); res.append("A customer" if (pm and pm.group(1)[0].isupper()) else "a customer")
        last = e
    res.append(text[last:])
    return "".join(res)


def scrub_obj(x, names):
    """Walk dicts (names in mapping labels too), lists and strings."""
    if isinstance(x, str):
        return scrub_names(x, names)
    if isinstance(x, list):
        return [scrub_obj(v, names) for v in x]
    if isinstance(x, dict):
        return {scrub_names(k, names): scrub_obj(v, names) for k, v in x.items()}
    return x


def write_snapshot(out: dict, docs: dict, data_dir: str, names: dict[str, bool]) -> int:
    """Scrub, re-scan the serialised result, and write only if nothing survived."""
    out, docs = scrub_obj(out, names), scrub_obj(docs, names)
    left = name_spans(json.dumps(out, ensure_ascii=False), names) + name_spans(json.dumps(docs, ensure_ascii=False), names)
    if left:
        print(f"ABORT: {len(left)} name hit(s) survived redaction; nothing written", file=sys.stderr)
        return 2
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "dashboard.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    with open(os.path.join(data_dir, "docs.json"), "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    demo_names = {_h("acmewidgets"): False}           # placeholder name: "Acme Widgets"
    print(scrub_names("Invoice sent to the Acme Widgets (Pty) Ltd team; see reports/acmewidgets-notes.md", demo_names))
    print(redact("deploy with ghp_" + "A" * 20 + " today", BUILTIN_PATTERNS, {}))
