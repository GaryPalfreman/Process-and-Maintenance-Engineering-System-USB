import io
import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Dict, List, Tuple

WORD_RE = re.compile(r"([A-Z])([+\-]?(?:\d+(?:\.\d*)?|\.\d+))", re.I)
MACRO_RE = re.compile(r"(#\d+)\s*=?\s*([+\-]?(?:\d+(?:\.\d*)?|\.\d+))?", re.I)
SEQ_RE = re.compile(r"^\s*N\d+(?:\.\d+)?\s*", re.I)
PAREN_COMMENT_RE = re.compile(r"\([^)]*\)")


def read_uploaded_file(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    data = uploaded_file.getvalue()
    if name.endswith(".pdf"):
        try:
            from PyPDF2 import PdfReader
        except ImportError as exc:
            raise RuntimeError("PDF support requires PyPDF2. Install dependencies from requirements.txt.") from exc
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def preprocess_content(content: str) -> List[str]:
    lines = []
    for line in content.splitlines():
        stripped = re.sub(r"^\d+:\s*", "", line).strip()
        if stripped:
            lines.append(stripped)
    return lines


def normalize_content(content: str) -> List[str]:
    return sorted(line.strip() for line in preprocess_content(content) if line.strip())


def line_compare(content1: str, content2: str) -> List[Dict]:
    a = preprocess_content(content1)
    b = preprocess_content(content2)
    diffs = []
    for i in range(max(len(a), len(b))):
        left = a[i] if i < len(a) else ""
        right = b[i] if i < len(b) else ""
        if left != right:
            diffs.append({"line": i + 1, "file1": left, "file2": right, "similarity": round(SequenceMatcher(None, left, right).ratio() * 100, 1)})
    return diffs


def _strip_comments(line: str) -> str:
    line = PAREN_COMMENT_RE.sub("", line)
    if ";" in line:
        line = line.split(";", 1)[0]
    return line


def cnc_normalize_line(line: str, ignore_sequence: bool = True, ignore_comments: bool = True, ignore_whitespace: bool = True) -> str:
    text = line.strip().upper()
    if ignore_comments:
        text = _strip_comments(text)
    if ignore_sequence:
        text = SEQ_RE.sub("", text)
    text = text.strip()
    if ignore_whitespace:
        text = re.sub(r"\s+", "", text)
    else:
        text = re.sub(r"\s+", " ", text)
    return text


def cnc_blocks(content: str, ignore_sequence: bool = True, ignore_comments: bool = True, ignore_whitespace: bool = True) -> List[Dict]:
    blocks = []
    for line_no, raw in enumerate(content.splitlines(), start=1):
        if not raw.strip():
            continue
        blocks.append({"line": line_no, "raw": raw.rstrip(), "key": cnc_normalize_line(raw, ignore_sequence=ignore_sequence, ignore_comments=ignore_comments, ignore_whitespace=ignore_whitespace)})
    return blocks


def _token_map(line: str) -> Dict[str, List[str]]:
    code = _strip_comments(line.upper())
    result: Dict[str, List[str]] = {}
    for address, value in WORD_RE.findall(code):
        result.setdefault(address.upper(), []).append(value)
    for macro, value in MACRO_RE.findall(code):
        result.setdefault(macro.upper(), []).append(value or "(expression)")
    return result


def _category_for_address(address: str) -> str:
    if address == "G": return "G-CODE / MOTION"
    if address == "M": return "M-CODE"
    if address == "T": return "TOOL CHANGE"
    if address == "S": return "SPINDLE CHANGE"
    if address == "F": return "FEED CHANGE"
    if address in {"X", "Y", "Z", "A", "B", "C", "U", "V", "W"}: return "POSITION CHANGE"
    if address in {"I", "J", "K", "R"}: return "ARC / GEOMETRY CHANGE"
    if address in {"H", "D"}: return "OFFSET CHANGE"
    if address in {"P", "Q", "L"}: return "CYCLE / PARAMETER CHANGE"
    if address.startswith("#"): return "MACRO CHANGE"
    if address == "N": return "SEQUENCE CHANGE"
    return "OTHER ADDRESS CHANGE"


def classify_cnc_change(left: str, right: str, ignore_sequence: bool = True, ignore_comments: bool = True) -> Dict:
    lmap, rmap = _token_map(left), _token_map(right)
    if ignore_sequence:
        lmap.pop("N", None); rmap.pop("N", None)
    categories, details = [], []
    for address in sorted(set(lmap) | set(rmap)):
        lv = lmap.get(address, []); rv = rmap.get(address, [])
        if lv != rv:
            category = _category_for_address(address)
            if category not in categories:
                categories.append(category)
            details.append({"address": address, "file1": ", ".join(lv) if lv else "—", "file2": ", ".join(rv) if rv else "—", "category": category})
    l_comments = PAREN_COMMENT_RE.findall(left) + ([left.split(";", 1)[1]] if ";" in left else [])
    r_comments = PAREN_COMMENT_RE.findall(right) + ([right.split(";", 1)[1]] if ";" in right else [])
    if (not ignore_comments) and l_comments != r_comments and "COMMENT CHANGE" not in categories:
        categories.append("COMMENT CHANGE")
    if not categories and left.strip() != right.strip():
        categories.append("TEXT / FORMAT CHANGE")
    return {"categories": categories, "details": details}


def _pair_replace(left: List[Dict], right: List[Dict]) -> List[Tuple]:
    m, n = len(left), len(right)
    gap = 0.72
    dp = [[0.0] * (n + 1) for _ in range(m + 1)]
    move = [[""] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1): dp[i][0], move[i][0] = i * gap, "del"
    for j in range(1, n + 1): dp[0][j], move[0][j] = j * gap, "ins"
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            sim = SequenceMatcher(None, left[i-1]["key"], right[j-1]["key"], autojunk=False).ratio()
            sub_cost = 1.0 - sim if sim >= 0.18 else 1.55
            candidates = [(dp[i-1][j-1] + sub_cost, "sub"), (dp[i-1][j] + gap, "del"), (dp[i][j-1] + gap, "ins")]
            dp[i][j], move[i][j] = min(candidates, key=lambda x: x[0])
    out = []
    i, j = m, n
    while i or j:
        action = move[i][j]
        if action == "sub": out.append(("modified", left[i-1], right[j-1])); i -= 1; j -= 1
        elif action == "del": out.append(("deleted", left[i-1], None)); i -= 1
        else: out.append(("inserted", None, right[j-1])); j -= 1
    return list(reversed(out))


def cnc_compare(content1: str, content2: str, ignore_sequence: bool = True, ignore_comments: bool = True, ignore_whitespace: bool = True) -> Dict:
    left = cnc_blocks(content1, ignore_sequence, ignore_comments, ignore_whitespace)
    right = cnc_blocks(content2, ignore_sequence, ignore_comments, ignore_whitespace)
    matcher = SequenceMatcher(None, [b["key"] for b in left], [b["key"] for b in right], autojunk=False)
    rows, matched = [], 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal": matched += i2 - i1; continue
        if tag == "delete": rows.extend(("deleted", block, None) for block in left[i1:i2])
        elif tag == "insert": rows.extend(("inserted", None, block) for block in right[j1:j2])
        else: rows.extend(_pair_replace(left[i1:i2], right[j1:j2]))
    changes, category_counts = [], {}
    for status, lblock, rblock in rows:
        lraw = lblock["raw"] if lblock else ""; rraw = rblock["raw"] if rblock else ""
        if status == "modified":
            classified = classify_cnc_change(lraw, rraw, ignore_sequence, ignore_comments)
            categories, details = classified["categories"], classified["details"]
            similarity = round(SequenceMatcher(None, lblock["key"], rblock["key"], autojunk=False).ratio() * 100, 1)
        elif status == "inserted": categories, details, similarity = ["INSERTED BLOCK"], [], 0.0
        else: categories, details, similarity = ["DELETED BLOCK"], [], 0.0
        for category in categories: category_counts[category] = category_counts.get(category, 0) + 1
        changes.append({"status": status, "file1_line": lblock["line"] if lblock else None, "file2_line": rblock["line"] if rblock else None, "file1": lraw, "file2": rraw, "similarity": similarity, "categories": categories, "details": details})
    return {"changes": changes, "matched_blocks": matched, "file1_blocks": len(left), "file2_blocks": len(right), "category_counts": category_counts}


def ignore_position_compare(content1: str, content2: str) -> Dict[str, List[str]]:
    left = Counter(preprocess_content(content1)); right = Counter(preprocess_content(content2))
    return {"only_file1": list((left - right).elements()), "only_file2": list((right - left).elements())}


def merge_files(content1: str, content2: str, prefer: str = "file2") -> str:
    a = preprocess_content(content1); b = preprocess_content(content2); merged = []
    for i in range(max(len(a), len(b))):
        left = a[i] if i < len(a) else ""; right = b[i] if i < len(b) else ""
        merged.append(left if left == right else (right if prefer == "file2" else left))
    return "\n".join(merged)


def inline_difference(left: str, right: str) -> Tuple[str, str]:
    matcher = SequenceMatcher(None, left, right); lparts, rparts = [], []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        ltxt, rtxt = left[i1:i2], right[j1:j2]
        if tag == "equal": lparts.append(ltxt); rparts.append(rtxt)
        else:
            if ltxt: lparts.append(f"**{ltxt}**")
            if rtxt: rparts.append(f"**{rtxt}**")
    return "".join(lparts), "".join(rparts)


def summary_stats(content1: str, content2: str) -> Dict[str, int]:
    a, b = preprocess_content(content1), preprocess_content(content2); diffs = line_compare(content1, content2)
    return {"file1_lines": len(a), "file2_lines": len(b), "differences": len(diffs), "matching_lines": max(min(len(a), len(b)) - len(diffs), 0)}
