"""Check a recorded (or trimmed) video file. Exit code 0 = pass, 1 = fail.

  python check_recording.py <file> --expected 10842          # a full recording
  python check_recording.py <file> --expected 720 --test     # the pre-run test clip (stricter)
  python check_recording.py <trimmed> --seams <original> [--min-minutes 4 --after 3 --before 2]

Checks: length vs expected (stalls / early stops), audio present and not silent per window,
picture not black (DRM or minimised window), audio/video in sync, long digital silences
(reported, usually from the source), and for trimmed files that each cut sits in quiet audio
with talking right after.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import duration, ffmpeg_stderr, silences, volume  # noqa: E402


def stream_durations(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True).stdout.split()
    d = {}
    for line in out:
        kind, _, val = line.partition(",")
        try:
            d[kind] = float(val)
        except ValueError:
            pass
    return d


def brightness_samples(path, total, n):
    """Average luma (0-255) of n frames spread over the file."""
    vals = []
    for i in range(n):
        t = total * (i + 0.5) / n
        err = ffmpeg_stderr(["-ss", f"{t:.1f}", "-i", str(path), "-frames:v", "1", "-vf", "signalstats,metadata=print",
                             "-f", "null", "NUL"])
        m = re.search(r"YAVG=([\d.]+)", err)
        if m:
            vals.append(float(m.group(1)))
    return vals


def black_bars(path, total, n=5):
    """(frame w, h, picture w, h) from ffmpeg cropdetect over a few sampled spots; None if unknown."""
    sizes = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip().split(",")
    try:
        fw, fh = int(sizes[0]), int(sizes[1])
    except (ValueError, IndexError):
        return None
    best_w = best_h = 0
    for i in range(n):  # widest picture seen wins (dark scenes look like bars)
        err = ffmpeg_stderr(["-ss", f"{total * (i + 0.5) / n:.1f}", "-i", str(path), "-frames:v", "15",
                             "-vf", "cropdetect=24:2:0", "-f", "null", "NUL"])
        m = re.findall(r"crop=(\d+):(\d+):\d+:\d+", err)
        if m:
            w, h = map(int, m[-1])
            best_w, best_h = max(best_w, w), max(best_h, h)
    return (fw, fh, best_w, best_h) if best_w else None


def contact_sheet(path, total, out_png, n=10):
    """n frames spread over the file (denser at the start, where page/ad problems show up), labeled, 5 per row.
    Look at it: the numbers can't tell a recorded web page or overlay from the video."""
    import tempfile
    early = [0.5, 2, 5, 10]
    spread = [total * k / (n - len(early) + 1) for k in range(1, n - len(early) + 1)]
    times = []
    for t in sorted(t for t in set(early + spread) if t < total - 0.5):
        if not times or t - times[-1] >= 1.5:  # short clips: no near-duplicate frames
            times.append(t)
    times = times[:n]
    tmp = Path(tempfile.mkdtemp(prefix="bvr_sheet_"))
    font = "C\\:/Windows/Fonts/arialbd.ttf"
    tiles = []
    for i, t in enumerate(times):
        tile = tmp / f"{i:02d}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1", "-vf",
                        "scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2:color=0x404040,"
                        # label in seconds: ':' would split ffmpeg's filter options
                        f"drawtext=fontfile='{font}':text='{t:.0f} s':fontsize=14:fontcolor=yellow:box=1:boxcolor=black@0.7:x=4:y=4",
                        str(tile)], capture_output=True)
        if tile.exists():
            tiles.append(tile)
    while len(tiles) % 5:
        tiles.append(tiles[-1])
    rows = len(tiles) // 5
    inputs = [a for t in tiles for a in ("-i", str(t))]
    graph = ";".join(f"{''.join(f'[{r * 5 + c}]' for c in range(5))}hstack=5[r{r}]" for r in range(rows))
    graph += f";{''.join(f'[r{r}]' for r in range(rows))}vstack={rows}" if rows > 1 else ""
    if rows == 1:
        graph = graph.replace("[r0]", "")
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, str(out_png)], capture_output=True)
    for t in tmp.iterdir():
        t.unlink()
    tmp.rmdir()
    return Path(out_png).exists()


def hms(t):
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("--expected", type=float, help="expected length in seconds")
    ap.add_argument("--test", action="store_true", help="strict checks for the pre-run test clip")
    ap.add_argument("--seams", type=Path, metavar="ORIGINAL", help="check cut points of a trimmed copy")
    ap.add_argument("--min-minutes", type=float, default=4)
    ap.add_argument("--after", type=float, default=3)
    ap.add_argument("--before", type=float, default=2)
    ap.add_argument("--sheet", type=Path, metavar="PNG", help="also save a contact sheet of frames to look at")
    a = ap.parse_args()
    f = a.file
    problems, notes = [], []
    total = duration(f)
    print(f"{f.name}: {total / 60:.1f} min, {f.stat().st_size / 1e9:.2f} GB")

    # length
    if a.expected:
        if total < a.expected * 0.97:
            problems.append(f"too short: {total:.0f} s of expected {a.expected:.0f} s (stalls or early stop)")
        elif total > a.expected + 120:
            problems.append(f"too long: {total:.0f} s of expected {a.expected:.0f} s (repeated or frozen parts?)")
        else:
            notes.append(f"length OK ({total:.0f} s, expected {a.expected:.0f} s)")

    # streams and sync
    sd = stream_durations(f)
    if "video" not in sd or "audio" not in sd:
        problems.append(f"missing stream(s): found {list(sd)}")
    elif abs(sd["video"] - sd["audio"]) > 1.0:
        problems.append(f"audio/video lengths differ by {abs(sd['video'] - sd['audio']):.1f} s (sync)")
    else:
        notes.append(f"audio/video in sync (differ by {abs(sd['video'] - sd['audio']):.2f} s)")

    # audio per window
    win = 120 if a.test else 1800
    levels = []
    t = 0.0
    while t < total - 1:
        mean, _ = volume(f, t, min(win, total - t))
        levels.append((t, mean))
        t += win
    silent = [(s, m) for s, m in levels if m is None or m < -60]
    for s, m in levels:
        print(f"   audio {hms(s)}-{hms(min(s + win, total))}: mean {m} dB")
    if silent and a.test:
        problems.append(f"silent audio in {len(silent)} test window(s) - sound device dropped, wrong window, or "
                        "a genuinely silent part of the video (re-test at another point if so)")
    elif silent:
        notes.append(f"{len(silent)} silent {win // 60}-min window(s) - check the long-silence list below")

    # picture: black frames mean DRM / minimised window / broken capture (limited-range black is Y=16)
    br = brightness_samples(f, total, 6 if a.test else 16)
    dark = sum(v < 17 for v in br)
    if br and dark / len(br) > 0.8:
        problems.append(f"picture is black in {dark}/{len(br)} samples (DRM-protected video or minimised window)")
    else:
        notes.append(f"picture OK ({dark}/{len(br)} sampled frames dark)")

    # black bars: the recorder crops to the video, so big bars mean a wrong crop or bars in the source
    bars = black_bars(f, total)
    if bars:
        fw, fh, pw, ph = bars
        if pw < fw * 0.95 or ph < fh * 0.95:
            notes.append(f"black bars: frame {fw}x{fh}, picture about {pw}x{ph} (bars in the source video, "
                         "or the crop missed - look at a frame)")
        else:
            notes.append(f"no black bars ({fw}x{fh})")

    # long digital silences (usually breaks/breakout rooms in the source)
    if not a.test:
        long_quiet = silences(f, 120, noise_db=-85)
        if long_quiet:
            notes.append("digital silence over 2 min (usually in the source): " +
                         ", ".join(f"{hms(s)}-{hms(e)}" for s, e in long_quiet))

    # cut points of a trimmed copy
    if a.seams:
        import trim_silence as ts
        orig_total = duration(a.seams)
        segs = ts.keep_segments(orig_total, silences(a.seams, a.min_minutes * 60), a.after, a.before)
        expect = sum(b - s for s, b in segs)
        if abs(expect - total) > 2:
            problems.append(f"trimmed length {total:.1f} s, expected {expect:.1f} s")
        pos = 0.0
        for i, (s, b) in enumerate(segs[:-1], 1):
            pos += b - s
            before = volume(f, pos - a.after, a.after)[1]
            after_talk = volume(f, pos + a.before, 4)[1]
            print(f"   cut {i} at {hms(pos)}: loudest before cut {before} dB, talking after {after_talk} dB")
            if before is not None and before > -35:
                problems.append(f"cut {i} at {hms(pos)}: sound right before the cut ({before} dB) - speech clipped?")
            if after_talk is not None and after_talk < -45:
                notes.append(f"cut {i} at {hms(pos)}: quiet after the cut ({after_talk} dB) - talk starts later")

    if a.sheet:
        if contact_sheet(f, total, a.sheet):
            notes.append(f"frames to look at: {a.sheet}")
        else:
            notes.append("could not make the contact sheet")

    for n in notes:
        print("  ok:", n)
    for p in problems:
        print("  PROBLEM:", p)
    print("RESULT:", "PASS" if not problems else "FAIL")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
