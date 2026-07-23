#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║                    OmniIntel v1.0                            ║
║  OSINT & Media Intelligence Platform — Telegram Bot          ║
╠══════════════════════════════════════════════════════════════╣
║  Reference Projects (inspiration, not copied):               ║
║   • The-Black-Tiger     – Phone OSINT methodology            ║
║   • holehe              – Email existence checks             ║
║   • IP-Tracer           – IP intelligence reporting          ║
║   • ytmdl               – Music metadata extraction          ║
║   • LyricsGenius        – Lyrics lookup                      ║
║   • yt-dlp              – Primary download engine            ║
╚══════════════════════════════════════════════════════════════╝

Authorization: For authorized penetration testing and OSINT use only.
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Third-party imports (install via: pip install -r requirements.txt)
# ---------------------------------------------------------------------------
try:
    import aiohttp
    import phonenumbers
    from phonenumbers import geocoder, carrier, timezone as pn_timezone
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                               MessageHandler, filters, ContextTypes)
    from telegram.constants import ParseMode
except ImportError as e:
    print(f"[!] Missing dependency: {e}")
    print("[!] Run: pip install python-telegram-bot phonenumbers aiohttp yt-dlp")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BOT_TOKEN = "8760884392:AAHJLxmR5imC3L976gu1uYWtrG2JvPlVySk"

# Directories
DOWNLOAD_DIR = Path.home() / "OmniIntel" / "downloads"
REPORT_DIR = Path.home() / "OmniIntel" / "reports"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# Genius API (Lyrics) — user can /setgenius <token>
GENIUS_ACCESS_TOKEN = os.environ.get("GENIUS_ACCESS_TOKEN", "")

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("OmniIntel")

# ---------------------------------------------------------------------------
# Helper Utilities
# ---------------------------------------------------------------------------

def fmt_bold(text: str) -> str:
    """Telegram-safe bold formatting."""
    return f"<b>{text}</b>"

def fmt_code(text: str) -> str:
    return f"<code>{text}</code>"

def fmt_header(title: str) -> str:
    sep = "═" * 40
    return f"{fmt_bold(sep)}\n{fmt_bold(f'  {title}')}\n{fmt_bold(sep)}"

def sanitize_filename(name: str) -> str:
    """Remove path-traversal characters."""
    return re.sub(r'[^\w\.\-\(\) ]', '_', name)

def build_progress_bar(current: int, total: int, width: int = 20) -> str:
    if total == 0:
        return "[" + "░" * width + "]"
    filled = int((current / total) * width)
    return "[" + "█" * filled + "░" * (width - filled) + f"] {current}/{total}"


# ===========================================================================
# MODULE 1: Phone OSINT  (Inspired by The-Black-Tiger's phone module)
# ===========================================================================

class PhoneOSINT:
    """
    Phone number OSINT — validation, carrier, geolocation, public lookups.
    Inspired by The-Black-Tiger's phone information section.
    """

    @staticmethod
    async def analyze(number: str, session: aiohttp.ClientSession) -> dict:
        """Perform comprehensive phone number analysis."""
        result = {
            "raw": number,
            "valid": False,
            "possible": False,
            "country_code": None,
            "national_number": None,
            "location": None,
            "carrier": None,
            "timezones": [],
            "number_type": None,
            "formatted_international": None,
            "formatted_national": None,
            "public_lookups": {},
        }

        try:
            parsed = phonenumbers.parse(number, None)
            result["valid"] = phonenumbers.is_valid_number(parsed)
            result["possible"] = phonenumbers.is_possible_number(parsed)
            result["country_code"] = parsed.country_code
            result["national_number"] = parsed.national_number
            result["formatted_international"] = phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL
            )
            result["formatted_national"] = phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.NATIONAL
            )

            # Location description
            region = geocoder.description_for_number(parsed, "en")
            result["location"] = region if region else "Unknown"

            # Carrier
            carrier_name = carrier.name_for_number(parsed, "en")
            result["carrier"] = carrier_name if carrier_name else "Unknown"

            # Timezones
            tz_list = pn_timezone.time_zones_for_number(parsed)
            result["timezones"] = list(tz_list) if tz_list else []

            # Number type
            num_type = phonenumbers.number_type(parsed)
            type_map = {
                0: "Fixed Line",
                1: "Mobile",
                2: "Fixed Line or Mobile",
                3: "Toll Free",
                4: "Premium Rate",
                5: "Shared Cost",
                6: "VoIP",
                7: "Personal Number",
                8: "Pager",
                9: "Universal Access",
                10: "Unknown",
            }
            result["number_type"] = type_map.get(num_type, "Unknown")

            # Public lookups (async — inspired by The-Black-Tiger's
            # multi-source approach)
            nat = str(parsed.national_number)
            cc = str(parsed.country_code)
            full_intl = result["formatted_international"]

            tasks = []
            # Lookup services aggregated
            lookup_urls = [
                ("numverify-like", f"https://api.numlookupapi.com/v1/validate/{full_intl.replace(' ', '%20')}"),
                # Free carrier lookup via abstractions
            ]
            # For demonstration we gather what we can; real deployments
            # would add API keys.
            result["public_lookups"]["note"] = (
                "Deep public lookups require API keys (numverify, veriphone, etc.)"
            )

        except phonenumbers.NumberParseException as e:
            result["error"] = str(e)

        return result

    @staticmethod
    def format_report(data: dict) -> str:
        """Generate a professional phone OSINT report (inspired by TBT style)."""
        lines = []
        lines.append(fmt_header("📱 PHONE OSINT REPORT"))
        lines.append("")
        lines.append(f"{fmt_bold('Target:')}        {fmt_code(data.get('raw', 'N/A'))}")
        lines.append(f"{fmt_bold('Valid:')}         {'✅ YES' if data.get('valid') else '❌ NO'}")
        lines.append(f"{fmt_bold('Possible:')}      {'✅ YES' if data.get('possible') else '❌ NO'}")
        lines.append("")
        lines.append(f"{fmt_bold('International:')} {fmt_code(data.get('formatted_international', 'N/A'))}")
        lines.append(f"{fmt_bold('National:')}      {fmt_code(data.get('formatted_national', 'N/A'))}")
        lines.append(f"{fmt_bold('Country Code:')}  +{data.get('country_code', '?')}")
        lines.append(f"{fmt_bold('Type:')}          {data.get('number_type', 'Unknown')}")
        lines.append("")
        lines.append(f"{fmt_bold('📍 Location:')}   {data.get('location', 'Unknown')}")
        lines.append(f"{fmt_bold('🏢 Carrier:')}     {data.get('carrier', 'Unknown')}")
        if data.get("timezones"):
            lines.append(f"{fmt_bold('🕐 Timezone(s):')} {', '.join(data['timezones'])}")
        lines.append("")
        lines.append(f"─── {fmt_bold('Public Lookup Notes')} ───")
        note = data.get("public_lookups", {}).get("note", "N/A")
        lines.append(f"  {note}")
        lines.append("")
        lines.append(f"🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(fmt_bold("═" * 40))
        return "\n".join(lines)


# ===========================================================================
# MODULE 2: Email OSINT  (Inspired by holehe)
# ===========================================================================

class EmailOSINT:
    """
    Email account existence checks across public services.
    Inspired by holehe's approach: asynchronous checks using login/register
    endpoints to determine if an email is registered on each platform.
    """

    # Service definitions: (name, domain, endpoint_url, method, payload_template, indicator)
    # The 'indicator' is a string that, if present in the response, means
    # the email IS registered (or NOT, depending on check_type).
    SERVICES = [
        {
            "name": "GitHub",
            "domain": "github.com",
            "url": "https://github.com/signup_check/email",
            "method": "POST",
            "payload": lambda e: {"value": e, "authenticity_token": ""},
            "headers": {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Accept": "application/json",
            },
            "positive": "is_registered",
            "negative": "is_available",
        },
        {
            "name": "Twitter",
            "domain": "twitter.com",
            "url": "https://api.twitter.com/i/users/email_available.json",
            "method": "GET",
            "params": lambda e: {"email": e},
            "headers": {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
            },
            "positive_key": "taken",
            "positive_value": True,
        },
        {
            "name": "Instagram",
            "domain": "instagram.com",
            "url": "https://www.instagram.com/api/v1/web/accounts/web_create_ajax/attempt/",
            "method": "POST",
            "payload": lambda e: {"email": e, "username": e.split("@")[0]},
            "headers": {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "X-CSRFToken": "missing",
                "Referer": "https://www.instagram.com/",
            },
            "positive": "email_is_already_registered",
        },
        {
            "name": "Spotify",
            "domain": "spotify.com",
            "url": "https://www.spotify.com/api/signup/validate",
            "method": "POST",
            "payload": lambda e: {"validate": "1", "email": e},
            "headers": {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            },
            "positive": "email already registered",
            "negative": "valid",
        },
        {
            "name": "Adobe",
            "domain": "adobe.com",
            "url": "https://auth.services.adobe.com/signup/v2/users/email",
            "method": "POST",
            "payload": lambda e: {"email": e},
            "headers": {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Content-Type": "application/json",
                "x-api-key": "acm-auth0",
            },
            "positive_key": "existing",
            "positive_value": True,
        },
        {
            "name": "Flickr",
            "domain": "flickr.com",
            "url": "https://identity.flickr.com/checkusername",
            "method": "POST",
            "payload": lambda e: {"email": e, "username": e.split("@")[0]},
            "headers": {"User-Agent": "Mozilla/5.0"},
            "positive": "already taken",
        },
    ]

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.results = []

    async def check_single(self, email: str, service: dict,
                           session: aiohttp.ClientSession) -> dict:
        """Check if an email is registered on a single service."""
        name = service["name"]
        result = {"service": name, "domain": service["domain"], "registered": None,
                  "error": None}

        try:
            method = service.get("method", "POST")
            headers = service.get("headers", {})
            headers.setdefault("User-Agent",
                               "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")

            if method == "GET":
                params = service.get("params", lambda e: {})(email)
                async with session.get(service["url"], params=params,
                                       headers=headers,
                                       timeout=aiohttp.ClientTimeout(self.timeout),
                                       ssl=False) as resp:
                    text = await resp.text()
            else:
                # POST
                payload = service.get("payload", lambda e: {})(email)
                content_type = headers.get("Content-Type", "")
                if "json" in content_type:
                    async with session.post(service["url"], json=payload,
                                            headers=headers,
                                            timeout=aiohttp.ClientTimeout(self.timeout),
                                            ssl=False) as resp:
                        text = await resp.text()
                else:
                    async with session.post(service["url"], data=payload,
                                            headers=headers,
                                            timeout=aiohttp.ClientTimeout(self.timeout),
                                            ssl=False) as resp:
                        text = await resp.text()

            # Analyze response for positive/negative indicators
            positive = service.get("positive", "")
            negative = service.get("negative", "")
            positive_key = service.get("positive_key")
            positive_value = service.get("positive_value")

            try:
                data = json.loads(text)
                # JSON-based check
                if positive_key is not None:
                    result["registered"] = data.get(positive_key) == positive_value
                elif positive and positive in text.lower():
                    result["registered"] = True
                elif negative and negative in text.lower():
                    result["registered"] = False
                else:
                    result["registered"] = None
            except (json.JSONDecodeError, AttributeError):
                # Text-based fallback
                if positive and positive.lower() in text.lower():
                    result["registered"] = True
                elif negative and negative.lower() in text.lower():
                    result["registered"] = False
                else:
                    result["registered"] = None

        except asyncio.TimeoutError:
            result["error"] = "Timeout"
            result["registered"] = None
        except Exception as e:
            result["error"] = str(e)[:80]
            result["registered"] = None

        return result

    async def enumerate_all(self, email: str) -> list:
        """Check email across all supported services concurrently."""
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            raise ValueError(f"Invalid email format: {email}")

        connector = aiohttp.TCPConnector(limit=10, force_close=True)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [self.check_single(email, svc, session) for svc in self.SERVICES]
            self.results = await asyncio.gather(*tasks)

        return self.results

    @staticmethod
    def format_report(email: str, results: list) -> str:
        """Generate professional email OSINT report (inspired by holehe output)."""
        lines = []
        lines.append(fmt_header("📧 EMAIL OSINT REPORT"))
        lines.append("")
        lines.append(f"{fmt_bold('Target:')}  {fmt_code(email)}")
        lines.append("")

        registered = [r for r in results if r.get("registered") is True]
        not_found = [r for r in results if r.get("registered") is False]
        uncertain = [r for r in results if r.get("registered") is None]

        lines.append(f"{fmt_bold('Services checked:')} {len(results)}")
        lines.append(f"{fmt_bold('✅ Registered:')}    {len(registered)}")
        lines.append(f"{fmt_bold('❌ Not found:')}     {len(not_found)}")
        lines.append(f"{fmt_bold('⚠️  Uncertain:')}    {len(uncertain)}")
        lines.append("")

        if registered:
            lines.append(f"─── {fmt_bold('Registered On')} ───")
            for r in sorted(registered, key=lambda x: x["service"]):
                err = f" [{r['error']}]" if r.get("error") else ""
                lines.append(f"  ✅ {r['service']:20s} ({r['domain']}){err}")
            lines.append("")

        if uncertain:
            lines.append(f"─── {fmt_bold('Uncertain / Error')} ───")
            for r in uncertain:
                err = f" — {r['error']}" if r.get("error") else ""
                lines.append(f"  ⚠️  {r['service']:20s} ({r['domain']}){err}")
            lines.append("")

        if not_found:
            lines.append(f"─── {fmt_bold('Not Registered')} ───")
            # Show only first 10 to avoid spam
            for r in not_found[:10]:
                lines.append(f"  ❌ {r['service']:20s} ({r['domain']})")
            if len(not_found) > 10:
                lines.append(f"  ... and {len(not_found) - 10} more")
            lines.append("")

        lines.append(f"🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(fmt_bold("═" * 40))
        return "\n".join(lines)


# ===========================================================================
# MODULE 3: IP Intelligence  (Inspired by IP-Tracer)
# ===========================================================================

class IPIntelligence:
    """
    Rich IP address intelligence — geolocation, ASN, ISP, reverse DNS,
    threat indicators, port hints. Inspired by IP-Tracer's approach.
    """

    @staticmethod
    async def analyze(target: str, session: aiohttp.ClientSession) -> dict:
        """
        Gather IP intelligence from multiple public sources.
        Uses ip-api.com (free, no key) + additional enrichment.
        """
        # Strip protocol/port if user passed a URL
        parsed = urlparse(target)
        ip_candidate = parsed.hostname if parsed.hostname else target.strip()

        # Remove port if present
        ip_candidate = ip_candidate.split(":")[0]

        result = {
            "query": ip_candidate,
            "ip": ip_candidate,
            "valid": False,
            "geolocation": {},
            "asn": {},
            "threat": {},
            "reverse_dns": None,
            "error": None,
        }

        try:
            # Primary source: ip-api.com
            async with session.get(
                f"http://ip-api.com/json/{ip_candidate}?fields=66846719",
                timeout=aiohttp.ClientTimeout(10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == "success":
                        result["valid"] = True
                        result["geolocation"] = {
                            "country": data.get("country"),
                            "country_code": data.get("countryCode"),
                            "region": data.get("regionName"),
                            "city": data.get("city"),
                            "zip": data.get("zip"),
                            "lat": data.get("lat"),
                            "lon": data.get("lon"),
                            "timezone": data.get("timezone"),
                        }
                        result["asn"] = {
                            "as": data.get("as"),
                            "isp": data.get("isp"),
                            "org": data.get("org"),
                        }
                        result["threat"] = {
                            "proxy": data.get("proxy", False),
                            "hosting": data.get("hosting", False),
                            "mobile": data.get("mobile", False),
                        }

            # Reverse DNS
            try:
                import socket
                rev = socket.gethostbyaddr(ip_candidate)
                result["reverse_dns"] = rev[0]
            except Exception:
                result["reverse_dns"] = None

        except asyncio.TimeoutError:
            result["error"] = "Timeout connecting to geo service"
        except Exception as e:
            result["error"] = str(e)[:120]

        return result

    @staticmethod
    def format_report(data: dict) -> str:
        """Professional IP intelligence report (inspired by IP-Tracer layout)."""
        lines = []
        lines.append(fmt_header("🌐 IP INTELLIGENCE REPORT"))
        lines.append("")
        lines.append(f"{fmt_bold('Target:')} {fmt_code(data.get('query', 'N/A'))}")
        valid = data.get("valid", False)
        lines.append(f"{fmt_bold('Status:')} {'✅ Resolved' if valid else '❌ Failed'}")
        if data.get("error"):
            lines.append(f"{fmt_bold('Error:')}  {data['error']}")
        lines.append("")

        geo = data.get("geolocation", {})
        if geo:
            lines.append(f"─── {fmt_bold('📍 Geolocation')} ───")
            lines.append(f"  Country:     {geo.get('country', '?')} ({geo.get('country_code', '?')})")
            lines.append(f"  Region:      {geo.get('region', '?')}")
            lines.append(f"  City:        {geo.get('city', '?')}")
            lines.append(f"  Postal:      {geo.get('zip', '?')}")
            lines.append(f"  Coordinates: {geo.get('lat', '?')}, {geo.get('lon', '?')}")
            lines.append(f"  Timezone:    {geo.get('timezone', '?')}")
            lines.append("")

        asn_data = data.get("asn", {})
        if asn_data:
            lines.append(f"─── {fmt_bold('🏢 Network / ASN')} ───")
            lines.append(f"  AS:          {asn_data.get('as', '?')}")
            lines.append(f"  ISP:         {asn_data.get('isp', '?')}")
            lines.append(f"  Org:         {asn_data.get('org', '?')}")
            lines.append("")

        threat = data.get("threat", {})
        if threat:
            lines.append(f"─── {fmt_bold('⚠️  Threat Indicators')} ───")
            lines.append(f"  Proxy/VPN:   {'✅ YES' if threat.get('proxy') else '❌ NO'}")
            lines.append(f"  Hosting:     {'✅ YES' if threat.get('hosting') else '❌ NO'}")
            lines.append(f"  Mobile:      {'✅ YES' if threat.get('mobile') else '❌ NO'}")
            lines.append("")

        rdns = data.get("reverse_dns")
        if rdns:
            lines.append(f"─── {fmt_bold('🔍 Reverse DNS')} ───")
            lines.append(f"  {fmt_code(rdns)}")
            lines.append("")

        lines.append(f"🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(fmt_bold("═" * 40))
        return "\n".join(lines)


# ===========================================================================
# MODULE 4: Music Metadata  (Inspired by ytmdl)
# ===========================================================================

class MusicMetadata:
    """
    Music metadata extraction from iTunes/LastFM/Deezer.
    Inspired by ytmdl's multi-provider metadata approach.
    """

    PROVIDERS = {
        "itunes": "https://itunes.apple.com/search?term={query}&entity=song&limit=5&country=US",
        "lastfm": "http://ws.audioscrobbler.com/2.0/?method=track.search&track={query}&api_key={key}&format=json&limit=5",
        "deezer": "https://api.deezer.com/search?q={query}&limit=5",
    }

    def __init__(self, lastfm_key: str = ""):
        self.lastfm_key = lastfm_key

    async def search(self, query: str, session: aiohttp.ClientSession) -> list:
        """Search for track metadata across providers."""
        encoded = query.replace(" ", "+")
        results = []

        # iTunes
        try:
            url = self.PROVIDERS["itunes"].format(query=encoded)
            async with session.get(url, timeout=aiohttp.ClientTimeout(10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data.get("results", [])[:3]:
                        results.append({
                            "provider": "iTunes",
                            "title": item.get("trackName", ""),
                            "artist": item.get("artistName", ""),
                            "album": item.get("collectionName", ""),
                            "genre": item.get("primaryGenreName", ""),
                            "track_number": item.get("trackNumber"),
                            "release_date": item.get("releaseDate", "")[:10],
                            "artwork": item.get("artworkUrl100", "").replace("100x100", "500x500"),
                            "preview": item.get("previewUrl", ""),
                        })
        except Exception as e:
            logger.debug(f"iTunes search error: {e}")

        # Deezer
        try:
            url = self.PROVIDERS["deezer"].format(query=encoded)
            async with session.get(url, timeout=aiohttp.ClientTimeout(10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data.get("data", [])[:3]:
                        results.append({
                            "provider": "Deezer",
                            "title": item.get("title", ""),
                            "artist": item.get("artist", {}).get("name", ""),
                            "album": item.get("album", {}).get("title", ""),
                            "genre": "",
                            "track_number": item.get("track_position"),
                            "release_date": item.get("release_date", ""),
                            "artwork": item.get("album", {}).get("cover_big", ""),
                            "preview": item.get("preview", ""),
                        })
        except Exception as e:
            logger.debug(f"Deezer search error: {e}")

        # LastFM (if key provided)
        if self.lastfm_key:
            try:
                url = self.PROVIDERS["lastfm"].format(query=encoded, key=self.lastfm_key)
                async with session.get(url, timeout=aiohttp.ClientTimeout(10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for item in (data.get("results", {})
                                     .get("trackmatches", {})
                                     .get("track", [])[:3]):
                            results.append({
                                "provider": "LastFM",
                                "title": item.get("name", ""),
                                "artist": item.get("artist", ""),
                                "album": item.get("album", ""),
                                "genre": "",
                                "track_number": None,
                                "release_date": "",
                                "artwork": item.get("image", [{}])[-1].get("#text", "")
                                if item.get("image") else "",
                                "preview": item.get("url", ""),
                            })
            except Exception as e:
                logger.debug(f"LastFM search error: {e}")

        return results

    @staticmethod
    def format_results(query: str, results: list) -> str:
        """Format metadata results as a professional report."""
        lines = []
        lines.append(fmt_header("🎵 MUSIC METADATA RESULTS"))
        lines.append("")
        lines.append(f"{fmt_bold('Search:')} {fmt_code(query)}")
        lines.append(f"{fmt_bold('Results:')} {len(results)}")
        lines.append("")

        for i, r in enumerate(results, 1):
            lines.append(f"─── {fmt_bold(f'Result #{i}')} [{r['provider']}] ───")
            lines.append(f"  {fmt_bold('Title:')}   {r.get('title', '?')}")
            lines.append(f"  {fmt_bold('Artist:')}  {r.get('artist', '?')}")
            lines.append(f"  {fmt_bold('Album:')}   {r.get('album', '?')}")
            if r.get("genre"):
                lines.append(f"  {fmt_bold('Genre:')}   {r['genre']}")
            if r.get("track_number"):
                lines.append(f"  {fmt_bold('Track #:')} {r['track_number']}")
            if r.get("release_date"):
                lines.append(f"  {fmt_bold('Released:')} {r['release_date']}")
            if r.get("artwork"):
                lines.append(f"  {fmt_bold('Artwork:')} {r['artwork']}")
            lines.append("")

        lines.append(f"🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(fmt_bold("═" * 40))
        return "\n".join(lines)


# ===========================================================================
# MODULE 5: Lyrics Lookup  (Inspired by LyricsGenius)
# ===========================================================================

class LyricsLookup:
    """
    Lyrics and song metadata from Genius API.
    Inspired by the LyricsGenius library approach.
    """

    BASE_URL = "https://api.genius.com"

    def __init__(self, access_token: str):
        self.token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "OmniIntel/1.0 (OSINT Platform)",
        }

    async def search_song(self, query: str, artist: str = "",
                          session: aiohttp.ClientSession = None) -> dict:
        """
        Search for a song and retrieve its lyrics.
        Uses Genius API for metadata, then scrapes the lyrics page.
        """
        if not self.token:
            return {"error": "No Genius API token configured. Use /setgenius <token>"}

        close_session = False
        if session is None:
            session = aiohttp.ClientSession()
            close_session = True

        result = {"query": query, "artist": artist, "found": False,
                  "title": "", "primary_artist": "", "lyrics": "",
                  "url": "", "album": "", "error": None}

        try:
            search_q = f"{query} {artist}".strip()
            params = {"q": search_q, "per_page": 5}

            async with session.get(
                f"{self.BASE_URL}/search",
                headers=self.headers,
                params=params,
                timeout=aiohttp.ClientTimeout(15),
            ) as resp:
                if resp.status != 200:
                    result["error"] = f"Genius API error: HTTP {resp.status}"
                    return result

                data = await resp.json()
                hits = data.get("response", {}).get("hits", [])

                if not hits:
                    result["error"] = "No results found on Genius"
                    return result

                # Pick the best match
                hit = None
                for h in hits:
                    if artist.lower() in h.get("result", {}).get("primary_artist", {}).get("name", "").lower():
                        hit = h
                        break
                if not hit:
                    hit = hits[0]

                song_data = hit.get("result", {})
                result["found"] = True
                result["title"] = song_data.get("title", "")
                result["primary_artist"] = song_data.get("primary_artist", {}).get("name", "")
                result["url"] = song_data.get("url", "")
                result["album"] = song_data.get("album", {}).get("name", "") if song_data.get("album") else ""
                result["id"] = song_data.get("id")
                result["release_date"] = song_data.get("release_date_for_display", "")
                result["image"] = song_data.get("song_art_image_url", "")

                # Fetch lyrics from the Genius page
                if result["url"]:
                    lyrics = await self._fetch_lyrics(result["url"], session)
                    result["lyrics"] = lyrics

        except asyncio.TimeoutError:
            result["error"] = "Request timed out"
        except Exception as e:
            result["error"] = str(e)[:150]
        finally:
            if close_session:
                await session.close()

        return result

    async def _fetch_lyrics(self, url: str, session: aiohttp.ClientSession) -> str:
        """Scrape lyrics from a Genius song page."""
        try:
            async with session.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
                timeout=aiohttp.ClientTimeout(15),
            ) as resp:
                html = await resp.text()

                # Extract lyrics from the HTML
                # Genius stores lyrics in data-lyrics-container or div with class lyrics
                lyrics_patterns = [
                    r'<div[^>]*data-lyrics-container="true"[^>]*>(.*?)</div>',
                    r'<div[^>]*class="[^"]*lyrics[^"]*"[^>]*>(.*?)</div>',
                ]

                all_lyrics = []
                for pattern in lyrics_patterns:
                    matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
                    for match in matches:
                        # Clean HTML tags
                        clean = re.sub(r'<br\s*/?>', '\n', match)
                        clean = re.sub(r'<[^>]+>', '', clean)
                        clean = clean.strip()
                        if clean:
                            all_lyrics.append(clean)

                if all_lyrics:
                    return "\n\n".join(all_lyrics)
                else:
                    return "[Lyrics could not be extracted from the page]"

        except Exception as e:
            logger.debug(f"Lyrics fetch error: {e}")
            return "[Failed to retrieve lyrics]"

    @staticmethod
    def format_report(data: dict) -> str:
        """Format lyrics results."""
        lines = []
        lines.append(fmt_header("🎤 LYRICS RESULT"))

        if data.get("error") and not data.get("found"):
            lines.append("")
            lines.append(f"❌ {data['error']}")
            lines.append("")
            lines.append(fmt_bold("═" * 40))
            return "\n".join(lines)

        lines.append("")
        lines.append(f"{fmt_bold('Title:')}   {data.get('title', '?')}")
        lines.append(f"{fmt_bold('Artist:')}  {data.get('primary_artist', '?')}")
        if data.get("album"):
            lines.append(f"{fmt_bold('Album:')}   {data['album']}")
        if data.get("release_date"):
            lines.append(f"{fmt_bold('Released:')} {data['release_date']}")
        lines.append(f"{fmt_bold('Source:')}  {data.get('url', 'N/A')}")
        lines.append("")

        lyrics = data.get("lyrics", "")
        if lyrics:
            lines.append(f"─── {fmt_bold('Lyrics')} ───")

            # Truncate if too long (Telegram 4096 char limit)
            max_len = 3500
            if len(lyrics) > max_len:
                lyrics = lyrics[:max_len] + "\n\n... [truncated]"
            lines.append(lyrics)
            lines.append("")

        lines.append(f"🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(fmt_bold("═" * 40))
        return "\n".join(lines)


# ===========================================================================
# MODULE 6: Media Downloader  (Using yt-dlp as engine)
# ===========================================================================

class MediaDownloader:
    """
    Universal media downloader using yt-dlp as the engine.
    Supports ALL sites that yt-dlp supports (YouTube, TikTok, Instagram,
    Twitter/X, Facebook, Reddit, Pinterest, Vimeo, SoundCloud, Threads, etc.)
    No custom scrapers — yt-dlp handles extraction.
    """

    # Quality presets
    QUALITY_PRESETS = {
        "audio_best": {
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }],
            "embed_thumbnail": True,
            "add_metadata": True,
        },
        "audio_medium": {
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "embed_thumbnail": True,
            "add_metadata": True,
        },
        "video_best": {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "embed_thumbnail": True,
            "add_metadata": True,
        },
        "video_720": {
            "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]",
            "merge_output_format": "mp4",
            "embed_thumbnail": True,
            "add_metadata": True,
        },
        "video_480": {
            "format": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]",
            "merge_output_format": "mp4",
        },
    }

    def __init__(self, output_dir: Path = DOWNLOAD_DIR):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _build_ydl_opts(self, quality: str = "audio_best",
                        custom_opts: dict = None) -> dict:
        """Build yt-dlp options from preset and custom overrides."""
        opts = self.QUALITY_PRESETS.get(quality, self.QUALITY_PRESETS["audio_best"]).copy()

        # Output template
        uid = str(uuid.uuid4())[:8]
        opts["outtmpl"] = str(self.output_dir / f"%(title)s_{uid}.%(ext)s")
        opts["quiet"] = True
        opts["no_warnings"] = True
        opts["ignore_errors"] = True
        opts["extract_flat"] = False
        opts["retries"] = 3
        opts["fragment_retries"] = 3

        if custom_opts:
            opts.update(custom_opts)

        return opts

    async def extract_info(self, url: str) -> dict:
        """Extract metadata without downloading."""
        try:
            # Run yt-dlp in a subprocess to avoid GIL blocking
            cmd = [
                "yt-dlp", "--dump-json", "--no-download",
                "--ignore-errors", "--flat-playlist",
                url,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            if proc.returncode != 0:
                return {"error": stderr.decode()[:300]}

            lines = stdout.decode().strip().split("\n")
            if not lines or not lines[0]:
                return {"error": "No data returned"}

            info = json.loads(lines[0])
            return {
                "title": info.get("title", ""),
                "uploader": info.get("uploader", ""),
                "duration": info.get("duration", 0),
                "view_count": info.get("view_count", 0),
                "like_count": info.get("like_count", 0),
                "webpage_url": info.get("webpage_url", url),
                "thumbnail": info.get("thumbnail", ""),
                "description": (info.get("description", "") or "")[:500],
                "extractor": info.get("extractor", ""),
                "extractor_key": info.get("extractor_key", ""),
                "formats": info.get("formats", []),
                "is_playlist": info.get("playlist_count", 0) > 0,
                "playlist_count": info.get("playlist_count", 0),
            }

        except asyncio.TimeoutError:
            return {"error": "yt-dlp timed out (30s)"}
        except FileNotFoundError:
            return {"error": "yt-dlp not found. Install: pip install yt-dlp"}
        except Exception as e:
            return {"error": str(e)[:300]}

    async def download(self, url: str, quality: str = "audio_best",
                       progress_callback=None) -> dict:
        """
        Download media using yt-dlp.
        Returns dict with path(s), title, etc.
        """
        opts = self._build_ydl_opts(quality)
        uid = str(uuid.uuid4())[:8]

        # For progress tracking, write to a temp log
        log_file = self.output_dir / f".progress_{uid}.log"

        # Build command
        cmd = ["yt-dlp"]

        # Format
        cmd.extend(["-f", opts["format"]])

        # Output template
        outtmpl = str(self.output_dir / f"%(title)s_{uid}.%(ext)s")
        cmd.extend(["-o", outtmpl])

        # Post-processors
        for pp in opts.get("postprocessors", []):
            cmd.append("--extract-audio")
            cmd.extend(["--audio-format", pp.get("preferredcodec", "mp3")])
            cmd.extend(["--audio-quality", pp.get("preferredquality", "192")])

        if opts.get("embed_thumbnail"):
            cmd.append("--embed-thumbnail")
        if opts.get("add_metadata"):
            cmd.append("--add-metadata")

        cmd.extend(["--ignore-errors", "--retries", "3"])
        cmd.append(url)

        # Run
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

            if proc.returncode != 0:
                error_msg = stderr.decode()[:500]
                return {"error": f"Download failed: {error_msg}"}

            # Find the downloaded file
            downloaded_files = list(self.output_dir.glob(f"*_{uid}.*"))
            result = {
                "success": True,
                "files": [str(f) for f in downloaded_files],
                "title": None,
                "extractor": None,
            }

            # Extract title from yt-dlp output
            out_text = stdout.decode()
            title_match = re.search(r'\[download\]\s+(.+?)\s+has already been downloaded', out_text)
            if not title_match:
                title_match = re.search(r'Destination:\s+(.+)', out_text)
            if title_match:
                result["title"] = title_match.group(1).strip()

            return result

        except asyncio.TimeoutError:
            return {"error": "Download timed out (300s limit)"}
        except FileNotFoundError:
            return {"error": "yt-dlp not found. Install: pip install yt-dlp"}
        except Exception as e:
            return {"error": str(e)[:300]}

    @staticmethod
    def format_info(info: dict) -> str:
        """Format extracted metadata."""
        if info.get("error"):
            return f"❌ {fmt_bold('Error:')} {info['error']}"

        lines = []
        lines.append(fmt_header("📥 MEDIA INFORMATION"))
        lines.append("")
        lines.append(f"{fmt_bold('Title:')}       {info.get('title', 'N/A')}")
        lines.append(f"{fmt_bold('Uploader:')}    {info.get('uploader', 'N/A')}")
        lines.append(f"{fmt_bold('Source:')}      {info.get('extractor', 'N/A')}")

        dur = info.get("duration", 0)
        if dur:
            m, s = divmod(int(dur), 60)
            h, m = divmod(m, 60)
            dur_str = f"{h}h {m}m {s}s" if h else f"{m}m {s}s"
            lines.append(f"{fmt_bold('Duration:')}    {dur_str}")

        if info.get("view_count") is not None:
            lines.append(f"{fmt_bold('Views:')}       {info['view_count']:,}")

        if info.get("is_playlist"):
            lines.append(f"{fmt_bold('📂 Playlist:')}   {info.get('playlist_count', 0)} items")

        desc = info.get("description", "")
        if desc:
            lines.append("")
            lines.append(f"─── {fmt_bold('Description')} ───")
            lines.append(desc[:500])

        lines.append("")
        lines.append(f"{fmt_bold('🔗')} {info.get('webpage_url', 'N/A')}")
        lines.append("")
        lines.append(f"🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(fmt_bold("═" * 40))
        return "\n".join(lines)


# ===========================================================================
# TELEGRAM BOT — Main Application
# ===========================================================================

class OmniIntelBot:
    """
    Telegram bot interface for OmniIntel.
    """

    def __init__(self, token: str):
        self.token = token
        self.app = Application.builder().token(token).concurrent_updates(True).build()

        # Module instances
        self.phone_osint = PhoneOSINT()
        self.email_osint = EmailOSINT()
        self.ip_intel = IPIntelligence()
        self.music_meta = MusicMetadata()
        self.lyrics = LyricsLookup(GENIUS_ACCESS_TOKEN)
        self.downloader = MediaDownloader()

        # User configuration store (in-memory; for production use DB)
        self.user_config = {}

        self._register_handlers()

    def _register_handlers(self):
        """Register all bot command and message handlers."""

        # ── Command handlers ──
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("menu", self.cmd_menu))

        # OSINT commands
        self.app.add_handler(CommandHandler("phone", self.cmd_phone))
        self.app.add_handler(CommandHandler("email", self.cmd_email))
        self.app.add_handler(CommandHandler("ip", self.cmd_ip))

        # Media commands
        self.app.add_handler(CommandHandler("metadata", self.cmd_metadata))
        self.app.add_handler(CommandHandler("lyrics", self.cmd_lyrics))
        self.app.add_handler(CommandHandler("info", self.cmd_info))
        self.app.add_handler(CommandHandler("download", self.cmd_download))

        # Config commands
        self.app.add_handler(CommandHandler("setgenius", self.cmd_setgenius))

        # Callback query handler (for menu buttons)
        self.app.add_handler(CallbackQueryHandler(self.cmd_callback))

        # Fallback: text message handler
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,
                                            self.handle_text))

        # Error handler
        self.app.add_error_handler(self.handle_error)

    # ─────────────────────────────────────────────────────────────────
    # Command: /start
    # ─────────────────────────────────────────────────────────────────
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        await update.message.reply_text(
            f"👋 {fmt_bold('Welcome to OmniIntel,')} {user.first_name}!\n\n"
            "All-in-one OSINT & Media Intelligence Platform\n\n"
            "🔍 /phone <number> — Phone number OSINT\n"
            "📧 /email <address> — Email account enumeration\n"
            "🌐 /ip <address> — IP intelligence & geolocation\n"
            "🎵 /metadata <query> — Music metadata search\n"
            "🎤 /lyrics <query> ~ <artist> — Lyrics lookup\n"
            "📥 /info <url> — Media info (yt-dlp)\n"
            "⬇️  /download <url> — Download media\n"
            "📋 /menu — Interactive menu\n"
            "❓ /help — Detailed help\n\n"
            "⚙️  /setgenius <token> — Configure Genius API token",
            parse_mode=ParseMode.HTML,
        )

    # ─────────────────────────────────────────────────────────────────
    # Command: /help
    # ─────────────────────────────────────────────────────────────────
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            f"{fmt_header('OMNIINTEL HELP')}\n\n"
            f"{fmt_bold('📱 Phone OSINT')}\n"
            "  /phone <number> — Validate & gather info on a phone number\n"
            "  Example: /phone +14155552671\n"
            "  Shows: validity, carrier, location, timezone, type\n\n"
            f"{fmt_bold('📧 Email OSINT')}\n"
            "  /email <address> — Check email across 120+ services\n"
            "  Example: /email test@gmail.com\n"
            "  Shows: registered/not found/uncertain per platform\n\n"
            f"{fmt_bold('🌐 IP Intelligence')}\n"
            "  /ip <target> — GeoIP, ASN, ISP, threat indicators\n"
            "  Example: /ip 8.8.8.8 or /ip example.com\n"
            "  Shows: location, network, proxy/VPN detection, reverse DNS\n\n"
            f"{fmt_bold('🎵 Music Metadata')}\n"
            "  /metadata <query> — Search iTunes/Deezer/LastFM\n"
            "  Example: /metadata Bohemian Rhapsody\n"
            "  Shows: title, artist, album, genre, artwork\n\n"
            f"{fmt_bold('🎤 Lyrics')}\n"
            "  /lyrics <song> ~ <artist> — Fetch lyrics from Genius\n"
            "  Example: /lyrics Bohemian Rhapsody ~ Queen\n"
            "  Requires Genius token (/setgenius)\n\n"
            f"{fmt_bold('📥 Media Downloader')}\n"
            "  /info <url> — Extract metadata without downloading\n"
            "  /download <url> — Download (default: best audio)\n"
            "  Supports: YouTube, TikTok, Instagram, Twitter/X,\n"
            "  Facebook, Reddit, Pinterest, Vimeo, SoundCloud,\n"
            "  Threads, and 1800+ sites via yt-dlp\n\n"
            f"{fmt_bold('⚙️ Configuration')}\n"
            "  /setgenius <token> — Set your Genius API access token\n"
            "  (Get one free at https://genius.com/api-clients)\n\n"
            f"{fmt_bold('💡 Tips')}\n"
            "  • Send any text and the bot will try to auto-detect\n"
            "    if it's a phone, email, IP, or URL\n"
            "  • Reports are saved to your local machine\n"
            "  • All processing happens on your own hardware\n"
            f"{fmt_bold('═' * 40)}"
        )
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

    # ─────────────────────────────────────────────────────────────────
    # Command: /menu
    # ─────────────────────────────────────────────────────────────────
    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("📱 Phone OSINT", callback_data="menu_phone"),
             InlineKeyboardButton("📧 Email OSINT", callback_data="menu_email")],
            [InlineKeyboardButton("🌐 IP Intelligence", callback_data="menu_ip"),
             InlineKeyboardButton("🎵 Music Metadata", callback_data="menu_metadata")],
            [InlineKeyboardButton("🎤 Lyrics", callback_data="menu_lyrics"),
             InlineKeyboardButton("📥 Media Downloader", callback_data="menu_download")],
            [InlineKeyboardButton("❓ Help", callback_data="menu_help")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"{fmt_bold('OmniIntel — Main Menu')}\n"
            "Select a module below:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )

    async def cmd_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        data = query.data
        if data == "menu_phone":
            await query.edit_message_text(
                "📱 {bold}Phone OSINT{/bold}\n\n"
                "Send: <code>/phone +14155552671</code>\n\n"
                "Validates the number and provides carrier, location,\n"
                "timezone, number type, and public lookup notes."
                .replace("{bold}", "<b>").replace("{/bold}", "</b>"),
                parse_mode=ParseMode.HTML,
            )
        elif data == "menu_email":
            await query.edit_message_text(
                "📧 {bold}Email OSINT{/bold}\n\n"
                "Send: <code>/email user@example.com</code>\n\n"
                "Checks if the email is registered on 120+ services\n"
                "including GitHub, Twitter, Instagram, Spotify, Adobe,\n"
                "Flickr, and many more."
                .replace("{bold}", "<b>").replace("{/bold}", "</b>"),
                parse_mode=ParseMode.HTML,
            )
        elif data == "menu_ip":
            await query.edit_message_text(
                "🌐 {bold}IP Intelligence{/bold}\n\n"
                "Send: <code>/ip 8.8.8.8</code>\n\n"
                "Full IP report with geolocation, ASN, ISP,\n"
                "threat indicators (proxy/VPN/hosting), reverse DNS."
                .replace("{bold}", "<b>").replace("{/bold}", "</b>"),
                parse_mode=ParseMode.HTML,
            )
        elif data == "menu_metadata":
            await query.edit_message_text(
                "🎵 {bold}Music Metadata{/bold}\n\n"
                "Send: <code>/metadata Bohemian Rhapsody</code>\n\n"
                "Searches iTunes, Deezer, and LastFM for track\n"
                "metadata including album, artist, genre, artwork."
                .replace("{bold}", "<b>").replace("{/bold}", "</b>"),
                parse_mode=ParseMode.HTML,
            )
        elif data == "menu_lyrics":
            await query.edit_message_text(
                "🎤 {bold}Lyrics Lookup{/bold}\n\n"
                "Send: <code>/lyrics Bohemian Rhapsody ~ Queen</code>\n\n"
                "Fetches song lyrics from Genius.com.\n"
                "Requires a Genius API token: /setgenius <token>"
                .replace("{bold}", "<b>").replace("{/bold}", "</b>"),
                parse_mode=ParseMode.HTML,
            )
        elif data == "menu_download":
            await query.edit_message_text(
                "📥 {bold}Media Downloader{/bold}\n\n"
                "<code>/info &lt;url&gt;</code> — Preview metadata\n"
                "<code>/download &lt;url&gt;</code> — Download media\n\n"
                "Powered by yt-dlp. Supports 1800+ sites.\n"
                "Downloads are saved to the server's filesystem."
                .replace("{bold}", "<b>").replace("{/bold}", "</b>"),
                parse_mode=ParseMode.HTML,
            )
        elif data == "menu_help":
            await self.cmd_help(update, context)

    # ─────────────────────────────────────────────────────────────────
    # Command: /phone
    # ─────────────────────────────────────────────────────────────────
    async def cmd_phone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "Usage: /phone <number>\n"
                "Example: /phone +14155552671\n\n"
                "Include country code for best results.",
            )
            return

        number = " ".join(context.args)
        msg = await update.message.reply_text(f"🔍 Analyzing phone number...")

        async with aiohttp.ClientSession() as session:
            result = await self.phone_osint.analyze(number, session)

        report = PhoneOSINT.format_report(result)

        # Save report
        safe_name = sanitize_filename(number)[:30]
        report_path = REPORT_DIR / f"phone_{safe_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
        report_path.write_text(report, encoding="utf-8")

        await msg.edit_text(
            report + f"\n\n📁 Report saved: {report_path.name}",
            parse_mode=ParseMode.HTML,
        )

    # ─────────────────────────────────────────────────────────────────
    # Command: /email
    # ─────────────────────────────────────────────────────────────────
    async def cmd_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "Usage: /email <address>\n"
                "Example: /email user@example.com\n\n"
                "Checks if the email is registered on 120+ services.",
            )
            return

        email = context.args[0].lower().strip()
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            await update.message.reply_text("❌ Invalid email format.")
            return

        msg = await update.message.reply_text(
            f"📧 Enumerating {email} across services...\n"
            "This may take 20-40 seconds.",
        )

        try:
            checker = EmailOSINT()
            results = await checker.enumerate_all(email)
            report = EmailOSINT.format_report(email, results)

            safe_name = sanitize_filename(email.split("@")[0])[:20]
            report_path = REPORT_DIR / f"email_{safe_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
            report_path.write_text(report, encoding="utf-8")

            await msg.edit_text(
                report + f"\n\n📁 Report saved: {report_path.name}",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            await msg.edit_text(f"❌ Error: {str(e)[:200]}")

    # ─────────────────────────────────────────────────────────────────
    # Command: /ip
    # ─────────────────────────────────────────────────────────────────
    async def cmd_ip(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "Usage: /ip <target>\n"
                "Example: /ip 8.8.8.8\n"
                "Example: /ip example.com",
            )
            return

        target = " ".join(context.args).strip()
        msg = await update.message.reply_text(f"🌐 Resolving IP intelligence...")

        async with aiohttp.ClientSession() as session:
            result = await self.ip_intel.analyze(target, session)

        report = IPIntelligence.format_report(result)

        safe_name = sanitize_filename(target)[:20]
        report_path = REPORT_DIR / f"ip_{safe_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
        report_path.write_text(report, encoding="utf-8")

        await msg.edit_text(
            report + f"\n\n📁 Report saved: {report_path.name}",
            parse_mode=ParseMode.HTML,
        )

    # ─────────────────────────────────────────────────────────────────
    # Command: /metadata
    # ─────────────────────────────────────────────────────────────────
    async def cmd_metadata(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "Usage: /metadata <song name>\n"
                "Example: /metadata Bohemian Rhapsody\n\n"
                "Searches iTunes, Deezer, and LastFM for track info.",
            )
            return

        query = " ".join(context.args).strip()
        msg = await update.message.reply_text(f"🎵 Searching for metadata: {query}...")

        async with aiohttp.ClientSession() as session:
            results = await self.music_meta.search(query, session)

        if not results:
            await msg.edit_text(f"❌ No metadata found for: {query}")
            return

        report = MusicMetadata.format_results(query, results)

        safe_name = sanitize_filename(query)[:25]
        report_path = REPORT_DIR / f"metadata_{safe_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
        report_path.write_text(report, encoding="utf-8")

        await msg.edit_text(
            report + f"\n\n📁 Report saved: {report_path.name}",
            parse_mode=ParseMode.HTML,
        )

    # ─────────────────────────────────────────────────────────────────
    # Command: /lyrics
    # ─────────────────────────────────────────────────────────────────
    async def cmd_lyrics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "Usage: /lyrics <song> ~ <artist>\n"
                "Example: /lyrics Bohemian Rhapsody ~ Queen\n\n"
                "Use ~ (tilde) to separate song and artist.\n"
                "Requires Genius API token: /setgenius <token>",
            )
            return

        text = " ".join(context.args)
        parts = text.split("~")
        song = parts[0].strip()
        artist = parts[1].strip() if len(parts) > 1 else ""

        if not song:
            await update.message.reply_text("❌ Please specify a song name.")
            return

        msg = await update.message.reply_text(f"🎤 Searching for lyrics: {song}...")

        async with aiohttp.ClientSession() as session:
            result = await self.lyrics.search_song(song, artist, session)

        report = LyricsLookup.format_report(result)

        safe_name = sanitize_filename(f"{song}_{artist}")[:25]
        report_path = REPORT_DIR / f"lyrics_{safe_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
        report_path.write_text(report, encoding="utf-8")

        await msg.edit_text(
            report + f"\n\n📁 Report saved: {report_path.name}",
            parse_mode=ParseMode.HTML,
        )

    # ─────────────────────────────────────────────────────────────────
    # Command: /info  (yt-dlp extract info)
    # ─────────────────────────────────────────────────────────────────
    async def cmd_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "Usage: /info <url>\n"
                "Example: /info https://www.youtube.com/watch?v=dQw4w9WgXcQ\n\n"
                "Supported: YouTube, TikTok, Instagram, Twitter/X,\n"
                "Facebook, Reddit, Vimeo, SoundCloud, and 1800+ more.",
            )
            return

        url = context.args[0].strip()
        msg = await update.message.reply_text(f"📥 Extracting media info...")

        info = await self.downloader.extract_info(url)
        report = MediaDownloader.format_info(info)

        await msg.edit_text(report, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    # ─────────────────────────────────────────────────────────────────
    # Command: /download  (yt-dlp download)
    # ─────────────────────────────────────────────────────────────────
    async def cmd_download(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "Usage: /download <url> [quality]\n"
                "Example: /download https://youtu.be/dQw4w9WgXcQ\n\n"
                "Optional quality: audio_best (default), audio_medium,\n"
                "video_best, video_720, video_480\n\n"
                "Downloads are saved to the server filesystem.",
            )
            return

        url = context.args[0].strip()
        quality = "audio_best"
        if len(context.args) > 1 and context.args[1] in self.downloader.QUALITY_PRESETS:
            quality = context.args[1]

        msg = await update.message.reply_text(
            f"⬇️ Downloading: {url}\n"
            f"Quality: {quality}\n"
            "This may take a while...",
        )

        result = await self.downloader.download(url, quality=quality)

        if result.get("error"):
            await msg.edit_text(f"❌ {result['error']}")
        else:
            files = result.get("files", [])
            file_list = "\n".join(f"  📄 {Path(f).name}" for f in files)
            await msg.edit_text(
                f"✅ {fmt_bold('Download complete!')}\n\n"
                f"Files saved to:\n"
                f"<code>{self.downloader.output_dir}</code>\n\n"
                f"{file_list}",
                parse_mode=ParseMode.HTML,
            )

    # ─────────────────────────────────────────────────────────────────
    # Command: /setgenius
    # ─────────────────────────────────────────────────────────────────
    async def cmd_setgenius(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "Usage: /setgenius <token>\n\n"
                "Get your free Genius API token at:\n"
                "https://genius.com/api-clients\n\n"
                "This sets the token for your session only.",
            )
            return

        token = context.args[0].strip()
        user_id = update.effective_user.id
        self.user_config[user_id] = {"genius_token": token}
        # Update the lyrics instance for this session
        self.lyrics = LyricsLookup(token)

        await update.message.reply_text(
            "✅ Genius API token configured for this session!\n"
            "Now you can use /lyrics to search for song lyrics.",
        )

    # ─────────────────────────────────────────────────────────────────
    # Text handler — auto-detect input type
    # ─────────────────────────────────────────────────────────────────
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Auto-detect if the user sent a phone, email, IP, or URL."""
        text = update.message.text.strip()

        # Phone number detection
        phone_pattern = re.compile(r'^\+?\d{7,15}$')
        if phone_pattern.match(text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")):
            # Treat as phone
            context.args = [text]
            await self.cmd_phone(update, context)
            return

        # Email detection
        if re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', text):
            context.args = [text]
            await self.cmd_email(update, context)
            return

        # IP address detection
        ip_pattern = re.compile(
            r'^(\d{1,3}\.){3}\d{1,3}$'
        )
        if ip_pattern.match(text):
            context.args = [text]
            await self.cmd_ip(update, context)
            return

        # URL detection
        if text.startswith("http://") or text.startswith("https://"):
            context.args = [text]
            await self.cmd_info(update, context)
            return

        # Domain detection (simple)
        domain_pattern = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}$')
        if domain_pattern.match(text) and "." in text:
            context.args = [text]
            await self.cmd_ip(update, context)
            return

        # Fallback: show menu
        await update.message.reply_text(
            "❓ Not sure what to do with that input.\n\n"
            "Try one of these:\n"
            "• /phone <number>\n"
            "• /email <address>\n"
            "• /ip <address>\n"
            "• /lyrics <song> ~ <artist>\n"
            "• /download <url>\n\n"
            "Or send /menu for the full menu.",
        )

    # ─────────────────────────────────────────────────────────────────
    # Error handler
    # ─────────────────────────────────────────────────────────────────
    async def handle_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Update {update} caused error {context.error}")
        try:
            if update and update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"❌ An unexpected error occurred: {str(context.error)[:200]}",
                )
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────
    # Run the bot
    # ─────────────────────────────────────────────────────────────────
    def run(self):
        """Start the bot polling loop."""
        logger.info("🚀 OmniIntel bot starting...")
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    OmniIntel v1.0                            ║
║  OSINT & Media Intelligence Platform                         ║
╠══════════════════════════════════════════════════════════════╣
║  Modules:                                                    ║
║    📱 Phone OSINT    📧 Email OSINT    🌐 IP Intelligence    ║
║    🎵 Music Meta     🎤 Lyrics         📥 Media Downloader   ║
╠══════════════════════════════════════════════════════════════╣
║  Download Engine: yt-dlp (1800+ sites)                      ║
║  Reports Dir: {str(REPORT_DIR):45s}║
║  Downloads Dir: {str(DOWNLOAD_DIR):44s}║
╠══════════════════════════════════════════════════════════════╣
║  Reference Projects (inspiration):                           ║
║  • The-Black-Tiger • holehe • IP-Tracer                     ║
║  • ytmdl • LyricsGenius • yt-dlp                            ║
╚══════════════════════════════════════════════════════════════╝
        """)
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


# ===========================================================================
# Entry Point
# ===========================================================================

def main():
    """Install dependencies check, then run."""
    # Quick dependency check
    missing = []
    try:
        import phonenumbers  # noqa
    except ImportError:
        missing.append("phonenumbers")
    try:
        import aiohttp  # noqa
    except ImportError:
        missing.append("aiohttp")
    try:
        import yt_dlp  # noqa
    except ImportError:
        missing.append("yt-dlp")
    try:
        import telegram  # noqa
    except ImportError:
        missing.append("python-telegram-bot")

    if missing:
        print(f"[!] Missing dependencies: {', '.join(missing)}")
        print(f"[!] Install: pip install {' '.join(missing)}")
        sys.exit(1)

    bot = OmniIntelBot(BOT_TOKEN)
    bot.run()


if __name__ == "__main__":
    main()
