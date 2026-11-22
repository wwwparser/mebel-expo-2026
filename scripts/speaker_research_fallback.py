"""Retry unresolved speaker searches with the name and a shorter organization hint."""
import json
from speaker_research import OUTPUT, search


def main():
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    for row in data:
        if not row.get("errors") or row.get("fallback_searches"):
            continue
        words = row["role"].replace("«", " ").replace("»", " ").replace('"', " ").split()
        query = " ".join([row["name"], *words[:3]])
        try:
            matches = search(query, retries=2)
        except RuntimeError as exc:
            if "missing" in str(exc):
                raise
            row.setdefault("fallback_errors", []).append(type(exc).__name__)
            row["final_search_status"] = "serp_error_unresolved"
        else:
            row.setdefault("fallback_searches", []).append({"query": query, "engine": "google",
                "region": "RU", "results": matches, "purpose": "retry after original SERP error"})
            row["final_search_status"] = "fallback_success"
        temp = OUTPUT.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(OUTPUT)


if __name__ == "__main__":
    main()
