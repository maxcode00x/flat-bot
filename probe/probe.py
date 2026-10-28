import subprocess, json
out=[]
def P(*a): out.append(" ".join(str(x) for x in a))
urls=["https://www.olx.pl/api/v1/offers/?offset=0&limit=5&category_id=15&city_id=16705",
      "https://m.olx.pl/api/v1/offers/?offset=0&limit=5&category_id=15&city_id=16705",
      "https://olx.pl/api/v1/offers/?offset=0&limit=5&category_id=15&city_id=16705",
      "https://www.olx.pl/robots.txt"]
P("IP", subprocess.run(["curl","-s","https://api.ipify.org"],capture_output=True,text=True).stdout)
for u in urls:
    r=subprocess.run(["curl","-s","-o","/dev/null","-w","%{http_code}",u,"-H","User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"],capture_output=True,text=True)
    P("curl",r.stdout,u)
try:
    from curl_cffi import requests as cr
    for imp in ["chrome","safari","firefox"]:
        for u in urls:
            try:
                r=cr.get(u,impersonate=imp,timeout=30); P("cffi",imp,r.status_code,len(r.text),u, r.text[:120].replace("\n"," "))
            except Exception as e: P("cffi",imp,"EXC",repr(e)[:200])
except Exception as e: P("no cffi",e)
open("probe/out2.txt","w").write("\n".join(out)); print("\n".join(out))
