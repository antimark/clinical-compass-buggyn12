"""Application health only; model inference readiness is checked separately."""
from urllib.request import build_opener,ProxyHandler
with build_opener(ProxyHandler({})).open('http://127.0.0.1:8766/api/v1/health',timeout=2) as response:
    if response.status!=200:raise SystemExit(1)
