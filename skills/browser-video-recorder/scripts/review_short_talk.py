"""One review video of the short talk bits that sit inside long silent blocks (exercise time).

Lets the user decide whether those bits matter before trimming - the agent can't hear audio.
Each bit gets a label (number, file, time, length) and a few seconds of lead-in.

  python review_short_talk.py --input-dir <recordings> --output "<dir>\\Review - short talk.mp4"
  python review_short_talk.py --input-dir <rec> --output <file> --min-minutes 4 --max-talk 60
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import duration, silences  # noqa: E402

FONT = "C\\:/Windows/Fonts/arialbd.ttf"


def hms(t):
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"


def short_bits(path, min_block_s, max_talk_s):
    """Talk bits shorter than max_talk_s between silences (>= 60 s) whose chain totals >= min_block_s."""
    spans = silences(path, 60)
    chains, cur = [], None
    for s, e in spans:
        if cur and s - cur["end"] < max_talk_s:
            cur["bits"].append((cur["end"], s - cur["end"]))
            cur["silent"] += e - s
            cur["end"] = e
        else:
            if cur:
                chains.append(cur)
            cur = {"end": e, "silent": e - s, "bits": []}
    if cur:
        chains.append(cur)
    return [b for c in chains if c["silent"] >= min_block_s for b in c["bits"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--pattern", default="*.mp4")
    ap.add_argument("--min-minutes", type=float, default=4, help="silent block size worth cutting")
    ap.add_argument("--max-talk", type=float, default=60, help="talk shorter than this counts as a 'short bit'")
    ap.add_argument("--lead", type=float, default=3)
    ap.add_argument("--tail", type=float, default=2)
    a = ap.parse_args()

    bits = []
    for src in sorted(a.input_dir.glob(a.pattern)):
        if src.name.startswith(("TEST - ", "Review - ")):
            continue
        bits += [(src, at, ln) for at, ln in short_bits(src, a.min_minutes * 60, a.max_talk)]
    if not bits:
        print("no short talk bits inside long silent blocks")
        return

    work = Path(tempfile.mkdtemp(prefix="bvr_review_"))
    parts = []
    for n, (src, at, ln) in enumerate(bits, 1):
        label = work / f"label{n}.txt"
        label.write_text(f"Bit {n} of {len(bits)}  -  {src.stem[:40]}  -  at {hms(at)}  -  {ln:.0f} s of talk",
                         encoding="utf-8")
        lab = str(label).replace("\\", "/").replace(":", "\\:")
        vf = (f"scale=1920:1080,drawtext=fontfile='{FONT}':textfile='{lab}':fontsize=36:fontcolor=white:"
              "box=1:boxcolor=black@0.7:boxborderw=12:x=30:y=30")
        part = work / f"part{n:03d}.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(at - a.lead, 0):.2f}", "-i", str(src),
                        "-t", f"{ln + a.lead + a.tail:.2f}", "-vf", vf, "-r", "30", "-c:v", "libx264",
                        "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000",
                        "-ac", "2", "-b:a", "160k", str(part)], check=True)
        parts.append(part)
        print(f"{n:3d}. {src.stem} at {hms(at)} ({ln:.0f} s)", flush=True)
    lst = work / "list.txt"
    lst.write_text("".join(f"file '{str(p).replace(chr(92), '/')}'\n" for p in parts), encoding="utf-8")
    a.output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                    "-movflags", "+faststart", str(a.output)], check=True)
    for p in work.iterdir():
        p.unlink()
    work.rmdir()
    print(f"saved {a.output}: {len(bits)} bits, {duration(a.output) / 60:.1f} min")


if __name__ == "__main__":
    main()
