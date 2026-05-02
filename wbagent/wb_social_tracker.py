"""
wb_social_tracker.py — WBAgent Social Media Tracker
Runs on Oracle Cloud VM every Sunday 08:00 WIB via APScheduler
"""

import os, json, logging, requests, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

CHANNEL_ID   = "UCUwpIWHPkHxzpHP4Sh69Z-Q"
FB_PAGE      = "WilliamBunartoPage"
FB_PAGE_ID   = "273909099794732"
CACHE_FILE   = Path.home() / "wbagent" / "social_cache.json"
REPORTS_DIR  = Path.home() / "wbagent" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

YT_API_KEY   = os.environ.get("YT_API_KEY", "")
IG_TOKEN     = os.environ.get("IG_ACCESS_TOKEN", "")
FB_TOKEN     = os.environ.get("FB_PAGE_TOKEN", "")
TG_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
WIB = datetime.timezone(datetime.timedelta(hours=7))


def load_cache():
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except:
            pass
    return {"last_updated": None, "weeks": [], "current": {}}

def save_cache(data):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

def push_to_history(cache, snapshot):
    cache.setdefault("weeks", []).append(snapshot)
    if len(cache["weeks"]) > 8:
        cache["weeks"] = cache["weeks"][-8:]
    cache["current"] = snapshot
    cache["last_updated"] = datetime.datetime.now(WIB).isoformat()

def fmt(n):
    if not n:
        return "—"
    n = int(n)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def fetch_youtube(prev):
    if not YT_API_KEY:
        logger.warning("YT_API_KEY not set")
        return prev.get("youtube", {})
    base = "https://www.googleapis.com/youtube/v3"
    result = {}
    try:
        r = requests.get(
            f"{base}/channels",
            params={"part": "statistics,snippet", "id": CHANNEL_ID, "key": YT_API_KEY},
            timeout=10,
        )
        r.raise_for_status()
        stats = r.json()["items"][0]["statistics"]
        result["subscribers"] = int(stats.get("subscriberCount", 0))
        result["total_views"] = int(stats.get("viewCount", 0))
        result["video_count"] = int(stats.get("videoCount", 0))
        prev_yt = prev.get("youtube", {})
        result["subs_delta"] = result["subscribers"] - prev_yt.get("subscribers", result["subscribers"])
    except Exception as e:
        logger.error(f"YT channel fetch failed: {e}")
        result.update(prev.get("youtube", {}))
    try:
        r = requests.get(
            f"{base}/search",
            params={
                "part": "snippet",
                "channelId": CHANNEL_ID,
                "order": "date",
                "maxResults": 5,
                "type": "video",
                "key": YT_API_KEY,
            },
            timeout=10,
        )
        r.raise_for_status()
        items = r.json().get("items", [])
        video_ids = [i["id"]["videoId"] for i in items if "videoId" in i.get("id", {})]
        if video_ids:
            r2 = requests.get(
                f"{base}/videos",
                params={"part": "statistics,snippet", "id": ",".join(video_ids), "key": YT_API_KEY},
                timeout=10,
            )
            r2.raise_for_status()
            videos = []
            for v in r2.json().get("items", []):
                pub = v["snippet"]["publishedAt"][:10]
                days_ago = (datetime.date.today() - datetime.date.fromisoformat(pub)).days
                videos.append({
                    "title": v["snippet"]["title"],
                    "views": int(v["statistics"].get("viewCount", 0)),
                    "likes": int(v["statistics"].get("likeCount", 0)),
                    "comments": int(v["statistics"].get("commentCount", 0)),
                    "age": f"{days_ago}d ago",
                    "published": pub,
                })
            result["recent_videos"] = videos
    except Exception as e:
        logger.error(f"YT videos fetch failed: {e}")
        result["recent_videos"] = prev.get("youtube", {}).get("recent_videos", [])
    return result


def fetch_instagram(prev):
    if not IG_TOKEN:
        logger.warning("IG_ACCESS_TOKEN not set")
        return prev.get("instagram", {})
    result = {}
    base = "https://graph.instagram.com"
    try:
        r = requests.get(
            f"{base}/me",
            params={"fields": "id,username,followers_count,media_count", "access_token": IG_TOKEN},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        result["followers"] = data.get("followers_count", 0)
        result["post_count"] = data.get("media_count", 0)
        result["username"] = data.get("username", "williambunarto")
        prev_ig = prev.get("instagram", {})
        result["followers_delta"] = result["followers"] - prev_ig.get("followers", result["followers"])
    except Exception as e:
        logger.error(f"IG account fetch failed: {e}")
        result.update(prev.get("instagram", {}))
    try:
        r = requests.get(
            f"{base}/me/media",
            params={
                "fields": "id,caption,like_count,comments_count,timestamp,media_type,permalink",
                "limit": 6,
                "access_token": IG_TOKEN,
            },
            timeout=10,
        )
        r.raise_for_status()
        posts = [
            {
                "caption": (m.get("caption") or "")[:80],
                "likes": m.get("like_count", 0),
                "comments": m.get("comments_count", 0),
                "type": m.get("media_type", "IMAGE"),
                "url": m.get("permalink", ""),
            }
            for m in r.json().get("data", [])
        ]
        result["recent_posts"] = posts
    except Exception as e:
        logger.error(f"IG media fetch failed: {e}")
        result["recent_posts"] = prev.get("instagram", {}).get("recent_posts", [])
    return result


def refresh_ig_token():
    if not IG_TOKEN:
        return ""
    try:
        r = requests.get(
            "https://graph.instagram.com/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": IG_TOKEN},
            timeout=10,
        )
        r.raise_for_status()
        new_token = r.json().get("access_token", IG_TOKEN)
        env_file = Path.home() / ".env_wbagent"
        if env_file.exists():
            lines = env_file.read_text().splitlines()
            lines = [
                l if not l.startswith("IG_ACCESS_TOKEN=") else f"IG_ACCESS_TOKEN={new_token}"
                for l in lines
            ]
            env_file.write_text("\n".join(lines) + "\n")
        logger.info("IG token refreshed")
        return new_token
    except Exception as e:
        logger.error(f"IG token refresh failed: {e}")
        return IG_TOKEN


def fetch_facebook(prev):
    if not FB_TOKEN:
        logger.warning("FB_PAGE_TOKEN not set")
        return prev.get("facebook", {})
    result = {}
    base = "https://graph.facebook.com/v19.0"
    try:
        r = requests.get(
            f"{base}/{FB_PAGE_ID}",
            params={"fields": "fan_count,followers_count,name", "access_token": FB_TOKEN},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        result["followers"] = data.get("followers_count", data.get("fan_count", 0))
        result["page_likes"] = data.get("fan_count", 0)
        prev_fb = prev.get("facebook", {})
        result["followers_delta"] = result["followers"] - prev_fb.get("followers", result["followers"])
    except Exception as e:
        logger.error(f"FB page fetch failed: {e}")
        result.update(prev.get("facebook", {}))
    try:
        r = requests.get(
            f"{base}/{FB_PAGE_ID}/posts",
            params={
                "fields": "message,created_time,reactions.summary(true),shares,comments.summary(true)",
                "limit": 5,
                "access_token": FB_TOKEN,
            },
            timeout=10,
        )
        r.raise_for_status()
        posts = []
        for p in r.json().get("data", []):
            posts.append({
                "message": (p.get("message") or "")[:80],
                "reactions": p.get("reactions", {}).get("summary", {}).get("total_count", 0),
                "shares": p.get("shares", {}).get("count", 0),
                "comments": p.get("comments", {}).get("summary", {}).get("total_count", 0),
            })
        result["recent_posts"] = posts
        result["total_engagement"] = sum(
            p["reactions"] + p["shares"] + p["comments"] for p in posts
        )
    except Exception as e:
        logger.error(f"FB posts fetch failed: {e}")
        result["recent_posts"] = prev.get("facebook", {}).get("recent_posts", [])
    return result


def fetch_tiktok(prev):
    return dict(prev.get("tiktok", {}))


def parse_manual_update(text, cache):
    current = dict(cache.get("current", {}))
    for line in text.splitlines():
        line = line.strip()
        if "=" not in line or line.startswith("#"):
            continue
        key, _, val = line.partition("=")
        key = key.strip().lower()
        try:
            val = int(val.strip().replace(",", ""))
        except ValueError:
            continue
        if key == "yt_subs":
            current.setdefault("youtube", {})["subscribers"] = val
        elif key == "yt_rev":
            current.setdefault("youtube", {})["weekly_revenue_idr"] = val
        elif key == "tt_followers":
            current.setdefault("tiktok", {})["followers"] = val
        elif key == "tt_likes":
            current.setdefault("tiktok", {})["total_likes"] = val
        elif key == "tt_views":
            current.setdefault("tiktok", {})["weekly_views"] = val
        elif key == "ig_followers":
            current.setdefault("instagram", {})["followers"] = val
        elif key == "fb_followers":
            current.setdefault("facebook", {})["followers"] = val
        elif key == "adsense":
            current["adsense_weekly_idr"] = val
    return current


def build_telegram_report(data, week_label, prev):
    yt = data.get("youtube", {})
    ig = data.get("instagram", {})
    fb = data.get("facebook", {})
    tt = data.get("tiktok", {})

    def delta_str(n):
        if not n:
            return ""
        return f" `{'+'if n>=0 else ''}{fmt(n)}`"

    lines = [
        f"📊 *Weekly Social Media Report*",
        f"_{week_label}_",
        f"Generated by WBAgent · Oracle Cloud",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"▶️ *YOUTUBE* `@WilliamBunarto`",
        f"  Subscribers: *{fmt(yt.get('subscribers'))}*{delta_str(yt.get('subs_delta'))}",
        f"  Total Views: *{fmt(yt.get('total_views'))}*",
        f"  Videos: {yt.get('video_count','—')}",
    ]
    for i, v in enumerate(yt.get("recent_videos", [])[:3], 1):
        lines.append(f"  {i}. {v['title'][:50]}… `{fmt(v.get('views',0))} views`")
    lines += [
        "",
        f"📸 *INSTAGRAM* `@williambunarto`",
        f"  Followers: *{fmt(ig.get('followers'))}*{delta_str(ig.get('followers_delta'))}",
    ]
    for i, p in enumerate(ig.get("recent_posts", [])[:3], 1):
        lines.append(f"  {i}. {(p.get('caption') or '—')[:45]}… `❤️{fmt(p.get('likes',0))}`")
    lines += [
        "",
        f"🎵 *TIKTOK* `@william_bunarto`",
        f"  Followers: *{fmt(tt.get('followers'))}*",
        f"  Total Likes: *{fmt(tt.get('total_likes'))}*",
    ]
    lines += [
        "",
        f"📘 *FACEBOOK* `WilliamBunartoPage`",
        f"  Followers: *{fmt(fb.get('followers'))}*{delta_str(fb.get('followers_delta'))}",
        f"  Weekly engagement: *{fmt(fb.get('total_engagement'))}*",
    ]
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "_Archive: williambunarto.duckdns.org/reports_",
    ]
    return "\n".join(l for l in lines if l is not None)


def run_weekly_social_report(send_telegram_fn=None):
    logger.info("WBAgent: Starting weekly social media report...")
    cache = load_cache()
    prev = cache.get("current", {})
    now = datetime.datetime.now(WIB)
    week_label = f"{(now - datetime.timedelta(days=6)).strftime('%b %d')} – {now.strftime('%b %d, %Y')}"
    report_date = now.strftime("%Y-%m-%d")
    data = {}
    data["youtube"] = fetch_youtube(prev)
    data["instagram"] = fetch_instagram(prev)
    data["facebook"] = fetch_facebook(prev)
    data["tiktok"] = fetch_tiktok(prev)
    push_to_history(cache, data)
    save_cache(cache)
    tg_text = build_telegram_report(data, week_label, prev)
    html_path = REPORTS_DIR / f"report_{report_date}.html"
    html_path.write_text(f"<html><body><pre>{tg_text}</pre></body></html>", encoding="utf-8")
    logger.info(f"Report saved to {html_path}")
    if send_telegram_fn:
        try:
            send_telegram_fn(TG_CHAT_ID, tg_text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
    else:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT_ID, "text": tg_text, "parse_mode": "Markdown"},
                timeout=15,
            )
        except Exception as e:
            logger.error(f"Telegram direct send failed: {e}")
    logger.info("Weekly social report complete.")
    return data


if __name__ == "__main__":
    try:
        import dotenv
        dotenv.load_dotenv(Path.home() / ".env_wbagent")
    except ImportError:
        pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = run_weekly_social_report()
    cache = load_cache()
    print("\n=== TELEGRAM PREVIEW ===")
    print(build_telegram_report(result, "Test Run", {}))
