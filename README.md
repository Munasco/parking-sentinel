# Parking Sentinel

An event-driven parking prototype: **dashcam snapshot → vision model → confidence check → parking session API**.

Python 3.9+, standard library only. No continuously streamed video. No private camera footage, real plate lists, location history, or credentials in this repository. The included one-minute parking video is generated test footage; its provenance is in `parking_sentinel/media/ATTRIBUTION.md`.

## What works

- Analyze one to four locally supplied JPEG/PNG snapshots with an Ollama vision model.
- Match locally configured plates, then fall back to a strict combination of visual attributes.
- Validate model output before acting; reject low-confidence or malformed observations.
- Create/end sessions through a **Park Graph** API adapter; search lots and read session details directly.
- Optionally open **AMP Park / AIMS Mobile Pay**, a real hosted parking payment website.
- Persist session state in SQLite so repeated detections and process restarts do not repeat a checkout or session request.
- Run an entirely offline demo using synthetic observations.

## Run

### Single-file Gemini preview — no Python or Ollama

Download [`parking-preview.html`](parking-preview.html) and the [generated one-minute parking clip](parking_sentinel/media/parking-enforcement-staged-60s.mp4), or clone this repo. Open the HTML in a browser, choose the included MP4 from `parking_sentinel/media/`, and enter your own Gemini API key in the page. Click **Connect / load models**, choose an image-capable model, then **Start 60-second Gemini test**. The MP4 is already generated and committed: a fixed parked-car view, ordinary vehicles, and a staged white patrol-style vehicle with roof cameras. No video-generation service is needed to play it.

No installation, WebGPU, video hosting, or local server is required. The file is self-contained; recognition requires internet access and a usable Gemini API key. Keys are held in page memory only and can be removed with **Forget key**. No credentials are bundled in the file or saved in browser storage. This is a personal bring-your-own-key demo, not a place to distribute a shared API credential.

The browser detects pixel changes, samples at most one JPEG every five seconds, sends up to 12 images to Google's `generateContent` API, validates the returned observation, and applies the same plate/appearance rules as the Python version. Repeated matches are suppressed in page memory. Playback stops at 60 seconds or the end of a shorter clip. No payment call exists. Models and API quotas may vary; slow inference can skip events. The default confidence cutoff is 0.98 and can be changed visibly before a run. In an in-app browser test on the included clip, 0.98 rejected the patrol frames as uncertain; a second run at 0.95 sent 11 frames, flagged the patrol at 37.5 seconds, and suppressed a repeat at 48.1 seconds while earlier ordinary cars were ignored. These are observed results for this generated clip, not a guarantee for future runs or real footage.

API references: [Gemini image understanding](https://ai.google.dev/gemini-api/docs/image-understanding), [generateContent structured output](https://ai.google.dev/gemini-api/docs/generate-content/structured-output), [model listing](https://ai.google.dev/api/models).

### Local video preview

```sh
python3 -m parking_sentinel simulate
```

Open **http://127.0.0.1:8765**. The generated one-minute parking clip is already loaded. Preview it with the video controls, or enter your Gemini key, click **Connect / load models**, and then **Start 60-second Gemini test**. No Ollama or WebGPU is required. The server only serves the page and MP4; sampled images go directly from your browser to Gemini.

The player compares decoded frames once per second. Motion triggers a JPEG sample at most once per five seconds, with up to 12 requests per run. Video plays at 1× while inference runs. The displayed observation, confidence check, and duplicate suppression use the model's actual response. There are no scripted scenarios or timed detection results. API latency can cause a brief event to be missed. A generated clip tests a staged case and does not establish accuracy on real parking footage.

Playback is a prerecorded clip replayed in real time, not a live dashcam connection. Motion alone does not identify enforcement. Recognition requires a usable Gemini API key; playback does not. No payment or checkout endpoint is available in this preview.

The generated test MP4 is the sole media exception in `.gitignore`; locally selected videos and snapshots are not committed. See [media provenance](parking_sentinel/media/ATTRIBUTION.md).

For the smaller terminal-only demo:

```sh
python3 -m parking_sentinel demo
python3 -m parking_sentinel status
python3 -m parking_sentinel end
python3 -m unittest discover -s tests -v
```

The demo simulates a detection and session. A second detection is suppressed until the session ends. It makes no network requests and spends no money.

To classify snapshots, set `OLLAMA_MODEL` to an installed vision-capable model, then run:

```sh
python3 -m parking_sentinel detect --image /path/to/snapshot.jpg
```

The default provider is always `dry-run`. `OLLAMA_URL` defaults to `http://localhost:11434`. Snapshots are sent only to that configured vision endpoint and are not copied or logged by this program. Inference speed depends on the model and hardware; Raspberry Pi latency has not been measured.

## Real parking providers

### Park Graph — API adapter

Set `PARKGRAPH_API_KEY`, `PARKING_LOT_ID`, and `PARKING_PLATE` privately. Get a provider-issued key from the [Park Graph dashboard](https://parkgraph.com/dashboard); sandbox and production keys use the same API base URL.

```sh
python3 -m parking_sentinel health
python3 -m parking_sentinel search --lat 39.74 --lng -104.99
python3 -m parking_sentinel detect --image /path/to/snapshot.jpg --provider parkgraph
python3 -m parking_sentinel status --provider parkgraph
python3 -m parking_sentinel get --session-id YOUR_SESSION_ID
python3 -m parking_sentinel end --provider parkgraph
```

`health`, `search`, and `get` always address Park Graph. Search coordinates above are illustrative. `get` deliberately prints the provider's session details and may contain private data; do not share its output. `status` reads the local duplicate-prevention guard, not live provider state. Other normal command output omits private receipts.

The adapter uses the documented `POST /sessions` payload (`lot_id`, `plate`) and `POST /sessions/end` payload (`session_id`, `session_code`). It accepts a session object directly or under `session`, matching the envelope shown in the provider SDK documentation. A string `id` is required; `session_code` is required to end a session. An unrecognized response leaves the request pending for manual reconciliation.

**Integration status:** the public health endpoint was reachable on September 9, 2026. An unauthenticated lot search returned HTTP 401, despite the reference describing that endpoint as public. Authenticated creation, receipt shape, billing, and lot coverage have not been verified with a provider account. The automated tests use a local HTTP fixture; they are not proof of live payment compatibility.

This is a start/stop adapter, not a fixed 15-minute purchase API. Sessions do not automatically expire locally. End the session explicitly through the provider when finished. No claim is made that Park Graph supports your lot or interoperates with AMP Park.

### AMP Park — hosted checkout

```sh
python3 -m parking_sentinel detect --image /path/to/snapshot.jpg --provider amp
```

A confirmed detection opens [AIMS Mobile Pay](https://aimsmobilepay.com/) in the system browser. Sign in, select the correct posted parking location, choose a duration, and complete payment there. An existing AMP URL can be configured through `AMP_CHECKOUT_URL`.

**Opening checkout is not proof of payment.** Local state stays `awaiting_payment`; it never claims you have paid. This path requires a graphical browser on the machine running the command. It does not fill forms, keep payment credentials, or perform headless purchases. A headless Pi requires an additional browser/notification bridge.

After the actual parking session has ended, clear the local checkout guard:

```sh
python3 -m parking_sentinel reconcile --provider amp --confirmed-ended
```

## Configuration and state

Copy `.env.example` to `.env`, edit it, and load it with `source .env` if desired. The CLI reads environment variables; it does not automatically read `.env`.

| Variable | Purpose |
| --- | --- |
| `OLLAMA_MODEL` | Installed vision model; required for image analysis |
| `OLLAMA_URL` | Vision endpoint, default `http://localhost:11434` |
| `CONFIDENCE_THRESHOLD` | Decision threshold, default `0.98` |
| `KNOWN_PLATES_FILE` | Private JSON array of plates; optional |
| `AMP_CHECKOUT_URL` | AMP HTTPS checkout URL; defaults to the website root |
| `PARKGRAPH_API_KEY` | Provider-issued API credential |
| `PARKING_LOT_ID` | Supported provider lot identifier |
| `PARKING_PLATE` | Vehicle receiving the parking session |

`--observation examples/observation.json` exercises the decision pipeline without a model. These values are synthetic. The vision model is not trained or calibrated by this repository; its confidence score is a heuristic, not a measured error rate. No pedestrian classifier is included.

The dashcam must supply snapshots to the command; camera firmware/export integration is device-specific and is not included. Invoke once per camera event. No background watcher or scheduler is installed. The simulator's local video player is a test harness for that event-to-snapshot boundary, not a direct live dashcam connection.

State defaults to `.local/sessions.sqlite3`; use `--state` for another path. A pending record is committed before each network write. Timeouts, invalid receipts, and crashes keep the guard in place. Requests are never automatically retried. Inspect the provider dashboard and resolve any session before using `reconcile --confirmed-ended`.

Receipts remain in the private local database while active; normal detection output omits plates, images, credentials, and raw receipts. The explicit `get` command prints private provider details. `.gitignore` excludes common media, databases, `.env` files, `private/`, and `snapshots/`. Keep custom sensitive files in those directories.

## Sources

- [AIMS Mobile Pay service description](https://www.aimsparking.com/amp-terms-conditions/)
- [Park Graph REST API](https://parkgraph.com/developers/api)
- [Park Graph SDK response examples](https://parkgraph.com/developers/sdk)
- [Park Graph API reference](https://parkgraph.com/developers/api-reference)
- [Ollama chat API](https://docs.ollama.com/api/chat)

This repository publishes a prototype, not the original field-test results. No claims of zero false positives, guaranteed response time, savings, or completed real-world payments are made.
