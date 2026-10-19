"""Download first: save every video in videos.json that has a "download_url" (the site's own download
offer, found by find_videos.py) instead of recording it in real time. Run before the recorder; the
recorder skips videos whose file already exists.

  python download_videos.py --config <work>\\videos.json

Uses the recorder's browser profile cookies, so downloads offered to a signed-in user work too.
Streams to disk (no size limit), resumes nothing - a broken download is deleted and reported, and that
video is then recorded as usual. Appends finished files to <work>\\recorded.json like recordings.
"""
import argparse
import http.cookiejar
import json
import logging
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import duration, load_config, read_json, write_json  # noqa: E402

log = logging.getLogger("dl")
EXTS = (".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".wmv", ".mpg", ".mpeg", ".ogv")


def saved_file(out_dir: Path, name: str):
    """The finished file for this video name, whatever its extension (recordings are .mp4)."""
    for ext in EXTS:
        f = out_dir / f"{name}{ext}"
        if f.exists():
            return f
    return None


def browser_cookies(cfg):
    """Cookies from the recorder's own browser profile (read through the browser itself, never from disk)."""
    try:
        from playwright.sync_api import sync_playwright
        from record_videos import launch
        with sync_playwright() as p:
            ctx = launch(p, cfg, fullscreen=False, muted=True)
            cookies = ctx.cookies()
            ctx.close()
        return cookies
    except Exception as e:
        log.warning("could not read the browser's cookies (%s); downloading without sign-in", str(e)[:120])
        return []


def opener_for(cookies):
    jar = http.cookiejar.CookieJar()
    for c in cookies:
        jar.set_cookie(http.cookiejar.Cookie(
            0, c["name"], c["value"], None, False, c["domain"], True, c["domain"].startswith("."), c["path"], True,
            c.get("secure", False), c.get("expires") if c.get("expires", -1) > 0 else None, False, None, None, {}))
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                                    "Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0")]
    return op


def download(op, url, target: Path, referer=None):
    req = urllib.request.Request(url, headers={"Referer": referer} if referer else {})
    part = target.with_name(target.name + ".part")
    with op.open(req, timeout=60) as r, open(part, "wb") as f:
        ctype = r.headers.get("Content-Type", "")
        if "text/html" in ctype:
            raise RuntimeError(f"the link returned a web page ({ctype}), not a video file - sign-in needed?")
        total = int(r.headers.get("Content-Length") or 0)
        got, last = 0, time.time()
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if time.time() - last > 30:
                log.info("  %s: %.0f MB%s", target.name, got / 1e6, f" of {total / 1e6:.0f}" if total else "")
                last = time.time()
    if total and got < total:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"download ended early ({got} of {total} bytes)")
    part.replace(target)
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    cfg = load_config(args.config)
    out = cfg["output_dir"]
    out.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.FileHandler(cfg["work"] / "recorder.log", encoding="utf-8"),
                                  logging.StreamHandler(sys.stdout)])
    todo = [v for v in cfg["videos"] if v.get("download_url") and not saved_file(out, v["name"])]
    if not todo:
        log.info("downloads: nothing to download")
        return
    log.info("downloads: %d video(s) offered for download by their sites", len(todo))
    op = opener_for(browser_cookies(cfg))
    for v in todo:
        url = v["download_url"]
        ext = Path(urlparse(url).path).suffix.lower()
        target = out / f"{v['name']}{ext if ext in EXTS else '.mp4'}"
        try:
            log.info("downloading %s from %s", target.name, urlparse(url).netloc)
            size = download(op, url, target, referer=v.get("url"))
            d = duration(target)
            if d <= 0:
                target.unlink(missing_ok=True)
                raise RuntimeError("the file isn't a playable video")
            exp = (v.get("expected_minutes") or 0) * 60
            if exp and abs(d - exp) > 0.1 * exp:
                log.warning("%s: %.1f min but the page said %.1f min - check it's the right file",
                            target.name, d / 60, exp / 60)
            log.info("downloaded %s (%.0f s, %.2f GB)", target.name, d, size / 1e9)
            rec = read_json(cfg["work"] / "recorded.json", [])
            rec.append({"name": v["name"], "file": str(target), "expected": round(exp or d, 1),
                        "saved": time.strftime("%F %T"), "downloaded": True})
            write_json(cfg["work"] / "recorded.json", rec)
        except Exception as e:
            log.error("%s: download failed (%s); it will be recorded instead", v["name"], str(e)[:200])


if __name__ == "__main__":
    main()
