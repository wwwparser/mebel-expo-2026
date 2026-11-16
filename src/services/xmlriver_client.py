"""Small, isolated XMLRiver client for sourced project research."""
from __future__ import annotations

import os
import re
import time
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path
from urllib.parse import urlencode

import requests

ENDPOINT = "https://xmlriver.com/search/xml"


def load_project_env() -> None:
    path = Path(__file__).resolve().parents[2] / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() and key.strip() not in os.environ:
                os.environ[key.strip()] = value.strip().strip('"').strip("'")


def search(query: str, *, country: str = "2643", language: str = "ru", retries: int = 3) -> list[dict]:
    load_project_env()
    user, key = os.getenv("XMLRIVER_USER"), os.getenv("XMLRIVER_KEY")
    if not user or not key:
        raise RuntimeError("XMLRIVER_USER/XMLRIVER_KEY are missing from environment or portal/.env")
    params = {"user": user, "key": key, "query": query, "groupby": 10,
              "country": country, "lr": language, "page": 1}
    last_error = ""
    for attempt in range(retries):
        try:
            response = requests.get(ENDPOINT, params=params, timeout=60)
            response.raise_for_status()
            raw = response.content
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError:
                content = raw.decode("windows-1251")
            error = re.search(r"<error[^>]*>(.*?)</error>", content, re.S)
            if error:
                last_error = unescape(error.group(1)).strip()
                if "превышено" in last_error.casefold() or "баланс" in last_error.casefold():
                    raise RuntimeError("XMLRiver quota/balance limit: " + last_error)
                if attempt + 1 == retries:
                    raise RuntimeError("XMLRiver: " + last_error)
                time.sleep(4 * (attempt + 1))
                continue
            root = ET.fromstring(content)
            return [{"position": i, "url": d.findtext("url", ""),
                     "title": (d.findtext("title", "") or "").strip(),
                     "snippet": " ".join(x.text or "" for x in d.iter("passage")).strip()}
                    for i, d in enumerate(root.iter("doc"), 1)]
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt + 1 == retries:
                break
            time.sleep(4 * (attempt + 1))
    raise RuntimeError("XMLRiver request failed: " + last_error)
