from datetime import datetime
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from engine import analyze_proposal, load_playbook, retrieve_similar, validate_playbook
from ingestion import read_uploaded_file, make_sample_data

load_dotenv()
st.set_page_config(page_title="Acme Negotiation Agent", page_icon="🤝", layout="wide")

st.markdown("""
<style>
.block-container {padding-top:1.5rem; max-width:1400px}
.metric-card {background:#111827;padding:16px;border-radius:12px;border:1px solid #293548}
.small-muted {color:#9ca3af;font-size:0.85rem}
</style>
""", unsafe_allow_html=True)

if "history" not in st.session_state: st.session_state.history=[]
if "negotiations" not in st.session_state:
    st.session_state.negotiations = make_sample_data()

playbook=load_playbook()
st.title("🤝 Acme AI Supplier Negotiation Agent")
st.caption("Hackathon MVP · Playbook-grounded decisions · Human approval required")

with st.sidebar:
    st.header("Workspace")
    page=st.radio("Navigate", ["Overview","Analyze a proposal","Bulk upload & review","Decision history","Acme playbook"])
    st.divider()
    st.caption("Demo mode uses synthetic sample negotiations. Replace with authorized company data before real use.")
    st.metric("Historical records", len(st.session_state.negotiations))

df=st.session_state.negotiations.copy()
if page=="Overview":
    st.subheader("Procurement intelligence")
    total=len(st.session_state.history)
    counts=pd.Series([x["decision"] for x in st.session_state.history]).value_counts() if total else pd.Series(dtype=int)
    a,b,c,d=st.columns(4)
    a.metric("Analyzed proposals",total)
    b.metric("Accept",int(counts.get("ACCEPT",0)))
    c.metric("Counter",int(counts.get("COUNTER",0)))
    d.metric("Escalate / Reject",int(counts.get("ESCALATE",0)+counts.get("REJECT",0)))
    st.info("Start with **Analyze a proposal** or upload a batch. The sample dataset is synthetic and intended for demonstration.")
    if total:
        st.subheader("Recent decisions")
        st.dataframe(pd.DataFrame(st.session_state.history).tail(10), use_container_width=True, hide_index=True)
    st.subheader("Sample historical dataset")
    st.dataframe(df.head(12), use_container_width=True, hide_index=True)

elif page=="Analyze a proposal":
    st.subheader("Analyze supplier proposal")
    with st.form("proposal_form"):
        col1,col2=st.columns(2)
        with col1:
            supplier=st.text_input("Supplier name", "Northstar Components")
            category=st.selectbox("Category", ["Electronics","Packaging","Logistics","Raw materials","IT services","Other"])
            price=st.number_input("Quoted unit price (₹)", min_value=0.0, value=11200.0, step=100.0)
            target=st.number_input("Acme target unit price (₹)", min_value=0.0, value=10000.0, step=100.0)
        with col2:
            delivery=st.number_input("Proposed delivery (days)", min_value=0, value=25)
            max_delivery=st.number_input("Acme maximum delivery (days)", min_value=0, value=20)
            payment=st.number_input("Payment term (days)", min_value=0, value=30)
            min_payment=st.number_input("Minimum payment term required (days)", min_value=0, value=30)
        notes=st.text_area("Additional supplier terms / context", "Supplier requests a 5% advance payment and offers a one-year warranty.")
        submitted=st.form_submit_button("Analyze negotiation", type="primary", use_container_width=True)
    if submitted:
        proposal={"supplier":supplier,"category":category,"quoted_price":price,"target_price":target,
                  "delivery_days":delivery,"max_delivery_days":max_delivery,"payment_days":payment,
                  "min_payment_days":min_payment,"notes":notes}
        result=analyze_proposal(proposal, playbook, df)
        similar=retrieve_similar(proposal,df,n=3)
        result["supplier"]=supplier
        result["timestamp"]=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state.history.append(result)
        st.session_state.last_result=result
        st.session_state.last_similar=similar
    if "last_result" in st.session_state:
        r=st.session_state.last_result
        colors={"ACCEPT":"success","COUNTER":"info","REJECT":"error","ESCALATE":"warning"}
        getattr(st,colors[r["decision"]])(f"Recommended decision: **{r['decision']}**")
        x,y,z=st.columns(3)
        x.metric("Decision confidence",f"{r['confidence']}%")
        y.metric("Price variance",f"{r['price_variance_pct']:.1f}%")
        z.metric("Policy checks",f"{r['checks_passed']}/{r['checks_total']} passed")
        st.markdown("### Why the agent decided this")
        for reason in r["reasons"]: st.write("• "+reason)
        st.markdown("### Suggested next action")
        st.write(r["next_action"])
        st.markdown("### Draft counteroffer")
        st.text_area("Editable draft",r["counteroffer"],height=130)
        st.markdown("### Similar historical negotiations")
        sim=st.session_state.get("last_similar",[])
        if sim: st.dataframe(pd.DataFrame(sim),use_container_width=True,hide_index=True)
        st.warning("This is a recommendation only. A procurement manager must review and approve any supplier communication or commitment.")

elif page=="Bulk upload & review":
    st.subheader("Bulk negotiation ingestion")
    st.write("Upload CSV, XLSX, PDF or TXT files. For the MVP, CSV/XLSX rows are the most reliable structured input.")
    uploads=st.file_uploader("Upload files", type=["csv","xlsx","pdf","txt"], accept_multiple_files=True)
    if st.button("Process uploaded files",type="primary",disabled=not uploads):
        new_rows=[]
        errors=[]
        for f in uploads:
            try:
                rows=read_uploaded_file(f)
                new_rows.extend(rows)
            except Exception as e: errors.append(f"{f.name}: {e}")
        if new_rows:
            incoming=pd.DataFrame(new_rows)
            st.session_state.negotiations=pd.concat([st.session_state.negotiations,incoming],ignore_index=True).fillna("")
            st.success(f"Imported {len(new_rows)} records.")
        for e in errors: st.error(e)
    st.divider()
    st.markdown("### Download synthetic sample dataset")
    csv=df.to_csv(index=False).encode("utf-8")
    st.download_button("Download sample negotiations CSV",csv,"sample_negotiations.csv","text/csv")
    st.markdown("### Current historical records")
    st.dataframe(st.session_state.negotiations,use_container_width=True,hide_index=True)
    st.caption("Imported documents are added to the in-session historical set. Restarting the app resets demo data.")

elif page=="Decision history":
    st.subheader("Decision audit trail")
    if st.session_state.history:
        hist=pd.DataFrame(st.session_state.history)
        st.dataframe(hist,use_container_width=True,hide_index=True)
        st.download_button("Export decisions CSV",hist.to_csv(index=False).encode(), "decision_audit.csv","text/csv")
    else: st.info("No decisions yet. Analyze a proposal to create the first audit entry.")

elif page=="Acme playbook":
    st.subheader("Acme negotiation playbook (demo policy)")
    st.warning("These are illustrative assumptions created for the hackathon. They are not actual Acme corporate policy.")
    playbook_issues = validate_playbook(playbook)
    if playbook_issues:
        for issue in playbook_issues:
            st.error(issue)
    else:
        st.success("Playbook loaded and validated.")
    st.json(playbook)
    st.markdown("""
**Decision principles**
- Mandatory policy violations or high-risk terms → ESCALATE or REJECT according to severity.
- A proposal within all thresholds → ACCEPT recommendation.
- A commercially negotiable gap → COUNTER.
- Missing or conflicting information → ESCALATE.
- The AI does not send emails, sign contracts, or approve purchases.
""")
