
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime

from nse_data import NSEClient
from analytics import (
    prepare_option_chain,
    filter_expiry,
    select_atm_zone,
    calculate_summary,
    add_oi_analysis,
    max_pain,
    build_heatmap,
    build_stock_snapshot,
    safe_num,
)

st.set_page_config(
    page_title="Bank Nifty Derivatives Analytics",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🏦 Bank Nifty Derivatives Analytics Dashboard")
st.caption("Options • Futures • OI Analysis • PCR • Max Pain • ATM Heatmap • Stock Comparison")
st.caption("Educational/research dashboard. NSE data access is subject to NSE availability and terms.")

@st.cache_resource
def client():
    return NSEClient()

nse = client()

# ---------------- Sidebar ----------------
st.sidebar.header("⚙️ Dashboard Controls")

if "loaded" not in st.session_state:
    st.session_state.loaded = None
if "cache_data" not in st.session_state:
    st.session_state.cache_data = {}

try:
    constituents = nse.get_banknifty_constituents()
except Exception as e:
    constituents = []
    st.sidebar.error("Current Nifty Bank constituents could not be loaded.")
    st.sidebar.caption(str(e))

instruments = ["BANKNIFTY"] + constituents
symbol = st.sidebar.selectbox("Instrument", instruments)

is_index = symbol == "BANKNIFTY"
label = "NIFTY BANK" if is_index else symbol

expiry_number = st.sidebar.selectbox(
    "Expiry",
    ["Nearest", "2nd", "3rd"],
    index=0,
)
expiry_index = {"Nearest": 0, "2nd": 1, "3rd": 2}[expiry_number]

atm_each_side = st.sidebar.slider(
    "ATM strikes each side",
    3, 20, 8,
)

refresh_seconds = st.sidebar.number_input(
    "Auto-refresh seconds (0 = off)",
    min_value=0,
    max_value=3600,
    value=0,
    step=30,
)

load = st.sidebar.button("🔄 Load / Refresh", type="primary")

# Optional auto-refresh using native Streamlit rerun.
if refresh_seconds > 0:
    st.sidebar.info(f"Auto-refresh is set to {refresh_seconds}s.")

# ---------------- Load selected instrument ----------------
cache_key = f"{symbol}:{expiry_index}"

if load or cache_key not in st.session_state.cache_data:
    with st.spinner(f"Loading {label} from NSE..."):
        try:
            raw = nse.get_option_chain(symbol, is_index=is_index)
            df, expiries, underlying = prepare_option_chain(raw)

            if not expiries:
                raise RuntimeError("NSE returned no expiry dates.")

            expiry_index_actual = min(expiry_index, len(expiries) - 1)
            expiry = expiries[expiry_index_actual]

            selected_df = filter_expiry(df, expiry)
            selected_df = add_oi_analysis(selected_df)

            # Futures for both BANKNIFTY and stock derivatives.
            futures = pd.DataFrame()
            try:
                fq = nse.get_derivative_quote("BANKNIFTY" if is_index else symbol)
                futures = nse.parse_futures(fq)
            except Exception:
                futures = pd.DataFrame()

            st.session_state.cache_data[cache_key] = {
                "df": selected_df,
                "expiries": expiries,
                "underlying": underlying,
                "expiry": expiry,
                "futures": futures,
                "loaded_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
            }

        except Exception as e:
            st.error("Data load failed.")
            st.info(
                "NSE may temporarily return 401/403/429 for automated requests. "
                "Wait a little and press Refresh rather than repeatedly refreshing."
            )
            st.code(str(e))
            st.stop()

data = st.session_state.cache_data[cache_key]
df = data["df"].copy()
underlying = data["underlying"]
expiry = data["expiry"]
futures = data["futures"]

# ---------------- Top metrics ----------------
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

# ---------------- ATM zone ----------------
atm_df, atm_strike = select_atm_zone(df, underlying, atm_each_side)

st.subheader(f"🎯 ATM Option Chain — ATM {atm_strike:,.0f}" if pd.notna(atm_strike) else "🎯 ATM Option Chain")

show_cols = [
    "CE_oi", "CE_change", "CE_volume", "CE_iv", "CE_ltp", "CE_changePrice",
    "CE_OI_Analysis", "strikePrice",
    "PE_OI_Analysis", "PE_changePrice", "PE_ltp", "PE_iv", "PE_volume",
    "PE_change", "PE_oi"
]
show_cols = [x for x in show_cols if x in atm_df.columns]

rename = {
    "CE_oi":"CE OI", "CE_change":"CE OI Chg", "CE_volume":"CE Volume",
    "CE_iv":"CE IV", "CE_ltp":"CE LTP", "CE_changePrice":"CE Chg",
    "CE_OI_Analysis":"CE Analysis", "strikePrice":"STRIKE",
    "PE_OI_Analysis":"PE Analysis", "PE_changePrice":"PE Chg",
    "PE_ltp":"PE LTP", "PE_iv":"PE IV", "PE_volume":"PE Volume",
    "PE_change":"PE OI Chg", "PE_oi":"PE OI"
}

st.dataframe(
    atm_df[show_cols].rename(columns=rename),
    use_container_width=True,
    hide_index=True,
)

# ---------------- Tabs ----------------
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔥 OI Heatmap",
    "📊 OI / PCR Charts",
    "🎯 Max Pain",
    "📦 Futures",
    "🏦 Bank Stock Comparison",
])

with tab1:
    st.subheader("OI Heatmap — ATM Zone")
    heat = build_heatmap(atm_df)
    if not heat.empty:
        fig = px.imshow(
            heat.T,
            aspect="auto",
            labels={"x": "Strike", "y": "Side", "color": "OI"},
            title=f"{label} — Call vs Put OI",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(heat, use_container_width=True)
    else:
        st.info("Heatmap data is not available.")

    st.subheader("OI Change Heatmap")
    change_heat = build_heatmap(atm_df, change=True)
    if not change_heat.empty:
        fig2 = px.imshow(
            change_heat.T,
            aspect="auto",
            labels={"x": "Strike", "y": "Side", "color": "OI Change"},
            title=f"{label} — Change in OI",
        )
        st.plotly_chart(fig2, use_container_width=True)

with tab2:
    st.subheader("Open Interest by Strike")
    long_oi = atm_df[["strikePrice", "CE_oi", "PE_oi"]].copy()
    long_oi = long_oi.melt(
        id_vars="strikePrice",
        value_vars=["CE_oi", "PE_oi"],
        var_name="Side",
        value_name="OI",
    )
    long_oi["Side"] = long_oi["Side"].map({"CE_oi":"CE", "PE_oi":"PE"})
    fig = px.bar(
        long_oi,
        x="strikePrice",
        y="OI",
        color="Side",
        barmode="group",
        title="CE / PE Open Interest",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Change in Open Interest")
    long_chg = atm_df[["strikePrice", "CE_change", "PE_change"]].copy()
    long_chg = long_chg.melt(
        id_vars="strikePrice",
        value_vars=["CE_change", "PE_change"],
        var_name="Side",
        value_name="OI Change",
    )
    long_chg["Side"] = long_chg["Side"].map({"CE_change":"CE", "PE_change":"PE"})
    fig2 = px.bar(
        long_chg,
        x="strikePrice",
        y="OI Change",
        color="Side",
        barmode="group",
        title="CE / PE Change in OI",
    )
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader("PCR by ATM Zone")
    pcr_rows = atm_df[["strikePrice", "CE_oi", "PE_oi"]].copy()
    pcr_rows["Strike PCR"] = np.where(
        pcr_rows["CE_oi"] > 0,
        pcr_rows["PE_oi"] / pcr_rows["CE_oi"],
        np.nan,
    )
    fig3 = px.line(
        pcr_rows,
        x="strikePrice",
        y="Strike PCR",
        markers=True,
        title="Strike-wise PE OI / CE OI",
    )
    st.plotly_chart(fig3, use_container_width=True)

with tab3:
    st.subheader("Max Pain — Selected Expiry")
    mp_table, mp_strike = max_pain(df)

    if pd.notna(mp_strike):
        st.metric("Calculated Max Pain Strike", f"{mp_strike:,.0f}")
        fig = px.line(
            mp_table,
            x="strikePrice",
            y="totalPain",
            markers=True,
            title="Total Option Pain by Settlement Strike",
        )
        fig.add_vline(
            x=mp_strike,
            line_dash="dash",
            annotation_text=f"Max Pain {mp_strike:,.0f}",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(mp_table, use_container_width=True, hide_index=True)
    else:
        st.info("Not enough CE/PE OI data to calculate Max Pain.")

with tab4:
    st.subheader("Futures Contracts")
    if futures.empty:
        st.info("Futures data was not returned for this instrument.")
    else:
        st.dataframe(futures, use_container_width=True, hide_index=True)

with tab5:
    st.subheader("Current Nifty Bank Stocks — Snapshot")
    st.caption(
        "This table loads option-chain snapshots one stock at a time when the comparison button is pressed. "
        "Large batches can be rate-limited by NSE."
    )

    compare = st.button("📊 Load All Current Bank Stock Snapshots")

    if compare:
        rows = []
        progress = st.progress(0)
        total = len(constituents)

        for i, s in enumerate(constituents, start=1):
            try:
                raw_s = nse.get_option_chain(s, is_index=False)
                d_s, exps_s, und_s = prepare_option_chain(raw_s)

                if not exps_s:
                    continue

                exp_s = exps_s[min(expiry_index, len(exps_s)-1)]
                d_s = add_oi_analysis(filter_expiry(d_s, exp_s))
                rows.append(build_stock_snapshot(s, d_s, und_s, exp_s))
            except Exception:
                pass

            progress.progress(i / max(total, 1))

        if rows:
            snap = pd.DataFrame(rows).sort_values(
                "OI_Change_Total",
                ascending=False,
            )
            st.dataframe(snap, use_container_width=True, hide_index=True)
        else:
            st.warning("No stock snapshots were returned.")

# ---------------- Full data / downloads ----------------
st.markdown("---")
st.subheader("📥 Downloads")

csv = df.to_csv(index=False).encode("utf-8")
st.download_button(
    "Download Selected Expiry CSV",
    csv,
    file_name=f"{symbol}_{expiry}_option_chain.csv",
    mime="text/csv",
)

summary_df = pd.DataFrame([summary])
st.download_button(
    "Download Summary CSV",
    summary_df.to_csv(index=False).encode("utf-8"),
    file_name=f"{symbol}_{expiry}_summary.csv",
    mime="text/csv",
)

st.subheader("📌 OI Analysis Logic")
st.write(
    """
    **Long Buildup:** price change ↑ + OI change ↑  
    **Short Buildup:** price change ↓ + OI change ↑  
    **Short Covering:** price change ↑ + OI change ↓  
    **Long Unwinding:** price change ↓ + OI change ↓  
    **Neutral:** no clear combination.
    """
)
st.warning(
    "These are rule-based descriptive labels, not guaranteed market direction or trading signals."
)

# ---------------- Simple auto-refresh ----------------
if refresh_seconds > 0:
    st.markdown(
        f"<meta http-equiv='refresh' content='{int(refresh_seconds)}'>",
        unsafe_allow_html=True,
    )
