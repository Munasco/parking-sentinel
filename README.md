# Parking Sentinel

An event-driven parking prototype: **dashcam snapshot → vision model → confidence check → parking session API**.

Python 3.9+, standard library only. No continuously streamed video. No private camera footage, real plate lists, location history, or credentials in this repository. The included public traffic sample is credited in `parking_sentinel/media/ATTRIBUTION.md`.

## What works

- Analyze one to four locally supplied JPEG/PNG snapshots with an Ollama vision model.
- Match locally configured plates, then fall back to a strict combination of visual attributes.
- Validate model output before acting; reject low-confidence or malformed observations.
- Create/end sessions through a **Park Graph** API adapter; search lots and read session details directly.
- Optionally open **AMP Park / AIMS Mobile Pay**, a real hosted parking payment website.
- Persist session state in SQLite so repeated detections and process restarts do not repeat a checkout or session request.
- Run an entirely offline demo using synthetic observations.

## Run

For a visual test, start the local simulator:

```sh
python3 -m parking_sentinel simulate
```

Open **http://127.0.0.1:8765** and click **Play 60-second test**. A real recorded traffic video plays at normal speed. No packages, API keys, camera, or model are required for pixel-based motion detection. Stop the server with Ctrl+C; use `--port 8766` if the port is occupied.

The player compares actual decoded video frames once per second. Significant changes trigger a snapshot, at most once per five seconds. The latest snapshot shows an outline around changed pixels and its video timestamp. The one-minute test stops automatically, with at most 12 captures. Events are derived from pixels, not a scripted timeline. The included sample contains ongoing moving traffic, so captures recur throughout the minute.

**Motion detection is not enforcement recognition.** In motion-only mode, no plate/make analysis is performed, no enforcement result is invented, and no simulated session is created. The changed-pixel outline may cover several cars, headlights, shadows, or camera movement; it is not an object detector's bounding box. The source is prerecorded video replayed in real time, not a connection to a live camera.

To test actual recognition, run Ollama with an installed vision model and export its name as `OLLAMA_MODEL` before starting the simulator. Select **Enforcement recognition** in the analysis selector. The same captured JPEGs then go through `analyze()` and the real decision/duplicate-prevention code. Model setup is not included, and the public night traffic clip is not an enforcement benchmark. Dark/blurry footage or unreadable plates should not be expected to match.

Choose **Use your own video instead** to load a local browser-compatible MP4/WebM. Each run replays its first 60 seconds (or stops at the end of a shorter clip). Only captured frames go to `OLLAMA_URL` when recognition is selected; motion-only analysis stays in the browser. The full video is never uploaded. Sampled images are visible locally in the page; temporary server-side images are removed after inference. Simulator session state is separate from normal CLI state and removed when the server stops.

**Scripted rule tests** remain available as a separate mode. Run the guided sequence to send an ordinary car, a known synthetic plate, the same plate again, and an uncertain sighting through the real Python rules. Expected actions: **ignored → simulated → suppressed → ignored**. This mode supplies observations directly and does not test recognition. `DEMO123` is the only known plate in the simulator; other plates can match only through the appearance fallback.

The simulator binds to loopback and is hardwired to `DryRun`: **it cannot buy parking or open checkout**, even with payment credentials in the environment. The 2 MB public sample is the sole media exception in `.gitignore`; your selected videos and snapshots are not committed.

Sample attribution: *Cars driving at night*, [Editor](https://www.youtube.com/user/Editor), [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/), via [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Cars_driving_at_night.webm). Changes: first 60 seconds, resized to 640 × 360, 15 fps H.264, audio removed. No endorsement implied.

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
