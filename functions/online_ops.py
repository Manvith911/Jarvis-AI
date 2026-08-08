import requests
import wikipedia
import pywhatkit as kit
from email.message import EmailMessage
import smtplib
from urllib.parse import quote
from decouple import config

def find_my_ip():
    ip_address = requests.get('https://api64.ipify.org?format=json').json()
    return ip_address["ip"]

def search_on_wikipedia(query):
    results = wikipedia.summary(query, sentences=2)
    return results

def play_on_youtube(video):
    kit.playonyt(video)

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

def send_whatsapp_message(number, message):
    kit.sendwhatmsg_instantly(f"+351{number}", message)

EMAIL = config("EMAIL", default="")
PASSWORD = config("PASSWORD", default="")


def send_email(receiver_address, subject, message):
    try:
        email = EmailMessage()
        email['To'] = receiver_address
        email["Subject"] = subject
        email['From'] = EMAIL
        email.set_content(message)
        s = smtplib.SMTP("smtp.gmail.com", 587)
        s.starttls()
        s.login(EMAIL, PASSWORD)
        s.send_message(email)
        s.close()
        return True
    except Exception as e:
        print(e)
        return False

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

TMDB_API_KEY = config("TMDB_API_KEY", default="")


def get_trending_movies():
    trending_movies = []
    res = requests.get(
        f"https://api.themoviedb.org/3/trending/movie/day?api_key={TMDB_API_KEY}").json()
    results = res["results"]
    for r in results:
        trending_movies.append(r["original_title"])
    return trending_movies[:5]

def get_random_joke():
    headers = {
        'Accept': 'application/json'
    }
    res = requests.get("https://icanhazdadjoke.com/", headers=headers).json()
    return res["joke"]

def get_random_advice():
    res = requests.get("https://api.adviceslip.com/advice").json()
    return res['slip']['advice']