# -*- coding: utf-8 -*-
"""Probe v2: di akun order yang env-nya udah quiet (hermes SUCCESS, router/terminal
belum pernah deploy), coba serviceInstanceDeploy langsung ke router.
Tujuan: jawab kenapa deploy router selama ini "Not Authorized" terus."""
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
    svc_map = {"hermes": order["service_id"],
               "router": order.get("router_service_id"),
               "terminal": order.get("terminal_service_id")}
    eid = order["environment_id"]
    out = {"steps": [], "kicks": []}

    p = dep.make_browser()
    try:
        p.get("https://railway.com/login")
        time.sleep(3)
        dep.inject_stealth(p)
        did = dep.login_and_exchange(p, order["email"], order["mail_token"])
        if not did:
            out["steps"].append(("did", "gagal"))
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

        # state awal
        pre = {n: _extract_newest(dep.gql(p, dep.SVC_STATUS_QUERY, {"id": s})) for n, s in svc_map.items() if s}
        out["pre_state"] = pre

        # dump service router lengkap (source/isCreated/config)
        r = dep.gql(p, 'query service($id: String!) { service(id: $id) { id name serviceInstances { environment { id } isCreated } } }', {"id": svc_map["router"]})
        out["router_instances"] = r[:800]

        DEPLOY_MUT = """
        mutation serviceInstanceDeploy($serviceId: String!, $environmentId: String!, $latestCommit: Boolean) {
          serviceInstanceDeploy(serviceId: $serviceId, environmentId: $environmentId, latestCommit: $latestCommit)
        }
        """
        # KICK 1: persis kayak code production
        k1 = dep.gql(p, DEPLOY_MUT, {"serviceId": svc_map["router"], "environmentId": eid, "latestCommit": True})
        out["kicks"].append(("kick1_latestCommit_true", k1[:400]))

        # KICK 2: tanpa latestCommit
        k2 = dep.gql(p, DEPLOY_MUT, {"serviceId": svc_map["router"], "environmentId": eid, "latestCommit": False})
        out["kicks"].append(("kick2_latestCommit_false", k2[:400]))

        # kalau masih error semua → coba patch dulu, langsung kick lagi
        if '"errors"' in k1 and '"errors"' in k2:
            r = dep.gql(p, """
            mutation environmentPatchCommit($environmentId: String!, $patch: EnvironmentConfig!, $message: String) {
              environmentPatchCommit(environmentId: $environmentId, patch: $patch, commitMessage: $message)
            }
            """, {"environmentId": eid,
                  "patch": {"services": {svc_map["router"]: {"isCreated": True, "source": {"image": dep.ROUTER_IMAGE}}}},
                  "message": "probe2 patch router"})
            out["kicks"].append(("patch_router", r[:400]))
            time.sleep(5)
            k3 = dep.gql(p, DEPLOY_MUT, {"serviceId": svc_map["router"], "environmentId": eid, "latestCommit": True})
            out["kicks"].append(("kick3_after_patch", k3[:400]))

        # poll router 3 menit
        for i in range(12):
            time.sleep(15)
            st = _extract_newest(dep.gql(p, dep.SVC_STATUS_QUERY, {"id": svc_map["router"]}))
            out["steps"].append((f"poll_{i+1}", str(st)))
        return out
    finally:
        p.quit()
