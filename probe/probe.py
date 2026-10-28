import sys, os; sys.path.insert(0, ".")
import bot
out=[]
def P(*a): out.append(" ".join(str(x) for x in a)); print(*a, flush=True)
f = bot.clean_filters({"type":"both","src":bot.ALL_SOURCES,"city":"szczecin","pMax":3500,"ex":["LIFT","BALCONY"],"furn":True})
pages = bot.Pages()
for src in bot.ALL_SOURCES:
    for kind in ["flat","room"]:
        url = bot.SOURCES[src][0](f, kind)
        if not url: P(src,kind,"—"); continue
        try:
            ads = pages.get(src, url)
            ok = [a for a in ads if bot.passes(a, f, kind)]
            P(src, kind, "ads", len(ads), "pass", len(ok))
            for a in ok[:2]:
                P("   ", a.key, a.price, a.area, a.rooms, a.floor, a.places, "priv", a.private, "lift", a.lift, "unk", bot.unknowns(a,f,kind))
        except Exception as e:
            P(src, kind, "ERR", repr(e)[:300])
open("probe/out3.txt","w").write("\n".join(out))
