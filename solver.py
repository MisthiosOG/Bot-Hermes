# -*- coding: utf-8 -*-
import os, requests, time
class MuaraicaptchaSolver:
    """Solve Cloudflare Turnstile via Muaraicaptcha API."""

    def __init__(
        self,
        api_key: str = "",
        *,
        timeout: float = 45.0,
        poll_interval: float = 2.0,
        debug: bool = False,
        fallback_solver=None,  # BrowserTurnstileSolver for balance fallback
        **kwargs,  # absorb BrowserTurnstileSolver kwargs
    ):
        self._api_key = api_key or os.environ.get("MUARAI_API_KEY", "")
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._debug = debug
        self._base = "https://api.muaraicaptcha.com/v1"
        self._fallback = fallback_solver
        self._balance_exhausted = False

    def _check_balance(self) -> float:
        """Check remaining balance."""
        try:
            r = requests.post(
                f"{self._base}/getBalance",
                json={"clientKey": self._api_key},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            return float(data.get("balance", 0))
        except Exception:
            return -1

    def solve_turnstile(self, website_url: str, website_key: str, **kwargs) -> str:
        if not self._api_key:
            if self._fallback:
                return self._fallback.solve_turnstile(website_url, website_key, **kwargs)
            raise ValueError("MUARAI_API_KEY not set")

        if self._balance_exhausted:
            if self._fallback:
                return self._fallback.solve_turnstile(website_url, website_key, **kwargs)
            raise BalanceExhaustedError("muarai balance exhausted, no fallback")

        # create task
        r = requests.post(
            f"{self._base}/createTask",
            json={
                "clientKey": self._api_key,
                "task": {
                    "type": "TurnstileTaskProxyless",
                    "websiteURL": website_url,
                    "websiteKey": website_key,
                },
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("errorId", 1) != 0:
            err = data.get("errorDescription", "unknown")
            if "balance" in err.lower() or "zero" in err.lower():
                self._balance_exhausted = True
                if self._fallback:
                    print("[muarai] balance exhausted, fallback to browser")
                    return self._fallback.solve_turnstile(website_url, website_key, **kwargs)
                raise BalanceExhaustedError(f"muarai balance: {err}")
            raise RuntimeError(f"createTask: {err}")

        task_id = data.get("taskId")
        if not task_id:
            raise RuntimeError("no taskId")

        if self._debug:
            print(f"[muarai] taskId={task_id}")

        # poll
        deadline = time.time() + self._timeout
        while time.time() < deadline:
            time.sleep(self._poll_interval)
            r = requests.post(
                f"{self._base}/getTaskResult",
                json={"clientKey": self._api_key, "taskId": task_id},
                timeout=15,
            )
            r.raise_for_status()
            res = r.json()

            if res.get("status") == "ready":
                token = res.get("solution", {}).get("token", "")
                if token:
                    if self._debug:
                        print(f"[muarai] solved in {time.time() - (deadline - self._timeout):.1f}s")
                    return token
                raise RuntimeError("ready but no token")

            if res.get("status") == "processing":
                continue

            if res.get("errorId", 0) != 0:
                err = res.get("errorDescription", "unknown")
                if "balance" in err.lower() or "zero" in err.lower():
                    self._balance_exhausted = True
                    if self._fallback:
                        print("[muarai] balance exhausted, fallback to browser")
                        return self._fallback.solve_turnstile(website_url, website_key, **kwargs)
                    raise BalanceExhaustedError(f"muarai balance: {err}")
                raise RuntimeError(f"solve: {err}")

        raise TimeoutError(f"timeout after {self._timeout}s")


class BalanceExhaustedError(RuntimeError):
    """Muaraicaptcha balance exhausted — fallback to browser."""
    pass
