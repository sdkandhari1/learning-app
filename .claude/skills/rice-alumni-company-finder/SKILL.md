---
name: rice-alumni-company-finder
description: Produce a verified list of Rice University alumni holding a relevant role at a target company, for networking and informational-interview outreach. Runs read-only inside the user's own signed-in LinkedIn session via Claude in Chrome. Use when the user asks to find Rice alumni at a company or in a function (e.g. "Rice alumni in supply chain at Microsoft").
---

# Rice Alumni Company Finder

## Purpose

Produce a verified list of Rice alumni who hold a relevant role at a target company, for networking and informational-interview outreach. The skill runs in three stages inside the user's own authenticated LinkedIn session:

1. **Search** — a broad pool capture and a precise title match.
2. **Classify and deduplicate** — rank candidates by relevance and remove anyone already in the user's alumni CRM.
3. **Verify** — open the profiles of shortlisted candidates to confirm their Rice degree and current role.

**Reference engagement:** Rice alumni in supply chain and sustainability at Microsoft (September 2026). About 165 profiles screened; 16 qualified (7 core, 6 adjacent, 3 customer-facing or former); none already in the CRM.

## Operating principles

- **Session handoff comes first.** Don't search until the user has supplied the URL of an active LinkedIn tab and the session has been verified (Step 0).
- **Read, never engage.** Don't connect, message, follow, endorse, react, or change any LinkedIn setting.
- **Open profiles only to verify, and only with consent.**
  - Open a profile only for shortlisted candidates, and only to confirm education and current role (Step 8).
  - Each visit appears in that person's "Who viewed your profile" list under the user's name, unless the user has switched LinkedIn to private viewing mode themselves.
  - Tell the user this during the handoff, and honor a "no profile visits" instruction.
- **The user keeps control of credentials.** Ask only for a page URL. Never ask for, accept, or type passwords, one-time codes, cookies (e.g. `li_at`), or session tokens.
  - If the session isn't signed in, the user signs in personally.
  - If LinkedIn shows a verification check or CAPTCHA, the user completes it.
- **Personal-research scale only.** LinkedIn's User Agreement restricts automated access. The user accepts that risk for their own account, and the skill keeps its footprint minimal.
  - Use visible, paced page navigation in a single tab.
  - No background request loops, direct HTTP fetches of LinkedIn pages, or LinkedIn's internal APIs.
  - Stay within the limits in **Volume and pacing**.
- **Minimal footprint.** Keep results in the page's `localStorage` under one run key, clear that key after the report is delivered, and close the tab.
- **Deliver incrementally.** Report results as soon as they are usable, not after long idle waits.

## Tooling

Use **Claude in Chrome** (`mcp__claude-in-chrome__*`), which runs in the user's own Chrome profile and therefore has their LinkedIn session. The in-app browser pane has a separate profile and is not suitable. This skill cannot run in a cloud session without the extension connected.

Load the tools in a single ToolSearch call: `tabs_context_mcp`, `tabs_create_mcp`, `tabs_close_mcp`, `navigate`, `computer`, `get_page_text`, `find`, `javascript_tool`, `browser_batch`.

The batch generator `li_batch.py` lives next to this file.

## Volume and pacing

| Activity | Limit per session | Pacing |
|---|---|---|
| Search result pages | About 40 | 3 s wait per page, via `browser_batch` (≤ 5 pages per call) |
| Profiles verified | About 20 people (40 page views) | One person at a time, 3 s per page, 5 s pause between people |
| On a 999, 429, `/checkpoint` or login redirect | Stop immediately | Report progress and hand control back to the user |

## Workflow

### Step 0: Session handoff (required on every activation)

Before doing anything else, send the user this request (adapt wording as needed):

> To run this search I'll work inside your signed-in LinkedIn session in Chrome. Please:
>
> 1. Open LinkedIn in Chrome (with the Claude in Chrome extension connected) and make sure you're signed in.
> 2. Paste the URL of that tab here. Any linkedin.com page works. A People search already filtered to the company (and, if you like, to Rice University) is ideal, because I'll reuse its filters.
> 3. Confirm the target company and function(s), for example "Microsoft, supply chain and sustainability."
>
> **Profile verification:** to confirm each shortlisted person's Rice degree and current role, I'll open their LinkedIn profile — about two page views per person. Those visits show up in their "Who viewed your profile" list under your name, unless you first switch to private mode yourself (LinkedIn → Settings → Visibility → Profile viewing options). Reply "no profile visits" if you'd like me to skip verification.
>
> I won't connect with or message anyone. Please don't paste passwords, codes, or cookies; the page URL is all I need.

Then wait for the reply. Don't proceed on assumptions.

**Validate the URL:**

- Accept only `https://www.linkedin.com/...` (or `linkedin.com/...`). Reject any other domain and ask again.
- If the reply contains anything that looks like a credential (cookie string, token, password), don't use it. Tell the user it isn't needed, suggest they change their password if they shared a real one, and ask for the page URL only.

**Take over the session:**

1. Call `tabs_context_mcp({createIfEmpty:true})` to get a tab in the Claude tab group. Claude in Chrome can act only on tabs in its own group; a new tab there uses the same browser profile and therefore the user's signed-in session.
2. `navigate` that tab to the URL the user supplied.
3. Check the resulting URL from the tool output:

| Resulting URL contains | Meaning | Action |
|---|---|---|
| `/login`, `/uas/login`, `/authwall`, `/signup` | Not signed in | Ask the user to sign in in Chrome and resend the URL. Never enter credentials. |
| `/checkpoint` or a security challenge | Verification required | Ask the user to complete it personally, then continue. |
| `/feed`, `/search/`, `/in/`, `/company/`, `/school/` | Signed in | Continue. |

**Reuse the user's filters:** if the URL is a People search (`/search/results/people/`), read these parameters and use them as the seed configuration (`li_batch.py --seed-url` does this for company and school):

- `currentCompany`: company ID(s)
- `schoolFilter`: school ID(s)
- `keywords` / `title`: an initial term

### Step 1: Confirm search parameters

| Parameter | Source / default |
|---|---|
| Company ID | From the seed URL; otherwise see the lookup below. Known: Microsoft = `1035`. |
| School IDs | From the seed URL. Default `6076` (Rice University) and `15101508` (Rice Business / Jones). Exclude the engineering-school ID, which returns pre-college profiles. |
| Function vocabulary | Derived from the user's stated function (Step 4). |
| Location emphasis | Optional. Houston-based alumni are usually the most reachable. |
| CRM exclusion | On by default (Step 7). |
| Profile verification | On by default, unless the user replied "no profile visits" (Step 8). |

**Company ID lookup** (only if no seed URL supplies it):

1. Open `linkedin.com/search/results/people/?keywords=<company>`.
2. Open the **Current companies** filter, select the company, click **Show results**.
3. Read `currentCompany=["<id>"]` from the tab URL.

### Step 2: Query construction

```
https://www.linkedin.com/search/results/people/
  ?currentCompany=%5B%22<COMPANY_ID>%22%5D
  &schoolFilter=%5B%226076%22%2C%2215101508%22%5D
  &origin=FACETED_SEARCH
  &keywords=<term>   (Pass A)   |   &title=<term>   (Pass B)
  &page=<n>
```

| Parameter | Behavior | Role in this skill |
|---|---|---|
| `title=` | Narrow. Matches only the current position title; misses people whose function appears only in their headline. | Core confirmation. Run it first: it's cheap and fixes the core list early. |
| `keywords=` | Broad. Matches any profile text and returns most of the company's Rice alumni, ranked by relevance. | Pool capture |

Run both passes. Neither is sufficient on its own.

### Step 3: Result capture

Each result card is `main [role="listitem"]`; the first `a[href*="/in/"]` inside it is the person. The capture snippet:

- stores every card under one `localStorage` key;
- deduplicates by profile slug;
- keeps the query-specific text excerpt LinkedIn shows for each query;
- returns only counts (return values containing URLs are blocked by the tool).

```js
const Q="supply chain";   // query label ("T:<term>" for title queries)
const K='alumni_run';     // one localStorage key per run
const d=JSON.parse(localStorage.getItem(K)||'{}');let n=0,c=0;
for(const li of document.querySelectorAll('main [role="listitem"]')){
  const a=li.querySelector('a[href*="/in/"]');if(!a)continue;
  const m=a.href.match(/\/in\/([^/?#]+)/);if(!m)continue;c++;
  const s=decodeURIComponent(m[1]);
  const t=li.innerText.split('\n').map(x=>x.trim())
    .filter(x=>x&&!/^(Connect|Follow|Message|See open roles|Pending)$/.test(x)).join(' | ');
  if(!d[s]){d[s]={t,q:[Q]};n++;}
  else{if(!d[s].q.includes(Q))d[s].q.push(Q);d[s]['t_'+Q]=t;}
}
localStorage.setItem(K,JSON.stringify(d));
Q+': cards '+c+', new '+n+', total '+Object.keys(d).length
```

### Step 4: Search execution

Generate the page visits with `li_batch.py` and pass its output as the actions of one `browser_batch` call. Each page is three actions: navigate, wait 3 s, capture.

**Pass B first (core confirmation):**

- Run `--mode title` across a function vocabulary, up to 8 terms per call.
- Reference vocabulary for supply chain / sustainability: supply chain, sustainability, sourcing, procurement, logistics, supplier, materials, carbon, energy, planning, manufacturing, commodity, capacity, environmental, hardware, cloud operations.
- Adapt the vocabulary to the function requested:
  - Strategy: strategy, corporate development, business planning, chief of staff
  - Finance: finance, FP&A, treasury, controller
- Expect 0 to 4 results per term.

**Pass A (pool capture):**

- Run the primary term with `--mode keywords --pages 1-5`, then continue in blocks of five.
- Stop a term when a page returns `cards 0`, or a full page yields `new 0`.
- Run each additional term for pages 1–5 only. If it adds under about 10% new records, the pool is saturated.
- Reference run: "supply chain" pages 1–15 captured 148 people; "sustainability" pages 1–5 added 5.

**Efficiency practices:**

- Relevance falls steeply after about page 10 of a keyword pass. For a named function, pages 1–10 plus the title pass usually capture every qualified candidate. Go deeper only if the user asks for completeness.
- Don't re-run a saturated term with a new label; the pool won't change.
- Keep every query in the same run key, so later steps read one merged dataset.

### Step 5: Data extraction

`javascript_tool` return values are capped at about 1,000 characters and block URL-like content. Instead, write the records to a `<pre>` prepended to `<main>`, then read them with `get_page_text`.

```js
const d=JSON.parse(localStorage.getItem('alumni_run')||'{}');
const re=/supply|sustainab|procure|sourcing|carbon|logistic|circular|environment|climate|energy|datacenter|data center|CO\+I|Operations \+ Innovation|demand plan|inventory|materials|hardware|manufactur|vendor|supplier|S&OP|fulfil|ESG|net.zero|water|waste|decarbon|emission|renewable|operations/i; // replace with the target function's vocabulary
const hit=[],miss=[];
for(const [s,v] of Object.entries(d)){
  const all=Object.keys(v).filter(k=>k==='t'||k.startsWith('t_')).map(k=>v[k]).join(' ## ');
  (re.test(all)?hit:miss).push('LI:'+s+' ['+v.q.join(',')+'] :: '+all.replace(/[\d,]+ followers/g,'').slice(0,600));
}
let pre=document.getElementById('cc-dump');
if(!pre){pre=document.createElement('pre');pre.id='cc-dump';document.querySelector('main').prepend(pre);}
pre.textContent='=== MATCHED '+hit.length+' ===\n'+hit.join('\n')+'\n=== UNMATCHED '+miss.length+' ===\n'+miss.map(x=>x.slice(0,140)).join('\n');
hit.length+' matched / '+miss.length+' unmatched'
```

- Review the unmatched list manually. Headlines such as "Global Cloud Expansion; Strategic Planning" or "Supplier Management" can fall outside the pattern.
- Keep the connection degree (`• 2nd`) and the mutual-connection text for the report.
- Profile URL format: `https://www.linkedin.com/in/<slug>/`.

### Step 6: Candidate classification

**How to read a card:**

| Card signal | Classification |
|---|---|
| Function terms in the current title or headline | Tier 1 |
| Function terms only in the excerpt (e.g. "…across … supply chain workflows") | Tier 1 or 2, depending on how central the function is |
| "&lt;Role&gt; at &lt;Co&gt; from &lt;date&gt; to &lt;date&gt;" | Former role. Tier 3; verify in Step 8. |
| "for the last 0 months" | Recent hire. Flag it. |
| Headline names a different employer | The `currentCompany` filter leaked. Exclude. |
| Headline doesn't name the company | Retain, and verify in Step 8. |
| Student headline, or "Prev @ &lt;Co&gt;" / "ex-&lt;Co&gt;" | Exclude. |

**Tier definitions:**

- **Tier 1, core function:** the role sits directly in the requested function (e.g. sourcing, logistics, supply chain finance, sustainability program management).
- **Tier 2, adjacent:** the role borders the function (e.g. data center operations, hardware manufacturing, capacity planning, prior procurement experience).
- **Tier 3, customer-facing or former:** related industry coverage, or relevant roles that may have ended.

### Step 7: CRM deduplication (before verification, so no profile views are wasted)

Default reference file: `Rice/Resume/Resume/Assure consulting/Rice Alumni CRM.xlsx`; ask if another CRM applies. Match full names and surnames across all sheets. Review each hit by hand — short surnames produce false positives (e.g. a surname matching a firm name).

```python
import openpyxl
wb = openpyxl.load_workbook("Rice Alumni CRM.xlsx", read_only=True, data_only=True)
names = ["<Surname 1>", "<Full Name 2>"]
for ws in wb.worksheets:
    for row in ws.iter_rows(values_only=True):
        line = " | ".join(str(c) for c in row if c is not None)
        for n in names:
            if n.lower() in line.lower():
                print(n, "->", ws.title, ":", line[:160])
```

### Step 8: Profile verification

Skip this step if the user replied "no profile visits".

**Who to verify, in priority order:**

1. Tier 1 and Tier 2 candidates not already in the CRM.
2. Any candidate flagged "verify": a former role, a missing company name, or a recent hire.
3. Tier 3 candidates only if the user asks.

Stay within the session limit (about 20 people).

**How:** LinkedIn's section pages render complete lists without scrolling; the main profile page lazy-loads sections on scroll, so don't use it. For each person visit:

- `https://www.linkedin.com/in/<slug>/details/education/`
- `https://www.linkedin.com/in/<slug>/details/experience/`

On each page run this compact reader instead of `get_page_text`. It returns only the section list (under 1,000 characters) and skips the footer, language menu and "People also viewed":

```js
const m=document.querySelector('main');
(m?m.innerText:'').split(/\n(?:Profile language|Who your viewers also viewed|People also viewed)\n/)[0]
  .replace(/\n{2,}/g,'\n').slice(0,950)
```

If the tab URL after navigation contains `/checkpoint`, `/authwall` or `/login`, or the page reports the profile is unavailable, stop verification and tell the user.

**What to record:**

| Field | Rule |
|---|---|
| Rice credential | An education entry for Rice University or Rice University – Jesse H. Jones Graduate School of Business; record degree and years, e.g. "MBA, 2014–2016". Executive education, certificates or non-degree programs count as "Rice (non-degree)". No Rice entry: mark "Not confirmed" and move the person down a tier. |
| Current role | The top experience entry marked Present. If at the target company, record title and start date. If the top current entry is at another company, the person has left: exclude them. |
| Tenure | Start month and year of the current role. Under 3 months counts as a recent hire. |

From the reference test: the education page lists school, degree, grade and activities; the experience page groups multiple roles at one employer under that employer, with a "Present" marker and a start date for each role.

`li_batch.py --mode verify --terms "<slug1>,<slug2>"` generates the paced verification batch. It enforces at most 3 people per `browser_batch` call.

### Step 9: Report

**Summary line:** total qualified candidates, count per tier, how many were verified, and how many are not yet in the CRM.

**One table per tier:**

| Name (linked) | Current role at &lt;Co&gt; (since) | Rice credential | Location | Connection |
|---|---|---|---|---|

Mark the Rice credential column "✓ &lt;degree, year&gt;" when verified, or "Listed (unverified)" when not.

**Recommended first contacts:** prioritize verified Tier 1 people who are 2nd-degree and Houston-based. Point out any mutual connection who links to several candidates — one introduction request can reach all of them.

**Limitations** (one line each):

- Unverified entries rely on LinkedIn's school filter.
- Roles are current as of the report date.
- Coverage is limited to members who list Rice on LinkedIn.

**Next step offer:** a spreadsheet export, or adding the candidates to a new CRM tab.

**Sources:** if web search contributed anything, cite it as markdown links.

**Cleanup:** remove the run key (`localStorage.removeItem('alumni_run')`) and close the tab.

## Troubleshooting

| Symptom | Resolution |
|---|---|
| "Claude in Chrome is not connected" mid-batch | Call `tabs_context_mcp` to see how far the tab got. Check the stored total with `Object.keys(JSON.parse(localStorage.getItem('alumni_run'))).length`, then resume from that page. Re-runs are safe because records are deduplicated. |
| Tab group no longer exists | Call `tabs_context_mcp({createIfEmpty:true})` and navigate back to the user's URL. The `localStorage` data persists on the linkedin.com origin. |
| Profile page shows only the header, no Experience or Education | Use the `/details/education/` and `/details/experience/` pages, not the main profile. |
| Screenshots time out or `get_page_text` returns nothing | The Chrome window is probably minimized or covered. Ask the user to bring it to the front and leave it visible. |
| Redirect to login, authwall or checkpoint, or HTTP 999 or 429 | Stop immediately. Ask the user to sign in or complete the check personally. Resume only if they want to, and at a slower pace. |
| Results stop around 250–360 per query | LinkedIn's per-query cap. Split the query by school ID (run `6076` and `15101508` separately) or add more terms. |
| Web search (`site:linkedin.com/in`) returns little | Expected. In the reference run it surfaced one useful profile. Use LinkedIn search as the primary source. |

## Appendix: `li_batch.py`

Builds `browser_batch` actions for search passes and paced profile verification. Example invocations:

```bash
python li_batch.py --tab <TAB_ID> --seed-url "<user's LinkedIn search URL>" --mode title --terms "sourcing,procurement,logistics,sustainability"
python li_batch.py --tab <TAB_ID> --company 1035 --mode keywords --terms "supply chain" --pages 1-5
python li_batch.py --tab <TAB_ID> --mode verify --terms "<slug-1>,<slug-2>,<slug-3>"
```
