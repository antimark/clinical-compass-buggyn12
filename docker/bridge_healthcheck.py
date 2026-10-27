from urllib.request import build_opener,ProxyHandler
with build_opener(ProxyHandler({})).open('http://127.0.0.1:11434/health',timeout=2) as response:
    if response.status!=200:raise SystemExit(1)
