# Compatibility: which sites work

Anything that plays in an HTML5 `<video>` element without DRM or
bot protection. Tested end-to-end (a test clip per site, checked by numbers *and* by looking at
its frames), over 35 sites in October 2026:

| Site / player | What made it tricky | Result |
|---|---|---|
| Zoom cloud-recording replays (course platform) | ~3 h lectures, overnight, player stops 1 s before the end | ✅ |
| Vimeo (vimeo.com page) | streaming player that ignores direct jumps | ✅ |
| Internet Archive (page and embedded) | video hidden inside a web component | ✅ |
| Wikimedia Commons, Wikipedia | real player created only after a click | ✅ |
| PeerTube (page and embedded) | peer-to-peer streaming, embed waits for its own play button | ✅ |
| TED | starts muted, ads in a second video element, takes over full screen | ✅ |
| NASA SVS, NASA+ | hidden gallery videos; NASA+ keeps its player in a hidden pop-up | ✅ |
| HLS (hls.js), DASH (Shaka, dash.js 4K) | streams break if touched while they set up; 4K scaled to 1080p | ✅ |
| Apple WWDC, Microsoft Learn, media.ccc.de, CERN lectures | conference/course talks; CERN's player is an iframe that needs a click | ✅ |
| ESA, Dailymotion, Odysee, Bilibili, Twitch replays, Wistia (4K) | assorted players, a 2.5 h live-stream replay | ✅ |
| Plyr / Video.js, Mux Player | captions turned off on request; 24-s video in a web component | ✅ |
| NFB (4:3 film), ARD Mediathek (German), KAN 11 (Hebrew), Euronews (heavy ads), C-SPAN | "Watch now" button (`play_selector`), foreign-language pages, ad-heavy page | ✅ |
| **YouTube** | in the October 2026 test the site cut playback off in the automated browser after ~40 s | ⚠️ tried like any site; stops and saves what it has if cut off (YouTube Premium downloads are the official route) |
| Library of Congress, Europeana | "checking your browser" wall that needs a person | ❌ unless you pass it yourself in the recorder's window |
| Vimeo players embedded in real articles (Colossal) | lazy-loaded below the fold; Play button off-screen; `play()` first would jam it | ✅ |
| OneDrive / SharePoint video player (a file opened in the browser) | signed-in work account; 3-hour file, jump to 30:00 | ✅ (for files you may download, the finder tells you to download instead) |
| Dailymotion players embedded on other pages | refuses to play outside the sites its owner approved ("Forbidden") | ❌ open the video on dailymotion.com instead |
| DW | its player never takes over from the browser's failed HLS attempt (stream itself is fine) | ❌ not solved |
| Netflix-style DRM services | encrypted video records black | ❌ not supported, by design |

The **one-link finder** was tested on Microsoft Learn shows, media.ccc.de conferences, TED playlists,
Apple's video topics, Wistia series, Internet Archive collections, KAN series and YouTube playlists. On Vimeo channels the menu can outrank the videos: pick the right
link group (`--group N`). Cloud storage folders (OneDrive etc.) are recognised and sent to download.

Ads are never recorded as part of the video: the recorder follows the main video and pauses
recording while it isn't playing. Set `expected_minutes` per video if a page could show a
different video first (trailer, intro).
