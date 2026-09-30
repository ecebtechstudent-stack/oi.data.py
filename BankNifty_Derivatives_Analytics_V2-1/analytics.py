
import numpy as np
import pandas as pd


def safe_num(x):
    try:
        return float(x)
    except Exception:
        return np.nan


def prepare_option_chain(payload):
    records = payload.get("records", {})
    raw = records.get("data", [])
    expiries = records.get("expiryDates", []) or []
    underlying = safe_num(records.get("underlyingValue"))

    rows = []

    for item in raw:
        row = {
            "strikePrice": safe_num(item.get("strikePrice")),
            "expiryDate": item.get("expiryDate"),
        }

        for side in ("CE", "PE"):
            x = item.get(side) or {}

            row[f"{side}_oi"] = safe_num(x.get("openInterest"))
            row[f"{side}_change"] = safe_num(x.get("changeinOpenInterest"))
            row[f"{side}_volume"] = safe_num(x.get("totalTradedVolume"))
            row[f"{side}_iv"] = safe_num(x.get("impliedVolatility"))
            row[f"{side}_ltp"] = safe_num(x.get("lastPrice"))
            row[f"{side}_changePrice"] = safe_num(x.get("change"))
            row[f"{side}_pChange"] = safe_num(x.get("pChange"))
            row[f"{side}_bid"] = safe_num(x.get("bidprice"))
            row[f"{side}_ask"] = safe_num(x.get("askPrice"))

        rows.append(row)

    df = pd.DataFrame(rows)

    if df.empty:
        return df, expiries, underlying

    numeric = [c for c in df.columns if c not in ("expiryDate",)]
    df[numeric] = df[numeric].apply(pd.to_numeric, errors="coerce")
    return df, expiries, underlying


def filter_expiry(df, expiry):
    if df.empty:
        return df.copy()

    out = df[df["expiryDate"] == expiry].copy()
    out = out.sort_values("strikePrice").reset_index(drop=True)
    return out


def classify(price_change, oi_change):
    if pd.isna(price_change) or pd.isna(oi_change):
        return "N/A"

    if oi_change > 0 and price_change > 0:
        return "Long Buildup"
    if oi_change > 0 and price_change < 0:
        return "Short Buildup"
    if oi_change < 0 and price_change > 0:
        return "Short Covering"
    if oi_change < 0 and price_change < 0:
        return "Long Unwinding"
    return "Neutral"


def add_oi_analysis(df):
    out = df.copy()

    out["CE_OI_Analysis"] = out.apply(
        lambda r: classify(r["CE_changePrice"], r["CE_change"]), axis=1
    )
    out["PE_OI_Analysis"] = out.apply(
        lambda r: classify(r["PE_changePrice"], r["PE_change"]), axis=1
    )

    return out


def select_atm_zone(df, underlying, each_side=8):
    if df.empty or pd.isna(underlying):
        return df.copy(), np.nan

    strikes = sorted(
        [x for x in df["strikePrice"].dropna().unique()]
    )

    if not strikes:
        return df.copy(), np.nan

    atm = min(strikes, key=lambda x: abs(x - underlying))
    pos = strikes.index(atm)

    low = max(0, pos - each_side)
    high = min(len(strikes), pos + each_side + 1)

    selected = strikes[low:high]
    return df[df["strikePrice"].isin(selected)].copy(), atm


def calculate_summary(df, underlying):
    ce_oi = df["CE_oi"].fillna(0).sum()
    pe_oi = df["PE_oi"].fillna(0).sum()

    ce_chg = df["CE_change"].fillna(0).sum()
    pe_chg = df["PE_change"].fillna(0).sum()

    ce_vol = df["CE_volume"].fillna(0).sum()
    pe_vol = df["PE_volume"].fillna(0).sum()

    ce_premium = (df["CE_ltp"].fillna(0) * df["CE_volume"].fillna(0)).sum()
    pe_premium = (df["PE_ltp"].fillna(0) * df["PE_volume"].fillna(0)).sum()

    if ce_oi > 0:
        pcr = pe_oi / ce_oi
    else:
        pcr = np.nan

    if not df.empty:
        max_ce_strike = df.loc[df["CE_oi"].fillna(0).idxmax(), "strikePrice"]
        max_pe_strike = df.loc[df["PE_oi"].fillna(0).idxmax(), "strikePrice"]
    else:
        max_ce_strike = np.nan
        max_pe_strike = np.nan

    _, mp = max_pain(df)

    return {
        "underlying": underlying,
        "ce_oi": ce_oi,
        "pe_oi": pe_oi,
        "ce_change": ce_chg,
        "pe_change": pe_chg,
        "ce_volume": ce_vol,
        "pe_volume": pe_vol,
        "ce_premium": ce_premium,
        "pe_premium": pe_premium,
        "premium_difference": ce_premium - pe_premium,
        "pcr": pcr,
        "max_ce_strike": max_ce_strike,
        "max_pe_strike": max_pe_strike,
        "max_pain": mp,
    }


def max_pain(df):
    if df.empty:
        return pd.DataFrame(), np.nan

    work = df[
        ["strikePrice", "CE_oi", "PE_oi"]
    ].copy().dropna(subset=["strikePrice"])

    work["CE_oi"] = work["CE_oi"].fillna(0)
    work["PE_oi"] = work["PE_oi"].fillna(0)

    strikes = sorted(work["strikePrice"].unique())
    rows = []

    for settle in strikes:
        call_pain = (
            np.maximum(settle - work["strikePrice"], 0) * work["CE_oi"]
        ).sum()

        put_pain = (
            np.maximum(work["strikePrice"] - settle, 0) * work["PE_oi"]
        ).sum()

        rows.append({
            "strikePrice": settle,
            "callPain": call_pain,
            "putPain": put_pain,
            "totalPain": call_pain + put_pain,
        })

    table = pd.DataFrame(rows)
    if table.empty:
        return table, np.nan

    strike = table.loc[table["totalPain"].idxmin(), "strikePrice"]
    return table, strike


def build_heatmap(df, change=False):
    if df.empty:
        return pd.DataFrame()

    if change:
        ce = df.set_index("strikePrice")["CE_change"].fillna(0)
        pe = df.set_index("strikePrice")["PE_change"].fillna(0)
    else:
        ce = df.set_index("strikePrice")["CE_oi"].fillna(0)
        pe = df.set_index("strikePrice")["PE_oi"].fillna(0)

    out = pd.DataFrame({"CE": ce, "PE": pe})
    return out.sort_index()


def build_stock_snapshot(symbol, df, underlying, expiry):
    s = calculate_summary(df, underlying)

    return {
        "Symbol": symbol,
        "Underlying": underlying,
        "Expiry": expiry,
        "PCR": s["pcr"],
        "CE_OI": s["ce_oi"],
        "PE_OI": s["pe_oi"],
        "OI_Change_Total": s["ce_change"] + s["pe_change"],
        "CE_OI_Change": s["ce_change"],
        "PE_OI_Change": s["pe_change"],
        "Max_CE_OI_Strike": s["max_ce_strike"],
        "Max_PE_OI_Strike": s["max_pe_strike"],
        "Max_Pain": s["max_pain"],
    }
