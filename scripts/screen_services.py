"""Create a transparent first-pass screening register for business-facing services."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
TERMS = [
    "software", "software", "crm", "erp", "saas", "digital platform", "analytics", "market research",
    "advertising agency", "marketing agency", "business media", "magazine", "journal", "publisher",
    "программное обеспечение", "автоматизация", "crm", "erp", "платформа", "аналитика",
    "маркетинговое агентство", "рекламное агентство", "журнал", "издательство", "медиа",
    "исследование рынка", "маркетинговые исследования", "it-компания", "разработка сайтов",
]
SPECIAL = ["БАЗИС-ЦЕНТР", "ФАБРИКОД"]
VERIFIED_IDS = {"p-abc70e6fdae9", "p-c5ab0b69bb3b"}


def domain(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").encode("idna").decode("ascii").lower().removeprefix("www.")
    except Exception:
        return ""


def main() -> None:
    data = ROOT / "data" / "portal"
    participants = json.loads((data / "participants.json").read_text(encoding="utf-8"))
    scraped = [json.loads(x) for x in (ROOT / "data/raw/contacts/contacts.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    scraped_by_host = {domain(r.get("home", "")): r for r in scraped}
    results = []
    for participant in participants:
        sites = [x for x in participant.get("links", []) if x.get("label") == "Сайт из официального путеводителя"]
        evidence = []
        candidate_sources = []
        text = participant["name"]
        for site in sites:
            item = scraped_by_host.get(domain(site.get("url", "")))
            if item:
                text += " " + " ".join((item.get("title", ""), item.get("meta_desc", ""), item.get("description", ""), item.get("home_text", "")))
                if item.get("meta_desc"):
                    evidence.append(item["meta_desc"][:350])
                    candidate_sources.append(site["url"])
        hits = [term for term in TERMS if term.casefold() in text.casefold()]
        named_candidate = any(x.casefold() in participant["name"].casefold() for x in SPECIAL)
        if (hits or named_candidate) and participant["id"] not in VERIFIED_IDS:
            results.append({"participant_id": participant["id"], "name": participant["name"],
                "stand": participant.get("stands", [""])[0], "status": "needs_manual_review",
                "screening_terms": list(dict.fromkeys(hits)), "site_evidence": evidence[:2],
                "source_urls": candidate_sources, "website_count": len(sites),
                "note": "Первичный лексический отбор; услуга и принадлежность сайта требуют проверки по первоисточнику."})
    guide_site_count = sum(bool([x for x in p.get("links", []) if x.get("label") == "Сайт из официального путеводителя"]) for p in participants)
    summary = {"checked_at": "2026-11-16", "catalogue_rows": len(participants),
        "websites_attempted": len(scraped), "websites_reachable": sum(bool(x.get("reachable")) for x in scraped),
        "participants_with_guide_sites": guide_site_count,
        "candidate_count": len(results), "confirmed_services": 2,
        "criteria": TERMS, "limitation": "Лексический проход проведён по всем названиям и доступным сайтам; он не доказывает оказываемую услугу. Кандидаты ждут смысловой проверки."}
    (data / "service_screening.json").write_text(json.dumps({"summary": summary, "candidates": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    services = [
        {"id": "service-bazis", "title": "Система БАЗИС для мебельных предприятий", "description": "Программный комплекс для проектирования мебели и подготовки производства: модули создания 3D-моделей, визуализации и формирования спецификаций.", "evidence": "Интуитивное создание 3D-моделей мебели любой сложности", "categories": ["IT и автоматизация"], "url": "https://www.bazissoft.ru/system/design", "participant_ids": ["p-abc70e6fdae9"], "sources": [{"title": "Возможности модулей проектирования БАЗИС", "url": "https://www.bazissoft.ru/system/design", "date": "2026-11-16"}, {"title": "Официальный сайт БАЗИС-ЦЕНТР", "url": "https://www.bazissoft.ru/", "date": "2026-11-16"}, {"title": "Участник МЕБЕЛЬ-2026: БАЗИС-ЦЕНТР", "url": "https://www.meb-expo.ru/ru/exhibition/exhibitors/", "date": "2026-11-13", "note": "Официальный каталог: стенд 14F070"}]},
        {"id": "service-fabrikod", "title": "Фабрикод: конфигуратор мебели, расчёт цены и интеграция с CRM", "description": "Цифровой сервис для мебельных заказов связывает конфигуратор и расчёт с передачей заказов в интернет-магазин и CRM. Полезен производителям, которые хотят автоматизировать путь от выбора параметров изделия до производственного заказа.", "evidence": "Фабрикод — программа для расчёта корпусной мебели: клиент или менеджер выбирает размеры, материалы и комплектацию, система проверяет правила, рассчитывает стоимость и формирует готовую заявку.", "categories": ["IT и автоматизация", "Цифровые платформы"], "url": "https://fabrikod.ru/solutions/visual-cpq", "participant_ids": ["p-c5ab0b69bb3b"], "sources": [{"title": "Расчёт мебели и коммерческого предложения — Фабрикод", "url": "https://fabrikod.ru/solutions/visual-cpq", "date": "2026-11-16"}, {"title": "Интеграция с интернет-магазином — Фабрикод", "url": "https://fabrikod.ru/solutions/ecommerce-integration", "date": "2026-11-16"}, {"title": "Участник МЕБЕЛЬ-2026: ФАБРИКОД", "url": "https://www.meb-expo.ru/ru/exhibition/exhibitors/", "date": "2026-11-13", "note": "Официальный каталог: стенд 15B094"}]}
    ]
    (data / "services.json").write_text(json.dumps(services, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
