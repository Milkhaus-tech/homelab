#!/usr/bin/env python3
"""Log the Instagram burner in using Bitwarden's browser shortcut."""

import json
import os
import subprocess
import sys
import time
import urllib.request

import websocket


LOGIN_URL = "https://www.instagram.com/accounts/login/"
USER_FIELD = "document.querySelector('input[name=username], input[name=email]')"
PASS_FIELD = "document.querySelector('input[name=password], input[name=pass]')"
# Saved-profile picker hides the form; always take "Use another profile" so a remembered account is never used.
OTHER_PROFILE = "[...document.querySelectorAll('[role=button],button')].find(b => b.innerText.trim() === 'Use another profile')?.click()"


def username_matches(value, expected):
    return value.casefold() == expected.casefold()


def url_failure(url):
    lowered = url.lower()
    if any(part in lowered for part in ("/challenge/", "/two_factor", "/accounts/suspended", "/auth_platform/codeentry")):
        return "instagram wants a challenge or 2FA"
    return None


class CDP:
    def __init__(self, connection):
        self.connection = connection
        self.next_id = 1

    def call(self, method, params=None, session_id=None):
        message_id = self.next_id
        self.next_id += 1
        message = {"id": message_id, "method": method}
        if params is not None:
            message["params"] = params
        if session_id is not None:
            message["sessionId"] = session_id
        self.connection.send(json.dumps(message))
        while True:
            reply = json.loads(self.connection.recv())
            if reply.get("id") != message_id:
                continue
            if "error" in reply:
                raise RuntimeError(reply["error"].get("message", f"CDP {method} failed"))
            return reply.get("result", {})


def evaluate(cdp, session_id, expression):
    result = cdp.call(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True},
        session_id,
    )
    if "exceptionDetails" in result:
        raise RuntimeError("page evaluation failed")
    return result.get("result", {}).get("value")


def has_session(cdp):
    cookies = cdp.call("Storage.getCookies").get("cookies", [])
    return any(
        cookie.get("name") == "sessionid"
        and cookie.get("domain", "").lower().endswith("instagram.com")
        for cookie in cookies
    )


def press_bitwarden():
    environment = os.environ.copy()
    environment.update(DISPLAY=":0", XAUTHORITY="/home/noah/.Xauthority")
    subprocess.run(
        [
            "/usr/bin/xdotool",
            "search", "--onlyvisible", "--name", "Instagram",
            "windowactivate", "--sync",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
    )
    subprocess.run(
        ["/usr/bin/xdotool", "key", "--clearmodifiers", "ctrl+shift+l"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
    )


def page_state(cdp, session_id):
    return evaluate(
        cdp,
        session_id,
        """(() => {
            const alert = document.querySelector('#slfErrorAlert, [role="alert"]');
            return {
                url: location.href,
                error: alert ? alert.innerText.trim().replace(/\\s+/g, ' ').slice(0, 120) : ''
            };
        })()""",
    )


def login(port, expected_login):
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/json/version", timeout=5
    ) as response:
        debugger_url = json.load(response)["webSocketDebuggerUrl"]
    connection = websocket.create_connection(debugger_url, suppress_origin=True, timeout=10)
    cdp = CDP(connection)
    target_id = None
    leave_open = False
    try:
        target_id = cdp.call("Target.createTarget", {"url": LOGIN_URL})["targetId"]
        session_id = cdp.call(
            "Target.attachToTarget", {"targetId": target_id, "flatten": True}
        )["sessionId"]
        cdp.call("Target.activateTarget", {"targetId": target_id})

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if has_session(cdp):
                return
            if evaluate(cdp, session_id, f"!!{USER_FIELD}"):
                break
            evaluate(cdp, session_id, OTHER_PROFILE)
            time.sleep(0.25)
        else:
            raise RuntimeError("instagram login page did not load")

        focus = f"{USER_FIELD}.focus()"
        for _ in range(5):
            value = ""
            password_filled = False
            evaluate(cdp, session_id, focus)
            press_bitwarden()
            fill_deadline = time.monotonic() + 5
            while time.monotonic() < fill_deadline:
                value = evaluate(
                    cdp, session_id, f"{USER_FIELD}.value"
                )
                if value and username_matches(value, expected_login):
                    password_filled = evaluate(
                        cdp,
                        session_id,
                        f"{PASS_FIELD}.value.length > 0",
                    )
                    if password_filled:
                        break
                elif value:
                    break
                time.sleep(0.2)
            if value and username_matches(value, expected_login) and password_filled:
                break
        else:
            raise RuntimeError("bitwarden did not fill the burner (vault locked?)")

        evaluate(
            cdp,
            session_id,
            "document.querySelector('button[type=submit], input[type=submit]').click()",
        )
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if has_session(cdp):
                return
            state = page_state(cdp, session_id)
            failure = url_failure(state["url"])
            if failure:
                leave_open = True
                raise RuntimeError(failure)
            if state["error"]:
                raise RuntimeError(f"instagram rejected the login: {state['error']}")
            time.sleep(0.5)
        raise RuntimeError("login timed out")
    finally:
        if target_id is not None and not leave_open:
            try:
                cdp.call("Target.closeTarget", {"targetId": target_id})
            except Exception:
                pass
        connection.close()


def main():
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <cdp_port> <expected_login>", file=sys.stderr)
        return 1
    try:
        login(*sys.argv[1:])
        return 0
    except Exception as exc:
        print(str(exc).splitlines()[0], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
