"""Fact-checked executive memos: draft, verify, edit, approve, export."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import TIER_BADGE, get_store, identity, page_setup, succeeded_runs  # noqa: E402

page_setup("Memos", "📝")

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from memo_service import draft_memo, edit_memo, export_markdown, export_slack, facts_for_item  # noqa: E402
from memo_writer import configured_writer  # noqa: E402
from run_store import StoreError  # noqa: E402

store = get_store()
actor, ws = identity()
runs = succeeded_runs(ws)

st.title("📝 Memos")
st.caption("Every number in a memo must come from a fact the code produced. Drafts are verified before you see them, and nothing "
           "can be exported until a person approves it.")
if not runs:
    st.info("Create a run first (Dashboard → Try with demo data).")
    st.stop()

ai = configured_writer()
if ai:
    st.success(f"AI drafting is on ({ai.model}). Drafts that fail verification fall back to the template writer automatically.")
else:
    st.info("Template drafting only. Set the ANTHROPIC_API_KEY environment variable to enable AI drafting.")
use_ai = bool(ai) and st.checkbox("Use the AI writer for new drafts", value=True)

labels = {r["id"]: f"{r['label'] or 'Run'} · {r['created_at'][:16].replace('T', ' ')}" for r in runs}
if st.session_state.get("memo_run") not in labels:
    st.session_state["memo_run"] = next(iter(labels))
run_id = st.selectbox("Run", list(labels), format_func=labels.get, key="memo_run")
items = store.list_inbox(ws, run_id=run_id)
if not items:
    st.info("This run has no agent packets, so there is nothing to write a memo about.")
    st.stop()
item_labels = {i["id"]: f"{i['packet']['title']} · {i['status']}" for i in items}
if st.session_state.get("memo_item") not in item_labels:
    st.session_state["memo_item"] = next(iter(item_labels))
item_id = st.selectbox("Packet", list(item_labels), format_func=item_labels.get, key="memo_item")
item = next(i for i in items if i["id"] == item_id)
st.caption(item["packet"]["strategic_callout"])

if st.button("Draft memo", type="primary"):
    try:
        memo = draft_memo(store, ws, item, facts_for_item(store, ws, run_id, item), run_id, ai if use_ai else None, actor)
        st.toast("Memo drafted and verified." + (" The AI draft was replaced by the template." if memo["fallback_reason"] else ""), icon="📝")
    except (StoreError, ValueError) as exc:
        st.error(str(exc))

memos = store.list_memos(ws, item_id)  # newest first
if not memos:
    st.stop()
memo = memos[0]  # actions only ever apply to the newest memo for this packet; older versions are read only
mid = memo["id"]
if len(memos) > 1:
    with st.expander(f"Earlier versions ({len(memos) - 1}, read only)"):
        st.dataframe(pd.DataFrame([{"Created": m["created_at"][:19].replace("T", " "), "Writer": m["writer"], "Status": m["status"],
                                    "Verified": m["verification"]["ok"], "Text": m["text_clean"][:120]} for m in memos[1:]]), hide_index=True, width="stretch")
v = memo["verification"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Status", memo["status"])
c2.metric("Writer", "AI (Claude)" if memo["ai_drafted"] else "Template")
c3.metric("Verification", "Passed" if v["ok"] else "Failed")
c4.metric("Numbers checked", v["numbers_checked"])
if memo["fallback_reason"]:
    st.warning(f"The AI draft was not used: {memo['fallback_reason']}")
if not v["ok"]:
    for i in v["issues"]:
        st.error(i)

st.markdown("**Memo**")
st.write(memo["text_clean"])
with st.expander("Facts this memo may use and how each number was verified"):
    st.dataframe(pd.DataFrame([{"Id": f["id"], "Fact": f["label"], "Value": f["display"]} for f in memo["facts"]]), hide_index=True, width="stretch")
    st.caption(f"Cited: {', '.join(v['cited']) or 'none'}")
if memo["attempts"]:
    with st.expander("Writer attempts"):
        for a in memo["attempts"]:
            st.write(a)

if memo["status"] == "draft":
    st.markdown("**Edit (optional).** Keep the [F#] markers; edits are re-verified.")
    edited = st.text_area("Memo text with fact markers", memo["text_cited"], height=180, key=f"edit_{mid}")
    e1, e2 = st.columns(2)
    if e1.button("Save edit", key=f"save_{mid}"):
        res = edit_memo(store, ws, mid, edited, actor)
        if res["ok"]:
            st.success("Edit saved and re-verified.")
            st.rerun()
        for issue in res["issues"]:
            st.error(issue)
    if e2.button("Approve", type="primary", disabled=not v["ok"], key=f"approve_{mid}"):
        try:
            store.transition_memo(ws, mid, "approved", actor)
            st.rerun()
        except StoreError as exc:
            st.error(str(exc))
else:
    st.success(f"Approved by {memo['approved_by']} on {memo['approved_at'][:10]}.")
    try:
        d1, d2, d3 = st.columns(3)
        d1.download_button("Download Markdown", export_markdown(memo), f"memo_{memo['id']}.md", "text/markdown")
        d2.download_button("Download Slack text", export_slack(memo), f"memo_{memo['id']}.txt", "text/plain")
        if memo["status"] == "approved" and d3.button("Mark as exported", key=f"export_{mid}"):
            store.transition_memo(ws, mid, "exported", actor)
            st.rerun()
    except PermissionError as exc:
        st.error(str(exc))
