#!/usr/bin/env python3
"""Бот поиска жилья в Польше: OLX + Otodom -> Telegram.

Запускается по расписанию (GitHub Actions). За один запуск:
  1. скачивает страницы поиска из config.yaml,
  2. фильтрует объявления,
  3. отправляет в Telegram только новые,
  4. сохраняет просмотренные ID в seen.json.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests
import yaml

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get("BOT_CONFIG", ROOT / "config.yaml"))
STATE_PATH = Path(os.environ.get("BOT_STATE", ROOT / "seen.json"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
}

ROOMS_OLX = {1: "one", 2: "two", 3: "three", 4: "four"}
ROOMS_OTODOM = {1: "ONE", 2: "TWO", 3: "THREE", 4: "FOUR", 5: "FIVE", 6: "SIX",
                7: "SEVEN", 8: "EIGHT", 9: "NINE", 10: "TEN"}
ROOMS_FROM_TEXT = {v: k for k, v in ROOMS_OLX.items()} | {v: k for k, v in ROOMS_OTODOM.items()} | {"MORE": 10}

# Путь локации Otodom: воеводство/повят/гмина/город
OTODOM_CITIES = {
    "szczecin": "zachodniopomorskie/szczecin/szczecin/szczecin",
    "warszawa": "mazowieckie/warszawa/warszawa/warszawa",
    "krakow": "malopolskie/krakow/krakow/krakow",
    "wroclaw": "dolnoslaskie/wroclaw/wroclaw/wroclaw",
    "poznan": "wielkopolskie/poznan/poznan/poznan",
    "gdansk": "pomorskie/gdansk/gdansk/gdansk",
    "gdynia": "pomorskie/gdynia/gdynia/gdynia",
    "lodz": "lodzkie/lodz/lodz/lodz",
    "katowice": "slaskie/katowice/katowice/katowice",
    "lublin": "lubelskie/lublin/lublin/lublin",
    "bydgoszcz": "kujawsko--pomorskie/bydgoszcz/bydgoszcz/bydgoszcz",
    "bialystok": "podlaskie/bialystok/bialystok/bialystok",
}

FLOORS = {"CELLAR": "подвал", "GROUND": "0", "0": "0", "FIRST": "1", "SECOND": "2", "THIRD": "3",
          "FOURTH": "4", "FIFTH": "5", "SIXTH": "6", "SEVENTH": "7", "EIGHTH": "8", "NINTH": "9",
          "TENTH": "10", "ABOVE_TENTH": "10+", "HIGHER_10": "10+", "GARRET": "мансарда",
          **{str(i): str(i) for i in range(1, 11)}}

ROOMS_LABEL = {1: "1 pok.", 2: "2 pok.", 3: "3 pok.", 4: "4 pok.", 10: "10+ pok."}


@dataclass
class Ad:
    key: str            # уникальный ключ для дедупликации (olx:123 / otodom:ID4abc)
    source: str         # OLX / Otodom
    title: str
    url: str
    price: float | None = None
    czynsz: float | None = None
    area: float | None = None
    rooms: int | None = None
    location: str = ""
    private: bool | None = None
    photo: str | None = None
    text: str = ""      # заголовок + описание для фильтра по словам
    created: str = ""
    extra: list[str] = field(default_factory=list)

    @property
    def total(self) -> float | None:
        if self.price is None:
            return None
        return self.price + (self.czynsz or 0)


# ---------------------------------------------------------------- utils

def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def num(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d,.]", "", str(v)).replace(",", ".")
    try:
        return float(s) if s else None
    except ValueError:
        return None


def fmt_money(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:,.0f}".replace(",", " ") + " zł"


def otodom_token(s: str | None) -> str | None:
    """ID объявления Otodom из ссылки/слага: ...-ID4DFSM -> ID4DFSM."""
    if not s:
        return None
    m = re.search(r"-(ID[0-9A-Za-z]+)(?:[/?#]|$)", s)
    return m.group(1) if m else None


def fetch(url: str, retries: int = 2) -> str:
    last = None
    for i in range(retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                return r.text
            last = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            last = str(e)
        time.sleep(2 + 3 * i)
    raise RuntimeError(f"не удалось загрузить страницу ({last})")


# ---------------------------------------------------------------- OLX

def olx_url(s: dict) -> str:
    if s.get("url"):
        return s["url"]
    city = s["city"].lower()
    path = "mieszkania/wynajem" if s.get("type", "flat") == "flat" else "stancje-pokoje"
    q: list[tuple[str, str]] = [("search[order]", "created_at:desc")]
    if s.get("price_min"):
        q.append(("search[filter_float_price:from]", str(s["price_min"])))
    if s.get("price_max"):
        q.append(("search[filter_float_price:to]", str(s["price_max"])))
    if s.get("type", "flat") == "flat":
        for i, r in enumerate(sorted({min(int(x), 4) for x in s.get("rooms") or []})):
            q.append((f"search[filter_enum_rooms][{i}]", ROOMS_OLX[r]))
        if s.get("area_min"):
            q.append(("search[filter_float_m:from]", str(s["area_min"])))
        if s.get("area_max"):
            q.append(("search[filter_float_m:to]", str(s["area_max"])))
    if s.get("private_only"):
        q.append(("search[private_business]", "private"))
    return f"https://www.olx.pl/nieruchomosci/{path}/{city}/?" + urlencode(q)


def parse_olx(page: str) -> list[Ad]:
    m = re.search(r'window\.__PRERENDERED_STATE__\s*=\s*("(?:[^"\\]|\\.)*")', page)
    if not m:
        raise RuntimeError("OLX: не найден блок данных на странице (сайт мог измениться)")
    state = json.loads(json.loads(m.group(1)))
    ads = []
    for a in state["listing"]["listing"]["ads"]:
        params = {p.get("key"): p for p in a.get("params") or []}
        price = ((a.get("price") or {}).get("regularPrice") or {}).get("value")
        rent = params.get("rent", {}).get("normalizedValue")
        area = params.get("m", {}).get("normalizedValue")
        rooms = ROOMS_FROM_TEXT.get(str(params.get("rooms", {}).get("normalizedValue")))
        loc = a.get("location") or {}
        location = ", ".join(x for x in [loc.get("cityName"), loc.get("districtName")] if x)
        ext = a.get("externalUrl") or ""
        tok = otodom_token(ext) if "otodom" in ext else None
        url = ext if tok else a.get("url")
        photos = a.get("photos") or []
        photo = None
        if photos:
            photo = re.sub(r";s=\d+x\d+", ";s=1000x750", str(photos[0])).replace("{width}", "1000").replace("{height}", "750")
        extra = []
        if params.get("furniture", {}).get("normalizedValue") == "yes":
            extra.append("с мебелью")
        if params.get("pets", {}).get("normalizedValue") in ("Tak", "yes"):
            extra.append("можно с животными")
        floor = params.get("floor_select", {}).get("value")
        if floor:
            extra.append(f"этаж {floor}")
        if params.get("roomsize", {}).get("value"):
            extra.append(params["roomsize"]["value"])
        ads.append(Ad(
            key=f"otodom:{tok}" if tok else f"olx:{a['id']}",
            source="Otodom (через OLX)" if tok else "OLX",
            title=a.get("title") or "",
            url=url,
            price=num(price),
            czynsz=num(rent),
            area=num(area),
            rooms=rooms,
            location=location,
            private=(not a.get("isBusiness")) if a.get("isBusiness") is not None else None,
            photo=photo,
            text=f"{a.get('title', '')} {re.sub('<[^>]+>', ' ', a.get('description') or '')}",
            created=a.get("createdTime") or "",
            extra=extra,
        ))
    return ads


# ---------------------------------------------------------------- Otodom

def otodom_url(s: dict) -> str:
    if s.get("url"):
        return s["url"]
    loc = s.get("otodom_location") or OTODOM_CITIES.get(s["city"].lower())
    if not loc:
        raise RuntimeError(
            f"Otodom: неизвестный город '{s['city']}'. Добавь в поиск otodom_location "
            "(например 'zachodniopomorskie/szczecin/szczecin/szczecin') или url.")
    estate = "mieszkanie" if s.get("type", "flat") == "flat" else "pokoj"
    q: list[tuple[str, str]] = [("by", "LATEST"), ("direction", "DESC"), ("limit", "36")]
    if s.get("price_min"):
        q.append(("priceMin", str(s["price_min"])))
    if s.get("price_max"):
        q.append(("priceMax", str(s["price_max"])))
    if s.get("type", "flat") == "flat":
        if s.get("area_min"):
            q.append(("areaMin", str(s["area_min"])))
        if s.get("area_max"):
            q.append(("areaMax", str(s["area_max"])))
        rooms = sorted({min(int(x), 10) for x in s.get("rooms") or []})
        if rooms:
            q.append(("roomsNumber", "[" + ",".join(ROOMS_OTODOM[r] for r in rooms) + "]"))
    return f"https://www.otodom.pl/pl/wyniki/wynajem/{estate}/{loc}?" + urlencode(q)


def parse_otodom(page: str) -> list[Ad]:
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        raise RuntimeError("Otodom: не найден блок данных (сайт мог измениться или заблокировал запрос)")
    data = json.loads(m.group(1))["props"]["pageProps"].get("data") or {}
    items = (data.get("searchAds") or {}).get("items") or []
    ads = []
    for it in items:
        slug = it.get("slug") or ""
        tok = otodom_token(slug) or str(it.get("id"))
        geo = [l.get("name") for l in ((it.get("location") or {}).get("reverseGeocoding") or {}).get("locations") or []
               if l.get("locationLevel") != "voivodeship"]
        street = (((it.get("location") or {}).get("address") or {}).get("street") or {}).get("name")
        location = ", ".join([x for x in geo if x] + ([street] if street else []))
        imgs = it.get("images") or []
        photo = (imgs[0].get("large") or imgs[0].get("medium")) if imgs else None
        extra = []
        floor = FLOORS.get(str(it.get("floorNumber") or "").upper().replace("FLOOR_", ""))
        if floor:
            extra.append(f"этаж {floor}")
        if it.get("peoplePerRoom"):
            extra.append({"ONE": "на 1 человека", "TWO": "на 2 человек"}.get(it["peoplePerRoom"], ""))
        ads.append(Ad(
            key=f"otodom:{tok}",
            source="Otodom",
            title=it.get("title") or "",
            url=f"https://www.otodom.pl/pl/oferta/{slug}",
            price=num((it.get("totalPrice") or {}).get("value")),
            czynsz=num((it.get("rentPrice") or {}).get("value")),
            area=num(it.get("areaInSquareMeters")),
            rooms=ROOMS_FROM_TEXT.get(str(it.get("roomsNumber"))),
            location=location,
            private=it.get("isPrivateOwner"),
            photo=photo,
            text=f"{it.get('title', '')} {it.get('shortDescription') or ''}",
            created=it.get("dateCreated") or "",
            extra=[e for e in extra if e],
        ))
    return ads


SOURCES = {"olx": (olx_url, parse_olx), "otodom": (otodom_url, parse_otodom)}


# ---------------------------------------------------------------- filters

def passes(ad: Ad, s: dict) -> bool:
    if s.get("price_min") and ad.price is not None and ad.price < s["price_min"]:
        return False
    if s.get("price_max") and ad.price is not None and ad.price > s["price_max"]:
        return False
    if s.get("total_max") and ad.total is not None and ad.total > s["total_max"]:
        return False
    if s.get("type", "flat") == "flat":
        if s.get("area_min") and ad.area is not None and ad.area < s["area_min"]:
            return False
        if s.get("area_max") and ad.area is not None and ad.area > s["area_max"]:
            return False
        if s.get("rooms") and ad.rooms is not None and ad.rooms not in {min(int(r), 10) for r in s["rooms"]} \
                and not (ad.rooms >= 4 and any(int(r) >= 4 for r in s["rooms"])):
            return False
    if s.get("private_only") and ad.private is False:
        return False
    text = f"{ad.text} {ad.location}".lower()
    if any(w.lower() in text for w in s.get("exclude_words") or []):
        return False
    districts = [d.lower() for d in s.get("districts") or []]
    if districts and not any(d in ad.location.lower() for d in districts):
        return False
    return True


# ---------------------------------------------------------------- telegram

class Telegram:
    def __init__(self, token: str, chat_ids: list[str], dry_run: bool = False):
        self.base = f"https://api.telegram.org/bot{token}"
        self.chat_ids = chat_ids
        self.dry_run = dry_run

    def _call(self, method: str, payload: dict) -> bool:
        if self.dry_run:
            log("[dry-run]", method, payload.get("caption") or payload.get("text"))
            return True
        for _ in range(3):
            try:
                r = requests.post(f"{self.base}/{method}", json=payload, timeout=30)
            except requests.RequestException as e:
                log("telegram error:", e)
                time.sleep(3)
                continue
            if r.status_code == 429:
                wait = r.json().get("parameters", {}).get("retry_after", 5)
                time.sleep(wait + 1)
                continue
            if r.ok:
                return True
            log("telegram", method, r.status_code, r.text[:200])
            return False
        return False

    def text(self, msg: str):
        for cid in self.chat_ids:
            self._call("sendMessage", {"chat_id": cid, "text": msg, "parse_mode": "HTML",
                                       "disable_web_page_preview": True})
            time.sleep(1.1)

    def ad(self, ad: Ad, search_name: str):
        cap = render(ad, search_name)
        for cid in self.chat_ids:
            ok = False
            if ad.photo:
                ok = self._call("sendPhoto", {"chat_id": cid, "photo": ad.photo, "caption": cap,
                                              "parse_mode": "HTML"})
            if not ok:
                self._call("sendMessage", {"chat_id": cid, "text": cap, "parse_mode": "HTML",
                                           "disable_web_page_preview": False})
            time.sleep(1.1)


def render(ad: Ad, search_name: str) -> str:
    e = html.escape
    head = f"🏠 <b>{fmt_money(ad.price)}</b>"
    if ad.czynsz:
        head += f" + czynsz {fmt_money(ad.czynsz)} = <b>{fmt_money(ad.total)}</b>"
    specs = []
    if ad.rooms:
        specs.append(ROOMS_LABEL.get(ad.rooms, f"{ad.rooms} pok."))
    if ad.area:
        specs.append(f"{ad.area:g} m²")
    specs += ad.extra
    lines = [head]
    if specs:
        lines.append(" · ".join(e(x) for x in specs))
    if ad.location:
        lines.append(f"📍 {e(ad.location)}")
    lines.append(f'<a href="{e(ad.url, quote=True)}">{e(ad.title[:200])}</a>')
    who = {True: "частник", False: "агентство"}.get(ad.private, "")
    tail = " · ".join(x for x in [ad.source, who, f"🔎 {e(search_name)}"] if x)
    lines.append(f"<i>{tail}</i>")
    return "\n".join(lines)[:1020]


# ---------------------------------------------------------------- state

def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text("utf-8"))
        except json.JSONDecodeError:
            log("seen.json повреждён — начинаю заново")
    return {"seen": {}, "initialized": [], "errors": {}}


def save_state(st: dict, keep_days: int = 90):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat()
    st["seen"] = {k: v for k, v in st["seen"].items() if v >= cutoff}
    STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=0, sort_keys=True), "utf-8")


# ---------------------------------------------------------------- main

def search_id(s: dict) -> str:
    return s.get("name") or f"{s['source']}-{s.get('type', 'flat')}-{s.get('city', '')}"


def main() -> int:
    cfg = yaml.safe_load(CONFIG_PATH.read_text("utf-8"))
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chats = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
    dry = os.environ.get("DRY_RUN") == "1" or not token or not chats
    if dry:
        log("Нет TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID — режим проверки, в Telegram ничего не уходит")
    tg = Telegram(token, chats, dry_run=dry)

    settings = cfg.get("settings") or {}
    first_run_send = int(settings.get("first_run_send", 3))
    max_per_run = int(settings.get("max_per_run", 15))

    st = load_state()
    now = datetime.now(timezone.utc).isoformat()
    sent = 0
    for s in cfg.get("searches") or []:
        if s.get("enabled") is False:
            continue
        sid = search_id(s)
        src = s.get("source", "").lower()
        if src not in SOURCES:
            log(f"[{sid}] неизвестный source '{src}' (нужно olx или otodom)")
            continue
        build, parse = SOURCES[src]
        try:
            url = build(s)
            ads = parse(fetch(url))
            st["errors"].pop(sid, None)
        except Exception as e:  # noqa: BLE001
            n = st["errors"].get(sid, 0) + 1
            st["errors"][sid] = n
            log(f"[{sid}] ошибка: {e}")
            if n == 3:
                tg.text(f"⚠️ Поиск «{html.escape(sid)}» не работает уже 3 проверки подряд:\n"
                        f"<code>{html.escape(str(e))[:300]}</code>")
            continue

        matched = [a for a in ads if passes(a, s)]
        fresh = [a for a in matched if a.key not in st["seen"]]
        log(f"[{sid}] на странице {len(ads)}, по фильтрам {len(matched)}, новых {len(fresh)}")

        first = sid not in st["initialized"]
        to_send = fresh
        if first:
            fresh.sort(key=lambda a: a.created, reverse=True)
            to_send = fresh[:first_run_send]
            tg.text(f"✅ Начал следить: <b>{html.escape(sid)}</b>\n"
                    f"Сейчас подходит {len(matched)} объявл. Присылаю {len(to_send)} самых свежих, "
                    f"дальше — только новые.")
            st["initialized"].append(sid)
            for a in fresh:
                st["seen"][a.key] = now      # при первом запуске старые объявления не шлём
        for a in sorted(to_send, key=lambda a: a.created):
            if sent >= max_per_run:
                break                        # остальные уйдут в следующий запуск
            tg.ad(a, sid)
            st["seen"][a.key] = now
            sent += 1
        time.sleep(2)

    save_state(st)
    log(f"Готово, отправлено {sent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
