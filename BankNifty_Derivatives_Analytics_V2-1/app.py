import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime
from nse_data import NSEClient
from analytics import prepare_option_chain, filter_expiry, select_atm_zone, calculate_summary, add_oi_analysis, max_pain, build_heatmap

st.set_page_config(page_title="Bank Nifty Derivatives Analytics", page_icon="🏦", layout="wide")
st.title("🏦 Bank Nifty Derivatives Analytics Dashboard")
st.caption("Options • Futures • OI Analysis • PCR • Max Pain • ATM Heatmap")
st.caption("Note: NSE blocks cloud IPs, so Streamlit shows DEMO data. Local PC pe real data aayega.")

@st.cache_resource
def client():
    return NSEClient()
nse = client()

if "cache_data" not in st.session_state:
    st.session_state.cache_data = {}

st.sidebar.header("⚙️ Dashboard Controls")
try:
    constituents = nse.get_banknifty_constituents()
except:
    constituents = ["HDFCBANK","ICICIBANK","SBIN","KOTAKBANK","AXISBANK","INDUSINDBK"]

instruments = ["BANKNIFTY"] + constituents
symbol = st.sidebar.selectbox("Instrument", instruments)
is_index = symbol == "BANKNIFTY"
label = "NIFTY BANK" if is_index else symbol
expiry_number = st.sidebar.selectbox("Expiry", ["Nearest","2nd","3rd"], index=0)
expiry_index = {"Nearest":0,"2nd":1,"3rd":2}[expiry_number]
atm_each_side = st.sidebar.slider("ATM strikes each side", 3, 20, 8)
load_real = st.sidebar.button("🔄 Try Real NSE Data", type="primary")
st.sidebar.caption("Streamlit Cloud pe NSE block hota hai, isliye default DEMO dikhega")

def get_demo_payload():
    return {"records":{"underlyingValue":56400, "expiryDates":["28-Mar-2026"], "data":[{"strikePrice":56000+ i*100, "expiryDate":"28-Mar-2026", "CE":{"openInterest":10000+i*100, "changeinOpenInterest":500, "totalTradedVolume":2000, "impliedVolatility":15, "lastPrice":100+i, "change":2, "pChange":1}, "PE":{"openInterest":12000+i*100, "changeinOpenInterest":-200, "totalTradedVolume":2500, "impliedVolatility":16, "lastPrice":90+i, "change":-1, "pChange":-0.5}} for i in range(-8,9)]}}

cache_key = f"{symbol}:{expiry_index}"

# Auto-load DEMO instantly so page generates immediately
if cache_key not in st.session_state.cache_data:
    demo_payload = get_demo_payload()
    df, expiries, underlying = prepare_option_chain(demo_payload)
    expiry = expiries[0]
    selected_df = add_oi_analysis(filter_expiry(df, expiry))
    st.session_state.cache_data[cache_key] = {"df":selected_df,"expiries":expiries,"underlying":underlying,"expiry":expiry,"futures":pd.DataFrame(),"loaded_at":datetime.now().strftime("%d-%m-%Y %H:%M:%S")+" (DEMO - Instant)"}

# If user clicks Try Real, then only hit NSE
if load_real:
    with st.spinner(f"Trying real NSE data for {label}... (NSE may block)"):
        try:
            raw = nse.get_option_chain(symbol, is_index=is_index)
            df, expiries, underlying = prepare_option_chain(raw)
            if not expiries:
                raise RuntimeError("No expiry from NSE")
            expiry = expiries[min(expiry_index, len(expiries)-1)]
            selected_df = add_oi_analysis(filter_expiry(df, expiry))
            futures = pd.DataFrame()
            try:
                fq = nse.get_derivative_quote("BANKNIFTY" if is_index else symbol)
                futures = nse.parse_futures(fq)
            except:
                futures = pd.DataFrame()
            st.session_state.cache_data[cache_key] = {"df":selected_df,"expiries":expiries,"underlying":underlying,"expiry":expiry,"futures":futures,"loaded_at":datetime.now().strftime("%d-%m-%Y %H:%M:%S")+" (REAL NSE)"}
            st.success("Real NSE data loaded!")
        except Exception as e:
            st.error(f"Real NSE failed: {e}")
            st.info("Demo data hi dikh raha hai. Local PC pe 'py -m streamlit run app.py' se real data aayega.")

data = st.session_state.cache_data[cache_key]
df = data["df"].copy()
underlying = data["underlying"]
expiry = data["expiry"]
futures = data["futures"]

summary = calculate_summary(df, underlying)
m = st.columns(7)
m[0].metric("Instrument", label)
m[1].metric("Underlying", f"{underlying:,.2f}" if pd.notna(underlying) else "—")
m[2].metric("Expiry", str(expiry))
m[3].metric("PCR", f"{summary['pcr']:.2f}" if pd.notna(summary["pcr"]) else "—")
m[4].metric("Max CE OI", f"{summary['max_ce_strike']:,.0f}" if pd.notna(summary["max_ce_strike"]) else "—")
m[5].metric("Max PE OI", f"{summary['max_pe_strike']:,.0f}" if pd.notna(summary["max_pe_strike"]) else "—")
m[6].metric("Max Pain", f"{summary['max_pain']:,.0f}" if pd.notna(summary["max_pain"]) else "—")
st.caption(f"Last loaded: {data['loaded_at']}")

atm_df = select_atm_zone(df, underlying, atm_each_side)
st.subheader(f"ATM Zone - {atm_each_side} strikes each side")
st.dataframe(atm_df, use_container_width=True)

tab1, tab2, tab3, tab4 = st.tabs(["🔥 OI Heatmap","📊 OI / PCR Charts","🎯 Max Pain","📦 Futures"])
with tab1:
    heat = build_heatmap(atm_df)
    if not heat.empty:
        fig = px.imshow(heat.T, aspect="auto", labels={"x":"Strike","y":"Side","color":"OI"}, title=f"{label} — Call vs Put OI")
        st.plotly_chart(fig, use_container_width=True)
with tab2:
    long_oi = atm_df[["strikePrice","CE_oi","PE_oi"]].melt(id_vars="strikePrice", value_vars=["CE_oi","PE_oi"], var_name="Side", value_name="OI")
    fig = px.bar(long_oi, x="strikePrice", y="OI", color="Side", barmode="group", title="CE / PE Open Interest")
    st.plotly_chart(fig, use_container_width=True)
with tab3:
    mp_table, mp_strike = max_pain(df)
    if pd.notna(mp_strike):
        st.metric("Max Pain", f"{mp_strike:,.0f}")
        st.dataframe(mp_table, use_container_width=True)
with tab4:
    if futures.empty:
        st.info("Futures data not available (NSE blocked or market closed) - DEMO me futures nahi hota")
    else:
        st.dataframe(futures, use_container_width=True)

st.download_button("Download CSV", df.to_csv(index=False).encode("utf-8"), file_name=f"{symbol}_{expiry}.csv", mime="text/csv")
st.markdown("---")
st.success("✅ Dashboard Generated! Ab ye link kaam karega. Local PC pe real NSE data ke liye terminal me 'py -m streamlit run app.py' chalao.")
