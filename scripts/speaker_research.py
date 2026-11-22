"""Find professional accounts associated with named speakers through XMLRiver."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.services.xmlriver_client import search

OUTPUT = ROOT / "data/raw/speaker_search_log.json"


def main():
    people = json.loads((ROOT / "data/portal/people.json").read_text(encoding="utf-8-sig"))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    results = {r["person_id"]: r for r in json.loads(OUTPUT.read_text(encoding="utf-8"))} if OUTPUT.exists() else {}
    for person in people:
        person_id = person["id"]
        entry = results.setdefault(person_id, {"person_id": person_id, "name": person["name"],
                                             "role": person.get("role", ""), "searches": [], "errors": []})
        role = " ".join(entry["role"].split()[:5])
        done = {s["query"] for s in entry["searches"]}
        for networks in ["Telegram", "VK OR Instagram OR YouTube"]:
            query = f'"{person["name"]}" {role} {networks}'
            if query in done:
                continue
            try:
                matches = search(query)
            except RuntimeError as exc:
                if "missing" in str(exc):
                    raise
                entry["errors"].append({"query": query, "error": type(exc).__name__})
            else:
                entry["searches"].append({"query": query, "engine": "google", "region": "RU",
                                         "date_utc": datetime.now(timezone.utc).isoformat(), "results": matches})
            temp = OUTPUT.with_suffix(".tmp")
            temp.write_text(json.dumps(list(results.values()), ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(OUTPUT)


if __name__ == "__main__":
    main()
