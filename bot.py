#!/usr/bin/env python3
"""Бот поиска жилья в Польше: OLX + Otodom -> Telegram.

Запускается по расписанию (GitHub Actions). За один запуск:
  1. ищет новые объявления на OLX и Otodom по фильтрам каждого пользователя,
  2. присылает каждому только новые подходящие,
  3. несколько минут отвечает на сообщения (Start, сохранение фильтров) почти сразу,
  4. сохраняет фильтры и просмотренные объявления в зашифрованный seen.json.
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlencode

import requests
from bs4 import BeautifulSoup

from features import fingerprint, owner_message, price_eval, scam_flags, stats_add
from i18n import (BUILDING_T, EXTRAS_T, HEATING_T, LANG_NAMES, LANG_PROMPT, LANGS, PREF_T, SCAM_T, T,
                  lang_of, t, tr)

ROOT = Path(__file__).resolve().parent
STATE_PATH = Path(os.environ.get("BOT_STATE", ROOT / "seen.json"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
}

# ---------------------------------------------------------------- справочники

ROOMS_OLX = {1: "one", 2: "two", 3: "three", 4: "four"}
ROOMS_OTODOM = {1: ["ONE"], 2: ["TWO"], 3: ["THREE"], 4: ["FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN"]}
ROOMS_FROM_TEXT = {"one": 1, "two": 2, "three": 3, "four": 4, "ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4,
                   "FIVE": 4, "SIX": 4, "SEVEN": 4, "EIGHT": 4, "NINE": 4, "TEN": 4, "MORE": 4}

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
CITY_NAMES = {"szczecin": "Szczecin", "warszawa": "Warszawa", "krakow": "Kraków", "wroclaw": "Wrocław",
              "poznan": "Poznań", "gdansk": "Gdańsk", "gdynia": "Gdynia", "lodz": "Łódź",
              "katowice": "Katowice", "lublin": "Lublin", "bydgoszcz": "Bydgoszcz", "bialystok": "Białystok"}

# Районы (дзельницы) и осидла Щецина
SZCZECIN = {
    "Śródmieście": ["Centrum", "Drzetowo-Grabowo", "Łasztownia", "Łękno", "Międzyodrze-Wyspa Pucka",
                    "Niebuszewo-Bolinko", "Nowe Miasto", "Stare Miasto", "Śródmieście-Północ",
                    "Śródmieście-Zachód", "Turzyn"],
    "Północ": ["Bukowo", "Golęcino-Gocław", "Niebuszewo", "Skolwin", "Stołczyn", "Warszewo", "Żelechowa"],
    "Zachód": ["Arkońskie-Niemierzyn", "Głębokie-Pilchowo", "Gumieńce", "Krzekowo-Bezrzecze", "Osów",
               "Pogodno", "Pomorzany", "Świerczewo", "Zawadzkiego-Klonowica"],
    "Prawobrzeże": ["Bukowe-Klęskowo", "Dąbie", "Kijewo", "Klucz", "Majowe", "Płonia-Śmierdnica-Jezierzyce",
                    "Podjuchy", "Słoneczne", "Wielgowo-Sławociesze", "Zdroje", "Załom-Kasztanowe"],
}

ALL_OSIEDLA = [o for group in SZCZECIN.values() for o in group]   # порядок важен: так же в docs/index.html

# Тип дома: код Otodom -> значения OLX
BUILDING = {"BLOCK": ["blok"], "TENEMENT": ["kamienica"], "APARTMENT": ["apartamentowiec"],
            "HOUSE": ["wolnostojacy", "szeregowiec"], "LOFT": ["loft"], "OTHER": ["pozostale"]}


# Удобства: код Otodom -> поиск по тексту объявления OLX (там таких фильтров нет)
EXTRAS_TEXT = {
    "BALCONY": r"balkon|loggi",
    "TERRACE": r"taras",
    "GARDEN": r"ogrod",
    "LIFT": r"wind[aąy]",
    "GARAGE": r"garaz|miejsce (postojowe|parkingowe)|hala garazowa",
    "AIR_CONDITIONING": r"klimatyzac",
    "SEPARATE_KITCHEN": r"(oddzieln|osobn)\w* kuchn",
    "INTERNET": r"internet|wi-?fi|swiatlowod",
}


# Отопление: код Otodom -> как это пишут в тексте объявлений OLX
HEATING = ["URBAN", "GAS", "ELECTRICAL", "BOILER_ROOM", "TILED_STOVE", "OTHER"]

HEATING_TEXT = {
    "URBAN": r"miejsk|msc|siec\w* cieplown|cieplo systemowe|c\.?\s?o\.? z sieci",
    "GAS": r"gazow|piec dwufunkcyjny",
    "ELECTRICAL": r"elektryczn|pompa ciepla|podlogowe elektryczne",
    "BOILER_ROOM": r"kotlowni",
    "TILED_STOVE": r"kaflow",
}

FLOORS_OTODOM = ["GROUND", "FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH", "EIGHTH",
                 "NINTH", "TENTH", "ABOVE_TENTH"]          # индекс = этаж (11 = выше 10)
FLOOR_FROM_OTODOM = {v: i for i, v in enumerate(FLOORS_OTODOM)} | {"CELLAR": 0, "GARRET": None}

PREFS = ["man", "women", "student", "working"]
PEOPLE_OTODOM = {1: "ONE", 2: "TWO", 3: "THREE"}
PEOPLE_OLX = {1: "one", 2: "two", 3: "three"}

ALL_SOURCES = ["olx", "otodom", "domiporta", "nol"]
SOURCE_NAMES = {"olx": "OLX", "otodom": "Otodom", "domiporta": "Domiporta", "nol": "Nieruchomosci-online"}

DEFAULT_FILTERS = {
    "v": 2, "type": "flat", "src": list(ALL_SOURCES), "city": "szczecin", "dist": [], "noDist": True,
    "pMin": None, "pMax": None, "tMax": None, "rooms": [], "aMin": None, "aMax": None, "floors": [],
    "bt": [], "ex": [], "heat": [], "furn": False, "pets": False, "yearMin": None, "ppl": [], "pref": "",
    "priv": False, "excl": "tylko dla kobiet, tylko dla studentek, na doby, krótkoterminowy", "incl": "",
    "first": 3, "paused": False,
}


@dataclass
class Ad:
    key: str
    source: str                                       # название сайта для подписи
    title: str
    url: str
    site: str = ""                                    # код сайта: olx / otodom / domiporta / nol
    price: float | None = None
    czynsz: float | None = None
    area: float | None = None
    rooms: int | None = None
    floor: int | None = None
    places: list[str] = field(default_factory=list)   # осидле/район как на сайте
    zone: str | None = None                           # дзельница (Otodom)
    location: str = ""
    private: bool | None = None
    furniture: bool | None = None
    pets: bool | None = None
    lift: bool | None = None
    building: str | None = None                       # код как в BUILDING
    people: int | None = None
    prefs: list[str] = field(default_factory=list)
    parking: str = ""
    photo: str | None = None
    text: str = ""
    created: str = ""
    extra: list[tuple] = field(default_factory=list)   # коды: ("furn",), ("floor", 3) ...

    @property
    def total(self) -> float | None:
        return None if self.price is None else self.price + (self.czynsz or 0)


# ---------------------------------------------------------------- utils

def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def norm(s: str | None) -> str:
    s = (s or "").lower().replace("ł", "l").replace("ê", "e")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).strip()


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


def area_num(s: str) -> float | None:
    """«36 m2», «41,10 m²» -> 36.0, 41.1 (без цифры 2 из m2)."""
    m = re.search(r"(\d[\d\s]*(?:[.,]\d+)?)\s*m", s or "")
    return num(m.group(1)) if m else None


def fmt_money(v: float | None) -> str:
    return "—" if v is None else f"{v:,.0f}".replace(",", " ") + " zł"


def otodom_token(s: str | None) -> str | None:
    m = re.search(r"-(ID[0-9A-Za-z]+)(?:[/?#]|$)", s or "")
    return m.group(1) if m else None


def fetch(url: str, retries: int = 2) -> str:
    last = None
    for i in range(retries + 1):
        try:
            h = dict(HEADERS, Accept="application/json") if "/api/" in url else HEADERS
            r = requests.get(url, headers=h, timeout=30)
            if r.status_code == 200:
                return r.text
            last = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            last = str(e)
        time.sleep(2 + 3 * i)
    raise RuntimeError(f"не удалось загрузить страницу ({last})")


def words(s: str) -> list[str]:
    return [norm(w) for w in re.split(r"[,;\n]", s or "") if norm(w)]


# ---------------------------------------------------------------- OLX

def extras_codes(floor=None, furn=False, pets=False, people=None, prefs=None) -> list[tuple]:
    out: list[tuple] = []
    if furn:
        out.append(("furn",))
    if pets:
        out.append(("pets",))
    if floor is not None:
        out.append(("floor", floor))
    if people:
        out.append(("people", people))
    if prefs:
        out.append(("prefs", tuple(prefs)))
    return out


OLX_CITY_IDS = {"szczecin": 16705, "warszawa": 17871, "krakow": 8959, "wroclaw": 19701, "poznan": 13983,
                "gdansk": 5659, "gdynia": 5849, "lodz": 10609, "katowice": 7691, "lublin": 10119,
                "bydgoszcz": 4019, "bialystok": 1079}


def olx_url(f: dict, kind: str) -> str:
    """Запрос к API OLX (тот же, которым пользуется сам сайт; HTML-страницы OLX блокирует для серверов)."""
    city = norm(f.get("city") or "szczecin")
    if city not in OLX_CITY_IDS:
        raise RuntimeError(f"OLX: город «{f.get('city')}» не поддерживается")
    q: list[tuple[str, str]] = [("offset", "0"), ("limit", "50"), ("category_id", "15" if kind == "flat" else "11"),
                                ("city_id", str(OLX_CITY_IDS[city])), ("sort_by", "created_at:desc")]
    if f.get("pMin"):
        q.append(("filter_float_price:from", str(f["pMin"])))
    if f.get("pMax"):
        q.append(("filter_float_price:to", str(f["pMax"])))
    if f.get("priv"):
        q.append(("owner_type", "private"))
    if f.get("furn"):
        q.append(("filter_enum_furniture[0]", "yes"))
    if kind == "flat":
        for i, r in enumerate(sorted({min(int(x), 4) for x in f.get("rooms") or []})):
            q.append((f"filter_enum_rooms[{i}]", ROOMS_OLX[r]))
        if f.get("aMin"):
            q.append(("filter_float_m:from", str(f["aMin"])))
        if f.get("aMax"):
            q.append(("filter_float_m:to", str(f["aMax"])))
        if f.get("pets"):
            q.append(("filter_enum_pets[0]", "Tak"))
        if "LIFT" in (f.get("ex") or []):
            q.append(("filter_enum_winda[0]", "Tak"))
        bts = [v for code in f.get("bt") or [] for v in BUILDING.get(code, [])]
        for i, v in enumerate(bts):
            q.append((f"filter_enum_builttype[{i}]", v))
    else:
        for i, p in enumerate(sorted(f.get("ppl") or [])):
            q.append((f"filter_enum_roomsize[{i}]", PEOPLE_OLX[int(p)]))
    return "https://www.olx.pl/api/v1/offers/?" + urlencode(q)


def _olx_raw_ads(page: str) -> list[dict]:
    """Объявления OLX в одном виде — и из API (JSON), и из HTML-страницы."""
    if page.lstrip().startswith("{"):
        out = []
        for a in json.loads(page).get("data") or []:
            params, price = [], None
            for x in a.get("params") or []:
                v = x.get("value") or {}
                if x.get("key") == "price":
                    price = v.get("value")
                    continue
                k = v.get("key")
                params.append({"key": x.get("key"), "normalizedValue": ",".join(map(str, k)) if isinstance(k, list) else k})
            loc = a.get("location") or {}
            photos = [ph.get("link") for ph in a.get("photos") or [] if ph.get("link")]
            out.append({"id": a.get("id"), "title": a.get("title"), "description": a.get("description"),
                        "url": a.get("url"), "externalUrl": a.get("external_url"), "isBusiness": a.get("business"),
                        "createdTime": a.get("created_time"), "price": {"regularPrice": {"value": price}},
                        "params": params, "photos": photos,
                        "location": {"cityName": (loc.get("city") or {}).get("name"),
                                     "districtName": (loc.get("district") or {}).get("name")}})
        return out
    m = re.search(r'window\.__PRERENDERED_STATE__\s*=\s*("(?:[^"\\]|\\.)*")', page)
    if not m:
        raise RuntimeError("OLX: не найден блок данных на странице (сайт мог измениться)")
    return json.loads(json.loads(m.group(1)))["listing"]["listing"]["ads"]


def parse_olx(page: str) -> list[Ad]:
    ads = []
    for a in _olx_raw_ads(page):
        p = {x.get("key"): x for x in a.get("params") or []}
        val = lambda k: (p.get(k) or {}).get("normalizedValue")  # noqa: E731
        loc = a.get("location") or {}
        ext = a.get("externalUrl") or ""
        tok = otodom_token(ext) if "otodom" in ext else None
        photos = a.get("photos") or []
        photo = None
        if photos:
            photo = re.sub(r";s=\d+x\d+", ";s=1000x750", str(photos[0])).replace("{width}", "1000").replace("{height}", "750")
        floor = None
        fs = str(val("floor_select") or "")
        if fs.startswith("floor_"):
            try:
                floor = int(fs[6:])
            except ValueError:
                floor = None
        bt_raw = val("builttype")
        building = next((code for code, vals in BUILDING.items() if bt_raw in vals), None) if bt_raw else None
        furn = val("furniture")
        pets = val("pets")
        lift = val("winda")
        people = {"one": 1, "two": 2, "three": 3}.get(str(val("roomsize")))
        prefs = [x for x in str(val("preferences") or "").split(",") if x]
        extra = extras_codes(floor=floor, furn=furn == "yes", pets=pets == "Tak", people=people, prefs=prefs)
        district = loc.get("districtName")
        ads.append(Ad(
            key=f"otodom:{tok}" if tok else f"olx:{a['id']}",
            source="OLX",
            site="olx",
            title=a.get("title") or "",
            url=ext if tok else a.get("url"),
            price=num(((a.get("price") or {}).get("regularPrice") or {}).get("value")),
            czynsz=num(val("rent")),
            area=num(val("m")),
            rooms=ROOMS_FROM_TEXT.get(str(val("rooms"))),
            floor=floor,
            places=[district] if district else [],
            location=", ".join(x for x in [loc.get("cityName"), district] if x),
            private=(not a.get("isBusiness")) if a.get("isBusiness") is not None else None,
            furniture=None if furn is None else furn == "yes",
            pets=None if pets is None else pets == "Tak",
            lift=None if lift is None else lift == "Tak",
            building=building,
            people=people,
            prefs=prefs,
            parking=str(val("parking") or ""),
            photo=photo,
            text=f"{a.get('title', '')} {re.sub('<[^>]+>', ' ', a.get('description') or '')}",
            created=a.get("createdTime") or "",
            extra=extra,
        ))
    return ads


# ---------------------------------------------------------------- Otodom

def otodom_url(f: dict, kind: str) -> str:
    city = norm(f.get("city") or "szczecin")
    loc = OTODOM_CITIES.get(city)
    if not loc:
        raise RuntimeError(f"Otodom: город «{f.get('city')}» не поддерживается")
    q: list[tuple[str, str]] = [("by", "LATEST"), ("direction", "DESC"), ("limit", "72")]
    if f.get("pMin"):
        q.append(("priceMin", str(f["pMin"])))
    if f.get("pMax"):
        q.append(("priceMax", str(f["pMax"])))
    if f.get("priv"):
        q.append(("isPrivateOwner", "true"))
    if kind == "flat":
        estate = "mieszkanie"
        if f.get("aMin"):
            q.append(("areaMin", str(f["aMin"])))
        if f.get("aMax"):
            q.append(("areaMax", str(f["aMax"])))
        rooms = [v for r in sorted({min(int(x), 4) for x in f.get("rooms") or []}) for v in ROOMS_OTODOM[r]]
        if rooms:
            q.append(("roomsNumber", "[" + ",".join(rooms) + "]"))
        floors = [FLOORS_OTODOM[int(x)] for x in sorted(set(f.get("floors") or [])) if 0 <= int(x) <= 11]
        if floors:
            q.append(("floors", "[" + ",".join(floors) + "]"))
        if f.get("bt"):
            q.append(("buildingType", "[" + ",".join(f["bt"]) + "]"))
        if f.get("ex"):
            q.append(("extras", "[" + ",".join(f["ex"]) + "]"))
        if f.get("yearMin"):
            q.append(("buildYearMin", str(f["yearMin"])))
        if f.get("heat"):
            q.append(("heating", "[" + ",".join(f["heat"]) + "]"))
    else:
        estate = "pokoj"
        ppl = [PEOPLE_OTODOM[int(p)] for p in sorted(f.get("ppl") or [])]
        if ppl:
            q.append(("peoplePerRoom", "[" + ",".join(ppl) + "]"))
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
        locs = ((it.get("location") or {}).get("reverseGeocoding") or {}).get("locations") or []
        zone = next((l.get("name") for l in locs if l.get("locationLevel") == "district"), None)
        resid = next((l.get("name") for l in locs if l.get("locationLevel") == "residential"), None)
        city = next((l.get("name") for l in locs if l.get("locationLevel") == "city_or_village"), None)
        street = (((it.get("location") or {}).get("address") or {}).get("street") or {}).get("name")
        imgs = it.get("images") or []
        floor = FLOOR_FROM_OTODOM.get(str(it.get("floorNumber") or ""))
        people = {"ONE": 1, "TWO": 2, "THREE": 3}.get(str(it.get("peoplePerRoom")))
        extra = extras_codes(floor=floor, people=people)
        ads.append(Ad(
            key=f"otodom:{tok}",
            source="Otodom",
            site="otodom",
            title=it.get("title") or "",
            url=f"https://www.otodom.pl/pl/oferta/{slug}",
            price=num((it.get("totalPrice") or {}).get("value")),
            czynsz=num((it.get("rentPrice") or {}).get("value")),
            area=num(it.get("areaInSquareMeters")),
            rooms=ROOMS_FROM_TEXT.get(str(it.get("roomsNumber"))),
            floor=floor,
            places=[resid] if resid else [],
            zone=zone,
            location=", ".join(x for x in [city, zone, resid, street] if x),
            private=it.get("isPrivateOwner"),
            people=people,
            photo=(imgs[0].get("large") or imgs[0].get("medium")) if imgs else None,
            text=f"{it.get('title', '')} {it.get('shortDescription') or ''}",
            created=it.get("dateCreated") or "",
            extra=extra,
        ))
    return ads



# ---------------------------------------------------------------- Domiporta (только квартиры)

VOIVODESHIPS = {"szczecin": "zachodniopomorskie", "warszawa": "mazowieckie", "krakow": "malopolskie",
                "wroclaw": "dolnoslaskie", "poznan": "wielkopolskie", "gdansk": "pomorskie", "gdynia": "pomorskie",
                "lodz": "lodzkie", "katowice": "slaskie", "lublin": "lubelskie", "bydgoszcz": "kujawsko-pomorskie",
                "bialystok": "podlaskie"}
ZONES = {norm(z): z for z in SZCZECIN}


def domiporta_url(f: dict, kind: str) -> str | None:
    if kind != "flat":
        return None                                   # комнат на Domiporta нет
    city = norm(f.get("city") or "szczecin")
    if city not in VOIVODESHIPS:
        raise RuntimeError(f"Domiporta: город «{f.get('city')}» не поддерживается")
    q: list[tuple[str, str]] = [("SortingOrderDirection", "InsertionDateDescending"), ("RowsPerPage", "72")]
    for key, name in (("pMin", "Price.From"), ("pMax", "Price.To"), ("aMin", "Surface.From"), ("aMax", "Surface.To")):
        if f.get(key):
            q.append((name, str(f[key])))
    rooms = sorted({min(int(x), 4) for x in f.get("rooms") or []})
    if rooms:
        q.append(("Rooms.From", str(rooms[0])))
        if rooms[-1] < 4:
            q.append(("Rooms.To", str(rooms[-1])))
    return f"https://www.domiporta.pl/mieszkanie/wynajme/{VOIVODESHIPS[city]}/{city}?" + urlencode(q)


def split_places(parts: list[str], city: str | None) -> tuple[list[str], str | None]:
    """Из «Szczecin, Śródmieście, Pogodno, ul. X 5» достаём осидла и дзельницу."""
    places, zone = [], None
    for part in parts:
        p = part.strip()
        if not p or (city and norm(p) == norm(city)):
            continue
        if norm(p) in ZONES:
            zone = ZONES[norm(p)]
        elif not re.search(r"\d|^(ul|al|pl|os)\.", p, re.I):
            places.append(p)
    return places, zone


def parse_domiporta(page: str) -> list[Ad]:
    soup = BeautifulSoup(page, "html.parser")
    cards = soup.select("article.sneakpeak[data-detail-id]")
    if not cards and "sneakpeak" not in page:
        raise RuntimeError("Domiporta: не найден список объявлений (сайт мог измениться)")
    ads = []
    for c in cards:
        link = c.select_one('a[href^="/nieruchomosci/"]')
        title_el = c.select_one(".sneakpeak__title--bold")
        loc_el = c.select_one(".sneakpeak__title--inblock")
        price_el = c.select_one(".sneakpeak__price_value")
        fee_el = c.select_one(".sneakpeak__price_fee")
        det = []
        for d in c.select(".sneakpeak__details_item"):
            txt = d.get_text(" ", strip=True)
            if txt and txt not in det:
                det.append(txt)
        area = next((area_num(x) for x in det if "m2" in x.replace(" ", "") and "zł" not in x), None)
        rooms_txt = next((x for x in det if re.fullmatch(r"\d+", x)), None)
        loc_parts = re.sub(r"^\s*\w+\s+", "", loc_el.get_text(" ", strip=True)) if loc_el else ""
        city = loc_parts.split(",")[0].strip() if loc_parts else None
        places, zone = split_places(loc_parts.split(","), city)
        img = c.select_one("img")
        photo = img.get("src") if img else None
        if photo:
            photo = photo.replace("/pictures/small/", "/pictures/big/")
        descr = c.select_one(".sneakpeak__description")
        title = title_el.get_text(" ", strip=True) if title_el else (link.get("title", "") if link else "")
        ads.append(Ad(
            key=f"domiporta:{c['data-detail-id']}",
            source="Domiporta",
            site="domiporta",
            title=title,
            url="https://www.domiporta.pl" + link["href"] if link else "https://www.domiporta.pl",
            price=num(price_el.get_text(" ", strip=True)) if price_el else None,
            czynsz=num(fee_el.get_text(" ", strip=True)) if fee_el else None,
            area=area,
            rooms=min(int(rooms_txt), 4) if rooms_txt else None,
            places=places,
            zone=zone,
            location=loc_parts,
            photo=photo,
            text=f"{title} {descr.get_text(' ', strip=True) if descr else ''}",
        ))
    return ads


# ---------------------------------------------------------------- Nieruchomosci-online

def nol_url(f: dict, kind: str) -> str:
    city = CITY_NAMES.get(norm(f.get("city") or "szczecin"))
    if not city:
        raise RuntimeError(f"Nieruchomosci-online: город «{f.get('city')}» не поддерживается")
    fields = ["3", "mieszkanie" if kind == "flat" else "pokoj", "wynajem", "", city, "", "", "", "", ""]
    if f.get("pMin") or f.get("pMax"):
        fields[8] = f"{f.get('pMin') or ''}-{f.get('pMax') or ''}"
    if kind == "flat" and (f.get("aMin") or f.get("aMax")):
        fields[9] = f"{f.get('aMin') or ''}-{f.get('aMax') or ''}"
    while fields and fields[-1] == "":
        fields.pop()
    return "https://www.nieruchomosci-online.pl/szukaj.html?" + quote(",".join(fields), safe=",-")


def parse_nol(page: str) -> list[Ad]:
    soup = BeautifulSoup(page, "html.parser")
    tiles = soup.select("div.tile[data-id]")
    if not tiles and "tile" not in page:
        raise RuntimeError("Nieruchomosci-online: не найден список объявлений (сайт мог измениться)")
    ads = []
    for tl in tiles:
        ad_id = re.sub(r"\D", "", tl.get("data-id", ""))
        a = tl.select_one("h2.name a") or tl.select_one("h2 a")
        if not ad_id or not a:
            continue
        attrs = {}
        for it in tl.select(".attributes__box--item"):
            txt = it.get_text(" ", strip=True)
            if ":" in txt:
                k, v = txt.split(":", 1)
                attrs[norm(k)] = v.strip()
        price_el = tl.select_one("p.title-a span")
        area_el = tl.select_one("span.area")
        prov = tl.select_one("p.province")
        loc = prov.get_text(",", strip=True) if prov else ""
        parts = [x for x in (y.strip(" ,") for y in loc.split(",")) if x]
        city = parts[-1] if parts else None
        places, zone = split_places(parts, city)
        fl = attrs.get("pietro", "")
        floor = 0 if norm(fl).startswith("parter") else (int(m.group()) if (m := re.match(r"\d+", fl)) else None)
        rooms = attrs.get("liczba pokoi")
        furn = attrs.get("umeblowane") or attrs.get("umeblowany")
        img = tl.select_one("img")
        desc = tl.select_one(".desc")
        title = a.get_text(" ", strip=True)
        href = a.get("href", "")
        ads.append(Ad(
            key=f"nol:{ad_id}",
            source="Nieruchomosci-online",
            site="nol",
            title=title,
            url=href if href.startswith("http") else "https:" + href if href.startswith("//") else href,
            price=num(price_el.get_text(" ", strip=True)) if price_el else None,
            area=area_num(area_el.get_text(" ", strip=True)) if area_el else None,
            rooms=min(int(rooms), 4) if rooms and rooms.isdigit() else None,
            floor=floor,
            places=places,
            zone=zone,
            location=", ".join(reversed(parts)),
            furniture=None if not furn else norm(furn).startswith("tak"),
            photo=img.get("src") if img else None,
            text=f"{title} {desc.get_text(' ', strip=True) if desc else ''}",
            extra=extras_codes(floor=floor, furn=bool(furn) and norm(furn).startswith("tak")),
        ))
    return ads


SOURCES = {"olx": (olx_url, parse_olx), "otodom": (otodom_url, parse_otodom),
           "domiporta": (domiporta_url, parse_domiporta), "nol": (nol_url, parse_nol)}


# ---------------------------------------------------------------- фильтры

def district_ok(ad: Ad, f: dict) -> bool:
    sel = f.get("dist") or []
    if not sel or norm(f.get("city")) != "szczecin":
        return True
    selected = {norm(d) for d in sel}
    first_tokens = {norm(d).split("-")[0] for d in sel}
    zones_touched = {norm(z) for z, osiedla in SZCZECIN.items() if any(norm(o) in selected for o in osiedla)}
    for p in ad.places:
        np_ = norm(p)
        if np_ in selected or np_ in first_tokens:
            return True
    if ad.places:
        return False
    # осидле неизвестно
    if ad.zone and norm(ad.zone) not in zones_touched:
        return False
    return bool(f.get("noDist", True))


def heating_types(t: str) -> set[str]:
    """Какое отопление упомянуто рядом со словом ogrzewanie / c.o. в тексте объявления."""
    found = set()
    windows = [t[max(0, m.start() - 40): m.end() + 60] for m in re.finditer(r"ogrzew|\bc\.?\s?o\.?\b|grzewcz|kotl|piec", t)]
    for w in windows:
        for code, rx in HEATING_TEXT.items():
            if re.search(rx, w):
                found.add(code)
    return found


def heating_ok(t: str, wanted: list[str]) -> bool:
    found = heating_types(t)
    if not found:
        return True                  # в объявлении не сказано — не отбрасываем
    return bool(found & set(wanted))


def passes(ad: Ad, f: dict, kind: str) -> bool:
    if f.get("pMin") and ad.price is not None and ad.price < f["pMin"]:
        return False
    if f.get("pMax") and ad.price is not None and ad.price > f["pMax"]:
        return False
    if f.get("tMax") and ad.total is not None and ad.total > f["tMax"]:
        return False
    if f.get("priv") and ad.private is False:
        return False
    if f.get("furn") and ad.furniture is False:
        return False
    if kind == "flat":
        if f.get("aMin") and ad.area is not None and ad.area < f["aMin"]:
            return False
        if f.get("aMax") and ad.area is not None and ad.area > f["aMax"]:
            return False
        if f.get("rooms") and ad.rooms is not None and ad.rooms not in {min(int(r), 4) for r in f["rooms"]}:
            return False
        floors = {int(x) for x in f.get("floors") or []}
        if floors and ad.floor is not None and min(ad.floor, 11) not in floors:
            return False
        if f.get("bt") and ad.building and ad.building not in f["bt"]:
            return False
        if f.get("pets") and ad.pets is False:
            return False
        if ad.site != "otodom":      # фильтры удобств есть только у Otodom — у остальных проверяем текст
            t = norm(ad.text)
            for code in f.get("ex") or []:
                if code == "LIFT" and ad.lift is not None:
                    if not ad.lift:
                        return False
                    continue
                if code == "GARAGE" and re.search(r"garaz|strzezony", norm(ad.parking)):
                    continue
                if not re.search(EXTRAS_TEXT[code], t):
                    return False
            if f.get("heat") and not heating_ok(t, f["heat"]):
                return False
    else:
        if f.get("ppl") and ad.people is not None and ad.people not in {int(p) for p in f["ppl"]}:
            return False
        if f.get("pref") and ad.prefs and f["pref"] not in ad.prefs:
            return False
    text = norm(f"{ad.text} {ad.location}")
    if any(w in text for w in words(f.get("excl", ""))):
        return False
    inc = words(f.get("incl", ""))
    if inc and not any(w in text for w in inc):
        return False
    return district_ok(ad, f)


def kinds(f: dict) -> list[str]:
    t = f.get("type", "flat")
    return ["flat", "room"] if t == "both" else [t if t in ("flat", "room") else "flat"]


def rng(lo, hi, unit: str, lang: str = "ru") -> str:
    if lo and hi:
        return f"{lo}–{hi} {unit}"
    return f"{t('from', lang)} {lo} {unit}" if lo else f"{t('to', lang)} {hi} {unit}"


def summary(f: dict, lang: str = "ru") -> str:
    e = html.escape
    kind = t({"flat": "kind_flat", "room": "kind_room", "both": "kind_both"}[f.get("type", "flat")], lang)
    lines = [f"🔎 <b>{kind}</b>, {e(CITY_NAMES.get(norm(f.get('city')), f.get('city') or ''))} · "
             + " + ".join(SOURCE_NAMES[x] for x in f.get("src") or [] if x in SOURCE_NAMES)]
    if f.get("dist"):
        lines.append("📍 " + e(", ".join(f["dist"][:12])) + (" …" if len(f["dist"]) > 12 else ""))
    pr = []
    if f.get("pMin") or f.get("pMax"):
        pr.append(t("rent", lang) + " " + rng(f.get("pMin"), f.get("pMax"), "zł", lang))
    if f.get("tMax"):
        pr.append(t("total_max", lang, v=f["tMax"]))
    if pr:
        lines.append("💰 " + ", ".join(pr))
    if f.get("type") in ("flat", "both"):
        fl = []
        if f.get("rooms"):
            fl.append(t("rooms_n", lang) + ": " + ", ".join("4+" if int(r) >= 4 else str(r) for r in sorted(f["rooms"])))
        if f.get("aMin") or f.get("aMax"):
            fl.append(rng(f.get("aMin"), f.get("aMax"), "m²", lang))
        if f.get("floors"):
            fl.append(t("floor", lang) + ": " + ", ".join(
                t("ground", lang) if int(x) == 0 else ("10+" if int(x) == 11 else str(x)) for x in sorted(f["floors"])))
        if f.get("bt"):
            fl.append(", ".join(tr(BUILDING_T, b, lang) for b in f["bt"]))
        if f.get("yearMin"):
            fl.append(t("built_from", lang, y=f["yearMin"]))
        if fl:
            lines.append("🏠 " + " · ".join(fl))
        if f.get("heat"):
            lines.append("🔥 " + t("heating", lang) + ": " + ", ".join(tr(HEATING_T, h, lang) for h in f["heat"]))
        ex = [tr(EXTRAS_T, x, lang) for x in f.get("ex") or []]
        if f.get("furn"):
            ex.append(t("furn", lang))
        if f.get("pets"):
            ex.append(t("pets", lang))
        if ex:
            lines.append("✔️ " + ", ".join(ex))
    if f.get("type") in ("room", "both"):
        rm = []
        if f.get("ppl"):
            rm.append(t("room_for", lang, n="/".join(str(p) for p in sorted(f["ppl"]))))
        if f.get("pref"):
            rm.append(t("rented_to", lang, who=tr(PREF_T, f["pref"], lang)))
        if rm:
            lines.append("🛏 " + ", ".join(rm))
    if f.get("priv"):
        lines.append("👤 " + t("private_only", lang))
    if f.get("excl"):
        lines.append("🚫 " + e(f["excl"][:150]))
    if f.get("incl"):
        lines.append("➕ " + e(f["incl"][:150]))
    return "\n".join(lines)


def clean_filters(raw: dict) -> dict:
    f = dict(DEFAULT_FILTERS)
    for k in DEFAULT_FILTERS:
        if k in raw:
            f[k] = raw[k]
    f["v"] = 2
    f["type"] = f["type"] if f["type"] in ("flat", "room", "both") else "flat"
    f["src"] = [x for x in f.get("src") or [] if x in SOURCES] or list(ALL_SOURCES)
    for k in ("pMin", "pMax", "tMax", "aMin", "aMax", "yearMin"):
        v = num(f.get(k))
        f[k] = int(v) if v else None
    f["rooms"] = sorted({int(x) for x in f.get("rooms") or [] if str(x).isdigit() and 1 <= int(x) <= 4})
    f["floors"] = sorted({int(x) for x in f.get("floors") or [] if str(x).isdigit() and 0 <= int(x) <= 11})
    f["ppl"] = sorted({int(x) for x in f.get("ppl") or [] if str(x).isdigit() and 1 <= int(x) <= 3})
    f["bt"] = [b for b in f.get("bt") or [] if b in BUILDING]
    f["ex"] = [x for x in f.get("ex") or [] if x in EXTRAS_TEXT]
    f["heat"] = [x for x in f.get("heat") or [] if x in HEATING]
    f["pref"] = f["pref"] if f.get("pref") in PREFS else ""
    f["first"] = max(0, min(int(num(f.get("first")) or 0), 10))
    f["excl"] = str(f.get("excl") or "")[:500]
    f["incl"] = str(f.get("incl") or "")[:500]
    f["dist"] = [ALL_OSIEDLA[d] if isinstance(d, int) and 0 <= d < len(ALL_OSIEDLA) else str(d)
                 for d in f.get("dist") or []][:60]
    for k in ("noDist", "furn", "pets", "priv", "paused"):
        f[k] = bool(f.get(k))
    f["name"] = str(raw.get("name") or "").strip()[:30]
    f["on"] = bool(raw.get("on", True))
    return f


# ---------------------------------------------------------------- telegram

class Telegram:
    def __init__(self, token: str, dry_run: bool = False):
        self.base = f"https://api.telegram.org/bot{token}"
        self.dry_run = dry_run

    def call(self, method: str, payload: dict, timeout: int = 40) -> dict:
        """Возвращает ответ Telegram; при ошибке {"ok": False, "error_code": ...}."""
        if self.dry_run:
            log("[dry-run]", method, (payload.get("caption") or payload.get("text") or "")[:120])
            return {"ok": True, "result": []}
        for _ in range(3):
            try:
                r = requests.post(f"{self.base}/{method}", json=payload, timeout=timeout)
            except requests.RequestException as e:
                log("telegram error:", e)
                time.sleep(3)
                continue
            if r.status_code == 429:
                time.sleep(r.json().get("parameters", {}).get("retry_after", 5) + 1)
                continue
            if r.ok:
                return r.json()
            log("telegram", method, r.status_code, r.text[:200])
            return {"ok": False, "error_code": r.status_code}
        return {"ok": False, "error_code": 0}

    def text(self, cid: str, msg: str, markup: dict | None = None, reply_to: int | None = None,
             preview: bool = False) -> dict:
        p = {"chat_id": cid, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": not preview}
        if markup:
            p["reply_markup"] = markup
        if reply_to:
            p["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
        res = self.call("sendMessage", p)
        time.sleep(0.4)
        return res

    def post(self, cid: str, caption: str, photo: str | None, markup: dict | None) -> dict:
        res = {"ok": False}
        if photo:
            res = self.call("sendPhoto", {"chat_id": cid, "photo": photo, "caption": caption, "parse_mode": "HTML",
                                          "reply_markup": markup})
        if not res.get("ok") and res.get("error_code") != 403:
            res = self.call("sendMessage", {"chat_id": cid, "text": caption, "parse_mode": "HTML",
                                            "reply_markup": markup})
        time.sleep(1.05)
        return res


def extra_text(code: tuple, lang: str) -> str:
    k = code[0]
    if k == "floor":
        fl = code[1]
        return t("ground", lang) if fl == 0 else f"{t('floor', lang)} {'10+' if fl == 11 else fl}"
    if k == "people":
        return t("people", lang, n=code[1])
    if k == "prefs":
        return t("for", lang) + ": " + ", ".join(tr(PREF_T, x, lang) for x in code[1])
    return t(k, lang)


def ev_line(ev: dict | None, lang: str) -> str | None:
    if not ev:
        return None
    m = f"{ev['median']:.0f} zł/m²" if ev["kind"] == "flat" else fmt_money(ev["median"])
    d = ev["diff"]
    if abs(d) < 5:
        return t("ev_avg", lang, w=ev["where"], m=m)
    return t("ev_below" if d < 0 else "ev_above", lang, d=abs(d), w=ev["where"], m=m)


def render(ad: Ad, kind: str, lang: str = "ru", ev: dict | None = None, flags: list | None = None,
           profile: str = "", head: str = "") -> str:
    e = html.escape
    lines = [head] if head else []
    price = f"🏠 <b>{fmt_money(ad.price)}</b>"
    if ad.czynsz:
        price += f" + czynsz {fmt_money(ad.czynsz)} = <b>{fmt_money(ad.total)}</b>"
    lines.append(price)
    specs = []
    if ad.rooms:
        specs.append("4+ pok." if ad.rooms >= 4 else f"{ad.rooms} pok.")
    if ad.area:
        specs.append(f"{ad.area:g} m²")
    specs += [extra_text(tuple(x), lang) for x in ad.extra]
    if specs:
        lines.append(" · ".join(e(x) for x in specs))
    if ad.location:
        lines.append(f"📍 {e(ad.location)}")
    line = ev_line(ev, lang)
    if line:
        lines.append(e(line))
    if flags:
        lines.append(t("scam_head", lang) + " " + e(", ".join(tr(SCAM_T, f, lang) for f in flags)))
    lines.append(f'<a href="{e(ad.url, quote=True)}">{e(ad.title[:200])}</a>')
    who = {True: t("private", lang), False: t("agency", lang)}.get(ad.private, "")
    label = t("kind_flat" if kind == "flat" else "kind_room", lang)
    tail = [ad.source, who, label] + ([f"🔎 {profile}"] if profile else [])
    lines.append("<i>" + e(" · ".join(x for x in tail if x)) + "</i>")
    return "\n".join(lines)[:1020]


def map_url(location: str, city: str = "") -> str | None:
    if not location:
        return None
    q = location if (not city or norm(city) in norm(location)) else f"{location}, {city}"
    return "https://www.google.com/maps/search/?api=1&query=" + quote(q)


def ad_markup(key: str, url: str, location: str, lang: str, faved: bool = False, city: str = "") -> dict:
    row2 = []
    m = map_url(location, city)
    if m:
        row2.append({"text": t("b_map", lang), "url": m})
    if url:
        row2.append({"text": t("b_open", lang), "url": url})
    rows = [[{"text": t("b_unfav" if faved else "b_fav", lang), "callback_data": f"f:{key}"[:64]},
             {"text": t("b_hide", lang), "callback_data": f"h:{key}"[:64]},
             {"text": t("b_write", lang), "callback_data": f"m:{key}"[:64]}]]
    if row2:
        rows.append(row2)
    return {"inline_keyboard": rows}


def short_profile(f: dict) -> dict:
    """Профиль для ссылки на страницу фильтров: только отличия от умолчаний, районы — номерами."""
    out = {}
    for k, v in f.items():
        if k in DEFAULT_FILTERS and DEFAULT_FILTERS[k] == v:
            continue
        if k == "on" and v is True:
            continue
        if k in ("v",) or v in (None, "", []):
            if k != "excl":
                continue
        out[k] = v
    if out.get("dist"):
        out["dist"] = [ALL_OSIEDLA.index(d) for d in out["dist"] if d in ALL_OSIEDLA]
    return out


def webapp_url(user: dict, lang: str = "ru") -> str | None:
    base = os.environ.get("WEBAPP_URL")
    if not base:
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        if "/" not in repo:
            return None
        owner, name = repo.split("/", 1)
        base = f"https://{owner.lower()}.github.io/{name}/"
    payload = {"s": user.get("settings") or DEFAULT_SETTINGS,
               "p": [short_profile(f) for f in (user.get("profiles") or [])]}
    data = base64.urlsafe_b64encode(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()).decode()
    return f"{base}?l={lang}&f={data.rstrip('=')}"


def keyboard(user: dict, lang: str = "ru") -> dict:
    url = webapp_url(user, lang)
    rows = [[{"text": t("btn_fav_list", lang)}, {"text": t("btn_lang", lang)}]]
    if url:
        rows.insert(0, [{"text": t("btn_filters", lang), "web_app": {"url": url}}])
    return {"keyboard": rows, "resize_keyboard": True, "is_persistent": True}


LANG_MENU = {"inline_keyboard": [[{"text": LANG_NAMES["ru"], "callback_data": "lang:ru"},
                                  {"text": LANG_NAMES["pl"], "callback_data": "lang:pl"}],
                                 [{"text": LANG_NAMES["en"], "callback_data": "lang:en"},
                                  {"text": LANG_NAMES["uk"], "callback_data": "lang:uk"}]]}
LANG_BUTTONS = {T["btn_lang"][x] for x in LANGS}
FAV_BUTTONS = {T["btn_fav_list"][x] for x in LANGS}


# ---------------------------------------------------------------- состояние

DEFAULT_SETTINGS = {"paused": False, "quiet": {"on": False, "from": 23, "to": 7}, "me": {}}
MAX_PROFILES = 3
SENT_KEEP = 400


def clean_settings(raw: dict | None) -> dict:
    raw = raw or {}
    q = raw.get("quiet") or {}
    hour = lambda v, d: int(v) if str(v).isdigit() and 0 <= int(v) <= 23 else d  # noqa: E731
    me = raw.get("me") or {}
    people = int(me["people"]) if str(me.get("people", "")).isdigit() and 1 <= int(me["people"]) <= 6 else None
    return {
        "paused": bool(raw.get("paused")),
        "quiet": {"on": bool(q.get("on")), "from": hour(q.get("from"), 23), "to": hour(q.get("to"), 7)},
        "me": {"name": str(me.get("name") or "").strip()[:40], "move": str(me.get("move") or "").strip()[:40],
               "people": people, "job": me.get("job") if me.get("job") in ("work", "study", "both") else "",
               "pets": me.get("pets") if me.get("pets") in ("no", "cat", "dog", "small") else "",
               "smoke": "no" if me.get("smoke") == "no" else "", "note": str(me.get("note") or "").strip()[:200]},
    }


def _cipher():
    """Шифр для seen.json: репозиторий публичный, а там фильтры людей. Ключ — из токена бота."""
    from cryptography.fernet import Fernet
    import hashlib
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return None
    key = base64.urlsafe_b64encode(hashlib.sha256(("flat-bot:" + token).encode()).digest())
    return Fernet(key)


_SAVED: dict = {}


def new_user() -> dict:
    return {"profiles": [], "pbase": [], "settings": clean_settings({}), "seen": {}, "sent": {}, "fav": {},
            "hidden": {}, "held": 0, "blocked": False, "joined": datetime.now(timezone.utc).isoformat()[:10]}


def upgrade_user(u: dict) -> None:
    """Переезд со старых версий: один набор фильтров -> профили + настройки."""
    for k, v in new_user().items():
        u.setdefault(k, v if not isinstance(v, (dict, list)) else type(v)(v))
    f = u.pop("filters", None)
    if f is not None and not u["profiles"]:
        if int(f.get("v") or 1) < 2:                      # v2: добавились Domiporta и Nieruchomosci-online
            f["src"] = list(dict.fromkeys(list(f.get("src") or []) + ["domiporta", "nol"]))
            u["baseline"] = True
        u["settings"]["paused"] = bool(f.get("paused"))
        f = clean_filters(f)
        u["profiles"] = [f]
        u["pbase"] = [bool(u.get("baseline", False))]
    u.pop("baseline", None)
    while len(u["pbase"]) < len(u["profiles"]):
        u["pbase"].append(True)


def load_state(admins: list[str]) -> dict:
    st = {}
    if STATE_PATH.exists():
        raw = STATE_PATH.read_text("utf-8").strip()
        try:
            if raw.startswith("{"):                       # старая незашифрованная версия
                st = json.loads(raw)
            elif raw:
                c = _cipher()
                st = json.loads(c.decrypt(raw.encode()).decode()) if c else {}
            _SAVED["plain"] = json.dumps(st, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        except Exception:  # noqa: BLE001
            log("seen.json не читается (сменился токен?) — начинаю заново")
            st = {}
    if "users" not in st:                                 # переезд с версии «для одного»
        old_f, old_seen = st.get("filters"), st.get("seen") or {}
        st = {"offset": st.get("offset", 0), "errors": {}, "users": {}}
        for a in admins:
            u = new_user()
            u["filters"], u["seen"], u["baseline"] = old_f, dict(old_seen), old_f is None
            st["users"][a] = u
    st.setdefault("offset", 0)
    st.setdefault("errors", {})
    st.setdefault("stats", {})
    for u in st["users"].values():
        upgrade_user(u)
    return st


def save_state(st: dict, keep_days: int = 60):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat()
    for u in st["users"].values():
        u["seen"] = {k: v for k, v in u["seen"].items() if v >= cutoff}
        u["hidden"] = {k: v for k, v in u["hidden"].items() if v >= cutoff}
        while len(u["sent"]) > SENT_KEEP:
            u["sent"].pop(next(iter(u["sent"])))
    data = json.dumps(st, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if data == _SAVED.get("plain") and STATE_PATH.exists():
        return                                   # ничего не изменилось — не трогаем файл (меньше коммитов)
    c = _cipher()
    STATE_PATH.write_text(c.encrypt(data.encode()).decode() if c else data, "utf-8")
    _SAVED["plain"] = data


# ---------------------------------------------------------------- сообщения боту

MAX_USERS = int(os.environ.get("MAX_USERS", "300"))


def profile_label(f: dict, i: int, lang: str) -> str:
    return f.get("name") or f"{t('profile', lang)} {i + 1}"


def all_summary(user: dict, lang: str) -> str:
    profs = user.get("profiles") or []
    s = user.get("settings") or DEFAULT_SETTINGS
    on = [(i, f) for i, f in enumerate(profs) if f.get("on", True)]
    parts = []
    for i, f in on:
        head = f"<b>{html.escape(profile_label(f, i, lang))}</b>\n" if len(on) > 1 else ""
        parts.append(head + summary(f, lang))
    if s.get("quiet", {}).get("on"):
        parts.append(t("quiet_on", lang, a=s["quiet"]["from"], b=s["quiet"]["to"]))
    return "\n\n".join(parts)


def send_welcome(tg: Telegram, cid: str, user: dict) -> None:
    lang = lang_of(user)
    tg.text(cid, t("welcome", lang), markup=keyboard(user, lang))


def send_filters(tg: Telegram, cid: str, user: dict) -> None:
    lang = lang_of(user)
    paused = t("paused", lang) + "\n\n" if user["settings"].get("paused") else ""
    tg.text(cid, f"{paused}{t('your_filters', lang)}\n\n{all_summary(user, lang)}\n\n"
                 f"{t('change_hint', lang, btn=t('btn_filters', lang))}", markup=keyboard(user, lang))


def send_favorites(tg: Telegram, cid: str, user: dict) -> None:
    lang = lang_of(user)
    favs = list(user["fav"].items())[::-1][:30]
    if not favs:
        tg.text(cid, t("fav_empty", lang), markup=keyboard(user, lang))
        return
    e = html.escape
    lines = [t("fav_title", lang, n=len(user["fav"]))]
    for _, a in favs:
        bits = [fmt_money(a.get("p"))] + ([f"{a['a']:g} m²"] if a.get("a") else []) + ([a["l"]] if a.get("l") else [])
        lines.append(f"• {e(' · '.join(bits))} — <a href=\"{e(a.get('u') or '', quote=True)}\">{e((a.get('t') or '')[:60])}</a>")
    lines.append("\n" + t("fav_hint", lang))
    tg.text(cid, "\n".join(lines), markup=keyboard(user, lang))


def send_owner_message(tg: Telegram, cid: str, user: dict, entry: dict) -> None:
    lang = lang_of(user)
    me = user["settings"].get("me") or {}
    full, short = owner_message(entry, me, entry.get("k", "flat"))
    e = html.escape
    msg = (f"{t('msg_intro', lang)}\n\n<code>{e(full)}</code>\n\n{t('msg_short', lang)}\n<code>{e(short)}</code>\n\n"
           f"🔗 <a href=\"{e(entry.get('u') or '', quote=True)}\">{e((entry.get('t') or '')[:80])}</a>")
    if not (me.get("name") or me.get("people") or me.get("move")):
        msg += "\n\n" + t("msg_fill", lang)
    tg.text(cid, msg)


def handle_callback(tg: Telegram, st: dict, cq: dict) -> None:
    msg = cq.get("message") or {}
    cid = str((msg.get("chat") or {}).get("id") or (cq.get("from") or {}).get("id"))
    data = cq.get("data") or ""
    user = st["users"].get(cid)
    if user is None:
        tg.call("answerCallbackQuery", {"callback_query_id": cq.get("id")})
        return
    lang = lang_of(user)
    if data.startswith("lang:") and data[5:] in LANGS:
        tg.call("answerCallbackQuery", {"callback_query_id": cq.get("id")})
        user["lang"] = data[5:]
        lang = user["lang"]
        if msg.get("message_id"):
            tg.call("editMessageText", {"chat_id": cid, "message_id": msg["message_id"], "text": t("lang_set", lang)})
        if user.get("profiles"):
            send_filters(tg, cid, user)
        else:
            send_welcome(tg, cid, user)
        return
    op, _, key = data.partition(":")
    entry = user["sent"].get(key) or user["fav"].get(key)
    if not entry:
        tg.call("answerCallbackQuery", {"callback_query_id": cq.get("id"), "text": t("gone", lang)})
        return
    if op == "f":
        if key in user["fav"]:
            user["fav"].pop(key)
            note, faved = t("unfaved", lang), False
        else:
            user["fav"][key] = dict(entry)
            note, faved = t("faved", lang), True
        tg.call("answerCallbackQuery", {"callback_query_id": cq.get("id"), "text": note})
        if msg.get("message_id"):
            tg.call("editMessageReplyMarkup", {"chat_id": cid, "message_id": msg["message_id"],
                                               "reply_markup": ad_markup(key, entry.get("u"), entry.get("l"), lang,
                                                                         faved, entry.get("city", ""))})
    elif op == "h":
        user["hidden"][key] = datetime.now(timezone.utc).isoformat()
        user["fav"].pop(key, None)
        tg.call("answerCallbackQuery", {"callback_query_id": cq.get("id"), "text": t("hidden", lang)})
        if msg.get("message_id"):
            tg.call("deleteMessage", {"chat_id": cid, "message_id": msg["message_id"]})
    elif op == "m":
        tg.call("answerCallbackQuery", {"callback_query_id": cq.get("id")})
        send_owner_message(tg, cid, user, entry)
    else:
        tg.call("answerCallbackQuery", {"callback_query_id": cq.get("id")})


def parse_webapp(data: str) -> tuple[dict, list[dict]]:
    raw = json.loads(data or "{}")
    if isinstance(raw, dict) and "p" in raw:                  # v3: настройки + профили
        profs = [clean_filters(p) for p in (raw.get("p") or []) if isinstance(p, dict)][:MAX_PROFILES]
        return clean_settings(raw.get("s")), profs
    f = clean_filters(raw)                                    # старая страница: один набор фильтров
    return clean_settings({"paused": raw.get("paused")}), [f]


def handle_updates(tg: Telegram, st: dict, wait: int = 0) -> None:
    res = tg.call("getUpdates", {"offset": st["offset"] + 1 if st["offset"] else 0, "timeout": wait,
                                 "allowed_updates": ["message", "callback_query"]}, timeout=wait + 15)
    for upd in res.get("result", []) or []:
        st["offset"] = max(st["offset"], upd["update_id"])
        if upd.get("callback_query"):
            handle_callback(tg, st, upd["callback_query"])
            continue
        msg = upd.get("message") or {}
        chat = msg.get("chat") or {}
        if chat.get("type") != "private":
            continue
        cid = str(chat.get("id"))
        user = st["users"].get(cid)
        text = (msg.get("text") or "").strip()
        if user is None:
            if len(st["users"]) >= MAX_USERS:
                tg.text(cid, t("closed", "en"))
                continue
            user = st["users"][cid] = new_user()
            log("новый пользователь")
        user["blocked"] = False
        lang = lang_of(user)
        wad = msg.get("web_app_data")
        if wad:
            try:
                settings, profs = parse_webapp(wad.get("data"))
            except (json.JSONDecodeError, TypeError, ValueError, AttributeError) as ex:
                tg.text(cid, t("read_error", lang, e=html.escape(str(ex))))
                continue
            old = user.get("profiles") or []
            changed = False
            pbase = []
            for i, f in enumerate(profs):
                same = i < len(old) and {k: v for k, v in old[i].items() if k != "name"} == \
                    {k: v for k, v in f.items() if k != "name"}
                pbase.append((user["pbase"][i] if i < len(user["pbase"]) else True) if same else True)
                changed |= not same
            user["profiles"], user["pbase"], user["settings"] = profs, pbase, settings
            if settings["paused"]:
                head, tail = t("paused", lang), t("paused_tail", lang)
            else:
                head = t("saved", lang)
                firsts = [f["first"] for i, f in enumerate(profs) if pbase[i] and f.get("on", True)]
                tail = t("first_tail", lang, n=max(firsts)) if changed and firsts and max(firsts) else t("only_new", lang)
            tg.text(cid, f"{head}\n\n{all_summary(user, lang)}\n\n{tail}", markup=keyboard(user, lang))
        elif text.startswith("/start") or text.startswith("/lang") or text in LANG_BUTTONS or not user.get("lang"):
            tg.text(cid, LANG_PROMPT, markup=LANG_MENU)
        elif text.startswith("/fav") or text in FAV_BUTTONS:
            send_favorites(tg, cid, user)
        elif not user.get("profiles"):
            send_welcome(tg, cid, user)
        else:
            send_filters(tg, cid, user)


# ---------------------------------------------------------------- поиск

def needs_own_query(src: str, f: dict, kind: str) -> bool:
    """Фильтры, которые сайт не показывает в списке — их можно применить только в самом запросе."""
    return src == "otodom" and kind == "flat" and bool(f.get("bt") or f.get("ex") or f.get("yearMin") or f.get("heat"))


class Pages:
    """Кэш страниц за один проход: одинаковые запросы разных людей скачиваются один раз."""

    def __init__(self):
        self.cache: dict[str, list[Ad] | Exception] = {}

    def get(self, src: str, url: str) -> list[Ad]:
        if url not in self.cache:
            try:
                self.cache[url] = SOURCES[src][1](fetch(url))
                time.sleep(1.5)
            except Exception as e:  # noqa: BLE001
                self.cache[url] = e
        res = self.cache[url]
        if isinstance(res, Exception):
            raise res
        return res


def is_quiet(settings: dict, now: datetime | None = None) -> bool:
    q = (settings or {}).get("quiet") or {}
    if not q.get("on"):
        return False
    from zoneinfo import ZoneInfo
    h = (now or datetime.now(ZoneInfo("Europe/Warsaw"))).hour
    a, b = int(q.get("from", 23)), int(q.get("to", 7))
    return (a <= h < b) if a < b else (h >= a or h < b)


def remember(user: dict, ad: Ad, kind: str, city: str, msg_id: int | None, fp: str | None) -> None:
    user["sent"].pop(ad.key, None)
    user["sent"][ad.key] = {"t": ad.title[:120], "p": ad.price, "c": ad.czynsz, "a": ad.area, "u": ad.url,
                            "l": ad.location[:100], "s": ad.source, "k": kind, "m": msg_id, "fp": fp,
                            "city": city, "d": datetime.now(timezone.utc).isoformat()[:10]}


def search_user(tg: Telegram, st: dict, cid: str, user: dict, pages: Pages, admins: list[str],
                now_local: datetime | None = None) -> int:
    settings = user["settings"]
    if settings.get("paused"):
        return 0
    lang = lang_of(user)
    stats = st.setdefault("stats", {})
    now = datetime.now(timezone.utc).isoformat()
    profs = user.get("profiles") or []
    multi = sum(1 for f in profs if f.get("on", True)) > 1
    fresh: dict[str, tuple] = {}                  # ключ -> (объявление, flat/room, профиль, город)
    drops: dict[str, tuple] = {}
    first_send: list[tuple] = []
    for i, f in enumerate(profs):
        if not f.get("on", True):
            continue
        baseline = user["pbase"][i] if i < len(user["pbase"]) else True
        pname = profile_label(f, i, lang) if multi else ""
        city = CITY_NAMES.get(norm(f.get("city")), f.get("city") or "")
        matched: dict[str, tuple] = {}
        ok_any = False
        for src in f["src"]:
            for kind in kinds(f):
                sid = f"{src}-{kind}-{norm(f.get('city'))}"
                try:
                    if baseline or needs_own_query(src, f, kind):
                        url = SOURCES[src][0](f, kind)                       # запрос с фильтрами человека
                    else:
                        url = SOURCES[src][0]({"city": f.get("city")}, kind)  # общая лента новых, фильтруем сами
                    if url is None:
                        continue                                          # на этом сайте нет такого типа жилья
                    ads = pages.get(src, url)
                    st["errors"].pop(sid, None)
                    ok_any = True
                except Exception as e:  # noqa: BLE001
                    n = st["errors"].get(sid, 0) + 1
                    st["errors"][sid] = n
                    log(f"[{sid}] ошибка: {e}")
                    if n == 3:
                        for a in admins:
                            tg.text(a, f"⚠️ {html.escape(sid)} не отвечает 3 проверки подряд:\n"
                                       f"<code>{html.escape(str(e))[:300]}</code>")
                    continue
                for a in ads:
                    stats_add(stats, kind, city, a.key, a.price, a.area, a.places, a.zone)
                for a in ads:
                    if a.key in user["hidden"] or not passes(a, f, kind):
                        continue
                    if baseline:
                        matched.setdefault(a.key, (a, kind, pname, city))
                    elif a.key in user["seen"]:
                        old = user["sent"].get(a.key)
                        if old and old.get("p") and a.price and a.price <= old["p"] * 0.97:
                            drops.setdefault(a.key, (a, kind, pname, city, old["p"]))
                    else:
                        fresh.setdefault(a.key, (a, kind, pname, city))
        if baseline and ok_any:
            items = sorted(matched.values(), key=lambda x: x[0].created)
            for x in items:
                user["seen"][x[0].key] = now
                fresh.pop(x[0].key, None)
            if f["first"]:
                first_send += items[-f["first"]:]
            user["pbase"][i] = False

    quiet = is_quiet(settings, now_local)
    queue = sorted(fresh.values(), key=lambda x: x[0].created)
    if quiet:
        user["held"] = max(user.get("held", 0), len(queue))
        queue, drops = [], {}
    elif user.get("held") and queue:
        tg.text(cid, t("night", lang, n=len(queue)))
    cap = 30 if user.get("held") else 15
    if not quiet:
        user["held"] = 0

    # индекс отпечатков уже присланного — для склейки дублей с разных сайтов
    fps = {v["fp"]: (k, v) for k, v in user["sent"].items() if v.get("fp")}
    sent = 0
    for item in first_send + queue[:cap]:
        a, kind, pname, city = item
        if a.key in user["seen"] and item not in first_send:
            continue
        fp = fingerprint(a.price, a.area, a.rooms)
        if fp and fp in fps and fps[fp][0] != a.key and fps[fp][1].get("s") != a.source:
            k0, v0 = fps[fp]                      # та же квартира на другом сайте (на одном сайте — не склеиваем)
            user["seen"][a.key] = now
            if k0 in user["hidden"]:
                continue
            res = tg.text(cid, f"{t('dup', lang, site=a.source)}\n<a href=\"{html.escape(a.url, quote=True)}\">"
                               f"{html.escape(a.title[:100])}</a>", reply_to=v0.get("m"))
            if res.get("error_code") == 403:
                user["blocked"] = True
                return sent
            continue
        ev = price_eval(stats, kind, city, a.key, a.price, a.area, a.places, a.zone)
        flags = scam_flags(a.text, ev)
        caption = render(a, kind, lang, ev, flags, pname)
        res = tg.post(cid, caption, a.photo, ad_markup(a.key, a.url, a.location, lang, a.key in user["fav"], city))
        if res.get("error_code") == 403:                  # человек заблокировал бота
            user["blocked"] = True
            return sent
        msg_id = ((res.get("result") or {}) if isinstance(res.get("result"), dict) else {}).get("message_id")
        remember(user, a, kind, city, msg_id, fp)
        user["seen"][a.key] = now
        if fp:
            fps[fp] = (a.key, user["sent"][a.key])
        sent += 1
    for a, kind, pname, city, old_price in list(drops.values())[:10]:
        head = t("drop", lang, old=fmt_money(old_price), new=fmt_money(a.price))
        ev = price_eval(stats, kind, city, a.key, a.price, a.area, a.places, a.zone)
        caption = render(a, kind, lang, ev, scam_flags(a.text, ev), pname, head=head)
        res = tg.post(cid, caption, a.photo, ad_markup(a.key, a.url, a.location, lang, a.key in user["fav"], city))
        if res.get("error_code") == 403:
            user["blocked"] = True
            return sent
        msg_id = ((res.get("result") or {}) if isinstance(res.get("result"), dict) else {}).get("message_id")
        remember(user, a, kind, city, msg_id, fingerprint(a.price, a.area, a.rooms))
        if a.key in user["fav"]:
            user["fav"][a.key]["p"] = a.price
        sent += 1
    return sent


_TRIES: dict[str, float] = {}


def needs_baseline(cid: str, u: dict) -> bool:
    """Есть включённый профиль с новыми фильтрами (и прошло 2 минуты с прошлой попытки)."""
    if not u.get("profiles") or u["settings"].get("paused") or u.get("blocked"):
        return False
    if time.time() - _TRIES.get(cid, 0) < 120:
        return False
    return any(b and f.get("on", True) for b, f in zip(u.get("pbase") or [], u["profiles"]))


def search_round(tg: Telegram, st: dict, admins: list[str], only: list[str] | None = None) -> None:
    pages = Pages()
    total = 0
    active = [(cid, u) for cid, u in st["users"].items()
              if u.get("profiles") and not u["settings"].get("paused") and not u.get("blocked")
              and (only is None or cid in only)]
    for cid, u in active:
        total += search_user(tg, st, cid, u, pages, admins)
    log(f"проверка: людей {len(active)}, страниц {len(pages.cache)}, отправлено {total}")


# ---------------------------------------------------------------- main

def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    admins = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
    dry = os.environ.get("DRY_RUN") == "1" or not token
    if dry:
        log("Нет TELEGRAM_BOT_TOKEN — режим проверки, в Telegram ничего не уходит")
    tg = Telegram(token, dry_run=dry)
    st = load_state(admins)
    listen = int(os.environ.get("RUN_SECONDS", "0"))      # сколько секунд слушать сообщения после поиска
    every = int(os.environ.get("SEARCH_EVERY", "600"))
    started = time.time()

    handle_updates(tg, st)
    search_round(tg, st, admins)
    last = time.time()
    if not dry:
        save_state(st)

    while time.time() - started < listen - 5:
        left = listen - (time.time() - started)
        t0 = time.time()
        handle_updates(tg, st, wait=int(max(1, min(25, left - 3))))
        if time.time() - t0 < 1:
            time.sleep(2)                                   # Telegram ответил ошибкой сразу — не долбим
        pending = [cid for cid, u in st["users"].items() if needs_baseline(cid, u)]
        if pending:
            for cid in pending:
                _TRIES[cid] = time.time()
            search_round(tg, st, admins, only=pending)       # новые фильтры — ищем сразу
        if time.time() - last >= every:
            search_round(tg, st, admins)
            last = time.time()
        if not dry:
            save_state(st)

    if not dry:
        save_state(st)
    log(f"Готово. Пользователей: {len(st['users'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
