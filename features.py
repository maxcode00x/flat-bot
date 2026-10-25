"""Доп. функции: средние цены, признаки обмана, отпечаток для дублей, шаблон сообщения владельцу."""
from __future__ import annotations

import re
import statistics
import unicodedata


def norm(s: str | None) -> str:
    s = (s or "").lower().replace("ł", "l").replace("ê", "e")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).strip()


# ---------------------------------------------------------------- средние цены

BUCKET_MAX = 150          # сколько последних объявлений помнить в каждой группе


def stat_keys(kind: str, city: str, places: list[str], zone: str | None) -> list[tuple[str, str, int]]:
    """Группы для статистики: (ключ, подпись, минимум объявлений для оценки) — от узкой к широкой."""
    c = norm(city)
    keys = []
    if places:
        keys.append((f"{kind}|{c}|{norm(places[0])}", places[0], 8))
    if zone:
        keys.append((f"{kind}|{c}|z:{norm(zone)}", zone, 10))
    keys.append((f"{kind}|{c}|*", city, 15))
    return keys


def stat_value(kind: str, price: float | None, area: float | None) -> float | None:
    """Квартиры сравниваем по цене за m², комнаты — по цене."""
    if not price or price < 200:
        return None
    if kind == "flat":
        if not area or area < 10:
            return None
        v = price / area
        return v if 10 <= v <= 400 else None
    return price if price <= 6000 else None


def stats_add(stats: dict, kind: str, city: str, key: str, price, area, places, zone) -> None:
    v = stat_value(kind, price, area)
    if v is None:
        return
    for k, _, _ in stat_keys(kind, city, places, zone):
        b = stats.setdefault(k, {})
        if key in b:
            continue
        b[key] = round(v, 1)
        while len(b) > BUCKET_MAX:
            b.pop(next(iter(b)))


def price_eval(stats: dict, kind: str, city: str, key: str, price, area, places, zone) -> dict | None:
    """{'diff': -12, 'where': 'Pogodno', 'median': 58.0, 'kind': 'flat'} или None, если данных мало."""
    v = stat_value(kind, price, area)
    if v is None:
        return None
    for k, label, need in stat_keys(kind, city, places, zone):
        vals = [x for kk, x in (stats.get(k) or {}).items() if kk != key]
        if len(vals) >= need:
            med = statistics.median(vals)
            return {"diff": round((v - med) / med * 100), "where": label, "median": med, "kind": kind}
    return None


# ---------------------------------------------------------------- признаки обмана

SCAM_RULES = [
    ("prepay", r"zaliczk|przedplat|wplat\w* (przed|zanim)|platnosc\w* (przed|z gory) (obejrz|ogladan)|"
               r"kaucj\w* (przed|zanim) (obejrz|ogladan)|oplat\w* rezerwac"),
    ("abroad", r"(jestem|przebywam|mieszkam|pracuje|obecnie) (obecnie )?za granic|wyjechal\w* za granic"),
    ("keys_mail", r"klucz\w* (wysle|przesle|wysylam|kurier|poczt|paczkomat)|(kurier|poczt)\w* (z )?klucz"),
    ("no_viewing", r"bez (mozliwosci )?ogladania|nie ma mozliwosci (obejrzenia|ogladania)|nie mozna obejrzec"),
    ("pay_service", r"airbnb|booking\.com|western union|moneygram"),
    ("contact_only", r"kontakt (tylko|wylacznie) (przez |na )?(whatsapp|mail|e-mail|email|telegram)"),
]


def scam_flags(text: str, ev: dict | None) -> list[str]:
    t = norm(text)
    flags = [code for code, rx in SCAM_RULES if re.search(rx, t)]
    if ev and ev["diff"] <= -45:
        flags.append("cheap")
    return flags


# ---------------------------------------------------------------- дубли

def fingerprint(price, area, rooms) -> str | None:
    """Одна и та же квартира на разных сайтах: цена + площадь (до 1 m²) + комнаты."""
    if not price or not area:
        return None
    return f"{int(round(price))}|{int(round(area))}|{rooms or 0}"


# ---------------------------------------------------------------- сообщение владельцу (по-польски)

def _osoby(n: int) -> str:
    return "1 osoby" if n == 1 else f"{n} osób"          # «dla 1 osoby», «dla 2 osób»


def owner_message(ad: dict, me: dict, kind: str) -> tuple[str, str]:
    """Полный текст для сайта и короткий для SMS/WhatsApp. ad: {'t','p','l'}; me: данные «О себе»."""
    obj = "pokój" if kind == "room" else "mieszkanie"
    n = int(me.get("people") or 0)
    many = n > 1
    price = f" ({int(ad['p'])} zł)" if ad.get("p") else ""
    lines = ["Dzień dobry,",
             f"piszę w sprawie ogłoszenia „{(ad.get('t') or '').strip()[:120]}”{price}. "
             f"Czy {obj} jest jeszcze {'aktualny' if kind == 'room' else 'aktualne'}?"]
    about = []
    move = (me.get("move") or "").strip()
    if move or n:
        s = f"Szukam {'pokoju' if kind == 'room' else 'mieszkania'}"
        if n:
            s += f" dla {_osoby(n)}"
        if move:
            s += f" od {move}"
        about.append(s + ".")
    job = me.get("job")
    if job == "work":
        about.append("Pracujemy na stałe." if many else "Pracuję na stałe.")
    elif job == "study":
        about.append("Studiujemy." if many else "Studiuję.")
    elif job == "both":
        about.append("Pracujemy i studiujemy.")
    pets = me.get("pets")
    if pets == "no":
        about.append("Bez zwierząt.")
    elif pets in ("cat", "dog", "small"):
        about.append({"cat": "Mam kota.", "dog": "Mam psa.", "small": "Mam małe zwierzę."}[pets])
    if me.get("smoke") == "no":
        about.append("Nie palę." if not many else "Nie palimy.")
    note = (me.get("note") or "").strip()
    if note:
        about.append(note[:200])
    if about:
        lines.append(" ".join(about))
    lines.append("Kiedy byłaby możliwość obejrzenia?")
    lines.append("Pozdrawiam" + (f",\n{me['name'].strip()[:40]}" if (me.get("name") or "").strip() else ""))
    full = "\n".join(lines)
    short = (f"Dzień dobry, czy {obj} z ogłoszenia{price} jest aktualn{'y' if kind == 'room' else 'e'}? "
             f"Chętnie obejrzę. " + ((me.get("name") or "").strip()[:40]))
    return full, short.strip()
