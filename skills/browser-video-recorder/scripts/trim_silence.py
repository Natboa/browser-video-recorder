"""Make copies of recordings with long silent stretches (exercise time, breaks) cut out.

Originals are never touched. Every bit of talking is kept; each cut starts --after seconds
after the last sound and ends --before seconds before talking resumes. Copies are re-encoded
(libx264 veryfast, ~13x real time) so the cut points are exact.

  python trim_silence.py --input-dir <recordings> --dry-run          # show what would be cut
  python trim_silence.py --input-dir <recordings>                    # -> <recordings>\\Without silence
  python trim_silence.py --input-dir <rec> --output-dir <dir> --min-minutes 4 --after 3 --before 2
  python trim_silence.py --input-dir <rec> --only "03 - " "06 - "

Wrap long runs in keep_awake.py:  python keep_awake.py run -- python trim_silence.py ...
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import duration, silences  # noqa: E402
import subprocess  # noqa: E402

ENCODE = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-r", "30",
          "-c:a", "aac", "-b:a", "160k", "-ar", "48000"]


def keep_segments(total, cuts, after, before):
    segs, start = [], 0.0
    for s, e in cuts:
        segs.append((start, s + after))
        start = e - before
    segs.append((start, total))
    return segs


def hms(t):
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"


def trim(src, out_dir, a):
    dst = out_dir / src.name
    if dst.exists() and not a.dry_run:
        print(f"skip (exists): {src.name}", flush=True)
        return
    t0 = time.time()
    total = duration(src)
    cuts = silences(src, a.min_minutes * 60)
    if not cuts:
        print(f"{src.name}: no silences over {a.min_minutes:g} min", flush=True)
        return
    segs = keep_segments(total, cuts, a.after, a.before)
    kept = sum(b - s for s, b in segs)
    if a.dry_run:
        print(f"{src.name}: {len(cuts)} cuts, {total / 60:.0f} -> {kept / 60:.0f} min", flush=True)
        for s, e in cuts:
            print(f"   cut {hms(s + a.after)} - {hms(e - a.before)} ({(e - s) / 60:.1f} min silent)")
        return
    lst = out_dir / f"_{src.stem}.concat.txt"
    path = str(src).replace("\\", "/").replace("'", r"'\''")
    lst.write_text("".join(f"file '{path}'\ninpoint {s:.3f}\noutpoint {b:.3f}\n" for s, b in segs), encoding="utf-8")
    tmp = dst.with_suffix(".partial.mp4")
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), *ENCODE,
                        "-movflags", "+faststart", str(tmp)], capture_output=True, text=True)
    lst.unlink()
    if r.returncode:
        print(f"FAILED {src.name}: {r.stderr[-400:]}", flush=True)
        tmp.unlink(missing_ok=True)
        return
    tmp.replace(dst)
    print(f"{src.name}: cut {len(cuts)} silences, {total / 60:.0f} -> {duration(dst) / 60:.1f} min "
          f"(expected {kept / 60:.1f}), {dst.stat().st_size / 1e9:.2f} GB, took {(time.time() - t0) / 60:.0f} min",
          flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True, type=Path)
    ap.add_argument("--output-dir", type=Path, help="default: <input-dir>\\Without silence")
    ap.add_argument("--pattern", default="*.mp4")
    ap.add_argument("--min-minutes", type=float, default=4)
    ap.add_argument("--after", type=float, default=3, help="seconds kept after the last sound")
    ap.add_argument("--before", type=float, default=2, help="seconds kept before talking resumes")
    ap.add_argument("--only", nargs="*", help="file name prefixes")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    out_dir = a.output_dir or a.input_dir / "Without silence"
    out_dir.mkdir(parents=True, exist_ok=True)
    for src in sorted(a.input_dir.glob(a.pattern)):
        if src.name.startswith("TEST - ") or (a.only and not any(src.name.startswith(o) for o in a.only)):
            continue
        trim(src, out_dir, a)


if __name__ == "__main__":
    main()
