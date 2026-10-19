"""Screen-record videos that play in a browser, with OBS, in real time.

Each video plays in its own browser window (Edge or Chrome, separate profile), full screen.
OBS records only that window and only its audio. Recording pauses while playback stalls,
the end is detected even when the player never fires "ended", and each file is saved as MP4.

  python record_videos.py --config <work>\\videos.json --login     # sign in once (user does it)
  python record_videos.py --config <work>\\videos.json --test 720  # test clip of the first video
  python record_videos.py --config <work>\\videos.json             # every video not yet saved
  python record_videos.py --config <work>\\videos.json --only "02 - Basics"

Logs to <work>\\recorder.log; appends finished files to <work>\\recorded.json.
"""
import argparse
import ctypes
import json
import logging
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BROWSER_EXE, duration, load_config, obs_client, read_json, remux_to_mp4, write_json  # noqa: E402
from keep_awake import KeepAwake  # noqa: E402

MARK = "BVRREC"  # pinned window title so OBS always finds the window
NAME = "Browser Video Recorder"  # OBS profile, scene collection and scene
CANVAS = (1920, 1080)
STALL_RELOAD_S = 300

log = logging.getLogger("rec")
user32 = ctypes.windll.user32

TITLE_JS = (f"if (window === window.top) setInterval(() => {{ if (document.title !== '{MARK}') "
            f"document.title = '{MARK}'; }}, 300);")
# Marks the main <video> in a frame and reports it. Players often use preload="none" (no length known
# until play) and keep the real player hidden behind a poster, while thumbnails/previews/ads are other
# <video>s - so load metadata for all, then prefer: loaded > longest > visible > biggest.
PICK_JS = """() => {
  // also look inside web components (open shadow roots): archive.org's <play-av> and others hide the <video> there
  const vs = [];
  (function walk(root) { for (const el of root.querySelectorAll('*')) {
    if (el.tagName === 'VIDEO') vs.push(el); if (el.shadowRoot) walk(el.shadowRoot); } })(document);
  if (!vs.length) return null;
  // nudge only videos idle because of preload="none"; never call load() on a stream being set up
  // (MediaSource/blob: src, networkState LOADING) - load() would tear down the stream
  for (const v of vs) if (v.readyState === 0 && !v.dataset.bvrLoad && v.preload === 'none' && v.networkState !== 2
                          && !(v.currentSrc || v.getAttribute('src') || '').startsWith('blob:')) {
    v.dataset.bvrLoad = '1'; v.preload = 'metadata'; try { v.load(); } catch (e) {} }
  const key = v => { const r = v.getBoundingClientRect(), a = r.width * r.height;
    const d = v.duration === Infinity ? 1e12 : (isFinite(v.duration) ? v.duration : 0);
    return [v.readyState >= 1 ? 1 : 0, Math.round(d), a > 0 ? 1 : 0, a]; };
  const better = (x, y) => { for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return x[i] > y[i]; return false; };
  let best = vs[0], bk = key(vs[0]);
  for (const v of vs.slice(1)) { const k = key(v); if (better(k, bk)) { best = v; bk = k; } }
  vs.forEach(v => v.removeAttribute('data-bvr')); best.setAttribute('data-bvr', '1');
  window.__bvrVideo = best;  // direct reference: works for videos inside shadow roots too
  return {key: bk, d: best.duration, rs: best.readyState, ns: best.networkState, drm: !!best.mediaKeys};
}"""
# the chosen video (set by PICK_JS; reaches into shadow roots). Parenthesised: used as an expression,
# e.g. f"{VID}.play()"
VID = ("(window.__bvrVideo && window.__bvrVideo.isConnected ? window.__bvrVideo"
       " : (document.querySelector('video[data-bvr]') || document.querySelector('video')))")
# start playback without awaiting play(): players like YouTube reject the promise when they manage
# playback themselves; the main loop presses play again if the video stays paused
PLAY_JS = f"() => {{ const v = {VID}; if (v) {{ const p = v.play(); if (p) p.catch(() => {{}}); }} }}"
STATE_JS = f"""() => {{ const v = {VID}; if (!v) return null;
  return {{t: v.currentTime, d: v.duration, paused: v.paused, ended: v.ended, rs: v.readyState, drm: !!v.mediaKeys,
           muted: v.muted, vol: v.volume}}; }}"""
# some players (TED) start muted and keep re-applying their own mute; the recording needs sound
UNMUTE_JS = f"() => {{ const v = {VID}; if (v) {{ v.muted = false; v.volume = 1; }} }}"
# Browsers draw their own play/time/volume bar over a full-screen video for a few seconds (and whenever it
# pauses); hide it on the recorded video. The style goes next to the video - inside its shadow root if it
# lives in a web component - since page styles don't reach in there.
# It also makes the video visible while it is full screen: some sites keep the player in a hidden pop-up
# until their own "Play" button is pressed (NASA+), and a full-screen video inherits visibility: hidden,
# so the window showed the web page while the page reported the video as full screen.
HIDE_CONTROLS_JS = f"""() => {{ const v = {VID}; if (!v) return false; v.controls = false;
  const root = v.getRootNode(); const where = root === document ? document.head : root;
  if (!where.querySelector('style[data-bvr]')) {{ const s = document.createElement('style'); s.setAttribute('data-bvr', '1');
    s.textContent = 'video[data-bvr]::-webkit-media-controls, video[data-bvr]::-webkit-media-controls-enclosure,' +
      'video[data-bvr]::-webkit-media-controls-panel {{ display: none !important; opacity: 0 !important; }}' +
      'video[data-bvr]:fullscreen {{ visibility: visible !important; opacity: 1 !important; }}';
    where.appendChild(s); }}
  return true; }}"""
# the video's own caption tracks are the only captions that can appear in a full-screen recording;
# config "captions": "off" hides them, "on" shows the first captions/subtitles track, absent = site's choice
CAPTIONS_JS = f"""(mode) => {{ const v = {VID}; if (!v || !v.textTracks) return 0; let shown = false;
  for (const tt of v.textTracks) {{
    if (mode === 'off') tt.mode = 'disabled';
    else if (!shown && (tt.kind === 'captions' || tt.kind === 'subtitles')) {{ tt.mode = 'showing'; shown = true; }}
    else tt.mode = 'disabled'; }}
  return v.textTracks.length; }}"""


# Tiny grayscale thumbnail of the video's current frame (args: [w, h]); null if the site's video can't be
# read (cross-origin without CORS) - then the capture check is skipped.
FRAME_JS = f"""([w, h]) => {{ const v = {VID}; if (!v || !v.videoWidth) return null;
  try {{ const c = document.createElement('canvas'); c.width = w; c.height = h;
    const g = c.getContext('2d', {{willReadFrequently: true}}); g.drawImage(v, 0, 0, w, h);
    const d = g.getImageData(0, 0, w, h).data; const out = [];
    for (let i = 0; i < d.length; i += 4) out.push(0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]);
    return out; }} catch (e) {{ return null; }} }}"""


class Unrecordable(Exception):
    pass


def _bmp_gray(data_uri):
    """(w, h, grayscale pixels) from OBS's base64 BMP screenshot (24/32-bit, either row order)."""
    import base64
    raw = base64.b64decode(data_uri.split(",", 1)[1])
    off = int.from_bytes(raw[10:14], "little")
    w = int.from_bytes(raw[18:22], "little", signed=True)
    h = int.from_bytes(raw[22:26], "little", signed=True)
    step = int.from_bytes(raw[28:30], "little") // 8
    bottom_up, h = h > 0, abs(h)
    row = (w * step + 3) & ~3
    px = []
    for y in range(h):
        base = off + ((h - 1 - y) if bottom_up else y) * row
        for x in range(w):
            b, g, r = raw[base + x * step: base + x * step + 3]
            px.append(0.299 * r + 0.587 * g + 0.114 * b)
    return w, h, px


def _corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va / n < 9 or vb / n < 9:  # nearly flat picture (black screen, fade): can't tell
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (va * vb) ** 0.5


def capture_match(cl, frame):
    """How well what OBS is recording matches the video's own current frame (-1..1), or None if it can't
    be told. Catches what page-level checks can't: a site that reports its video as full screen while the
    window shows the web page (TED during ads), a frozen capture, the wrong window."""
    try:
        w, h, obs_px = _bmp_gray(cl.get_source_screenshot(NAME, "bmp", 32, 32, -1).image_data)
        vid_px = frame.evaluate(FRAME_JS, [w, h])
    except Exception:
        return None
    if not vid_px or len(vid_px) != len(obs_px):
        return None
    return _corr(obs_px, vid_px)


# ---------- windows ----------

def find_window(prefix):
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        if n and user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value.startswith(prefix):
                cls = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls, 256)
                found.append((buf.value, cls.value))
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def obs_window_string(title, cls, exe):
    enc = lambda s: s.replace("#", "#22").replace(":", "#3A")
    return f"{enc(title)}:{enc(cls)}:{enc(exe)}"


def has_nvidia():
    import subprocess
    r = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController).Name -join ';'"],
                       capture_output=True, text=True)
    return "NVIDIA" in r.stdout.upper()


# ---------- OBS ----------

class Recorder:
    def __init__(self, cl, cfg):
        self.cl, self.cfg = cl, cfg
        orig_file = cfg["work"] / "obs_original.json"
        orig = read_json(orig_file, None)
        if not orig:  # remember the user's own profile/scenes once, so restores never point at ours
            orig = {"profile": cl.get_profile_list().current_profile_name,
                    "collection": cl.get_scene_collection_list().current_scene_collection_name}
            if NAME in orig.values():
                orig = {"profile": next(p for p in cl.get_profile_list().profiles if p != NAME),
                        "collection": next(c for c in cl.get_scene_collection_list().scene_collections if c != NAME)}
            write_json(orig_file, orig)
        self.orig = orig

    def switch_profile(self, name):
        for _ in range(10):  # OBS rejects switches while a previous switch is still loading
            if self.cl.get_profile_list().current_profile_name == name:
                return
            try:
                self.cl.set_current_profile(name)
            except Exception:
                pass
            time.sleep(1)
        raise RuntimeError(f"could not switch OBS to profile {name!r}")

    def switch_collection(self, name):
        for _ in range(15):
            if self.cl.get_scene_collection_list().current_scene_collection_name == name:
                time.sleep(1)
                return
            try:
                self.cl.set_current_scene_collection(name)
            except Exception:
                pass
            time.sleep(1)
        raise RuntimeError(f"could not switch OBS to scene collection {name!r}")

    def setup(self):
        cl, out = self.cl, self.cfg["output_dir"]
        if NAME not in cl.get_profile_list().profiles:
            cl.create_profile(NAME)
        self.switch_profile(NAME)
        for cat, key, val in [
            ("Output", "Mode", "Simple"),
            ("SimpleOutput", "FilePath", str(out)),
            ("SimpleOutput", "RecFormat2", "mkv"),  # survives crashes; remuxed to mp4 after
            ("SimpleOutput", "RecQuality", "Small"),
            ("SimpleOutput", "RecEncoder", "nvenc" if has_nvidia() else "x264"),
            ("SimpleOutput", "RecAudioEncoder", "aac"),
        ]:
            cl.set_profile_parameter(cat, key, val)
        self.switch_profile(self.orig["profile"])  # switch away and back so OBS reloads output settings
        self.switch_profile(NAME)
        cl.set_video_settings(30, 1, *CANVAS, *CANVAS)
        cl.set_record_directory(str(out))
        if NAME not in cl.get_scene_collection_list().scene_collections:
            cl.create_scene_collection(NAME)
        self.switch_collection(NAME)
        if NAME not in [s["sceneName"] for s in cl.get_scene_list().scenes]:
            cl.create_scene(NAME)
        cl.set_current_program_scene(NAME)
        for k, v in vars(cl.get_special_inputs()).items():  # global desktop/mic audio off in our scenes
            if v and (k.startswith("desktop") or k.startswith("mic")):
                cl.set_input_mute(v, True)

    def point_at_window(self, winstr):
        cl = self.cl
        names = [i["inputName"] for i in cl.get_input_list().inputs]
        for name, kind, settings in [
            ("Video window", "window_capture",
             {"window": winstr, "method": 2, "priority": 0, "cursor": False, "client_area": True}),
            ("Video audio", "wasapi_process_output_capture", {"window": winstr, "priority": 0}),
        ]:
            if name in names:
                cl.set_input_settings(name, settings, True)
            else:
                cl.create_input(NAME, name, kind, settings, True)

    def fit_to_video(self, vw, vh, expect=None):
        """Shape the recording like the video, whatever the screen's shape: crop the captured window to
        where the full-screen video actually is (the browser letterboxes/pillarboxes it with
        object-fit: contain) and size the canvas to the video's aspect, long side <= 1920 and never
        above the video's own resolution. Avoids bars on all four sides on 16:10/ultrawide/portrait
        screens and with 4:3 or vertical videos.
        expect: the full-screen window size in pixels as the page sees it. OBS reports the captured
        window's size a moment late, so a reading taken mid-switch (seen: 1265x1366 on a 2560x1440
        screen) gives a wrong crop; wait until OBS agrees with the page."""
        cl = self.cl
        item = cl.get_scene_item_id(NAME, "Video window").scene_item_id
        W = H = 0
        prev = None
        for _ in range(30):  # OBS needs a moment to report the captured window's size
            tr = cl.get_scene_item_transform(NAME, item).scene_item_transform
            W, H = tr.get("sourceWidth", 0), tr.get("sourceHeight", 0)
            agrees = expect is None or (abs(W - expect[0]) <= 4 and abs(H - expect[1]) <= 4)
            if W and H and agrees and prev == (W, H):
                break
            prev = (W, H)
            time.sleep(0.5)
        else:
            if expect:
                log.warning("OBS reports the window as %sx%s but the page is %.0fx%.0f; cropping by OBS's size",
                            W, H, *expect)
        if not (vw and vh and W and H):
            log.warning("video or window size unknown (video %sx%s, window %sx%s); using 16:9 canvas", vw, vh, W, H)
            cw, ch, crop_x, crop_y = CANVAS[0], CANVAS[1], 0, 0
        else:
            s = min(W / vw, H / vh)  # where the browser puts the video inside the window
            shown_w, shown_h = vw * s, vh * s
            crop_x, crop_y = int((W - shown_w) / 2), int((H - shown_h) / 2)
            long_side = min(1920, max(vw, vh), max(shown_w, shown_h))
            if vw >= vh:
                cw, ch = long_side, long_side * vh / vw
            else:
                cw, ch = long_side * vw / vh, long_side
            cw, ch = int(cw) // 2 * 2, int(ch) // 2 * 2  # encoders need even sizes
        if cl.get_record_status().output_active:  # OBS can't change the canvas mid-recording: keep it, fix the crop
            vs = cl.get_video_settings()
            cw, ch = vs.base_width, vs.base_height
        else:
            cl.set_video_settings(30, 1, cw, ch, cw, ch)
        cl.set_scene_item_transform(NAME, item, {
            "positionX": 0, "positionY": 0, "alignment": 5, "boundsType": "OBS_BOUNDS_SCALE_INNER",
            "boundsAlignment": 0, "boundsWidth": cw, "boundsHeight": ch,
            "cropLeft": crop_x, "cropRight": crop_x, "cropTop": crop_y, "cropBottom": crop_y})
        log.info("video %sx%s on a %sx%s window -> recording %sx%s (cropped %s px left/right, %s px top/bottom)",
                 vw, vh, W, H, cw, ch, crop_x, crop_y)

    def restore(self):
        try:
            s = self.cl.get_record_status()
            if s.output_active:
                if s.output_paused:
                    self.cl.resume_record()
                self.cl.stop_record()
            self.switch_collection(self.orig["collection"])
            self.switch_profile(self.orig["profile"])
            log.info("OBS switched back to profile %r / scenes %r", self.orig["profile"], self.orig["collection"])
        except Exception as e:
            log.warning("could not restore OBS settings: %s", e)


# ---------- browser ----------

def no_translate_offer(profile: Path):
    """Turn off the "Translate this page?" bubble in the profile itself: on a foreign-language page it
    pops up over the video and gets recorded. The flag below covers Chrome; Edge's translator only
    honours this preference. Written before launch, while the browser is closed."""
    prefs_file = profile / "Default" / "Preferences"
    try:
        prefs = json.loads(prefs_file.read_text(encoding="utf-8")) if prefs_file.exists() else {}
        if prefs.get("translate", {}).get("enabled") is False:
            return
        prefs.setdefault("translate", {})["enabled"] = False
        prefs_file.parent.mkdir(parents=True, exist_ok=True)
        prefs_file.write_text(json.dumps(prefs), encoding="utf-8")
    except Exception as e:
        log.warning("could not turn off the translate offer: %s", e)


def launch(p, cfg, fullscreen=True, muted=False):
    args = ["--autoplay-policy=no-user-gesture-required",
            # CalculateNativeWinOcclusion: keep rendering when covered. Translate: no "Translate this page?" bubble.
            "--disable-features=CalculateNativeWinOcclusion,Translate",
            "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
            "--disable-background-timer-throttling"]
    if fullscreen:
        args.insert(0, "--start-fullscreen")
    if muted:  # the link finder: nothing it opens may be heard (or end up in a recording running meanwhile)
        args.append("--mute-audio")
    no_translate_offer(cfg["work"] / "browser-profile")
    return p.chromium.launch_persistent_context(
        str(cfg["work"] / "browser-profile"), channel=cfg["browser"], headless=False, no_viewport=True,
        chromium_sandbox=True,  # otherwise --no-sandbox is added and a warning bar shows in the recording
        ignore_default_args=["--mute-audio", "--enable-automation"], args=args)


# Click-to-activate players: the <video> exists but has no source until the poster is clicked.
# Mark what a person would click: the main video if visible, else its nearest visible container.
# Players attached to their stream but waiting for a press of their own play button (PeerTube/video.js
# embeds): mark a visible "play" button inside the video's own player container - never buttons elsewhere
# on the page (a card list may hold play buttons for other videos).
PLAY_BUTTON_JS = f"""() => {{ const v = {VID}; if (!v) return false;
  let box = v; for (let i = 0; i < 4 && box; i++) box = box.parentElement || (box.getRootNode() && box.getRootNode().host) || null;
  if (!box) return false;
  const btns = []; (function walk(r) {{ for (const el of r.querySelectorAll('button,[role=button]')) btns.push(el);
    for (const el of r.querySelectorAll('*')) if (el.shadowRoot) walk(el.shadowRoot); }})(box);
  const ok = btns.filter(b => {{ const r = b.getBoundingClientRect(); const s = ((b.getAttribute('aria-label') || '') + ' ' +
    (b.title || '') + ' ' + (b.innerText || '')).toLowerCase(); return r.width * r.height > 300 && /\\bplay\\b/.test(s); }});
  if (!ok.length) return false;
  ok.sort((a, b) => b.getBoundingClientRect().width * b.getBoundingClientRect().height -
                    a.getBoundingClientRect().width * a.getBoundingClientRect().height);
  document.querySelectorAll('[data-bvr-click]').forEach(e => e.removeAttribute('data-bvr-click'));
  ok[0].setAttribute('data-bvr-click', '1'); return true; }}"""
CLICK_TARGET_JS = f"""() => {{ const v = {VID}; if (!v) return false;
  let el = v; for (let i = 0; i < 6 && el; i++) {{ const r = el.getBoundingClientRect();
    if (r.width * r.height > 2000) {{ document.querySelectorAll('[data-bvr-click]').forEach(e => e.removeAttribute('data-bvr-click'));
      el.setAttribute('data-bvr-click', '1'); return true; }}
    el = el.parentElement || (el.getRootNode() && el.getRootNode().host) || null; }} return false; }}"""


BOT_CHECK_JS = """() => /just a moment|attention required|verify you are human|checking your browser|are you a robot/i
  .test(document.title + ' ' + (document.body ? document.body.innerText.slice(0, 400) : '')) ||
  !!document.querySelector('iframe[src*="challenges.cloudflare.com"], iframe[src*="hcaptcha.com"], #challenge-form')"""


# A sign-in page: a password box, a login/SSO address, or a sign-in title. Not the words "Log in" alone -
# public sites show those in their header.
SIGNIN_JS = r"""() => [...document.querySelectorAll('input[type=password]')].some(i => {
    const r = i.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(i).visibility !== 'hidden'; }) ||
  /(^|[\/.?=_-])(login|log-in|signin|sign-in|sign_in|auth|sso|oauth|saml|accounts?)([\/.?=_-]|$)/i
    .test(location.host + location.pathname) ||
  /^(sign in|log in|login|התחברות|כניסה)\b/i.test((document.title || '').trim())"""


def wait_for_signin(page, url, minutes=15, say=None):
    """If the page asks to sign in, ask the user to do it in this browser window and wait - never type
    anything into it. Returns True when signed in (url reopened), False on timeout / not a sign-in page."""
    say = say or log.info
    try:
        if not page.evaluate(SIGNIN_JS):
            return False
        # a page with a video is never treated as a sign-in page (a guess that's wrong must cost nothing)
        if any(fr.evaluate("() => !!document.querySelector('video')") for fr in page.frames):
            return False
    except Exception:
        return False
    say(f"SIGN-IN NEEDED: please sign in in the browser window that opened ({urlparse_host(page.url)}). "
        f"Waiting up to {minutes} min; it continues by itself once you're signed in.")
    try:
        page.bring_to_front()
    except Exception:
        pass
    end = time.time() + minutes * 60
    while time.time() < end:
        time.sleep(3)
        try:
            if page.evaluate(SIGNIN_JS):
                continue
            time.sleep(3)  # let the site finish its redirects
            page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            time.sleep(3)
            if not page.evaluate(SIGNIN_JS):
                say("signed in; continuing")
                return True
        except Exception:
            continue
    say("still not signed in; giving up on this page")
    return False


def urlparse_host(url):
    from urllib.parse import urlparse
    return urlparse(url).netloc


def press(frame):
    """Click the element marked data-bvr-click like a person: bring it (and every frame holding it) into
    view first - a forced click on an element outside the window lands on nothing (seen: Vimeo's Play
    button below the fold of an article). If the video is still paused afterwards, click the element
    directly as a fallback (only then, so a press that worked is never undone)."""
    try:
        frame.evaluate("() => { const e = document.querySelector('[data-bvr-click]'); "
                       "if (e) e.scrollIntoView({block: 'center', inline: 'center'}); }")
        f = frame
        while f.parent_frame:  # the iframe itself, in each page above it
            f.frame_element().scroll_into_view_if_needed(timeout=5_000)
            f = f.parent_frame
        frame.evaluate("() => { const e = document.querySelector('[data-bvr-click]'); "
                       "if (e) e.scrollIntoView({block: 'center', inline: 'center'}); }")
    except Exception:
        pass
    frame.click("[data-bvr-click]", timeout=10_000, force=True)
    time.sleep(3)
    still = frame.evaluate(f"() => {{ const v = {VID}; return !!v && v.paused; }}")
    if still:
        log.info("the click didn't start it; clicking the button directly")
        frame.evaluate("() => { const e = document.querySelector('[data-bvr-click]'); if (e) e.click(); }")


def find_video(page, timeout_s=120):
    """Frame holding the main <video> (main page or an embedded player), chosen across all frames
    with the same preference as PICK_JS: loaded > longest > visible > biggest. If nothing loads,
    clicks the player once, like a person would."""
    end = time.time() + timeout_s
    t0 = time.time()
    asked_play = clicked = pressed = second_try = False
    scrolls = 0
    bot_since = None
    while time.time() < end:
        # a "checking your browser" page is bot protection: never solve it; say so instead of searching for 2 min
        bot = False
        for fr in page.frames:  # embedded players can show their own challenge inside the iframe
            try:
                bot = bot or fr.evaluate(BOT_CHECK_JS)
            except Exception:
                pass
        if bot:
            if not bot_since:
                log.info("the site shows a browser check; waiting for it to clear by itself (nothing is clicked)")
            bot_since = bot_since or time.time()
            # most "Just a moment..." pages are automatic checks a normal browser passes on its own in a few
            # seconds; only an interactive one (checkbox/puzzle) stays - that one is for the user, never us
            if time.time() - bot_since > 45:
                raise Unrecordable("the site shows a bot check ('checking your browser' / 'verify you are human'). "
                                   "The user can pass it themselves in --login mode; never solve it for them. "
                                   "If it comes back every time, the site isn't supported.")
            time.sleep(2)
            continue
        if bot_since:  # check passed: give the real page the usual time from now
            log.info("browser check cleared after %.0f s", time.time() - bot_since)
            t0, end = time.time(), time.time() + timeout_s
        bot_since = None
        best = None
        for fr in page.frames:
            try:
                info = fr.evaluate(PICK_JS)
            except Exception:
                continue
            if info and (best is None or info["key"] > best[1]["key"]):
                best = (fr, info)
        if best and best[1]["rs"] >= 1 and best[1]["d"] and best[1]["d"] > 0:
            return best
        waited = time.time() - t0
        # no video at all yet: scroll down like a person looking for the player - embeds are often
        # lazy-loaded (<iframe loading="lazy">, e.g. Vimeo players in articles) and only exist once in view
        if not best and waited > 4 and scrolls < 8:
            scrolls += 1
            try:
                page.mouse.wheel(0, 700)
            except Exception:
                pass
        # Not ready after 8 s: start it like a person would - with the player's OWN play button first.
        # Calling play() on the <video> first is a trap on players that fetch the stream themselves
        # (Vimeo): the element says "playing", nothing loads, and the player's button turns into "Pause",
        # so a later click only pauses it. Without a labelled play button:
        # - attached to its stream but waiting (networkState 2, e.g. PeerTube embeds): ask it to play;
        # - completely idle (networkState 0/3: placeholder, or a player whose own code must wire the
        #   video up, e.g. archive.org): click the player once.
        streaming = best and best[1].get("ns") == 2
        if best and waited > 8 and not (asked_play or clicked or pressed):
            try:
                if best[0].evaluate(PLAY_BUTTON_JS):
                    pressed = True
                    log.info("video not loading by itself; pressing the player's own play button")
                    press(best[0])
                elif streaming:
                    asked_play = True
                    log.info("video not loading by itself; asking it to play")
                    best[0].evaluate(PLAY_JS)
                elif best[0].evaluate(CLICK_TARGET_JS):
                    clicked = True
                    log.info("video not loading by itself; clicking the player once to activate it")
                    press(best[0])
            except Exception as e:
                log.warning("activation step failed: %s", str(e)[:200])
        elif best and waited > 20 and (asked_play or clicked or pressed) and not second_try:
            # still nothing: undo our own play() first (so the player isn't left believing it plays), then
            # try what wasn't tried: its play button (DW: an empty video.js placeholder with a "Play video"
            # button), else a click on the player
            second_try = True
            try:
                if asked_play:
                    best[0].evaluate(f"() => {{ const v = {VID}; if (v) v.pause(); }}")
                    time.sleep(1)
                if not pressed and best[0].evaluate(PLAY_BUTTON_JS):
                    log.info("still not loading; pressing the player's own play button")
                    press(best[0])
                elif not clicked and best[0].evaluate(CLICK_TARGET_JS):
                    log.info("still not loading; clicking the player once")
                    press(best[0])
                elif streaming and not asked_play:
                    log.info("still not loading; asking it to play")
                    best[0].evaluate(PLAY_JS)
            except Exception as e:
                log.warning("activation click failed: %s", str(e)[:200])
        time.sleep(2)
    # say what the page showed, so the cause can be read from the log (an error or privacy message inside an
    # embedded player, a sign-in wall, a video that never got a source)
    for fr in page.frames:
        try:
            info = fr.evaluate(PICK_JS)
            text = fr.evaluate(r"() => document.body ? document.body.innerText.replace(/\s+/g, ' ').slice(0, 160) : ''")
        except Exception:
            continue
        if info or fr == page.main_frame:
            log.warning("gave up on frame %s: video %s; text: %s", fr.url[:100],
                        {k: info[k] for k in ("d", "rs", "ns")} if info else "none", text)
    return None


# True only when the chosen video itself (or the iframe holding it) is full screen AND actually fills the
# window. Any other full-screen element (a site's player box with controls, an ad) doesn't count, and
# neither does a page that *reports* the video as full screen while showing the normal page (TED does
# this during its ads). Videos inside web components are reported on their shadow root, not the document.
FS_OK_JS = """() => {
  const covers = el => { const r = el.getBoundingClientRect();
    return r.width >= innerWidth * 0.97 && r.height >= innerHeight * 0.97; };
  const v = window.__bvrVideo;
  if (v && v.isConnected) { const root = v.getRootNode();
    const f = root === document ? document.fullscreenElement : root.fullscreenElement;
    const seen = !v.checkVisibility || v.checkVisibility({visibilityProperty: true});
    if (f === v && covers(v) && seen) return true; }
  const fr = document.querySelector('[data-bvr-frame]');
  return !!(fr && document.fullscreenElement === fr && covers(fr)); }"""


def fullscreen(page, frame):
    """Full screen the video (or the embedded player's iframe). Uses a CDP user gesture, so no clicks
    land on the site."""
    if page.evaluate(FS_OK_JS):
        return
    if page.evaluate("() => !!document.fullscreenElement"):  # something else took full screen
        page.evaluate("() => document.exitFullscreen().catch(() => {})")
        time.sleep(0.5)
    if frame == page.main_frame:
        target = VID
    else:
        top = frame
        while top.parent_frame and top.parent_frame != page.main_frame:
            top = top.parent_frame
        top.frame_element().evaluate("el => el.setAttribute('data-bvr-frame', '1')")
        target = "document.querySelector('[data-bvr-frame]')"
    cdp = page.context.new_cdp_session(page)
    try:
        cdp.send("Runtime.evaluate", {"expression": f"({target}).requestFullscreen()", "userGesture": True,
                                      "awaitPromise": True})
    finally:
        cdp.detach()


def open_video(page, url, start_at=None, play_selector=None, expected_s=None):
    page.goto(url, wait_until="domcontentloaded", timeout=120_000)
    time.sleep(2)
    wait_for_signin(page, url)  # signed out: the user signs in in this window (we never type anything)
    if play_selector:  # sites that only create the player after a click on their play button/poster
        page.click(play_selector, timeout=60_000)
        time.sleep(2)
    found = find_video(page)
    if not found:
        raise RuntimeError("no playable <video> found on the page within 2 minutes (signed out? use --login; "
                           "player only appears after a click? set play_selector for this video)")
    frame, info = found
    if info["drm"]:
        raise Unrecordable("this video uses encrypted media (DRM); it records as black frames - not recordable")
    if info["d"] == float("inf"):
        raise Unrecordable("this is a live stream (no fixed length); not supported")
    # a trailer, an ad or a play_selector that pressed the wrong card can bring up a different video
    if expected_s and abs(info["d"] - expected_s) > 0.1 * expected_s:
        raise Unrecordable(f"found a {info['d'] / 60:.1f}-min video but expected about {expected_s / 60:.0f} min - "
                           "probably the wrong video (trailer, ad, or play_selector pressed another item)")
    frame.evaluate(f"""() => {{ const v = {VID}; v.muted = false; v.volume = 1; v.playbackRate = 1;
        {'' if start_at is None else f'v.currentTime = {start_at};'} const p = v.play(); if (p) p.catch(() => {{}}); }}""")
    time.sleep(1)
    fullscreen(page, frame)
    return frame


def url_with_start(url, seconds):
    """The site's own "start at" link, for players that ignore direct jumps (they stream in pieces and
    only fetch what their own player asks for - YouTube, Vimeo). None if the site has none we know."""
    from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
    u = urlparse(url)
    host = u.netloc.lower()
    s = int(seconds)
    if host.endswith("youtube.com") or host.endswith("youtu.be"):
        q = parse_qs(u.query)
        q["t"] = [f"{s}s"]
        return urlunparse(u._replace(query=urlencode(q, doseq=True)))
    if host.endswith("vimeo.com"):
        return urlunparse(u._replace(fragment=f"t={s}s"))
    return None


def plays_near(frame, target, timeout=15):
    """True once playback is actually moving forward near target (a jump the player really followed)."""
    end, prev = time.time() + timeout, None
    while time.time() < end:
        time.sleep(1)
        st = frame.evaluate(STATE_JS)
        if not st:
            continue
        if st["paused"]:
            frame.evaluate(PLAY_JS)
        if prev is not None and st["t"] > prev + 0.3 and target - 3 <= st["t"] <= target + 30:
            return True
        prev = st["t"]
    return False


def jump(page, frame, url, target, play_selector=None):
    """Move playback to target seconds and make sure the player really plays from there.
    Returns (frame, ok). Direct jumps work on most players; streaming players that manage their own
    buffer may freeze on a far jump, so fall back to the site's start-time link."""
    frame.evaluate(f"(t) => {{ const v = {VID}; if (v) {{ v.currentTime = t; }} }}", target)
    frame.evaluate(PLAY_JS)
    if plays_near(frame, target):
        return frame, True
    alt = url_with_start(url, target)
    if alt:
        log.info("player ignored the jump to %.0f s; reloading with the site's start-time link", target)
        frame = open_video(page, alt, play_selector=play_selector)
        if plays_near(frame, target):
            return frame, True
    return frame, False


def ensure_fullscreen(page, frame, wait_s=10):
    """Re-request full screen until the video itself is the full-screen element. True if it is."""
    try:
        frame.evaluate(HIDE_CONTROLS_JS)
    except Exception:
        pass
    for _ in range(wait_s):
        try:
            fullscreen(page, frame)
        except Exception as e:
            log.warning("fullscreen request failed: %s", str(e)[:200])
        time.sleep(1)
        if page.evaluate(FS_OK_JS):
            return True
    return False


def finalize(mkv: Path, out_dir: Path, name: str, expect_s: float, work: Path):
    target = out_dir / f"{name}.mp4"
    for _ in range(30):  # OBS may still hold the file for a moment
        try:
            mkv_named = mkv.rename(out_dir / f"{name}.mkv")
            break
        except PermissionError:
            time.sleep(2)
    else:
        log.error("could not rename %s", mkv)
        return
    ok, err = remux_to_mp4(mkv_named, target)
    if not ok:
        log.error("remux failed, keeping mkv: %s", err)
        return
    d = duration(target)
    log.info("saved %s (%.0f s, expected ~%.0f s, %.2f GB)", target.name, d, expect_s, target.stat().st_size / 1e9)
    if d >= expect_s * 0.97:
        mkv_named.unlink()
    else:
        log.warning("mp4 shorter than expected; kept the mkv too")
    rec = read_json(work / "recorded.json", [])
    rec.append({"name": name, "file": str(target), "expected": round(expect_s, 1), "saved": time.strftime("%F %T")})
    write_json(work / "recorded.json", rec)


def record_one(page, rec, cfg, name, url, test_seconds=None, play_selector=None, expected_s=None):
    cl = rec.cl
    frame = open_video(page, url, play_selector=play_selector, expected_s=expected_s)
    win = None
    for _ in range(30):
        win = find_window(MARK)
        if win:
            break
        time.sleep(1)
    if not win:
        raise RuntimeError("could not find the browser window")
    rec.point_at_window(obs_window_string(*win, BROWSER_EXE[cfg["browser"]]))
    time.sleep(2)

    def refit():  # crop/canvas for where the video is drawn; only valid once the window is full screen
        vw, vh = frame.evaluate(f"() => {{ const v = {VID}; return [v.videoWidth, v.videoHeight]; }}")
        win_px = page.evaluate("() => [innerWidth * devicePixelRatio, innerHeight * devicePixelRatio]")
        rec.fit_to_video(vw, vh, win_px)

    duration_s = frame.evaluate(STATE_JS)["d"]
    if test_seconds and duration_s <= test_seconds + 5:  # short video: the test is the whole video
        log.info("video (%.0f s) is shorter than the test; testing all of it", duration_s)
        test_seconds = None
        test_whole = True
        start = 0.0
    elif test_seconds:  # test from the middle of the video when it is long enough
        test_whole = False
        start = 1800.0 if duration_s > 1800 + test_seconds + 60 else max(0.0, (duration_s - test_seconds) / 2)
        frame, ok = jump(page, frame, url, start, play_selector)
        if not ok:
            log.warning("this player doesn't follow jumps inside the video; testing from the start instead")
            frame = open_video(page, url, play_selector=play_selector)
            start = 0.0
    else:
        test_whole = False
        start = 0.0
    # setup played a few seconds; hold at the real start point (a short jump inside what is already
    # loaded, which every player follows), start OBS, then play
    frame.evaluate(f"() => {{ const v = {VID}; v.pause(); v.currentTime = {start}; }}")
    time.sleep(2)
    st = frame.evaluate(STATE_JS)
    log.info("%s: %.0f s long, starting at %.0f s", name, duration_s, st["t"])
    frame.evaluate(UNMUTE_JS)
    captions = cfg.get("captions")
    if captions in ("on", "off"):
        n = frame.evaluate(CAPTIONS_JS, captions)
        log.info("captions %s (%d caption track(s) on this video)", captions, n)
    # only start recording once the video itself is full screen (otherwise OBS records the web page)
    enforce_fs = ensure_fullscreen(page, frame)
    refit()
    if not enforce_fs:
        log.warning("%s: the site won't let the video go full screen; recording the window as it is", name)
    else:  # and only once OBS really shows the video (the page can claim full screen while showing itself)
        match = None
        for i in range(15):
            match = capture_match(cl, frame)
            if match is None or match >= 0.5:
                break
            if i % 5 == 4:  # nudge the browser to redraw full screen
                page.evaluate("() => document.exitFullscreen().catch(() => {})")
                time.sleep(0.5)
                ensure_fullscreen(page, frame, 3)
                refit()
            time.sleep(1)
        log.info("capture check before start: %s", "can't tell (video not readable or flat)" if match is None
                 else f"match {match:.2f}")
    cl.start_record()
    frame.evaluate(PLAY_JS)
    paused = False
    first_t = last_t = st["t"]
    last_progress = time.time()
    began = time.time()
    reset_since = None
    unmuted_logged = False
    fs_lost_since = None
    last_cap_check, cap_bad_count = 0.0, 0

    while True:
        time.sleep(1)
        try:
            st = frame.evaluate(STATE_JS)
        except Exception as e:
            log.warning("page not responding: %s", str(e)[:200])
            st = None
        now = time.time()
        # a test records N seconds of *video* (buffering pauses don't count), capped at 3x in clock time
        if test_seconds and (last_t - first_t >= test_seconds or now - began >= test_seconds * 3):
            break
        if st and (st["ended"] or st["t"] >= st["d"] - 0.5):
            break
        # the site's player threw playback away (position back to 0, nothing loaded) - e.g. YouTube shows
        # "Something went wrong" in automated browsers. Don't fight it: keep what we have and say so.
        if st is not None and last_t > 30 and st["t"] < 1 and st["rs"] == 0:
            reset_since = reset_since or now
            if now - reset_since > 30:
                log.error("%s: the site's player reset itself at %.0f s and did not recover (some sites, e.g. "
                          "YouTube, stop playback in automated browsers); saving what was recorded", name, last_t)
                break
        else:
            reset_since = None
        if captions in ("on", "off") and int(now) % 10 == 0:  # players may switch tracks back on
            frame.evaluate(CAPTIONS_JS, captions)
        if st and (st.get("muted") or st.get("vol", 1) < 0.05):
            if not unmuted_logged:
                log.info("the player muted the video; unmuting (the recording needs sound)")
                unmuted_logged = True
            frame.evaluate(UNMUTE_JS)
        # what OBS records vs the video's own frame, every 3 s while playing; 2 bad checks in a row = OBS isn't
        # showing the video even if the page says it is full screen
        if enforce_fs and not paused and now - last_cap_check >= 3:
            last_cap_check = now
            m = capture_match(cl, frame)
            cap_bad_count = cap_bad_count + 1 if (m is not None and m < 0.3) else 0
            if cap_bad_count == 2:
                log.info("OBS isn't showing the video (match %.2f); holding until it is", m)
        # never record the web page: if the video itself isn't full screen (a site's ad or player box took
        # over) or OBS isn't showing it, hold playback and OBS, restore full screen, then carry on - nothing
        # is skipped
        if enforce_fs and st is not None and (cap_bad_count >= 2 or not page.evaluate(FS_OK_JS)):
            if not fs_lost_since:
                fs_lost_since = now
                if cap_bad_count < 2:
                    log.info("video left full screen; holding playback and recording until it's back")
            if cap_bad_count >= 2:  # page claims full screen but isn't drawing it: force a fresh switch
                page.evaluate("() => document.exitFullscreen().catch(() => {})")
                time.sleep(0.5)
                ensure_fullscreen(page, frame, 3)
                refit()
                m = capture_match(cl, frame)
                if m is None or m >= 0.5:
                    log.info("OBS shows the video again%s", "" if m is None else f" (match {m:.2f})")
                    cap_bad_count = 0
            if not paused:
                cl.pause_record()
                paused = True
            frame.evaluate(f"() => {{ const v = {VID}; if (v) v.pause(); }}")
            try:
                fullscreen(page, frame)
            except Exception as e:
                log.warning("fullscreen failed: %s", str(e)[:200])
            if now - fs_lost_since > 60:
                log.warning("%s: can't keep the video full screen; recording the window as it is", name)
                enforce_fs = False
                frame.evaluate(PLAY_JS)
            last_progress = now  # not a stall
            continue
        if fs_lost_since:
            log.info("back in full screen after %.0f s", now - fs_lost_since)
            fs_lost_since = None
            frame.evaluate(PLAY_JS)
        if st is not None and st["t"] > last_t + 0.2:
            last_t, last_progress = st["t"], now
            if paused:
                cl.resume_record()
                paused = False
        else:
            # players often stop ~1 s short of the end without "ended", and may drop the <video>
            # element (st is None), so judge by the last position seen
            if last_t >= duration_s - 5 and now - last_progress > 15:
                log.info("playback stopped %.1f s before the end; treating as finished", duration_s - last_t)
                break
            if not paused:
                cl.pause_record()
                paused = True
            if st and st["paused"] and not st["ended"]:
                frame.evaluate(PLAY_JS)
            if now - last_progress > STALL_RELOAD_S:
                log.warning("stalled for %d s at %.0f s, reloading", STALL_RELOAD_S, last_t)
                frame = open_video(page, url, play_selector=play_selector)
                frame, ok = jump(page, frame, url, max(last_t - 1, 0), play_selector)
                if not ok:  # resuming from 0 would repeat content; keep what we have and flag it
                    log.error("%s: could not resume at %.0f s on this player; saving the partial recording",
                              name, last_t)
                    break
                last_progress = time.time()

    if paused:
        cl.resume_record()
    out = Path(cl.stop_record().output_path)
    finalize(out, cfg["output_dir"], name, test_seconds * 0.97 if test_seconds else duration_s, cfg["work"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--test", type=int, metavar="SECONDS", help="record a test clip of the first video")
    ap.add_argument("--only", nargs="*", help="file names (or name prefixes) to record")
    ap.add_argument("--login", action="store_true", help="open the browser profile so the user can sign in")
    args = ap.parse_args()
    cfg = load_config(args.config)
    cfg["output_dir"].mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.FileHandler(cfg["work"] / "recorder.log", encoding="utf-8"),
                                  logging.StreamHandler(sys.stdout)])
    from playwright.sync_api import sync_playwright

    if args.login:
        with sync_playwright() as p:
            ctx = launch(p, cfg, fullscreen=False)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(cfg["videos"][0]["url"])
            print("Sign in in the browser window that opened, then close that window.")
            page.wait_for_event("close", timeout=0)
            ctx.close()
        return

    from download_videos import saved_file
    # videos already saved (recorded, or downloaded from the site's own offer - any extension) are skipped
    every = [(v["name"], v["url"], v.get("play_selector"),
              v["expected_minutes"] * 60 if v.get("expected_minutes") else None) for v in cfg["videos"]]
    videos = [t for t in every if not saved_file(cfg["output_dir"], t[0])]
    if args.test:
        # test the first video still to record; if all are saved, still test the first (checking a site)
        pick = (videos or every)[0]
        todo = [(f"TEST - {pick[0]}", *pick[1:])]
    else:
        todo = [t for t in videos if not args.only or any(t[0].startswith(o) for o in args.only)]
    log.info("to record: %s", [t[0] for t in todo])
    if not todo:
        return

    rec = Recorder(obs_client(cfg["work"], start_if_needed=True, log=log.info), cfg)
    rec.setup()
    try:
        with KeepAwake("Recording browser video"), sync_playwright() as p:
            log.info("holding display + system awake")
            ctx = launch(p, cfg)
            ctx.add_init_script(TITLE_JS)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            for name, url, selector, expected_s in todo:
                try:
                    record_one(page, rec, cfg, name, url, args.test, selector, expected_s)
                except Unrecordable as e:
                    log.error("%s: NOT RECORDABLE - %s", name, e)
                    if rec.cl.get_record_status().output_active:
                        rec.cl.stop_record()
                except Exception:
                    log.exception("%s failed, moving on", name)
                    if rec.cl.get_record_status().output_active:
                        rec.cl.stop_record()
            ctx.close()
    finally:
        rec.restore()
    log.info("done")


if __name__ == "__main__":
    main()
