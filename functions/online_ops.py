import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from urllib.parse import quote
from decouple import config

_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_IPV6_RE = re.compile(r"^[0-9a-fA-F:.]+$")

# Internet-connectivity probe + a short shared cache so the check never
# hammers the network (every command call reuses the last result).
_INTERNET_PROBES = (
    "https://www.gstatic.com/generate_204",
    "https://api.ipify.org",
    "https://www.google.com/generate_204",
)
_INTERNET_CACHE_TTL = 30  # seconds
_internet_cache = {"result": None, "at": 0.0}


def have_internet():
    """True when this machine has internet access (cached for ~30s).

    Probes lightweight endpoints (fast, no API keys) so it returns quickly
    and the cached result is shared by all callers. Returns False, never
    raises, when there's no connectivity.
    """
    now = time.time()
    if now - _internet_cache["at"] < _INTERNET_CACHE_TTL:
        return bool(_internet_cache["result"])
    ok = False
    for url in _INTERNET_PROBES:
        try:
            resp = requests.get(url, timeout=4)
            if resp.status_code < 500:
                ok = True
                break
        except Exception:
            continue
    _internet_cache["at"] = now
    _internet_cache["result"] = ok
    return ok


def _fetch_ip(url):
    """Fetch the IP from one provider; return a valid IP string or None."""
    try:
        resp = requests.get(url, timeout=4)
        text = (resp.text or "").strip()
        if (resp.status_code == 200
                and (_IPV4_RE.match(text) or _IPV6_RE.match(text))):
            return text
    except Exception:
        pass
    return None


def find_my_ip():
    """Return the public IP address, or None when offline.

    Queries several free providers in parallel so a single outage (or being
    offline) never stalls the command; returns None, never raises, when no
    internet is available.
    """
    if not have_internet():
        return None
    providers = (
        "https://api64.ipify.org",
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
    )
    ex = ThreadPoolExecutor(max_workers=len(providers))
    try:
        futures = [ex.submit(_fetch_ip, url) for url in providers]
        for fut in as_completed(futures):
            ip = fut.result()
            if ip:
                return ip
    finally:
        ex.shutdown(wait=False)
    return None

# ---------------------------------------------------------------------------
# Wikipedia — direct MediaWiki API (no extra dependency).
#
# The `wikipedia` PyPI library is unmaintained and flaky: it regularly picks
# the wrong disambiguation option ("Java" -> Japan's summary!), raises
# DisambiguationError / PageError on perfectly normal queries, and breaks
# whenever Wikipedia tweaks its HTML. Querying the public API directly via
# `requests` is stable, dependency-free and lets us handle disambiguation
# pages properly.
# ---------------------------------------------------------------------------
_WIKI_API_URL = "https://en.wikipedia.org/w/api.php"
_WIKI_HEADERS = {
    "User-Agent": "JARVIS-Assistant/1.0 (personal desktop voice assistant; "
                  "local use)",
}


def _wiki_json(params):
    """GET the MediaWiki API; return the parsed JSON or None on failure."""
    try:
        resp = requests.get(_WIKI_API_URL, params=params,
                            headers=_WIKI_HEADERS, timeout=12)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[wiki] API error: {e}")
        return None


def search_on_wikipedia(query, sentences=2):
    """Short plain-text Wikipedia summary for a query — never raises.

    Resolves the query through Wikipedia search (handles redirects and
    nearby spelling), skips disambiguation pages in favour of a real
    article, and returns a friendly message instead of an exception when
    the topic can't be found or the API is unreachable. Always returns a
    non-empty string.
    """
    q = (query or "").strip()
    if not q:
        return "I need a topic to look up on Wikipedia."

    data = _wiki_json({
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": q,
        "gsrnamespace": 0,
        "gsrlimit": 5,
        "prop": "extracts|pageprops",
        "exintro": True,
        "explaintext": True,
        "exsentences": max(1, int(sentences)),
        "redirects": 1,
    })
    if not data:
        return "Wikipedia isn't reachable right now — try again in a moment."

    pages = (data.get("query") or {}).get("pages") or {}
    pages = sorted(pages.values(), key=lambda p: p.get("index", 999))
    if not pages:
        return f"Couldn't find anything on Wikipedia about {q!r}."

    # prefer the first real article — skip disambiguation pages
    first_extract = None
    for page in pages:
        extract = (page.get("extract") or "").strip()
        if not extract:
            continue
        if first_extract is None:
            first_extract = extract
        if "disambiguation" not in (page.get("pageprops") or {}):
            return extract
    if first_extract:
        return first_extract
    return f"Couldn't find anything on Wikipedia about {q!r}."

def play_on_youtube(video):
    """Open a video on YouTube. Uses pywhatkit when it's installed;
    otherwise opens a YouTube search page in the default browser.
    Never raises — the caller always gets a launched browser or a log."""
    video = (video or "").strip()
    if not video:
        return
    try:
        import pywhatkit as kit
        kit.playonyt(video)
        return
    except Exception as e:
        print(f"[online_ops] couldn't open via pywhatkit ({e}); "
              "opening YouTube search instead")
    try:
        import webbrowser
        webbrowser.open("https://www.youtube.com/results?search_query="
                        + quote(video))
    except Exception as e:
        print(f"[online_ops] could not open YouTube: {e}")

SERPAPI_KEY = config("SERPAPI_KEY", default="")


def _ddg_search(query, num_results=3):
    """Web search via DuckDuckGo using the ddgs library (free, no API key).

    Lazily imported so the module still works if ddgs isn't installed.
    """
    from ddgs import DDGS
    with DDGS(timeout=10) as ddgs:
        results = list(ddgs.text(query, max_results=num_results))
    out = []
    for r in results:
        title = (r.get("title") or "").strip()
        body = (r.get("body") or "").strip()
        if title:
            out.append(f"{title}\n{body}".strip())
    return out


def search_on_google(query, num_results=3):
    """Search the web and return titles + snippets of the top results.

    Uses DuckDuckGo via the free ``ddgs`` library first (no API key needed, so
    the "google ..." command always works), then SerpAPI as a fallback when a
    SERPAPI_KEY is configured.
    """
    try:
        results = _ddg_search(query, num_results)
        if results:
            return "\n\n".join(results)
        print("DDG returned no results; trying SerpAPI...")
    except Exception as e:
        print(f"DDG search error (trying SerpAPI): {e}")

    if SERPAPI_KEY:
        try:
            resp = requests.get(
                "https://serpapi.com/search",
                params={
                    "q": query,
                    "api_key": SERPAPI_KEY,
                    "engine": "google",
                    "num": num_results,
                    "hl": "en",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            for item in data.get('organic_results', [])[:num_results]:
                title = item.get('title', 'No title')
                snippet = item.get('snippet', 'No description')
                link = item.get('link', 'No link')
                results.append(f"{title}\n{snippet}\nLink: {link}")
            if results:
                return "\n\n".join(results)
        except Exception as e:
            print(f"SerpAPI error: {e}")
    return "No results found on the web."

# GNews.io — generous free tier (100 requests/day), real-time headlines.
GNEWS_API_KEY = config("GNEWS_API_KEY", default="")
NEWS_API_KEY = config("NEWS_API_KEY", default="")


def get_latest_news():
    """Return up to 5 current headline titles.

    Uses GNews.io first (100 free requests/day), falling back to NewsAPI
    (free dev tier) when no GNews key is configured or it errors out.
    """
    if GNEWS_API_KEY:
        try:
            res = requests.get(
                "https://gnews.io/api/v4/top-headlines",
                params={"category": "general", "lang": "en", "country": "in",
                        "max": 5, "apikey": GNEWS_API_KEY},
                timeout=10,
            ).json()
            titles = [a.get("title", "").strip()
                      for a in res.get("articles", []) if a.get("title")]
            if titles:
                return titles[:5]
            print(f"GNews returned no articles: {res}")
        except Exception as e:
            print(f"GNews error (falling back to NewsAPI): {e}")

    if NEWS_API_KEY:
        try:
            res = requests.get(
                "https://newsapi.org/v2/top-headlines",
                params={"country": "in", "category": "general",
                        "apiKey": NEWS_API_KEY},
                timeout=10,
            ).json()
            return [a.get("title", "").strip()
                    for a in res.get("articles", []) if a.get("title")][:5]
        except Exception as e:
            print(f"NewsAPI error: {e}")
    return []


# WeatherAPI.com — very generous free tier (1,000,000 calls/month) with
# current weather, 3-day forecast, astronomy and more. OpenWeatherMap is kept
# as a fallback when no WeatherAPI key is configured.
WEATHERAPI_KEY = config("WEATHERAPI_KEY", default="")
OPENWEATHER_APP_ID = config("OPENWEATHER_APP_ID", default="")


def get_city_from_ip():
    """Best-effort city name for the current public IP, or None.

    Tries ipapi.co, ip-api.com and ipinfo.io so the weather command keeps
    working even when one of them is down.
    """
    try:
        ip_address = find_my_ip()
    except Exception as e:
        print(f"IP lookup error: {e}")
        return None
    providers = (
        f"https://ip-api.com/json/{ip_address}",
        f"https://ipapi.co/{ip_address}/json/",
        f"https://ipinfo.io/{ip_address}/city",
    )
    for url in providers:
        try:
            resp = requests.get(url, timeout=6)
            if "ip-api.com" in url or "ipapi.co" in url:
                data = resp.json()
                if data.get("error") or data.get("status") == "fail":
                    continue
                city = data.get("city") or data.get("regionName")
            else:
                city = resp.text.strip()
            if city and city.lower() not in ("", "error", "not found"):
                return city
        except Exception:
            continue
    return None


def get_weather_report(city=None):
    """Return (condition, temperature, feels_like) for a city.

    Tries, in order: WeatherAPI.com (free tier: 1M calls/month), OpenWeatherMap,
    then wttr.in — which needs NO API key at all, so the weather command always
    answers. When city is None/empty, wttr.in auto-detects location by IP.
    """
    city = (city or "").strip()
    if WEATHERAPI_KEY and city:
        try:
            res = requests.get(
                "https://api.weatherapi.com/v1/current.json",
                params={"key": WEATHERAPI_KEY, "q": city},
                timeout=10,
            ).json()
            weather = res["current"]["condition"]["text"]
            temperature = res["current"]["temp_c"]
            feels_like = res["current"]["feelslike_c"]
            return weather, f"{temperature}℃", f"{feels_like}℃"
        except Exception as e:
            print(f"WeatherAPI error (falling back to OpenWeatherMap): {e}")

    if OPENWEATHER_APP_ID and city:
        try:
            res = requests.get(
                f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_APP_ID}&units=metric",
                timeout=10,
            ).json()
            weather = res["weather"][0]["main"]
            temperature = res["main"]["temp"]
            feels_like = res["main"]["feels_like"]
            return weather, f"{temperature}℃", f"{feels_like}℃"
        except Exception as e:
            print(f"OpenWeatherMap error: {e}")

    # wttr.in — free, no API key; auto-detects location when city is empty
    try:
        url = f"https://wttr.in/{quote(city)}" if city else "https://wttr.in/"
        res = requests.get(url, params={"format": "j1"}, timeout=10).json()
        cur = res["current_condition"][0]
        weather = cur["weatherDesc"][0]["value"]
        temperature = cur["temp_C"]
        feels_like = cur["FeelsLikeC"]
        return weather, f"{temperature}℃", f"{feels_like}℃"
    except Exception as e:
        print(f"wttr.in error: {e}")
    return "Unknown", "--℃", "--℃"

def get_random_joke():
    """A random dad joke, or a safe fallback when the API is unreachable.
    Never raises (matches the rest of this module)."""
    try:
        headers = {'Accept': 'application/json'}
        res = requests.get("https://icanhazdadjoke.com/", headers=headers,
                           timeout=10).json()
        joke = (res.get("joke") or "").strip()
        if joke:
            return joke
    except Exception as e:
        print(f"[online_ops] joke error: {e}")
    return ("Why did the scarecrow win an award? "
            "Because he was outstanding in his field!")