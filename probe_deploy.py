# -*- coding: utf-8 -*-
"""Probe langka: login via OTP ke akun order, dump deployment state, test
interval = 1 environmentPatchCommit (3 services) → apakah auto-deploy jalan?
JANGAN dipake production, cuma probe. Hasil dikirim balik sebagai JSON."""
import sys, os, re, time, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import deploy_via_api as dep


def _extract_newest(r):
    newest = (None, "")
    for obj in re.findall(r'\{[^{}]*"status"\s*:\s*"\w+"[^{}]*\}', r):
        s = re.search(r'"status"\s*:\s*"(\w+)"', obj)
        c = re.search(r'"createdAt"\s*:\s*"([^"]+)"', obj)
        if s and c and c.group(1) > newest[1]:
            newest = (s.group(1), c.group(1))
    return newest


def run(order):
    """order: dict dengan email, mail_token, service_id, router_service_id,
    terminal_service_id, environment_id, project_id."""
    out = {"steps": []}
    svc_map = {"hermes": order["service_id"],
               "router": order.get("router_service_id"),
               "terminal": order.get("terminal_service_id")}

    p = dep.make_browser()
    try:
        p.get("https://railway.com/login")
        time.sleep(3)
        dep.inject_stealth(p)
        did = dep.login_and_exchange(p, order["email"], order["mail_token"])
        out["steps"].append(("did", "ok" if did else "gagal"))
        if not did:
            return out
        from solver import MuaraicaptchaSolver
        solver = MuaraicaptchaSolver(api_key=dep.MUARAI_KEY)
        ts = None
        for s_try in range(3):
            try:
                ts = solver.solve_turnstile(website_url="https://railway.com/login", website_key=dep.SITEKEY)
                if ts:
                    break
            except Exception:
                time.sleep(3)
        if not ts:
            out["steps"].append(("turnstile", "gagal"))
            return out
        p.run_js(f"window.__did = {json.dumps(did)};")
        p.run_js(f"window.__body = {json.dumps({'referralCode': None, 'ref': None, 'posthogSessionId': None, 'turnstileToken': ts, 'attribution': {'referringDomain': '$direct', 'landingPath': '/login'}, 'signupSurface': 'web'})};")
        st = dep.run_async_store(p, """
            const res = await fetch('https://backboard.railway.com/login/magic', {
                method: 'POST', credentials: 'include',
                headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + window.__did},
                body: JSON.stringify(window.__body)
            });
            await res.text();
            window.__r = res.status;
        """)
        out["steps"].append(("exchange", str(st)))
        if "200" not in str(st):
            return out

        # 1) dump pre-state
        pre = {n: _extract_newest(dep.gql(p, dep.SVC_STATUS_QUERY, {"id": s})) for n, s in svc_map.items() if s}
        out["pre_state"] = pre

        # 3) patch just one missing service... hmm, actually first: try deploy suci via PATCH_MUT
        patch_payload = {s: {"isCreated": True, "source": {"image": img}}
                         for img, s in [(dep.IMAGE_NAME, svc_map["hermes"]),
                                         (dep.ROUTER_IMAGE, svc_map["router"]),
                                         (dep.TERMINAL_IMAGE, svc_map["terminal"])] if s}
        r = dep.gql(p, """
        mutation environmentPatchCommit($environmentId: String!, $patch: EnvironmentConfig!, $message: String) {
          environmentPatchCommit(environmentId: $environmentId, patch: $patch, commitMessage: $message)
        }
        """, {"environmentId": order["environment_id"], "patch": {"services": patch_payload}, "message": "probe patch"})
        out["patch_all"] = r[:300]

        # 4) poll 4 menit
        for i in range(16):
            time.sleep(15)
            state = {n: _extract_newest(dep.gql(p, dep.SVC_STATUS_QUERY, {"id": s})) for n, s in svc_map.items() if s}
            out["steps"].append((f"poll_{i+1}", str(state)))
        return out
    finally:
        p.quit()
