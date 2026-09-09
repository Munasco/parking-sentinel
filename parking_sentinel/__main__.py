import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from .core import AmpCheckout, DryRun, ParkGraph, ServiceError, Sessions, analyze, decide, request_json


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Snapshot → vision → decision → parking session")
    parser.add_argument("command", choices=["health", "search", "get", "detect", "demo", "status", "end", "reconcile"])
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lng", type=float)
    parser.add_argument("--radius-km", type=float, default=5)
    parser.add_argument("--session-id")
    parser.add_argument("--image", action="append", default=[], help="Local JPEG/PNG; repeat up to four times")
    parser.add_argument("--observation", help="Local JSON observation for testing without a VLM")
    parser.add_argument("--provider", choices=["dry-run", "amp", "parkgraph"], default="dry-run")
    parser.add_argument("--state", default=".local/sessions.sqlite3")
    parser.add_argument("--confirmed-ended", action="store_true", help="Attest provider has no active session before clearing local state")
    args = parser.parse_args()
    store = None
    try:
        if args.command == "health":
            print(json.dumps(request_json(ParkGraph.base + "/health")))
            return 0
        if args.command == "search":
            if args.lat is None or args.lng is None:
                raise ValueError("Search requires --lat and --lng")
            print(json.dumps(ParkGraph().search(args.lat, args.lng, args.radius_km)))
            return 0
        if args.command == "get":
            if not args.session_id:
                raise ValueError("Get requires --session-id")
            print(json.dumps(ParkGraph().get(args.session_id)))
            return 0
        if args.command == "demo" and args.provider != "dry-run":
            raise ValueError("Demo only supports dry-run")
        provider = {"dry-run": DryRun, "amp": AmpCheckout, "parkgraph": ParkGraph}[args.provider]()
        lot = os.environ.get("PARKING_LOT_ID", "demo-lot" if args.provider != "parkgraph" else "")
        plate = os.environ.get("PARKING_PLATE", "DEMO000" if args.provider != "parkgraph" else "")
        if not lot.strip() or not plate.strip():
            raise ValueError("Set PARKING_LOT_ID and PARKING_PLATE")
        store = Sessions(args.state)
        if args.command in ("detect", "demo"):
            if args.command == "demo":
                observation = dict(plate="", confidence=0.99, white=True, nissan=True, roof_lpr=True, blue_side_marking=True)
            elif bool(args.image) == bool(args.observation):
                raise ValueError("Provide either --image or --observation")
            elif args.image:
                observation = analyze(args.image)
            else:
                observation = json.loads(Path(args.observation).read_text())
            known = []
            if os.environ.get("KNOWN_PLATES_FILE"):
                known = json.loads(Path(os.environ["KNOWN_PLATES_FILE"]).read_text())
                if not isinstance(known, list) or not all(isinstance(p, str) for p in known):
                    raise ValueError("Known plates file must be a JSON array of strings")
            reason = decide(observation, known, float(os.environ.get("CONFIDENCE_THRESHOLD", "0.98")))
            result = store.start(provider, lot, plate) if reason in ("plate_match", "visual_match") else {"action": "ignored"}
            result["reason"] = reason
        elif args.command == "status":
            result = {"status": store.status(provider, lot, plate)}
        elif args.command == "end":
            result = store.end(provider, lot, plate)
        else:
            if not args.confirmed_ended:
                raise ValueError("Check provider dashboard, end any session, then use --confirmed-ended")
            result = store.reconcile(provider, lot, plate)
        print(json.dumps(result))
        return 0
    except (ValueError, ServiceError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    except (OSError, sqlite3.Error):
        print(json.dumps({"error": "Local file unavailable; check configuration and permissions"}), file=sys.stderr)
        return 1
    finally:
        if store:
            store.close()


if __name__ == "__main__":
    sys.exit(main())
