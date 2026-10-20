# Trimming silences

```powershell
python skills\browser-video-recorder\scripts\trim_silence.py --input-dir "D:\Courses\My course" --dry-run   # see what would be cut
python skills\browser-video-recorder\scripts\trim_silence.py --input-dir "D:\Courses\My course" --min-minutes 4 --after 3 --before 2
python skills\browser-video-recorder\scripts\review_short_talk.py --input-dir "D:\Courses\My course" --output "D:\Courses\My course\Without silence\Review.mp4"
```

Originals are never modified. Trimmed copies are re-encoded (libx264, ~13× real time) so every cut
lands exactly where intended. In real course recordings this removed 20–45% of each lecture.
