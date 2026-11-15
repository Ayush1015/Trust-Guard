"""Collect real legitimate deep URLs from public news/site sitemaps to
augment the PhiUSIIL legitimate class (which is homepage-only)."""
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

SEEDS = [
    "https://www.bbc.com/sitemap.xml",
    "https://www.bbc.com/news/sitemap.xml",
    "https://www.theguardian.com/sitemaps/news.xml",
    "https://www.theguardian.com/sitemaps/sitemap.xml",
    "https://www.cnn.com/sitemaps/sitemap-index.xml",
    "https://www.cnn.com/sitemap.xml",
    "https://www.ndtv.com/sitemap.xml",
    "https://indianexpress.com/news-sitemap.xml",
    "https://www.hindustantimes.com/sitemap.xml",
    "https://timesofindia.indiatimes.com/sitemap.xml",
    "https://www.aljazeera.com/sitemap.xml",
    "https://www.bloomberg.com/sitemap.xml",
    "https://www.forbes.com/sitemap.xml",
    "https://www.bbc.co.uk/sitemap.xml",
    "https://www.npr.org/sitemap.xml",
    "https://www.wired.com/sitemap.xml",
    "https://arstechnica.com/sitemap.xml",
    "https://www.theverge.com/sitemap.xml",
]

def fetch(url):
    try:
        out = subprocess.run(
            ["curl", "-sL", "--max-time", "20", "-A",
             "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36", url],
            capture_output=True, timeout=30)
        return out.stdout.decode("utf-8", "ignore")
    except Exception:
        return ""

locs_re = re.compile(r"<loc>\s*([^<]+?)\s*</loc>")

all_urls = set()
child_indexes = []

with ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(fetch, s): s for s in SEEDS}
    for f in as_completed(futs):
        body = f.result()
        locs = locs_re.findall(body)
        is_index = "<sitemapindex" in body
        print(f"{futs[f]}: {len(locs)} locs index={is_index}")
        if is_index:
            child_indexes.extend(locs[:30])
        else:
            all_urls.update(locs)

# one level of index children
with ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(fetch, s): s for s in child_indexes[:60]}
    for f in as_completed(futs):
        locs = locs_re.findall(f.result())
        all_urls.update(u for u in locs if "sitemap" not in u)

print("total unique legit deep URLs:", len(all_urls))
with open("legit_deep_urls.txt", "w") as fh:
    fh.write("\n".join(sorted(all_urls)))
