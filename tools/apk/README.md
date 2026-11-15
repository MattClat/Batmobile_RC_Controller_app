# APK analysis tools

String-extraction utilities written while reverse-engineering the original app. See [docs/REVERSE_ENGINEERING.md](../../docs/REVERSE_ENGINEERING.md) for how they were used.

Stdlib-only Python 3. These operate on an **extracted APK directory** — no car or network needed.

| Script | Purpose |
|---|---|
| `batmobile_lib_scan.py` | Walks every `.so` in an extracted APK and surfaces streaming/network-related strings, with URL-like hits flagged first |
| `batmobile_rtsp_url_scan.py` | Focused scan of `librtspclient.so` for the stream URL and ffmpeg options, filtering out generic ffmpeg symbols |

## Usage

```bash
python batmobile_lib_scan.py "/path/to/extracted_apk"
python batmobile_rtsp_url_scan.py "/path/to/extracted_apk"
```

Extract an APK by renaming it to `.zip` and unzipping, or let jadx do it.

## What they found

Both confirmed a **negative** result, which was still useful: the app's video path is YETi CGI's `RtspClient.cpp` built on stock ffmpeg, containing no hardcoded stream URL and no vendor-specific start command. The URL is assembled at runtime.

That's what pushed the camera investigation away from static analysis and toward live packet capture.

Note that the **control** protocol was not found this way — it came from the Java bridge in jadx, and the WiFi password came from parsing `global-metadata.dat`. See the reverse-engineering doc.
