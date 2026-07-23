#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║                    NEXUSBOT v3.0                        ║
║  Premium All-in-One Telegram Bot                        ║
║  OSINT (no API keys) | YouTube 4K | Pinterest | Music  ║
╚══════════════════════════════════════════════════════════╝
"""

import os, re, sys, json, time, logging, threading, tempfile, subprocess, html, asyncio
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, quote_plus
from typing import Optional, Tuple, List, Dict

import requests
from bs4 import BeautifulSoup
import phonenumbers
from phonenumbers import carrier, geocoder, timezone as pn_tz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode

# ── yt-dlp ──
try:
    import yt_dlp
    YT_DLP_AVAIL = True
except ImportError:
    YT_DLP_AVAIL = False

# ── FFmpeg check ──
FFMPEG_AVAIL = False
try:
    subprocess.run(["ffmpeg", "-version"], capture_output=True, check=False)
    FFMPEG_AVAIL = True
except:
    pass

# ═══════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════

BOT_TOKEN = os.environ.get("BOT_TOKEN", os.environ.get("TOKEN", "8760884392:AAHJLxmR5imC3L976gu1uYWtrG2JvPlVySk"))
TRUECALLER_ID = os.environ.get("TRUECALLER_ID", "")  # Optional: user provides their own
START_TIME = datetime.now()
MAX_TG_UPLOAD = 48 * 1024 * 1024  # 48MB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("NexusBot")

# ═══════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════

def fmt_time(seconds):
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    return f"{h}h {m}m {s}s" if h else (f"{m}m {s}s" if m else f"{s}s")

def divider(c="━", n=22):
    return c * n

def fmt_size(n):
    if n < 1024: return f"{n}B"
    if n < 1024**2: return f"{n/1024:.1f}KB"
    if n < 1024**3: return f"{n/1024**2:.1f}MB"
    return f"{n/1024**3:.2f}GB"

def upload_to_fileio(path):
    """Upload to file.io — free, no auth needed. Returns share link."""
    try:
        with open(path, "rb") as f:
            r = requests.post("https://file.io", files={"file": f}, timeout=180)
        if r.status_code == 200 and r.json().get("success"):
            return r.json()["link"]
    except Exception as e:
        logger.error(f"file.io error: {e}")
    return None

# ═══════════════════════════════════════════════
# PHONE OSINT — Zero API Keys
# ═══════════════════════════════════════════════

def phone_basic(raw: str) -> dict:
    """phonenumbers library — free, offline, no key needed."""
    r = {"valid": False, "error": None}
    try:
        num = phonenumbers.parse(raw, None)
        if not phonenumbers.is_valid_number(num):
            r["error"] = "Invalid phone number"; return r
        types = {0:"Fixed Line",1:"Mobile",2:"Fixed/Mobile",3:"Toll-Free",
                 4:"Premium Rate",5:"Shared Cost",6:"VoIP",7:"Personal",
                 8:"Pager",9:"UAN",10:"Voicemail"}
        r["valid"] = True
        r["intl"] = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
        r["national"] = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.NATIONAL)
        r["cc"] = f"+{num.country_code}"
        r["country"] = geocoder.description_for_number(num, "en") or "Unknown"
        r["carrier"] = carrier.name_for_number(num, "en") or "Unknown"
        r["type"] = types.get(phonenumbers.number_type(num), "Unknown")
        r["tz"] = ", ".join(pn_tz.time_zones_for_number(num)) or "Unknown"
        return r
    except Exception as e:
        r["error"] = str(e); return r

def phone_google_dork(raw: str) -> List[Dict]:
    """Scrape Google for public mentions of the number (name, address, etc)."""
    results = []
    try:
        query = quote_plus(f'"{raw}" phone OR contact OR address OR "call me"')
        h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(f"https://www.google.com/search?q={query}&num=10", headers=h, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for g in soup.select("div.g")[:8]:
                link_el = g.select_one("a")
                snippet_el = g.select_one(".VwiC3b")
                title_el = g.select_one("h3")
                if link_el and snippet_el:
                    results.append({
                        "title": title_el.get_text(strip=True) if title_el else "",
                        "snippet": snippet_el.get_text(strip=True)[:200],
                        "url": link_el.get("href", "")
                    })
    except Exception as e:
        logger.error(f"Google dork error: {e}")
    return results

def phone_truecaller(raw: str) -> Optional[Dict]:
    """Try truecallerpy if installation_id is configured."""
    if not TRUECALLER_ID:
        return None
    try:
        from truecallerpy import search_phonenumber
        clean = raw.lstrip("+")
        result = asyncio.run(search_phonenumber(clean, "US" if raw.startswith("+1") else "IN", TRUECALLER_ID))
        if result and result.get("data"):
            data = result["data"][0] if isinstance(result["data"], list) else result["data"]
            return {
                "name": data.get("name", ""),
                "photo": data.get("profileImage", ""),
                "addresses": data.get("addresses", []),
                "emails": data.get("emails", []),
                "spam": data.get("spamInfo", {}).get("spamScore", 0)
            }
    except Exception as e:
        logger.error(f"Truecaller error: {e}")
    return None

def phone_social_check(raw: str) -> dict:
    """Generate deep links for social platforms."""
    clean = raw.lstrip("+")
    return {
        "Telegram": f"https://t.me/+{clean}",
        "WhatsApp": f"https://wa.me/{clean}",
        "Signal": f"https://signal.me/#p/+{clean}",
    }

async def cmd_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(
            "❌ Usage: `/phone +1234567890`\nInclude country code (+1, +44, +91, etc)",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    raw = "+" + ctx.args[0].lstrip("+")
    msg = await update.message.reply_text(
        "🔍 *Scanning public sources...*",
        parse_mode=ParseMode.MARKDOWN
    )

    # ── Parallel free lookups ──
    basic = phone_basic(raw)
    if basic.get("error"):
        await msg.edit_text(f"❌ {basic['error']}", parse_mode=ParseMode.MARKDOWN)
        return
    if not basic.get("valid"):
        await msg.edit_text("❌ Invalid phone number. Check country code.", parse_mode=ParseMode.MARKDOWN)
        return

    web_results = phone_google_dork(raw)
    social = phone_social_check(raw)

    # ── Build dossier ──
    text = (
        f"📱 **PHONE OSINT DOSSIER**\n"
        f"{divider()}\n\n"
        f"**📞 Number**\n"
        f"  Intl: `{basic['intl']}`\n"
        f"  National: `{basic['national']}`\n"
        f"  Country: `{basic['country']}` ({basic['cc']})\n\n"
        f"**🏢 Carrier & Type**\n"
        f"  Carrier: `{basic['carrier']}`\n"
        f"  Type: `{basic['type']}`\n"
        f"  Timezone: `{basic['tz']}`\n"
        f"  Valid: ✅ Yes\n\n"
    )

    # ── Web footprint (name/address from public sources) ──
    text += f"**🌐 Public Web Footprint**\n"
    if web_results:
        text += f"  Found `{len(web_results)}` public mention(s):\n\n"
        for i, w in enumerate(web_results[:5], 1):
            snip = html.escape(w["snippet"][:150])
            text += f"  *{i}.* [{html.escape(w['title'][:60])}]({w['url']})\n"
            text += f"    `{snip}`\n\n"
    else:
        text += f"  ℹ️ No public web mentions found.\n"
        text += f"  💡 Try `/phone` with different number formats\n\n"

    # ── Social ──
    text += f"**🌐 Social / Messaging**\n"
    for platform, url in social.items():
        text += f"  • [{platform}]({url})\n"

    # ── Truecaller note ──
    if not TRUECALLER_ID:
        text += f"\n💡 *For owner name & photo: get Truecaller ID*\n"
        text += f"  `pip install truecallerpy` → `truecallerpy login`\n"
        text += f"  Set env `TRUECALLER_ID` on Render dashboard.\n"
    else:
        tc = phone_truecaller(raw)
        if tc and tc.get("name"):
            text += f"\n**👤 Truecaller:** `{tc['name']}`\n"
            if tc.get("emails"):
                text += f"  📧 {', '.join(tc['emails'][:3])}\n"
            if tc.get("spam", 0) > 70:
                text += f"  ⚠️ Spam score: {tc['spam']}/100\n"

    text += f"\n{divider()}\n"
    text += f"⚡ NexusOSINT • Scan: `{int(time.time())}`"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Google Search", url=f"https://google.com/search?q={raw.replace('+', '%2B')}"),
         InlineKeyboardButton("📋 Spokeo", url=f"https://www.spokeo.com/{raw.lstrip('+')}")]
    ])

    await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard,
                        disable_web_page_preview=True)


# ═══════════════════════════════════════════════
# IP OSINT
# ═══════════════════════════════════════════════

async def cmd_ip(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("❌ Usage: `/ip 8.8.8.8`", parse_mode=ParseMode.MARKDOWN)
        return
    ip = ctx.args[0]
    msg = await update.message.reply_text("🌐 *Tracing IP...*", parse_mode=ParseMode.MARKDOWN)
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=status,message,query,country,countryCode,region,city,zip,isp,org,as,timezone,lat,lon,proxy,hosting,mobile", timeout=10)
        d = r.json()
        if d.get("status") == "fail":
            await msg.edit_text(f"❌ Invalid IP: {d.get('message', '')}", parse_mode=ParseMode.MARKDOWN)
            return
        text = (
            f"🌐 **IP Intelligence**\n{divider()}\n"
            f"📍 **IP:** `{d['query']}`\n🏳️ **Country:** {d.get('country','?')} ({d.get('countryCode','?')})\n"
            f"🏙️ **City:** {d.get('city','?')} | 🗺️ **Region:** {d.get('region','?')}\n"
            f"📡 **ISP:** {d.get('isp','?')}\n🏢 **Org:** {d.get('org','?')}\n"
            f"🔗 **ASN:** {d.get('as','?')} | 📌 **Lat/Lon:** {d.get('lat','?')}, {d.get('lon','?')}\n"
            f"🕐 **Timezone:** {d.get('timezone','?')}\n{divider('─',10)}\n"
            f"🛡️ **Proxy/VPN:** {'⚠️ YES' if d.get('proxy') else '✅ No'}\n"
            f"🏭 **Hosting:** {'⚠️ YES' if d.get('hosting') else '✅ No'}\n"
            f"📱 **Mobile:** {'⚠️ YES' if d.get('mobile') else '✅ No'}\n{divider()}\n⚡ NexusOSINT"
        )
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}", parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════════
# YOUTUBE DOWNLOADER — Full Format Selection
# ═══════════════════════════════════════════════

def yt_get_formats(url: str) -> Tuple[Optional[list], Optional[str], Optional[str]]:
    """List all download formats for a YouTube URL. No download happens."""
    if not YT_DLP_AVAIL:
        return None, None, "yt-dlp not installed. Run: pip install yt-dlp"
    try:
        opts = {"quiet": True, "no_warnings": True, "nocheckcertificate": True, "no_color": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            fmts = info.get("formats", [])
            title = info.get("title", "Unknown")
            duration = info.get("duration", 0)

            clean = []
            seen = set()
            for f in fmts:
                fid = f.get("format_id", "")
                ext = f.get("ext", "")
                vcodec = f.get("vcodec", "none")
                acodec = f.get("acodec", "none")
                height = f.get("height") or 0
                fps = f.get("fps") or 0
                fs = f.get("filesize") or f.get("filesize_approx") or 0
                tbr = f.get("tbr") or 0

                if vcodec == "none" and acodec == "none": continue

                if vcodec != "none" and height > 0:
                    label = f"{height}p"
                    if fps >= 30: label += f" {fps}fps"
                    label += f" • {ext.upper()}"
                    if fs: label += f" • {fmt_size(fs)}"
                    key = height
                elif vcodec != "none" and height == 0:
                    continue  # skip weird
                else:
                    abr = f.get("abr", 0)
                    label = f"🎵 Audio • {ext.upper()}"
                    if abr: label += f" {int(abr)}kbps"
                    if fs: label += f" • {fmt_size(fs)}"
                    key = -1  # audio goes last

                dedup = f"{key}_{ext}_{vcodec.split('.')[0]}_{fps}"
                if dedup not in seen:
                    seen.add(dedup)
                    clean.append({
                        "id": fid,
                        "label": label,
                        "ext": ext,
                        "height": height,
                        "filesize": fs,
                        "fps": fps,
                        "codec": vcodec.split(".")[0] if vcodec != "none" else "audio"
                    })

            # Sort: highest res first, audio last
            clean.sort(key=lambda x: (0 if x["height"] > 0 else 1, -x["height"]))
            return clean, title, None
    except yt_dlp.utils.DownloadError as e:
        err = str(e)[:200]
        if "This video is not available" in err:
            return None, None, "❌ Video is unavailable (private/removed/geo-blocked)."
        if "HTTP Error 403" in err:
            return None, None, "❌ Access denied (403). Try a different URL."
        return None, None, f"❌ yt-dlp error: {err}"
    except Exception as e:
        return None, None, f"❌ Error: {str(e)[:200]}"


def yt_download_format(url: str, format_id: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Download a specific format. Returns (filepath, title, error)."""
    if not YT_DLP_AVAIL:
        return None, None, "yt-dlp not installed."
    tmpdir = tempfile.mkdtemp()
    opts = {
        "format": format_id,
        "outtmpl": f"{tmpdir}/%(title)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "no_color": True,
        "noprogress": True,
        "max_filesize": MAX_TG_UPLOAD + 10*1024*1024,  # 58MB max download
    }
    # Merge if needed
    if FFMPEG_AVAIL:
        opts["merge_output_format"] = "mp4"

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "Video")
            files = list(Path(tmpdir).iterdir())
            if files:
                return str(files[0]), title, None
            return None, title, "No file produced."
    except yt_dlp.utils.DownloadError as e:
        err = str(e)[:200]
        if "filesize" in err.lower():
            return None, None, "❌ File too large - using external upload..."
        if "requested format not available" in err.lower():
            return None, None, "❌ Format not available for this video."
        return None, None, f"❌ {err}"
    except Exception as e:
        return None, None, f"❌ {str(e)[:200]}"


async def yt_show_formats(update: Update, ctx: ContextTypes.DEFAULT_TYPE, url: str):
    """Show format selection keyboard to user."""
    msg = await update.message.reply_text("⏳ *Fetching available formats...*", parse_mode=ParseMode.MARKDOWN)
    fmts, title, err = yt_get_formats(url)

    if err:
        await msg.edit_text(err, parse_mode=ParseMode.MARKDOWN)
        return

    if not fmts:
        await msg.edit_text("❌ No formats found for this video.", parse_mode=ParseMode.MARKDOWN)
        return

    # Store in user_data for callback
    ctx.user_data["yt_url"] = url
    ctx.user_data["yt_title"] = title
    ctx.user_data["yt_formats"] = {f["id"]: f for f in fmts}

    # Build keyboard — group by resolution
    buttons = []
    audio_btn = None
    for f in fmts:
        label = f["label"]
        fid = f["id"]
        if f["codec"] == "audio":
            audio_btn = InlineKeyboardButton(label, callback_data=f"ytdl_{fid}")
        else:
            buttons.append(InlineKeyboardButton(label, callback_data=f"ytdl_{fid}"))

    keyboard = []
    # Put in rows of 2
    for i in range(0, len(buttons), 2):
        row = buttons[i:i+2]
        keyboard.append(row)
    if audio_btn:
        keyboard.append([audio_btn])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="ytdl_cancel")])

    msg_text = (
        f"🎬 **{title[:50]}**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📥 **Select quality:**\n"
        f"*Tap a format below to download*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Files >50MB sent via file.io link"
    )
    await msg.edit_text(msg_text, parse_mode=ParseMode.MARKDOWN,
                        reply_markup=InlineKeyboardMarkup(keyboard))


async def yt_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "ytdl_cancel":
        await query.edit_text("❌ Cancelled.", parse_mode=ParseMode.MARKDOWN)
        return

    format_id = query.data.replace("ytdl_", "")
    url = ctx.user_data.get("yt_url", "")
    title = ctx.user_data.get("yt_title", "Video")
    fmts = ctx.user_data.get("yt_formats", {})

    if not url:
        await query.edit_text("❌ Session expired. Send the YouTube link again.", parse_mode=ParseMode.MARKDOWN)
        return

    selected = fmts.get(format_id, {})
    label = selected.get("label", format_id)

    await query.edit_text(
        f"⏬ *Downloading...*\n{divider()}\n"
        f"🎬 `{title[:50]}`\n"
        f"📥 Format: `{label}`\n"
        f"⏳ Please wait...",
        parse_mode=ParseMode.MARKDOWN
    )

    filepath, dtitle, err = yt_download_format(url, format_id)
    if err:
        await query.edit_text(f"❌ {err}", parse_mode=ParseMode.MARKDOWN)
        return

    if not filepath:
        await query.edit_text("❌ Download failed - no file produced.", parse_mode=ParseMode.MARKDOWN)
        return

    size = os.path.getsize(filepath)

    if size <= MAX_TG_UPLOAD:
        await query.edit_text(
            f"📤 *Uploading to Telegram...* ({fmt_size(size)})",
            parse_mode=ParseMode.MARKDOWN
        )
        try:
            ext = os.path.splitext(filepath)[1].lower()
            with open(filepath, "rb") as f:
                if ext in (".mp4", ".webm", ".mov"):
                    await update.effective_chat.send_video(
                        video=InputFile(f, filename=f"{dtitle[:50]}{ext}"),
                        caption=f"🎬 `{dtitle[:50]}`\n📥 `{label}`\n⚡ NexusBot",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await update.effective_chat.send_document(
                        document=InputFile(f, filename=f"{dtitle[:50]}{ext}"),
                        caption=f"🎬 `{dtitle[:50]}`\n📥 `{label}`\n⚡ NexusBot",
                        parse_mode=ParseMode.MARKDOWN
                    )
            await query.delete()
        except Exception as e:
            await query.edit_text(f"❌ Upload error: {str(e)[:100]}", parse_mode=ParseMode.MARKDOWN)
    else:
        # Upload to file.io
        await query.edit_text(
            f"📤 *Uploading to cloud...* ({fmt_size(size)})",
            parse_mode=ParseMode.MARKDOWN
        )
        link = upload_to_fileio(filepath)
        if link:
            await query.edit_text(
                f"✅ **Download complete!**\n{divider()}\n"
                f"🎬 `{dtitle[:50]}`\n"
                f"📥 `{label}` | 📦 {fmt_size(size)}\n\n"
                f"🔗 [Download Link]({link})\n"
                f"⚠️ Link expires in 14 days.\n{divider()}\n⚡ NexusBot",
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
        else:
            await query.edit_text(
                f"❌ File too large ({fmt_size(size)}) and cloud upload failed.\n"
                f"Try a lower quality.",
                parse_mode=ParseMode.MARKDOWN
            )

    # Cleanup
    try:
        if filepath and os.path.exists(filepath): os.unlink(filepath)
    except: pass


# ═══════════════════════════════════════════════
# PINTEREST DOWNLOADER
# ═══════════════════════════════════════════════

async def download_pinterest(url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        resp = requests.get(url, headers=h, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Try video
        video = soup.find("video")
        if video:
            src = video.get("src") or (video.find("source").get("src") if video.find("source") else None)
            if src:
                if src.startswith("//"): src = "https:" + src
                data = requests.get(src, headers=h, timeout=30).content
                tmp = tempfile.mkdtemp()
                path = f"{tmp}/pin_video.mp4"
                with open(path, "wb") as f: f.write(data)
                return path, "Pinterest Video", None

        # Try high-res image
        img = soup.find("img", {"src": re.compile(r"originals|736x|1200x")})
        if not img:
            img = soup.find("meta", property="og:image")
        if img:
            src = img.get("src") or img.get("content", "")
            if src.startswith("//"): src = "https:" + src
            src_hd = re.sub(r"/(\d+)x/", "/736x/", src)
            data = requests.get(src_hd, headers=h, timeout=30).content
            tmp = tempfile.mkdtemp()
            path = f"{tmp}/pin_image.jpg"
            with open(path, "wb") as f: f.write(data)
            return path, "Pinterest Image", None

        return None, None, "No media found in that Pin."
    except Exception as e:
        return None, None, f"Pinterest error: {str(e)[:200]}"


# ═══════════════════════════════════════════════
# MUSIC FINDER
# ═══════════════════════════════════════════════

async def music_from_link(url: str) -> str:
    domain = urlparse(url).netloc.lower()

    if "spotify.com" in domain:
        try:
            r = requests.get(f"https://open.spotify.com/oembed?url={url}", timeout=8)
            if r.status_code == 200:
                d = r.json()
                return (
                    f"🎵 **Spotify Track**\n{divider()}\n"
                    f"🎤 **Track:** {d.get('title','?')}\n"
                    f"👤 **Artist:** {d.get('author_name','?')}\n"
                    f"💿 **Album:** {d.get('provider_name','?')}\n"
                    f"{divider()}\n⚡ NexusBot"
                )
        except:
            pass

    if "soundcloud.com" in domain:
        try:
            h = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=h, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            t = soup.find("meta", property="og:title")
            d = soup.find("meta", property="og:description")
            title = t.get("content", "Unknown") if t else "Unknown"
            desc = d.get("content", "Unknown") if d else "Unknown"
            return f"🎵 **SoundCloud**\n{divider()}\n🎤 **Track:** {title}\n👤 **Info:** {desc}\n{divider()}\n⚡ NexusBot"
        except:
            pass

    if any(x in domain for x in ["youtube.com", "youtu.be"]):
        try:
            h = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=h, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            t = soup.find("meta", property="og:title")
            title = t.get("content", "Unknown") if t else "Unknown"
            return f"🎵 **YouTube Media**\n{divider()}\n🎤 **Title:** {title}\n💡 *Use /yt or send the link to download*\n{divider()}\n⚡ NexusBot"
        except:
            pass

    return "❌ Unsupported platform. Try Spotify, SoundCloud, or YouTube."


# ═══════════════════════════════════════════════
# LYRICS
# ═══════════════════════════════════════════════

async def cmd_lyrics(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("❌ Usage: `/lyrics Artist - Song`\nExample: `/lyrics Taylor Swift - Blank Space`", parse_mode=ParseMode.MARKDOWN)
        return
    query = " ".join(ctx.args)
    msg = await update.message.reply_text("🎤 *Searching lyrics...*", parse_mode=ParseMode.MARKDOWN)

    # Try lyrics.ovh (free, no key)
    try:
        if " - " in query:
            artist, song = query.split(" - ", 1)
            r = requests.get(f"https://api.lyrics.ovh/v1/{artist.strip()}/{song.strip()}", timeout=10)
        else:
            r = requests.get(f"https://api.lyrics.ovh/v1///{query.strip()}", timeout=10)
        if r.status_code == 200:
            data = r.json()
            lyrics = (data.get("lyrics") or "").strip()
            if lyrics:
                if len(lyrics) > 3500: lyrics = lyrics[:3500] + "\n\n... (truncated)"
                await msg.edit_text(f"📝 **{query}**\n{divider()}\n```\n{lyrics}\n```\n{divider()}", parse_mode=ParseMode.MARKDOWN)
                return
    except:
        pass

    # Fallback
    try:
        r = requests.get(f"https://some-random-api.com/lyrics?title={query.split(' - ')[-1].strip() if ' - ' in query else query}", timeout=10)
        if r.status_code == 200:
            d = r.json()
            lyrics = d.get("lyrics", "")
            if lyrics and len(lyrics) > 10:
                if len(lyrics) > 3500: lyrics = lyrics[:3500] + "\n\n... (truncated)"
                await msg.edit_text(f"📝 **{d.get('title',query)}** — {d.get('author','')}\n{divider()}\n```\n{lyrics}\n```\n{divider()}", parse_mode=ParseMode.MARKDOWN)
                return
    except:
        pass

    await msg.edit_text("❌ Lyrics not found. Try: `/lyrics Artist - Song Name`", parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════════
# COMMANDS
# ═══════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Join Channel", url="https://t.me/nexusbot_updates"),
         InlineKeyboardButton("👨‍💻 GitHub Repo", url="https://github.com/nexusbot/nexusbot")]
    ])
    text = (
        f"✨ **Welcome to NexusBot, {user.first_name}!**\n\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"🔍 **OSINT Suite** _(no API keys needed)_\n"
        f"  `/phone +1234` — Public web footprint, carrier, location\n"
        f"  `/ip 8.8.8.8` — IP geolocation, ISP, proxy detection\n\n"
        f"📥 **YouTube 4K Downloader**\n"
        f"  Send any YouTube link → pick quality from menu\n"
        f"  Up to 4K • Auto cloud upload for large files\n\n"
        f"📌 **Pinterest Downloader**\n"
        f"  Send a Pinterest link → auto-extract image/video\n\n"
        f"🎵 **Music Tools**\n"
        f"  Send Spotify/SoundCloud link → track info\n"
        f"  `/lyrics Artist - Song` — Free lyrics\n\n"
        f"ℹ️ `/help` — Full reference\n"
        f"📊 `/stats` — Bot status"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        f"📚 **NexusBot Commands**\n\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"**🔍 OSINT**\n"
        f"`/phone +1234567890` — Public web + carrier + social check\n"
        f"`/ip 8.8.8.8` — Full IP intel\n\n"
        f"**📥 Auto-Download**\n"
        f"Just send a **YouTube** URL → format menu\n"
        f"Just send a **Pinterest** URL → auto media\n\n"
        f"**🎵 Music**\n"
        f"Send **Spotify/SoundCloud** link → track ID\n"
        f"`/lyrics Artist - Song` — Free lyrics\n\n"
        f"**ℹ️ General**\n"
        f"`/start` — Welcome\n`/stats` — Bot status & uptime\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Python • Render • Open Source"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uptime = datetime.now() - START_TIME
    dl_count = len(USER_SESSIONS)
    text = (
        f"📊 **NexusBot Status**\n{divider()}\n"
        f"⏱ **Uptime:** {fmt_time(uptime.total_seconds())}\n"
        f"🐍 **Python:** {sys.version.split()[0]}\n"
        f"📦 **yt-dlp:** {'✅' if YT_DLP_AVAIL else '❌'}\n"
        f"🎬 **FFmpeg:** {'✅' if FFMPEG_AVAIL else '❌'}\n"
        f"☁️ **Host:** Render Cloud\n"
        f"{divider()}\n"
        f"✅ **Online & Operational**"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════════
# MESSAGE HANDLER
# ═══════════════════════════════════════════════

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    urls = re.findall(r"https?://[^\s]+", text)
    if not urls:
        await update.message.reply_text("ℹ️ Send a **link** (YouTube, Pinterest, Spotify, SoundCloud)\nor use `/help` for commands.", parse_mode=ParseMode.MARKDOWN)
        return

    url = urls[0]
    domain = urlparse(url).netloc.lower()

    # YouTube
    if any(x in domain for x in ["youtube.com", "youtu.be", "m.youtube.com"]):
        await yt_show_formats(update, ctx, url)
        return

    # Pinterest
    if any(x in domain for x in ["pinterest.com", "pin.it", "pin.it"]):
        status = await update.message.reply_text("⏬ *Downloading Pinterest media...*", parse_mode=ParseMode.MARKDOWN)
        fp, title, err = await download_pinterest(url)
        if err:
            await status.edit_text(err, parse_mode=ParseMode.MARKDOWN)
            return
        await status.edit_text(f"📤 *Uploading:* {title}", parse_mode=ParseMode.MARKDOWN)
        ext = os.path.splitext(fp)[1].lower()
        with open(fp, "rb") as f:
            if ext in (".mp4", ".webm", ".mov"):
                await update.message.reply_video(InputFile(f, filename="pin_video.mp4"))
            else:
                await update.message.reply_photo(InputFile(f, filename="pin_image.jpg"))
        os.unlink(fp)
        await status.delete()
        return

    # Music platforms
    if any(x in domain for x in ["spotify.com", "soundcloud.com", "music.youtube.com"]):
        status = await update.message.reply_text("🎵 *Identifying music...*", parse_mode=ParseMode.MARKDOWN)
        result = await music_from_link(url)
        await status.edit_text(result, parse_mode=ParseMode.MARKDOWN)
        return

    await update.message.reply_text(f"❌ Unsupported: `{domain}`\nSupported: YouTube, Pinterest, Spotify, SoundCloud", parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════════
# ERROR HANDLER
# ═══════════════════════════════════════════════

async def on_error(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {ctx.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text("❌ An error occurred. Try again later.", parse_mode=ParseMode.MARKDOWN)
    except: pass


# ═══════════════════════════════════════════════
# HEALTH SERVER (for Render)
# ═══════════════════════════════════════════════

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"NexusBot OK")
    def log_message(self, fmt, *args): pass

def run_health():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()


# ═══════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════

def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.critical("BOT_TOKEN not set!"); sys.exit(1)

    threading.Thread(target=run_health, daemon=True).start()
    logger.info("Health server started.")

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("phone", cmd_phone))
    app.add_handler(CommandHandler("ip", cmd_ip))
    app.add_handler(CommandHandler("lyrics", cmd_lyrics))

    # YouTube format selection callback
    app.add_handler(CallbackQueryHandler(yt_callback, pattern=r"^ytdl_"))

    # Auto-detect links
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.add_error_handler(on_error)

    logger.info("🚀 NexusBot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()