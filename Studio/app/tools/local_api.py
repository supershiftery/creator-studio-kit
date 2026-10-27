"""Call THIS machine's Studio API from the command line (used over SSH by the other machine, remote.py).

    python local_api.py GET  "jobs"
    python local_api.py POST "project/run?id=abc" <base64 of the JSON body>
Prints the JSON reply; exit 1 with the error on stderr."""
import base64
import json
import os
import sys
import urllib.error
import urllib.request

PORT = int(os.environ.get("STUDIO_PORT", "8765"))


def main(a):
    method, path = a[0].upper(), a[1].lstrip("/")
    body = json.loads(base64.b64decode(a[2]).decode("utf-8")) if len(a) > 2 and a[2] else ({} if method == "POST" else None)
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/{path}", data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=float(os.environ.get("LOCAL_API_TIMEOUT", "120"))) as r:
            # raw UTF-8 bytes: an SSH session's console is cp1252 and can't print every title ("→" broke it, 2026-10-25)
            sys.stdout.buffer.write(r.read())
            sys.stdout.flush()
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}")
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
