# Camera diagnostic probes

Tools written during the (unsuccessful) investigation of the onboard camera. See [docs/CAMERA.md](../../docs/CAMERA.md) for findings.

All are stdlib-only Python 3. Run them while joined to the car's WiFi.

| Script | Purpose |
|---|---|
| `batmobile_recon.py` | General network recon — port scan, UDP probe, broadcast listen |
| `batmobile_camera_test.py` | Replays the app's CGI warm-up, then one clean frame-grab attempt (needs ffmpeg) |
| `batmobile_rtsp_probe.py` | Hand-rolled RTSP handshake over UDP and TCP; reports whether any RTP arrives |
| `batmobile_camera_probe2.py` | Port scan, full SDP dump, path-validation test, ONVIF probe |
| `batmobile_camera_probe3.py` | CGI name discovery, the `?cmd=` API, SET_PARAMETER + keepalives |
| `batmobile_camera_probe4.py` | Fixed-RTP-port and fixed-destination-IP tests |
| `batmobile_camera_probe5.py` | NAT punch packets, RTCP receiver reports, multicast |

## ⚠️ Before you run these

**Power-cycle the car first.** The camera holds a dead RTSP session for 60 seconds, so back-to-back attempts give false negatives.

**Run one at a time.** The camera serves very few concurrent connections.

**Don't run aggressive threaded port scans.** `batmobile_camera_probe2.py` uses 150 threads and *wedged the camera's HTTP server*, making every subsequent probe return false negatives until a power-cycle. `probe3` onward are deliberately gentle — one connection at a time with pauses. Learn from this.

`batmobile_camera_probe3.py` has an `--enumerate-cmd` flag that walks numeric API commands. **Read the warning in its source first** — command 301 writes the WiFi AP config, so neighbouring commands may also write settings. Recoverable with a factory reset, but don't run it casually.
