import sys, json, re, traceback, requests
sys.path.insert(0, ".")
import bot
out = []
def P(*a): out.append(" ".join(str(x) for x in a))
f = dict(bot.DEFAULT_FILTERS)
tests = {
 "olx_api_flat": bot.olx_url(f, "flat"),
 "olx_api_room": bot.olx_url(f, "room"),
 "olx_api_min": "https://www.olx.pl/api/v1/offers/?offset=0&limit=5&category_id=15&city_id=16705",
 "olx_api_noslash": "https://www.olx.pl/api/v1/offers?offset=0&limit=5&category_id=15&city_id=16705",
 "olx_html": "https://www.olx.pl/nieruchomosci/mieszkania/wynajem/szczecin/?search%5Border%5D=created_at:desc",
 "morizon": "https://www.morizon.pl/do-wynajecia/mieszkania/szczecin/?ps%5Bdate_filter%5D=1",
 "gratka": "https://gratka.pl/nieruchomosci/mieszkania/szczecin/wynajem?sort=newest",
}
for name, url in tests.items():
    P("=====", name, url)
    for hdr in ("bot", "json"):
        try:
            h = dict(bot.HEADERS)
            if hdr == "json" or "/api/" in url: h["Accept"] = "application/json"
            r = requests.get(url, headers=h, timeout=30)
            P(hdr, "HTTP", r.status_code, "len", len(r.text), "ctype", r.headers.get("content-type"), "server", r.headers.get("server"))
            P("final_url", r.url)
            P("head:", r.text[:600].replace("\n", " "))
            if name.startswith("olx") and r.status_code == 200:
                try:
                    ads = bot.parse_olx(r.text); P("PARSED", len(ads), ads[0].title if ads else "")
                except Exception as e:
                    P("PARSE_ERR", repr(e))
            if name in ("morizon", "gratka") and r.status_code == 200:
                open(f"probe/{name}.html", "w").write(r.text)
            if name == "olx_html" and r.status_code == 200:
                open("probe/olx.html", "w").write(r.text)
            if name == "olx_api_min" and r.status_code == 200:
                open("probe/olx_api.json", "w").write(r.text)
        except Exception as e:
            P(hdr, "EXC", repr(e))
        if hdr == "bot": continue
open("probe/out.txt", "w").write("\n".join(out))
print("\n".join(out))
