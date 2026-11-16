"""Join website links printed in the official guide to current catalogue stands."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
GUIDE_URL = "https://www.meb-expo.ru/common/img/uploaded/exhibitions/mebel/doc_2026/meb26guide.pdf"
STAND_RE = re.compile(r"(?:13|14|15)[A-Z][A-Z0-9]{3}")
URL_RE = re.compile(r"(?:www\.)?[\w\u0080-\uffff-]+(?:\.[\w\u0080-\uffff-]+)+(?:/[\w\u0080-\uffff./?=&%#-]*)?", re.I)


def main() -> None:
    data = ROOT / "data" / "portal" / "participants.json"
    participants = json.loads(data.read_text(encoding="utf-8"))
    by_stand: dict[str, list[dict]] = defaultdict(list)
    for p in participants:
        for stand in p.get("stands", []):
            by_stand[stand.upper()].append(p)
    found = 0
    ambiguous = 0
    with pdfplumber.open(ROOT / "data" / "raw" / "exhibitors.pdf") as pdf:
        # The official guide's alphabetic MEBEL-2026 directory occupies printed pages 17–21.
        for page_index in range(16, min(21, len(pdf.pages))):
            words = pdf.pages[page_index].extract_words(x_tolerance=2, y_tolerance=2)
            for stand_word in words:
                stand = stand_word["text"].upper()
                if not STAND_RE.fullmatch(stand):
                    continue
                matches = by_stand.get(stand, [])
                if len(matches) != 1:
                    if matches:
                        ambiguous += 1
                    continue
                lo, hi = (178, 268) if stand_word["x0"] < 300 else (435, 525)
                aligned = [w for w in words if lo <= w["x0"] < hi and abs(w["top"] - stand_word["top"]) < 2.5]
                text = "".join(w["text"] for w in sorted(aligned, key=lambda w: w["x0"]))
                candidate = URL_RE.search(text)
                if not candidate:
                    continue
                host_path = candidate.group(0).rstrip(".,;)")
                if "." not in host_path or ".." in host_path or "@" in host_path:
                    continue
                url = "https://" + host_path
                item = matches[0]
                if not any(x.get("url", "").casefold() == url.casefold() for x in item.get("links", [])):
                    item.setdefault("links", []).append({
                        "label": "Сайт из официального путеводителя",
                        "value": host_path,
                        "url": url,
                        "source_url": GUIDE_URL,
                        "source_page": page_index + 1,
                        "checked_at": "2026-11-16",
                    })
                    found += 1
    data.write_text(json.dumps(participants, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Linked {found} official-guide URLs; skipped {ambiguous} shared-stand matches")


if __name__ == "__main__":
    main()
