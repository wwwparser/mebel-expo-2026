"""Collect public Telegram posts for reviewed furniture brands and assemble the dated feed."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import json
from pathlib import Path
import re
import time
from collections import defaultdict

from bs4 import BeautifulSoup
import requests

from telegram_snapshot import ROOT, UA, image_to_webp

DATA = ROOT / "data/portal"
RAW = ROOT / "data/raw/factory-research"
CACHE = RAW / "previews"
PUBLIC = DATA / "factory_feed.json"
DIRECTORY = DATA / "factory_channels.json"
ANNOUNCEMENTS = DATA / "factory_attendance.json"
SLUG = re.compile(r"[A-Za-z][A-Za-z0-9_]{3,31}\Z")


def read(path, default=None):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else default


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    temp.replace(path)


def preview(handle, query=None):
    url = "https://t.me/s/" + handle
    for attempt in range(2):
        try:
            response = requests.get(url, params={"q": query} if query else {}, headers={"User-Agent": UA}, timeout=(6, 16))
            response.raise_for_status()
            break
        except requests.RequestException:
            if attempt: raise
            time.sleep(1)
    page = BeautifulSoup(response.content, "html.parser")
    posts = {}
    for node in page.select(".tgme_widget_message[data-post]"):
        ref = node["data-post"]
        owner, _, pid = ref.partition("/")
        stamp = node.select_one("time[datetime]")
        if owner.lower() != handle.lower() or not pid.isdigit() or not stamp:
            continue
        text_node = node.select_one(".tgme_widget_message_text")
        body = text_node.get_text(" ", strip=True) if text_node else ""
        pic = node.select_one(".tgme_widget_message_photo_wrap, .tgme_widget_message_video_thumb")
        if (not body and not pic) or body.startswith(("Channel created", "Channel photo updated", "Channel name was changed")):
            continue
        match = re.search(r"""url\(['"]?(.*?)['"]?\)""", pic.get("style", "")) if pic else None
        posts[int(pid)] = dict(url="https://t.me/"+ref, handle=handle.lower(), date=stamp["datetime"],
                               text=body, preview=match[1] if match else "")
    return sorted(posts.values(), key=lambda p:p["date"], reverse=True)


def collect(handle, day, known, limit=10):
    path = CACHE / (handle+".json")
    old = read(path, {})
    if old.get("date") == day and old.get("posts"):
        return
    latest = preview(handle)
    if not latest:
        raise ValueError("public preview empty")
    # Keep source imagery for albums and link to the full gallery at the publisher.
    posts = latest[:limit]
    pictured = False
    for p in posts:
        p["image"] = known.get(p["url"].lower(), "")
        if not p["image"] and p["preview"] and (limit > 3 or not pictured):
            seed = p["url"].lower()
            saved = image_to_webp(p["preview"], ROOT/"docs/media/tg", seed)
            p["image"] = saved or ""
        pictured = pictured or bool(p["image"])
    save(path, dict(date=day, posts=posts))
    # The public search can reveal an invitation older than the ten most recent posts.
    path = CACHE / (handle+"-search.json")
    try:
        results = preview(handle, "Крокус") + preview(handle, "Мебель-2026")
        start = date.fromisoformat(read(ROOT/"expo.json")["start_date"])
        found = {p["url"]:p for p in results if p["date"][:4]==str(start.year) and p["date"][:10]<=day}
        save(path, list(found.values()))
    except requests.RequestException:
        return


def fetch_channels(registry, day):
    known = {p["url"].lower():p["photos"][0] for p in read(DATA/"posts.json") if p.get("photos")}
    for p in read(PUBLIC, {}).get("posts", []):
        if p.get("image") and (ROOT/"docs"/p["image"]).is_file():
            known[p["url"].lower()] = p["image"]
    CACHE.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(10) as pool:
        jobs = {pool.submit(collect,c["handle"].lower(),day,known,c.get("post_limit",10)):c["handle"] for c in registry}
        for job in as_completed(jobs):
            try:job.result()
            except (requests.RequestException, ValueError) as e:
                print(jobs[job],type(e).__name__, flush=True)


def assemble(registry, day):
    marks = {p["url"].lower():p for p in read(ANNOUNCEMENTS, [])}
    previous = {p["url"].lower():p for p in read(PUBLIC, {}).get("posts", [])}
    announced_posts = defaultdict(list)
    for post in [*previous.values(), *read(RAW/"extra-posts.json", [])]:
        if post["url"].lower() in marks:
            announced_posts[post["handle"].lower()].append(post)
    output = {}
    for c in registry:
        handle=c["handle"].lower()
        if not SLUG.fullmatch(handle): raise ValueError(handle)
        saved = read(CACHE/(handle+".json"), {})
        if not saved.get("posts") or saved.get("date") != day:
            raise ValueError("Missing current preview: "+handle)
        recent = {p["url"].lower():p for p in saved["posts"]}
        for p in read(CACHE/(handle+"-search.json"), []) + announced_posts[handle]:
            url = p["url"].lower()
            if url in marks and p["handle"].lower()==handle:
                recent.setdefault(url,p)
        for url,p in recent.items():
            mark=marks.get(url)
            body=p.get("text") or ""
            if body in ("Channel created","Channel photo updated") or body.startswith("Channel name was changed"):continue
            if mark and mark["quote"] not in body and mark["quote"] != p.get("quote"):
                raise ValueError("Announcement needs a fresh source check: "+url)
            image=p.get("image") or ""
            if image and not (ROOT/"docs"/image).is_file(): raise ValueError(image)
            output[url]=dict(handle=handle,url=p["url"],date=p["date"],text=" ".join(body.split()[:34])+("…" if len(body.split())>34 else ""),image=image)
            if mark:
                output[url]["quote"]=mark["quote"]
                if mark.get("location"):
                    output[url]["location"]=mark["location"]
    if marks.keys()-output.keys(): raise ValueError("Missing announced posts: "+str(marks.keys()-output.keys()))
    order=sorted(output.values(),key=lambda p:p["date"],reverse=True)
    save(PUBLIC,dict(checked_at=day,posts=order))
    print(f"{len(registry)} channels; {len(order)} posts; {len(marks)} announcements")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["collect","assemble"])
    parser.add_argument("--registry",type=Path,default=DIRECTORY)
    parser.add_argument("--date",default=date.today().isoformat(),type=lambda s:date.fromisoformat(s).isoformat())
    args=parser.parse_args()
    records=read(args.registry)
    if isinstance(records,dict):records=records["channels"]
    if args.action=="collect":fetch_channels(records,args.date)
    else:assemble(records,args.date)
