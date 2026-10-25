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
from urllib.parse import urlencode

import requests

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
BUILDING_RU = {"BLOCK": "блок", "TENEMENT": "каменица", "APARTMENT": "апартаментовец", "HOUSE": "дом",
               "LOFT": "лофт", "OTHER": "другое"}

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
EXTRAS_RU = {"BALCONY": "балкон", "TERRACE": "терраса", "GARDEN": "сад", "LIFT": "лифт", "GARAGE": "гараж/парковка",
             "AIR_CONDITIONING": "кондиционер", "SEPARATE_KITCHEN": "отдельная кухня", "INTERNET": "интернет"}

# Отопление: код Otodom -> как это пишут в тексте объявлений OLX
HEATING = ["URBAN", "GAS", "ELECTRICAL", "BOILER_ROOM", "TILED_STOVE", "OTHER"]
HEATING_RU = {"URBAN": "городское (miejskie)", "GAS": "газовое", "ELECTRICAL": "электрическое",
              "BOILER_ROOM": "котельная", "TILED_STOVE": "кафельная печь", "OTHER": "другое"}
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

PREF_RU = {"man": "мужчине", "women": "женщине", "student": "студенту", "working": "работающему"}
PEOPLE_OTODOM = {1: "ONE", 2: "TWO", 3: "THREE"}
PEOPLE_OLX = {1: "one", 2: "two", 3: "three"}

DEFAULT_FILTERS = {
    "v": 1, "type": "flat", "src": ["olx", "otodom"], "city": "szczecin", "dist": [], "noDist": True,
    "pMin": None, "pMax": None, "tMax": None, "rooms": [], "aMin": None, "aMax": None, "floors": [],
    "bt": [], "ex": [], "heat": [], "furn": False, "pets": False, "yearMin": None, "ppl": [], "pref": "",
    "priv": False, "excl": "tylko dla kobiet, tylko dla studentek, na doby, krótkoterminowy", "incl": "",
    "first": 3, "paused": False,
}


@dataclass
class Ad:
    key: str
    source: str
    title: str
    url: str
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
    extra: list[str] = field(default_factory=list)

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
        extra = []
        if furn == "yes":
            extra.append("с мебелью")
        if pets == "Tak":
            extra.append("можно с животными")
        if floor is not None:
            extra.append("партер" if floor == 0 else f"этаж {floor}")
        if people:
            extra.append(f"на {people} чел.")
        prefs = [x for x in str(val("preferences") or "").split(",") if x]
        if prefs:
            extra.append("для: " + ", ".join(PREF_RU.get(x, x) for x in prefs))
        district = loc.get("districtName")
        ads.append(Ad(
            key=f"otodom:{tok}" if tok else f"olx:{a['id']}",
            source="Otodom (через OLX)" if tok else "OLX",
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
        extra = []
        if floor is not None:
            extra.append("партер" if floor == 0 else ("этаж 10+" if floor == 11 else f"этаж {floor}"))
        if people:
            extra.append(f"на {people} чел.")
        ads.append(Ad(
            key=f"otodom:{tok}",
            source="Otodom",
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


SOURCES = {"olx": (olx_url, parse_olx), "otodom": (otodom_url, parse_otodom)}


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
        if ad.source == "OLX":       # на OLX нет фильтров удобств — проверяем по тексту
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


def rng(lo, hi, unit: str) -> str:
    if lo and hi:
        return f"{lo}–{hi} {unit}"
    return f"от {lo} {unit}" if lo else f"до {hi} {unit}"


def summary(f: dict) -> str:
    e = html.escape
    t = {"flat": "квартира", "room": "комната", "both": "квартира или комната"}[f.get("type", "flat")]
    lines = [f"🔎 <b>{t}</b>, {e(CITY_NAMES.get(norm(f.get('city')), f.get('city') or ''))} · "
             + " + ".join({"olx": "OLX", "otodom": "Otodom"}[s] for s in f.get("src") or [])]
    if f.get("dist"):
        lines.append("📍 " + e(", ".join(f["dist"][:12])) + (" …" if len(f["dist"]) > 12 else ""))
    pr = []
    if f.get("pMin") or f.get("pMax"):
        pr.append("аренда " + rng(f.get("pMin"), f.get("pMax"), "zł"))
    if f.get("tMax"):
        pr.append(f"с czynsz до {f['tMax']} zł")
    if pr:
        lines.append("💰 " + ", ".join(pr))
    if f.get("type") in ("flat", "both"):
        fl = []
        if f.get("rooms"):
            fl.append("комнат: " + ", ".join("4+" if int(r) >= 4 else str(r) for r in sorted(f["rooms"])))
        if f.get("aMin") or f.get("aMax"):
            fl.append(rng(f.get("aMin"), f.get("aMax"), "m²"))
        if f.get("floors"):
            fl.append("этаж: " + ", ".join("партер" if int(x) == 0 else ("10+" if int(x) == 11 else str(x))
                                            for x in sorted(f["floors"])))
        if f.get("bt"):
            fl.append(", ".join(BUILDING_RU[b] for b in f["bt"] if b in BUILDING_RU))
        if f.get("yearMin"):
            fl.append(f"дом от {f['yearMin']} г.")
        if fl:
            lines.append("🏠 " + " · ".join(fl))
        if f.get("heat"):
            lines.append("🔥 отопление: " + ", ".join(HEATING_RU[h] for h in f["heat"]))
        ex = [EXTRAS_RU[x] for x in f.get("ex") or [] if x in EXTRAS_RU]
        if f.get("furn"):
            ex.append("с мебелью")
        if f.get("pets"):
            ex.append("можно с животными")
        if ex:
            lines.append("✔️ " + ", ".join(ex))
    if f.get("type") in ("room", "both"):
        rm = []
        if f.get("ppl"):
            rm.append("на " + "/".join(str(p) for p in sorted(f["ppl"])) + " чел.")
        if f.get("pref"):
            rm.append("сдают " + PREF_RU.get(f["pref"], f["pref"]))
        if rm:
            lines.append("🛏 комната " + ", ".join(rm))
    if f.get("priv"):
        lines.append("👤 только частники")
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
    f["type"] = f["type"] if f["type"] in ("flat", "room", "both") else "flat"
    f["src"] = [s for s in f.get("src") or [] if s in SOURCES] or ["olx", "otodom"]
    for k in ("pMin", "pMax", "tMax", "aMin", "aMax", "yearMin"):
        v = num(f.get(k))
        f[k] = int(v) if v else None
    f["rooms"] = sorted({int(x) for x in f.get("rooms") or [] if str(x).isdigit() and 1 <= int(x) <= 4})
    f["floors"] = sorted({int(x) for x in f.get("floors") or [] if str(x).isdigit() and 0 <= int(x) <= 11})
    f["ppl"] = sorted({int(x) for x in f.get("ppl") or [] if str(x).isdigit() and 1 <= int(x) <= 3})
    f["bt"] = [b for b in f.get("bt") or [] if b in BUILDING]
    f["ex"] = [x for x in f.get("ex") or [] if x in EXTRAS_TEXT]
    f["heat"] = [x for x in f.get("heat") or [] if x in HEATING]
    f["pref"] = f["pref"] if f.get("pref") in PREF_RU else ""
    f["first"] = max(0, min(int(num(f.get("first")) or 0), 10))
    f["excl"] = str(f.get("excl") or "")[:500]
    f["incl"] = str(f.get("incl") or "")[:500]
    f["dist"] = [str(d) for d in f.get("dist") or []][:60]
    for k in ("noDist", "furn", "pets", "priv", "paused"):
        f[k] = bool(f.get(k))
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

    def text(self, cid: str, msg: str, markup: dict | None = None) -> dict:
        p = {"chat_id": cid, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": True}
        if markup:
            p["reply_markup"] = markup
        res = self.call("sendMessage", p)
        time.sleep(0.4)
        return res

    def ad(self, cid: str, ad: Ad, label: str) -> dict:
        cap = render(ad, label)
        res = {"ok": False}
        if ad.photo:
            res = self.call("sendPhoto", {"chat_id": cid, "photo": ad.photo, "caption": cap, "parse_mode": "HTML"})
        if not res.get("ok") and res.get("error_code") != 403:
            res = self.call("sendMessage", {"chat_id": cid, "text": cap, "parse_mode": "HTML"})
        time.sleep(1.05)
        return res


def render(ad: Ad, label: str) -> str:
    e = html.escape
    head = f"🏠 <b>{fmt_money(ad.price)}</b>"
    if ad.czynsz:
        head += f" + czynsz {fmt_money(ad.czynsz)} = <b>{fmt_money(ad.total)}</b>"
    specs = []
    if ad.rooms:
        specs.append("4+ pok." if ad.rooms >= 4 else f"{ad.rooms} pok.")
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
    lines.append("<i>" + " · ".join(x for x in [ad.source, who, label] if x) + "</i>")
    return "\n".join(lines)[:1020]


def webapp_url(f: dict) -> str | None:
    base = os.environ.get("WEBAPP_URL")
    if not base:
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        if "/" not in repo:
            return None
        owner, name = repo.split("/", 1)
        base = f"https://{owner.lower()}.github.io/{name}/"
    # в ссылку кладём только непустые поля, районы — номерами (так ссылка короче)
    short = {k: v for k, v in f.items() if v not in (None, "", [], False) or k in ("noDist",)}
    if short.get("dist"):
        short["dist"] = [ALL_OSIEDLA.index(d) for d in short["dist"] if d in ALL_OSIEDLA]
    data = base64.urlsafe_b64encode(json.dumps(short, ensure_ascii=False, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{base}?f={data}"


def keyboard(f: dict) -> dict | None:
    url = webapp_url(f)
    if not url:
        return None
    return {"keyboard": [[{"text": "⚙️ Фильтры", "web_app": {"url": url}}]],
            "resize_keyboard": True, "is_persistent": True}


# ---------------------------------------------------------------- состояние

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
    return {"filters": None, "baseline": True, "seen": {}, "blocked": False,
            "joined": datetime.now(timezone.utc).isoformat()[:10]}


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
    return st


def save_state(st: dict, keep_days: int = 60):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat()
    for u in st["users"].values():
        u["seen"] = {k: v for k, v in u["seen"].items() if v >= cutoff}
    data = json.dumps(st, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if data == _SAVED.get("plain") and STATE_PATH.exists():
        return                                   # ничего не изменилось — не трогаем файл (меньше коммитов)
    c = _cipher()
    STATE_PATH.write_text(c.encrypt(data.encode()).decode() if c else data, "utf-8")
    _SAVED["plain"] = data


# ---------------------------------------------------------------- сообщения боту

WELCOME = ("Привет! Я ищу квартиры и комнаты на <b>OLX</b> и <b>Otodom</b> и присылаю только новые "
           "объявления по твоим фильтрам.\n\n"
           "Нажми <b>⚙️ Фильтры</b> внизу, выбери, что ищешь, и сохрани. Пока фильтры не выбраны, я ничего не присылаю.\n\n"
           "Проверка новых объявлений — примерно раз в 10 минут. Остановить — переключатель «Поиск на паузе» "
           "в фильтрах.")
MAX_USERS = int(os.environ.get("MAX_USERS", "300"))


def handle_updates(tg: Telegram, st: dict, wait: int = 0) -> None:
    res = tg.call("getUpdates", {"offset": st["offset"] + 1 if st["offset"] else 0, "timeout": wait,
                                 "allowed_updates": ["message"]}, timeout=wait + 15)
    for upd in res.get("result", []) or []:
        st["offset"] = max(st["offset"], upd["update_id"])
        msg = upd.get("message") or {}
        chat = msg.get("chat") or {}
        if chat.get("type") != "private":
            continue
        cid = str(chat.get("id"))
        user = st["users"].get(cid)
        if user is None:
            if len(st["users"]) >= MAX_USERS:
                tg.text(cid, "Извини, сейчас бот не принимает новых пользователей.")
                continue
            user = st["users"][cid] = new_user()
            log("новый пользователь")
        user["blocked"] = False
        wad = msg.get("web_app_data")
        if wad:
            try:
                f = clean_filters(json.loads(wad.get("data") or "{}"))
            except (json.JSONDecodeError, TypeError, ValueError) as ex:
                tg.text(cid, f"Не смог прочитать фильтры: {html.escape(str(ex))}")
                continue
            old = user.get("filters") or {}
            only_pause = {k: v for k, v in old.items() if k != "paused"} == {k: v for k, v in f.items() if k != "paused"}
            user["filters"] = f
            if not only_pause:
                user["baseline"] = True
            if f["paused"]:
                head, tail = "⏸ <b>Поиск на паузе.</b>", "\n\nЧтобы продолжить — открой фильтры и выключи паузу."
            else:
                head = "✅ <b>Фильтры сохранены.</b>"
                tail = (f"\n\nСейчас пришлю {f['first']} самых свежих подходящих, дальше — только новые."
                        if not only_pause and f["first"] else "\n\nДальше присылаю только новые объявления.")
            tg.text(cid, f"{head}\n\n{summary(f)}{tail}", markup=keyboard(f))
        elif (msg.get("text") or "").startswith("/start") or not user.get("filters"):
            tg.text(cid, WELCOME, markup=keyboard(user.get("filters") or DEFAULT_FILTERS))
        else:
            f = user["filters"]
            state = "⏸ Поиск на паузе.\n\n" if f.get("paused") else ""
            tg.text(cid, f"{state}Твои фильтры:\n\n{summary(f)}\n\nИзменить — кнопка <b>⚙️ Фильтры</b>.",
                    markup=keyboard(f))


# ---------------------------------------------------------------- поиск

def needs_own_otodom(f: dict, kind: str) -> bool:
    """Фильтры, которые Otodom не отдаёт в списке объявлений — их можно применить только в запросе."""
    return kind == "flat" and bool(f.get("bt") or f.get("ex") or f.get("yearMin") or f.get("heat"))


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


def search_user(tg: Telegram, st: dict, cid: str, user: dict, pages: Pages, admins: list[str]) -> int:
    f = user["filters"]
    baseline = user.get("baseline", True)
    now = datetime.now(timezone.utc).isoformat()
    found: dict[str, tuple[Ad, str]] = {}
    ok_any = False
    for src in f["src"]:
        for kind in kinds(f):
            label = {"flat": "квартира", "room": "комната"}[kind]
            if baseline or (src == "otodom" and needs_own_otodom(f, kind)):
                url = SOURCES[src][0](f, kind)                       # запрос с фильтрами человека
            else:
                url = SOURCES[src][0]({"city": f.get("city")}, kind)  # общая лента новых, фильтруем сами
            sid = f"{src}-{kind}-{norm(f.get('city'))}"
            try:
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
                if a.key not in user["seen"] and a.key not in found and passes(a, f, kind):
                    found[a.key] = (a, label)
    fresh = sorted(found.values(), key=lambda x: x[0].created)
    if baseline:
        if not ok_any:
            return 0
        for a, _ in fresh:
            user["seen"][a.key] = now
        to_send = fresh[-f["first"]:] if f["first"] else []
        user["baseline"] = False
    else:
        to_send = fresh[:15]                    # остальное — в следующую проверку
    sent = 0
    for a, label in to_send:
        res = tg.ad(cid, a, label)
        if res.get("error_code") == 403:        # человек заблокировал бота
            user["blocked"] = True
            break
        user["seen"][a.key] = now
        sent += 1
    return sent


def search_round(tg: Telegram, st: dict, admins: list[str], only: list[str] | None = None) -> None:
    pages = Pages()
    total = 0
    active = [(cid, u) for cid, u in st["users"].items()
              if u.get("filters") and not u["filters"].get("paused") and not u.get("blocked")
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
        pending = [cid for cid, u in st["users"].items()
                   if u.get("baseline") and u.get("filters") and not u["filters"].get("paused")]
        if pending:
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
