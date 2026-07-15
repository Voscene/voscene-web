Video demo drop location
========================

Put the /features demo video here as:

    voscene-demo.mp4

The <video> block on /features (templates/public/features.html,
just under the page intro) already points at
/static/videos/voscene-demo.mp4 with muted autoplay + loop, and
shows EPPO-Graphic-Switcher.png as the poster until the file exists.
Drop the mp4 in and it plays automatically — no template change needed.

Recommended encoding (keep it small — it ships in the git repo):
  - Format:      MP4 (H.264 / AAC), or add a .webm source for smaller size
  - Length:      15-30 s loop (silent — it plays muted)
  - Resolution:  1280x720 (720p) is plenty
  - Bitrate:     aim for a final file under ~8 MB
  - Content:     screen recording of the Graphic Switcher / Audio Mixer
                 (drag a source onto a screen, adjust a level) — matches
                 the poster image.

Optional: also drop voscene-demo.webm next to it and add a second
<source ... type="video/webm"> before the mp4 source for better
compression on supporting browsers.
