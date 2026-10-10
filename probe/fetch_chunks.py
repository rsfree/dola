#!/usr/bin/env python3
"""Extract script/chunk URLs from dola page.html and download them."""
import re
import os
import sys

BASE = "https://sf-flow-web-cdn.ciciai.com"
OUT = os.path.join(os.path.dirname(__file__), "bundles")

html = open(os.path.join(os.path.dirname(__file__), "page.html")).read()

# all src= and href= ending with .js
urls = set()
for m in re.findall(r'(?:src|href)="([^"]+)"', html):
    if ".js" in m and not m.endswith(".css"):
        urls.add(m)

print(f"total js urls: {len(urls)}")
for u in sorted(urls):
    print(u)
