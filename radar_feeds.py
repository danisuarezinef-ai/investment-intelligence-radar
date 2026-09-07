import email.utils, urllib.parse, xml.etree.ElementTree as ET
from datetime import timezone

from radar_core import con, init_db, fetch, log, now

NEWS_QUERIES = [
    "artificial intelligence investment semiconductors datacenter",
    "chips semiconductor ASML TSMC NVIDIA Broadcom export controls",
    "power grid electricity data centers nuclear energy investment",
    "copper lithium critical minerals mining supply investment",
    "pharma biotech obesity oncology drug approval investment",
    "trade sanctions tariffs geopolitics markets companies",
    "central banks inflation rates bonds markets economy",
    "defense aerospace drones cybersecurity contracts",
    "battery energy storage EV supply chain",
]

COMPANY_TERMS = {
    "MSFT": ("microsoft",),
    "NVDA": ("nvidia",),
    "GOOGL": ("alphabet", "google"),
    "AMZN": ("amazon", "aws"),
    "META": ("meta platforms", "facebook"),
    "AVGO": ("broadcom",),
    "ASML": ("asml",),
    "SAP": ("sap ", "sap se"),
    "TSM": ("tsmc", "taiwan semiconductor"),
    "TM": ("toyota",),
    "SHEL": ("shell plc", "royal dutch shell"),
    "RIO": ("rio tinto",),
    "LLY": ("eli lilly", "lilly"),
    "V": ("visa ", "visa inc"),
    "BRK-B": ("berkshire hathaway",),
    "NVS": ("novartis",),
}

def _iso_from_rfc822(text):
    try:
        dt = email.utils.parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return now()

def _tag_title(title):
    low = str(title or "").lower()
    tags = []
    for sym, terms in COMPANY_TERMS.items():
        if any(term in low for term in terms):
            tags.append(sym)
    if not tags:
        return str(title or "").strip()
    return "/".join(tags[:3]) + " · " + str(title or "").strip()

def _insert_event(c, ts, source, title, url, category):
    try:
        c.execute(
            "insert into information_events(ts,source,title,url,category) values(?,?,?,?,?)",
            (ts, source, title[:1000], url[:2000], category),
        )
        return 1
    except Exception:
        return 0

def collect_news(max_per_query=12):
    init_db()
    c = con()
    added = 0
    seen = 0
    failures = []
    for query in NEWS_QUERIES:
        try:
            url = (
                "https://news.google.com/rss/search?q="
                + urllib.parse.quote(query)
                + "&hl=en-US&gl=US&ceid=US:en"
            )
            xml = fetch(url, 20, {"Accept": "application/rss+xml,application/xml,text/xml"})
            root = ET.fromstring(xml)
            for item in root.findall(".//item")[:max_per_query]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub = (item.findtext("pubDate") or "").strip()
                source_el = item.find("source")
                source = (source_el.text or "").strip() if source_el is not None else "Google News"
                if not title or not link:
                    continue
                seen += 1
                added += _insert_event(
                    c, _iso_from_rfc822(pub), source or "Google News",
                    _tag_title(title), link, "news"
                )
        except Exception as e:
            failures.append(query[:40] + ": " + str(e))
    c.commit()
    c.close()
    status = "OK" if seen else "ERROR"
    detail = f"{added} noticias nuevas de {seen} recuperadas"
    if failures:
        detail += " · " + failures[0][:300]
    log("news", status, detail)
    return added

def collect_arxiv(max_results=30):
    init_db()
    query = "(cat:cs.AI OR cat:cs.LG OR cat:quant-ph OR cat:cond-mat.mtrl-sci OR cat:eess.SY)"
    url = (
        "https://export.arxiv.org/api/query?search_query="
        + urllib.parse.quote(query)
        + "&start=0&max_results="
        + str(int(max_results))
        + "&sortBy=submittedDate&sortOrder=descending"
    )
    added = 0
    seen = 0
    try:
        xml = fetch(url, 25, {"Accept": "application/atom+xml,application/xml,text/xml"})
        root = ET.fromstring(xml)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        c = con()
        for entry in root.findall("a:entry", ns):
            title = " ".join((entry.findtext("a:title", "", ns) or "").split())
            link = (entry.findtext("a:id", "", ns) or "").strip()
            pub = (entry.findtext("a:published", "", ns) or "").strip() or now()
            if not title or not link:
                continue
            seen += 1
            added += _insert_event(c, pub, "arXiv", _tag_title(title), link, "science")
        c.commit()
        c.close()
        log("arxiv", "OK", f"{added} trabajos nuevos de {seen} recuperados")
    except Exception as e:
        log("arxiv", "ERROR", str(e))
    return added

def collect_extended_information():
    return {
        "news": collect_news(),
        "arxiv": collect_arxiv(),
    }
