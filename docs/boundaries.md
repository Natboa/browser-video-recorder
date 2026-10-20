# Boundaries

This skill records what you are **already allowed to watch**, the same way you could with OBS or
Xbox Game Bar by hand. It is built to stay that way:

- **Official downloads first, recording second.** If the site itself offers a video as a download
  (a Download button or link, a "download options" list), it is downloaded, with your signed-in
  session when the site requires one, exactly as clicking that link would. If the download is
  refused, the video is recorded instead. For a cloud folder (OneDrive, Google Drive, Dropbox) it
  tells you to use that service's own Download.
- **Never pulls a stream out of a player.** It doesn't fetch a player's video address or get around
  a site that turned downloads off; that is what recording by playing is for.
- **No DRM circumvention.** Protected streams (Netflix-style) record as black frames by design. The
  recorder detects encrypted media and stops instead of trying to get around it.
- **Personal use.** Recordings are for your own offline viewing. Check the site's terms; some forbid
  recording.
