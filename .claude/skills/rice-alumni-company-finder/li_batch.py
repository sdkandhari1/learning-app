"""Generate browser_batch actions for a LinkedIn alumni sweep (see SKILL.md)."""
import argparse, json, urllib.parse

p = argparse.ArgumentParser(description="Generate browser_batch actions for a LinkedIn alumni sweep.")
p.add_argument("--tab", type=int, required=True, help="Claude in Chrome tab ID")
p.add_argument("--seed-url", help="LinkedIn people-search URL from the user; its filters are reused")
p.add_argument("--company", help="LinkedIn company ID, e.g. 1035 (overrides the seed URL)")
p.add_argument("--schools", help="Comma-separated school IDs (default 6076,15101508)")
p.add_argument("--mode", choices=["keywords", "title", "verify"], required=True)
p.add_argument("--terms", required=True, help="Comma-separated search terms, or profile slugs for verify mode")
p.add_argument("--pages", default="1-1", help="Page range for keyword mode, e.g. 1-5")
p.add_argument("--key", default="alumni_run", help="localStorage key for this run")
a = p.parse_args()
terms = [t.strip() for t in a.terms.split(",") if t.strip()]
wait = lambda s: {"name": "computer", "input": {"action": "wait", "duration": s, "tabId": a.tab}}
js = lambda code: {"name": "javascript_tool", "input": {"action": "javascript_exec", "tabId": a.tab, "text": code}}
nav = lambda url: {"name": "navigate", "input": {"url": url, "tabId": a.tab}}
actions = []

if a.mode == "verify":
    if len(terms) > 3:
        p.error("Verify at most 3 people per browser_batch call.")
    READER = ("const m=document.querySelector('main');(m?m.innerText:'').split(/\\n(?:Profile language|"
              "Who your viewers also viewed|People also viewed)\\n/)[0].replace(/\\n{2,}/g,'\\n').slice(0,950)")
    for i, slug in enumerate(terms):
        if i:
            actions.append(wait(5))                      # pause between people
        for section in ("education", "experience"):
            actions += [nav("https://www.linkedin.com/in/%s/details/%s/" % (urllib.parse.quote(slug), section)),
                        wait(3), js(READER)]
    print(json.dumps(actions))
    raise SystemExit

seed = {}
if a.seed_url:
    host = urllib.parse.urlparse(a.seed_url).hostname or ""
    if host != "linkedin.com" and not host.endswith(".linkedin.com"):
        p.error("--seed-url must be a linkedin.com URL.")
    seed = urllib.parse.parse_qs(urllib.parse.urlparse(a.seed_url).query)
def seed_list(name):
    v = seed.get(name, [None])[0]
    return json.loads(v) if v else None

company = [a.company] if a.company else seed_list("currentCompany")
schools = a.schools.split(",") if a.schools else (seed_list("schoolFilter") or ["6076", "15101508"])
if not company:
    p.error("No company ID: supply --company or a --seed-url containing currentCompany.")

q = lambda ids: urllib.parse.quote(json.dumps(ids, separators=(",", ":")))
base = ("https://www.linkedin.com/search/results/people/?currentCompany=" + q(company) +
        "&schoolFilter=" + q(schools) + "&origin=FACETED_SEARCH")
CAPTURE = ("const Q=%s;const K=%s;const d=JSON.parse(localStorage.getItem(K)||'{}');let n=0,c=0;"
           "for(const li of document.querySelectorAll('main [role=\"listitem\"]')){"
           "const a=li.querySelector('a[href*=\"/in/\"]');if(!a)continue;"
           "const m=a.href.match(/\\/in\\/([^/?#]+)/);if(!m)continue;c++;const s=decodeURIComponent(m[1]);"
           "const t=li.innerText.split('\\n').map(x=>x.trim()).filter(x=>x&&!/^(Connect|Follow|Message|See open roles|Pending)$/.test(x)).join(' | ');"
           "if(!d[s]){d[s]={t,q:[Q]};n++;}else{if(!d[s].q.includes(Q))d[s].q.push(Q);d[s]['t_'+Q]=t;}}"
           "localStorage.setItem(K,JSON.stringify(d));Q+' p'+%d+': cards '+c+', new '+n+', total '+Object.keys(d).length")

p0, p1 = (int(x) for x in a.pages.split("-"))
for term in terms:
    label = term if a.mode == "keywords" else "T:" + term
    for pg in (range(p0, p1 + 1) if a.mode == "keywords" else [1]):
        url = base + "&" + a.mode + "=" + urllib.parse.quote(term) + ("&page=%d" % pg if a.mode == "keywords" else "")
        actions += [nav(url), wait(3), js(CAPTURE % (json.dumps(label), json.dumps(a.key), pg))]
print(json.dumps(actions))
