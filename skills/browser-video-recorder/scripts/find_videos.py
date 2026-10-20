"""One link -> many videos: find the video pages a page links to, list them for the user to confirm,
then add the chosen ones to videos.json.

  python find_videos.py --config <work>\\videos.json --url "https://site/course/123"   # find + list
  python find_videos.py --config <work>\\videos.json --url "..." --group 2            # use another link group
  python find_videos.py --config <work>\\videos.json --add 1,3-5                      # add picks ("all" = all)

How it finds them: it opens the page in the recorder's own browser profile (so signed-in course pages
work), collects every link (also inside web components) and every embedded player, and groups the links
by URL shape - /lesson/1201, /lesson/1202 ... are one group. The group that looks most like a list
of videos is opened item by item to check that each really has a video, and how long it is. A page
without a video but with a link to a known recording host (Zoom replay, Vimeo, ...) or a "watch
recording" link is followed one step. Nothing is recorded or downloaded here; the result is a list in
<work>\\found.json that the user confirms. Run it while the recorder is NOT running (same profile).
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_config, read_json, write_json  # noqa: E402
from record_videos import BOT_CHECK_JS, PICK_JS, SIGNIN_JS, launch, wait_for_signin  # noqa: E402

# Pages and players that hold one video each. Used to rank link groups and to follow one hop from a
# lesson page to its recording.
VIDEO_HOST = re.compile(
    r"zoom\.us/rec/(play|share)|vimeo\.com/(video/)?\d+|youtube\.com/(watch|embed)|youtu\.be/|dailymotion\.com/(video|embed)"
    r"|archive\.org/(details|embed)/|/videos/(watch|embed)/|/w/[\w-]{10,}|loom\.com/(share|embed)|wistia\.(com|net)/(medias|embed)"
    r"|twitch\.tv/videos/|ted\.com/talks/|media\.ccc\.de/v/|bilibili\.com/video/|player\.mux\.com/|kaltura|panopto\.|"
    r"teams\.microsoft\.com/.*recording|sharepoint\.com/.*stream|stream\.microsoft\.com|vidyard\.com/watch|brightcove",
    re.I)
VIDEO_FILE = re.compile(r"\.(mp4|m4v|mov|mkv|webm|avi|wmv|mpe?g|ogv)(\?|$)", re.I)
ITEMISH = re.compile(r"lesson|lecture|episode|session|class|module|chapter|part\b|talk|recording|replay"
                     r"|week|day\b|unit|\b\d{1,3}\b|שיעור|פרק|הקלטה|מפגש|צפייה|הרצאה", re.I)
WATCH_LINK = re.compile(r"recording|replay|watch|play video|view video|הקלט|צפ(י|ה)|לצפייה", re.I)
SKIP_URL = re.compile(r"^mailto:|^javascript:|/(login|logout|signin|sign-in|signup|register|cart|checkout|account|"
                      r"privacy|terms|cookie|help|support|contact|about|search|tag|tags|category|categories)(/|$|\?)"
                      r"|facebook\.com/sharer|twitter\.com/intent|x\.com/intent|linkedin\.com/share|whatsapp|"
                      r"\.(pdf|zip|docx?|pptx?|xlsx?|png|jpe?g|gif|svg)(\?|$)", re.I)

# every link once, in page order; all texts of anchors pointing at the same page are kept (a thumbnail link
# often carries only the duration, the title link the title)
LINKS_JS = r"""() => {
  const out = [], byUrl = new Map();
  const NAV = 'nav, header, footer, [role=navigation], [role=menu], [role=menubar], [role=banner], [role=contentinfo]';
  const inNav = el => { for (let e = el; e; e = e.parentElement || (e.getRootNode() && e.getRootNode().host) || null)
    if (e.matches && (e.matches(NAV) || /^(nav|header|footer)$|-nav$|-header$|-footer$|topnav|navbar|menu/i
        .test(e.tagName))) return true; return false; };
  const walk = root => {
    for (const a of root.querySelectorAll('a[href]')) {
      const url = a.href.split('#')[0];
      if (!/^https?:/.test(url)) continue;
      const r = a.getBoundingClientRect();
      const text = (a.innerText || a.getAttribute('aria-label') || a.title || '').replace(/\s+/g, ' ').trim().slice(0, 150);
      const vis = r.width > 0 && r.height > 0, nav = inNav(a);
      let ln = byUrl.get(url);
      if (!ln) { ln = {url, texts: [], visible: false, nav: true, thumb: false}; byUrl.set(url, ln); out.push(ln); }
      ln.thumb = ln.thumb || !!a.querySelector('img, picture, video');
      if (text && !ln.texts.includes(text)) ln.texts.push(text);
      ln.visible = ln.visible || vis; ln.nav = ln.nav && nav;
    }
    for (const el of root.querySelectorAll('*')) if (el.shadowRoot) walk(el.shadowRoot);
  };
  walk(document);
  for (const ln of out) ln.text = ln.texts.join(' | ');
  return out; }"""


def shape(segment):
    """URL path segment -> its shape: numbers and id-like tokens become placeholders."""
    if re.fullmatch(r"\d+", segment):
        return "#"
    if len(segment) >= 8 and re.search(r"\d", segment) and re.fullmatch(r"[\w-]+", segment):
        return "*"
    return segment


def group_key(url):
    """Links to sibling items share this key: same host, same parent path shape, same depth, same query keys,
    and the same kind of last segment (the item): a number (#), an id-like code (*) or a word/slug. That keeps
    vimeo.com/1235421735 apart from vimeo.com/watch, and archive.org's films apart from its menu."""
    u = urlparse(url)
    segs = [s for s in u.path.split("/") if s]
    parent = "/".join(shape(s) for s in segs[:-1])
    last = shape(segs[-1]) if segs else ""
    kind = last if last in ("#", "*") else "slug"
    q = ",".join(sorted(k for k, _ in parse_qsl(u.query)))
    return f"{u.netloc.lower()}/{parent}/<{kind}>" + (f"?{q}" if q else "")


def is_file(url):
    """A link to a file (anything with an extension that isn't a web page), or an archive.org-style /download/."""
    path = urlparse(url).path
    m = re.search(r"\.(\w{1,6})$", path.rstrip("/").rsplit("/", 1)[-1])
    return "/download/" in path or bool(m and m.group(1).lower() not in ("html", "htm", "php", "asp", "aspx", "jsp", "shtml"))


def rank_groups(links, page_url):
    groups = {}
    for ln in links:
        if SKIP_URL.search(ln["url"]) or ln["url"].rstrip("/") == page_url.rstrip("/") or is_file(ln["url"]):
            continue  # (links to files - videos, subtitles, data - are downloads, not a list of video pages)
        groups.setdefault(group_key(ln["url"]), []).append(ln)
    ranked = []
    for key, items in groups.items():
        content = [i for i in items if not i["nav"]]
        if content and len(content) < len(items):  # same URL shape in the site menu and in the list: keep the list
            items = content
        n = len(items)
        hosts = sum(bool(VIDEO_HOST.search(i["url"])) for i in items)
        if n < 2 and not hosts:
            continue
        itemish = sum(bool(ITEMISH.search(i["text"] + " " + i["url"])) for i in items) / n
        nav = sum(i["nav"] for i in items) / n
        visible = sum(i["visible"] for i in items) / n
        # video lists usually show a thumbnail and/or a duration per item; menus don't
        thumbs = sum(bool(i.get("thumb")) for i in items) / n
        durations = sum(any(DURATION.search(t) for t in i.get("texts", [])) for i in items) / n
        score = (n * (0.5 + itemish) * (2 if hosts else 1) * (0.2 if nav > 0.5 else 1) * (0.5 + visible / 2)
                 * (1 + thumbs / 2) * (1 + durations / 2))
        ranked.append({"key": key, "score": round(score, 2), "count": n, "links": items})
    ranked.sort(key=lambda g: -g["score"])
    return ranked


def wait_ready(page, seconds=8):
    """Let the page settle; an automatic browser check is given time to clear by itself (never clicked)."""
    end = time.time() + 45
    while time.time() < end:
        try:
            if not page.evaluate(BOT_CHECK_JS):
                break
        except Exception:
            pass
        time.sleep(2)
    else:
        return "bot check"
    time.sleep(seconds)
    return None


def video_on(page, wait_s=15):
    """Best video across frames as PICK_JS sees it (no clicking): (frame, info) or None."""
    end = time.time() + wait_s
    best = None
    while time.time() < end:
        best = None
        for fr in page.frames:
            try:
                info = fr.evaluate(PICK_JS)
            except Exception:
                continue
            if info and (best is None or info["key"] > best[1]["key"]):
                best = (fr, info)
        if best and best[1]["d"] and best[1]["d"] > 0:
            return best
        time.sleep(1.5)
    return best


def probe(page, url, follow=True):
    """What is at url: {'status', 'minutes', 'title', 'record_url'}."""
    res = {"status": "", "minutes": None, "title": "", "record_url": url}
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    except Exception as e:
        res["status"] = f"could not open ({str(e).splitlines()[0][:80]})"
        return res
    if wait_ready(page, 4):
        res["status"] = "bot check - the user can pass it in --login mode"
        return res
    wait_for_signin(page, url, say=say)
    res["title"] = headline(page)
    try:  # the site's own download offer comes first: instant, original quality, no real-time recording
        res["download_url"] = best_download(page.evaluate(DOWNLOADS_JS))
    except Exception:
        res["download_url"] = None
    found = video_on(page)
    if found and found[1]["drm"]:
        res["status"] = "encrypted (DRM) - not recordable"
    elif found and found[1]["d"] == float("inf"):
        res["status"] = "live stream - not supported"
    elif found and found[1]["d"] and found[1]["d"] == found[1]["d"]:  # (NaN != NaN: length not known yet)
        res["status"], res["minutes"] = "video", round(found[1]["d"] / 60, 1)
        if found[0] != page.main_frame and VIDEO_HOST.search(found[0].url):
            res["status"] += " (embedded player)"
    elif found:
        res["status"] = "video player (length shows once it plays)"
    elif follow:
        # lesson page -> its recording: a link to a known video host, or one clear "watch recording" link
        links = [ln for ln in page.evaluate(LINKS_JS) if ln["visible"]]
        hops = [ln for ln in links if VIDEO_HOST.search(ln["url"])] or \
               [ln for ln in links if WATCH_LINK.search(ln["text"]) and not ln["nav"]]
        hops = list({ln["url"]: ln for ln in hops}.values())
        if len(hops) == 1:
            sub = probe(page, hops[0]["url"], follow=False)
            sub["status"] = f"{sub['status']} - via '{hops[0]['text'][:40]}'"
            sub["title"] = res["title"] or sub["title"]
            return sub
        res["status"] = "no video found" + (f" ({len(hops)} possible recording links)" if hops else "")
    else:
        res["status"] = "no video found"
    if not found and page.evaluate(SIGNIN_JS):
        res["status"] = "sign-in page - not signed in"
    if res.get("download_url") and not res["status"].startswith(("encrypted", "sign-in")):
        res["status"] = "DOWNLOAD offered by the site; " + res["status"]
    return res


# The site's own download offer: a link to a video file that the page shows (or marks as a download:
# download attribute, "Download" text/label, a /download/ address). Never a player's stream address - a site that
# offers no download is recorded by playing, not by pulling its stream.
DOWNLOADS_JS = r"""() => {
  const out = [], seen = new Set(), vid = /\.(mp4|m4v|mov|mkv|webm|avi|wmv|mpe?g|ogv)(\?|$)/i;
  const walk = root => { for (const a of root.querySelectorAll('a[href]')) {
      const label = ((a.innerText || '') + ' ' + (a.getAttribute('aria-label') || '') + ' ' + (a.title || '') + ' ' +
                     (a.closest('[class*=download i], [id*=download i], section, li, details') || {className: ''}).className)
                    .replace(/\s+/g, ' ').trim();
      const r = a.getBoundingClientRect();
      // a link the site shows to a video file IS an offer (a player's hidden stream address never is)
      const offered = a.hasAttribute('download') || /download|הורד/i.test(label) || /\/download\//i.test(a.href)
                      || (r.width > 0 && r.height > 0)
                      || /\S\.(mp4|m4v|mov|mkv|webm|avi|wmv|mpe?g|ogv)/i.test(a.innerText || '');  // file list in a menu
      if (offered && vid.test(a.href) && !seen.has(a.href)) { seen.add(a.href); out.push({url: a.href, text: label.slice(0, 80)}); } }
    for (const el of root.querySelectorAll('*')) if (el.shadowRoot) walk(el.shadowRoot); };
  walk(document); return out; }"""


def best_download(offers):
    """Pick one offered file: mp4 first, then the highest quality the labels/addresses mention."""
    if not offers:
        return None

    def score(o):
        s = (o["url"] + " " + o["text"]).lower()
        q = max([int(n) for n in re.findall(r"(\d{3,4})p", s)] + [1080 if re.search(r"\bhd\b|high", s) else 0]
                + [-1 if re.search(r"\blow|\bsd\b|small|preview|sample|trailer", s) else 0])
        # the best version up to 1080p first (what a recording would give anyway), bigger ones after that
        return (".mp4" in s, 0 < q <= 1080, q)
    return max(offers, key=score)["url"]


def headline(page):
    """The page's own title for its content: the share title (og:title), else the main heading, else the
    tab title. Tab titles often start with the site's name ("NASA SVS | Moon Phase ...")."""
    cands = safe_eval(page, """() => { const m = document.querySelector('meta[property="og:title"], meta[name="twitter:title"]');
      const h = document.querySelector('h1'); return [(m && m.content) || '', (h && h.innerText) || '']; }""", ["", ""])
    cands = [re.sub(r"\s+", " ", c or "").strip() for c in cands]
    cands = [c for c in cands if len(c) >= 4]
    tab = page.title()
    # the real title nearly always appears in the tab title too; a share title can be just the site's name
    for c in cands:
        if c.lower() in tab.lower():
            return c
    return cands[0] if cands else tab


def safe_eval(page, js, default):
    try:
        return page.evaluate(js)
    except Exception:
        return default


def say(msg):
    print(msg, flush=True)  # the agent or GUI shows these lines to the user as they come


DURATION = re.compile(r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})")


def link_title_and_minutes(ln):
    """(title, minutes) from a link's texts: a bare "1:02:03" / "05:56" text is the length, the longest other
    text the title."""
    minutes, titles = None, []
    for t in ln.get("texts") or [ln.get("text", "")]:
        m = DURATION.fullmatch(t.strip())
        if m:
            h, mi, se = (int(x or 0) for x in m.groups())
            minutes = round((h * 3600 + mi * 60 + se) / 60, 1)
        elif len(t) >= 4 and not WATCH_LINK.fullmatch(t):
            titles.append(DURATION.sub("", t).strip(" |-"))
    return (min(titles, key=len) if titles else ""), minutes


def page_title(title):
    """'Lesson 3 | Course | Site' -> 'Lesson 3'"""
    first = re.split(r"\s+[|–—:-]\s+", title or "")[0].strip()  # (" : " = archive.org; "Part 1: X" stays)
    return first if len(first) >= 4 else (title or "").strip()


def clean_name(text, n):
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .-")[:90]
    return f"{n:02d} - {text or 'Video'}"


def login(cfg, url):
    """The universal sign-in: open the link in the recorder's own browser profile, the user signs in
    (we never type anything), closes the window, and the session stays in the profile."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = launch(p, cfg, fullscreen=False, muted=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=90_000)
        say("SIGN IN: sign in to the site in the browser window that opened, open the course page to check "
            "you can see it, then CLOSE that browser window. Finding starts after that.")
        # wait until every window/tab of this browser is closed - sign-in flows open popups and replace or
        # close the first tab, so waiting for that one tab's "close" can hang forever (seen with Microsoft 365)
        while True:
            try:
                open_pages = [pg for pg in ctx.pages if not pg.is_closed()]
                if not open_pages:
                    break
                open_pages[0].wait_for_timeout(1000)  # (lets Playwright process close events meanwhile)
            except Exception:  # browser already gone
                break
        try:
            ctx.close()
        except Exception:
            pass


def find(cfg, url, group_index, max_items):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            ctx = launch(p, cfg, fullscreen=False, muted=True)
        except Exception as e:
            sys.exit(f"Could not open the browser profile ({str(e).splitlines()[0][:120]}).\n"
                     "Is the recorder (or another finder) running? Wait until it finishes.")
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        resp = page.goto(url, wait_until="domcontentloaded", timeout=90_000)
        if resp and resp.status >= 400 and resp.status not in (401, 403):  # 401/403 may be a sign-in or check page
            sys.exit(f"The page answered HTTP {resp.status} (not found / gone). Check the link.")
        if wait_ready(page):
            sys.exit("The page shows a bot check. Pass it yourself with record_videos.py --login, then retry.")
        if wait_for_signin(page, url, say=say):
            wait_ready(page)
        for _ in range(3):  # lazy lists load as you scroll
            page.mouse.wheel(0, 4000)
            time.sleep(1.5)
        links = []
        for fr in page.frames:
            try:
                links += fr.evaluate(LINKS_JS)
            except Exception:
                pass
        groups = rank_groups(links, page.url)
        # players embedded right on this page (several lessons on one page)
        embeds = [{"url": fr.url, "text": "", "visible": True, "nav": False} for fr in page.frames[1:]
                  if VIDEO_HOST.search(fr.url)]
        if len(embeds) >= 2:
            groups.insert(0, {"key": "players embedded on this page", "score": 999, "count": len(embeds),
                              "links": embeds})
        # a cloud storage folder (OneDrive, Google Drive, Dropbox, Box...) lists video FILES, not links: those
        # should be downloaded (official, instant, original quality), not recorded in real time
        files = safe_eval(page, r"""() => { const re = /\S{3,}\.(mp4|m4v|mov|mkv|webm|avi|wmv|flv|mpe?g)$/i, names = new Set();
          const walk = root => { for (const el of root.querySelectorAll('*')) { if (el.shadowRoot) walk(el.shadowRoot);
            const t = (el.children.length ? (el.getAttribute('aria-label') || el.title || '') : (el.textContent || '')).trim();
            if (re.test(t) && t.length < 200) names.add(t); } };
          walk(document); return [...names]; }""", [])
        if files:
            say(f"This page lists {len(files)} video FILE(S), e.g. {files[0][:80]}. It looks like a cloud storage "
                "folder: download the files with the site's Download button (or its sync app) - instant and in "
                "original quality, no recording needed. If the share is view-only, open each file and use its "
                "address as a video URL instead.\n")
        own = video_on(page, 5)
        say(f"Page: {page.title()}  ({page.url[:90]}; {len(links)} links)\n")
        parent = lambda x: urlparse(x).path.rstrip("/").rsplit("/", 1)[0]  # noqa: E731
        # sent elsewhere AND nothing useful there (shared links like OneDrive's always redirect, harmlessly)
        found_any = files or (own and own[1]["d"]) or any(g["score"] >= 4 for g in groups[:1])
        if parent(page.url) != parent(url) and not found_any:
            say(f"NOTE: the site opened {page.url} instead of the link you gave. If the videos need an account, "
                "you're probably signed out: rerun with --login and sign in first.\n")
        if groups:
            print("Link groups found (best first):")
            for i, g in enumerate(groups[:6], 1):
                ex = "; ".join((ln["text"] or ln["url"])[:40] for ln in g["links"][:3])
                print(f"  {i}. {g['count']} links  [{g['key']}]  e.g. {ex}")
            print()
        items = []
        if own and own[1]["d"] == own[1]["d"] and own[1]["d"] and (not groups or own[1]["d"] > 60):
            dl = best_download(page.evaluate(DOWNLOADS_JS))
            items.append({"title": page_title(headline(page)), "page_url": page.url, "record_url": page.url,
                          "status": ("DOWNLOAD offered by the site; video" if dl else "video"), "download_url": dl,
                          "minutes": round(own[1]["d"] / 60, 1) if own[1]["d"] != float("inf") else None})
        if groups:
            g = groups[min(group_index, len(groups)) - 1]
            chosen = g["links"][:max_items]
            say(f"Checking group {min(group_index, len(groups))} ({len(chosen)} of {g['count']} links)...")
            for i, ln in enumerate(chosen, 1):
                r = probe(page, ln["url"])
                text, link_min = link_title_and_minutes(ln)
                items.append({"title": page_title(r["title"]) or text or ln["url"], "link_text": text,
                              "page_url": ln["url"],
                              "record_url": r["record_url"], "status": r["status"],
                              "minutes": r["minutes"] or link_min, "download_url": r.get("download_url")})
                say(f"  {i}/{len(chosen)} {r['status']}: {items[-1]['title'][:60]}")
        ctx.close()
    titles = [it["title"] for it in items]
    for n, it in enumerate(items, 1):
        it["n"] = n
        if titles.count(it["title"]) > 1 and it.get("link_text"):  # site keeps one title for all pages
            it["title"] = it["link_text"]
    write_json(cfg["work"] / "found.json", {"source": url, "found": time.strftime("%F %T"),
                                            "groups": [{"key": g["key"], "count": g["count"]} for g in groups[:6]],
                                            "items": items})
    print("\nFound:")
    for it in items:
        mins = f"{it['minutes']:>6.1f} min" if it["minutes"] else "    ?     "
        print(f"  {it['n']:>2}. {mins}  {it['title'][:70]}\n        {it['status']}  {it['record_url'][:100]}")
        if it.get("download_url"):
            print(f"        download: {it['download_url'][:110]}")
    print(f"\nSaved to {cfg['work'] / 'found.json'}. Confirm the list with the user, then add the chosen ones:\n"
          f"  find_videos.py --config ... --add all   (or e.g. --add 1,3-5)\n"
          "Wrong links? Try --group N with another group number from the list above.")


def parse_picks(spec, count):
    if spec.strip().lower() == "all":
        return list(range(1, count + 1))
    picks = []
    for part in spec.split(","):
        a, _, b = part.strip().partition("-")
        picks += list(range(int(a), int(b or a) + 1))
    return [n for n in picks if 1 <= n <= count]


def add(cfg_path, cfg, spec):
    found = read_json(cfg["work"] / "found.json", None)
    if not found:
        sys.exit("No found.json yet - run with --url first.")
    items = found["items"]
    raw = json.loads(Path(cfg_path).read_text(encoding="utf-8-sig"))
    have = {v["url"] for v in raw.setdefault("videos", [])}
    added = []
    for n in parse_picks(spec, len(items)):
        it = items[n - 1]
        if spec.strip().lower() == "all" and not re.search(r"(^|; )video", it["status"]):
            continue  # "all" = every confirmed video; pick others by number if the user wants them
        if it["record_url"] in have:
            continue
        v = {"name": clean_name(it["title"], len(raw["videos"]) + 1), "url": it["record_url"]}
        if it.get("minutes"):
            v["expected_minutes"] = it["minutes"]  # guards against recording the wrong video (trailer, ad)
        if it.get("download_url"):
            v["download_url"] = it["download_url"]  # the site offers the file: downloaded instead of recorded
        raw["videos"].append(v)
        have.add(v["url"])
        added.append(v["name"])
    Path(cfg_path).write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Added {len(added)} video(s) to {cfg_path}:")
    for a in added:
        print("  " + a)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # titles in any language
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True, help="videos.json in the work folder (output_dir must be set)")
    ap.add_argument("--url", help="the one link: a course, playlist, channel or lesson-list page")
    ap.add_argument("--group", type=int, default=1, help="which link group to check (see the list it prints)")
    ap.add_argument("--max", type=int, default=60, help="check at most this many links")
    ap.add_argument("--login", action="store_true",
                    help="first open the link so the user can sign in (in the recorder's browser), then find")
    ap.add_argument("--add", metavar="PICKS", help='add found items to videos.json: "all" or e.g. "1,3-5"')
    args = ap.parse_args()
    cfg = load_config(args.config)
    if args.add:
        add(args.config, cfg, args.add)
    elif args.url:
        if args.login:
            login(cfg, args.url)
        try:
            find(cfg, args.url, max(1, args.group), args.max)
        except Exception as e:
            if "closed" in str(e).lower():  # the user closed the finder's browser window mid-search
                sys.exit("The browser window was closed before the search finished. Any sign-in is kept in "
                         "the profile; run the same command again.")
            raise
    else:
        ap.error("give --url to find videos, or --add to add found ones")


if __name__ == "__main__":
    main()
