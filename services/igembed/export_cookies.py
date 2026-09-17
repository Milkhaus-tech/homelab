#!/usr/bin/env python3
"""Export Instagram cookies from Chrome's browser-level CDP endpoint."""

import json
import os
import sys
import time
import urllib.request

import websocket


def main():
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <cdp_port> <out_file>", file=sys.stderr)
        return 1
    port, output = sys.argv[1:]
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/version", timeout=5
        ) as response:
            debugger_url = json.load(response)["webSocketDebuggerUrl"]
        connection = websocket.create_connection(debugger_url, suppress_origin=True, timeout=10)
        try:
            connection.send(json.dumps({"id": 1, "method": "Storage.getCookies"}))
            while True:
                reply = json.loads(connection.recv())
                if reply.get("id") == 1:
                    break
        finally:
            connection.close()
        if "error" in reply:
            raise RuntimeError(reply["error"].get("message", "CDP cookie request failed"))
        cookies = [
            cookie for cookie in reply.get("result", {}).get("cookies", [])
            if cookie.get("domain", "").lower().endswith("instagram.com")
        ]
        if not any(cookie.get("name") == "sessionid" for cookie in cookies):
            raise RuntimeError("burner is not logged in")

        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as cookie_file:
            cookie_file.write("# Netscape HTTP Cookie File\n")
            for cookie in cookies:
                domain = cookie["domain"]
                expires = cookie.get("expires", 0)
                if expires <= 0:
                    expires = time.time() + 365 * 24 * 60 * 60
                fields = (
                    domain,
                    "TRUE" if domain.startswith(".") else "FALSE",
                    cookie.get("path", "/"),
                    "TRUE" if cookie.get("secure") else "FALSE",
                    str(int(expires)),
                    cookie.get("name", ""),
                    cookie.get("value", ""),
                )
                cookie_file.write("\t".join(fields) + "\n")
        print(f"exported {len(cookies)} cookies: {', '.join(c['name'] for c in cookies)}")
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
