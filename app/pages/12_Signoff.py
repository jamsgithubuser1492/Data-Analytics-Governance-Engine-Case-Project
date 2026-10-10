"""Sign-off desk: the final human gate. Every decision is signed; nothing takes effect without it."""
from __future__ import annotations

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DATA_ROOT, auth_mode, get_store, identity, page_setup, safe_page_link  # noqa: E402

page_setup("Sign-off desk", ":material/draw:")

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import dashdata as dd  # noqa: E402
import signoff as so  # noqa: E402
import ui  # noqa: E402
import voice  # noqa: E402
from agent_schema import ACTIONS  # noqa: E402
from overrides import EXEC_ROLES, read_log, verify_log  # noqa: E402
from run_store import StoreError  # noqa: E402
from runview import load_view  # noqa: E402

store = get_store()
actor, ws = identity()
auth = auth_mode(actor)
log_path = Path(DATA_ROOT) / "workspaces" / ws / "run_audit_log.json"

ui.page_head("Decide", "Sign-off desk",
             "The last step before anything changes. Every decision, whether you approve it, change it or reject it, is signed with a note, your email and your role, and kept in a permanent record that cannot be quietly edited. "
             "A strong result never replaces your signature.")

items = store.list_inbox(ws)
if not items:
    ui.callout("There is nothing to decide yet. Decisions arrive here from the Dashboard, from scenarios on the Strategy page and from research ideas on the Research next page.")
    safe_page_link("app.py", "Go to the Dashboard", ":material/analytics:")
    st.stop()

signed = {i["id"]: store.get_signoff(ws, i["id"]) for i in items}
open_items = [i for i in items if i["status"] in ("new", "reviewed")]
approved_items = [i for i in items if i["status"] == "approved"]
n = {k: sum(1 for s in signed.values() if s and s["outcome"] == k) for k in so.OUTCOMES}
ui.stat_row([dict(label="Awaiting your signature", value=str(len(open_items)), kind="warn" if open_items else "ok"), dict(label="Signed approvals", value=str(n["APPROVED"]), kind="ok"),
             dict(label="Changed by you", value=str(n["OVERRIDDEN"])), dict(label="Rejections", value=str(n["REJECTED"]))], compact=True)

view = st.segmented_control("Show", ["Awaiting signature", "Approved", "Signed", "All"], default="Awaiting signature", key="so_filter", label_visibility="collapsed") or "Awaiting signature"
pool = {"Awaiting signature": open_items, "Approved": approved_items, "Signed": [i for i in items if signed[i["id"]]], "All": items}[view]
if not pool:
    ui.callout("Nothing in this view." + (" Every open decision has been signed." if view == "Awaiting signature" else ""), "ok")
else:
    labels = {i["id"]: f"{ui.scrub(i['packet']['title'])} · {i['status']}" for i in pool}
    pre = st.session_state.get("signoff_item")
    ids = list(labels)
    item_id = st.selectbox("Decision to review", ids, index=ids.index(pre) if pre in ids else 0, format_func=labels.get, key="so_pick")
    item = next(i for i in pool if i["id"] == item_id)
    p = item["packet"]
    v = load_view(store, ws, item["run_id"])
    camp = v.camp.set_index("campaign_id")
    if p["campaign_id"] in camp.index:
        trust, tier = float(camp.loc[p["campaign_id"], "trust_score"]), camp.loc[p["campaign_id"], "tier"]
    else:
        trust, tier = float(p.get("trust_score", v.report["average_trust_score"])), p.get("tier", "DIRECTIONAL")
    g = dd.gate(tier)
    action = voice.ACTION_WORDS.get(p["recommended_action"]) or ACTIONS.get(p["recommended_action"], (p["recommended_action"],))[0]
    sig = signed[item_id]

    # ------------------------------------------------------------------------------------------ the packet
    ui.decision_flow(6 if item["status"] == "executed" else (5 if item["status"] == "approved" else (4 if sig else 3)))
    with st.container(border=True):
        st.markdown(f"{ui.pill('Decision packet', 'info')} {ui.tier_pill(tier)} {ui.pill(item['status'].capitalize(), 'muted')}", unsafe_allow_html=True)
        st.markdown(f"### {ui.scrub(p['title'])}")
        ui.stat_row([dict(label="How sure we are", value=voice.conf_phrase(tier).split(":")[0], sub=g["label"], kind={"VERIFIED": "ok", "DIRECTIONAL": "warn"}.get(tier, "bad")),
                     dict(label="Counting method", value=v.basis), dict(label="Reference", value=item["run_id"][:8])], compact=True)
        _c = next((c for c in v.report["campaigns"] if c["campaign_id"] == p["campaign_id"]), None)
        if p.get("audience_tier"):
            _lo, _hi = p.get("audience_range", [float("nan")] * 2)
            ui.stat_row([dict(label="Platform credit per $1", value=f"{p.get('reported_roas', float('nan')):.2f}x"),
                         dict(label="Caused by the ads per $1", value=f"{p.get('strict_iroas', float('nan')):.2f}x", sub=f"95% range {_lo:.2f}x to {_hi:.2f}x", kind="ok"),
                         dict(label="Audience tier", value=str(p.get("tier_name", "")))], compact=True)
            st.caption("Audience tiers always count only the extra conversions the ads caused (strict lift).")
        _r = v.cd.set_index("campaign_id") if "campaign_id" in v.cd.columns else v.cd
        if p["campaign_id"] in _r.index:
            _x = lambda v: "n/a" if pd.isna(v) else f"{v:.2f}x"  # noqa: E731
            ui.measurement_trio(_x(_r.loc[p["campaign_id"], "claimed_roas"]), _x(_r.loc[p["campaign_id"], "model_roas"]), _x(_r.loc[p["campaign_id"], "proven"]))
        st.markdown("##### What is being proposed")
        st.markdown(f"**{html.escape(action)}** for {html.escape(p['channel'])}." if p["channel"] != "Multiple" else f"**{html.escape(action)}.**", unsafe_allow_html=True)
        chg = p.get("proposed_changes") or []
        if chg and "source_spend" in chg[0]:
            tbl = pd.DataFrame(chg).rename(columns={"entity": "Channel", "source_spend": "Spend today", "target_spend": "Spend after", "delta": "Change"})
            st.dataframe(tbl.round(0), hide_index=True, width="stretch")
        elif chg:
            st.markdown("\n".join(f"- {ui.esc(c['entity'])}: {ui.esc(c['change'])}" for c in chg))
        ui.stat_row([dict(label=ui.scrub(k), value=str(x)) for k, x in p["value_add_metrics"].items()], compact=True)
        st.markdown("##### Why it was raised")
        st.markdown(ui.safe(p["strategic_callout"]))
        if p.get("audience_tier") and p.get("audience_checks"):
            st.markdown("##### Governance checks")
            ui.governance_status([(label, bool(ok)) for label, ok in p["audience_checks"]])
        if _c:
            _names = {1: "Test and comparison markets moved together beforehand", 2: "The test was large enough", 3: "The likely range is narrow enough",
                      5: "Seasonality is not distorting the result", 6: "Our sources agree", 8: "The result is clear enough to base a decision on"}
            _items = [(_names[k["check_id"]], k["status"] == "PASS") for k in _c["checks"] if k["check_id"] in _names and k["status"] != "NA"]
            if _items:
                st.markdown("##### Governance checks")
                ui.governance_status(_items)
        st.markdown(f'<div class="note">{ui.esc("Source: this run, counted as " + v.basis + ". Figures show a 95% likely range where one applies.")}</div>', unsafe_allow_html=True)

    # ------------------------------------------------------------------------------------------ signed already
    if sig:
        st.write("")
        entry = next((e for e in read_log(log_path) if e.get("hash") == sig["entry_hash"]), None)
        ui.callout(f"<b>Signed: {html.escape(so.OUTCOMES[sig['outcome']])}.</b> By {html.escape(sig['email'])} ({html.escape(sig['role'])}) on {sig['created_at'][:10]}. "
                   f"Note: {html.escape(sig['note'])}", "ok" if sig["outcome"] == "APPROVED" else "")
        if entry:
            st.download_button("Download the signed receipt", so.receipt_json(entry), f"signoff_{item_id[:8]}.json", "application/json", key=f"rc_{item_id}")
        if item["status"] == "approved":
            st.write("")
            if g["can_execute"]:
                st.markdown("##### Hand off to the team")
                st.caption("Nothing is changed in any ad platform from here. This records the approved change so the team that makes it can pick it up.")
                if st.button("Record the hand off", type="primary", key=f"ex_{item_id}"):
                    try:
                        store.transition_inbox(ws, item_id, "executed", sig["email"], "hand off recorded to the action queue (simulated, nothing sent to a platform)")
                        st.rerun()
                    except StoreError as exc:
                        st.error(str(exc))
            else:
                ui.callout(f"Hand off stays off. {g['message']}", "warn")
        elif item["status"] == "executed":
            st.code(f"INSERT INTO MMGE_DB.GOVERNANCE.ACTION_QUEUE (executed_at, agent_id, item_id, action) VALUES ('{item['updated_at']}', '{p['agent_id']}', '{item_id}', '{p['recommended_action']}');", language="sql")
            st.caption("Hand off recorded. This is the entry that would be queued for the team or system that makes the change.")
    # ------------------------------------------------------------------------------------------ the form
    elif item["status"] in ("new", "reviewed"):
        st.write("")
        st.markdown("#### Your decision")
        key = lambda k: f"so_{k}_{item_id}"  # noqa: E731
        outcome = st.radio("What do you decide?", list(so.OUTCOMES), format_func=so.OUTCOMES.get, key=key("outcome"), index=None)
        if tier == so.NOT_DECISION_GRADE:
            ui.callout("The evidence behind this is not yet reliable, so it cannot be approved. You can change it to a decision of your own or reject it.", "bad")
        elif not g["can_execute"]:
            st.caption("The evidence points one way but is not yet strong. You may approve, but handing it off to the team stays off until further testing makes it solid.")
        note = st.text_area("Your note (why you are deciding this way)", key=key("note"), height=100, placeholder="At least 10 characters. For an override, say what you will do instead.")
        c1, c2 = st.columns(2)
        email = c1.text_input("Your email", value=actor if auth == "sso_verified" else "", key=key("email"), disabled=auth == "sso_verified")
        role = c2.selectbox("Your executive role", EXEC_ROLES, index=None, key=key("role"), placeholder="Choose a role")
        st.markdown("**Please confirm**")
        ticks = [st.checkbox(text, key=key(f"tick_{k}")) for k, text in so.CHECKLIST]
        todo = so.requirements(outcome, note, email, role or "", ticks, tier)
        if auth == "self_asserted":
            st.caption("Sign-in is not set up, so the email you type is recorded as typed in by you rather than verified.")
        if todo:
            st.markdown('<div class="note"><b>Still needed:</b> ' + " ".join(html.escape(t) for t in todo) + "</div>", unsafe_allow_html=True)
        if st.button("Sign and record this decision", type="primary", disabled=bool(todo), key=key("go")):
            try:
                entry = so.sign(store, ws, item, outcome, note, email, role, ticks, log_path, trust_score=trust, tier=tier, basis=v.basis, policy_version=str(v.report["settings_fingerprint"]), authentication=auth)
                st.session_state["signoff_item"] = item_id
                st.session_state["last_receipt"] = entry["audit_entry_id"]
                st.rerun()
            except (so.SignoffError, StoreError) as exc:
                st.error(str(exc))
    else:
        ui.callout(f"This decision is {item['status']}. It did not go through a signature on this desk (for example, a newer run replaced it).")

# ---------------------------------------------------------------------------------------------- the log
st.write("")
entries = read_log(log_path)
with st.expander(f"Signed decisions log ({len(entries)} entries)"):
    ok, why = verify_log(log_path)
    st.markdown(ui.pill("Log intact" if ok else "Log altered", "ok" if ok else "bad") + f" {html.escape(why if not ok else 'Every entry chains to the one before it, so an edit or deletion would show here.')}", unsafe_allow_html=True)
    if entries:
        st.dataframe(pd.DataFrame([{"When": e.get("timestamp_utc", "")[:19], "Decision": e.get("decision_outcome", ""), "Signed by": (e.get("authorizing_user") or {}).get("email", ""),
                                    "Role": (e.get("authorizing_user") or {}).get("role", ""), "Sign-in": {"self_asserted": "Typed in by user", "sso_verified": "Verified sign-in"}.get((e.get("authorizing_user") or {}).get("authentication", ""), ""),
                                    "Confidence score": e.get("trust_score_at_signing", ""), "Note": e.get("justification", "")} for e in entries]), hide_index=True, width="stretch")
        st.download_button("Download the full log", log_path.read_bytes(), "run_audit_log.json", "application/json", key="dl_log")
st.caption("Automation and statistics can suggest, but only a named person decides. Nothing here reaches an ad platform.")
