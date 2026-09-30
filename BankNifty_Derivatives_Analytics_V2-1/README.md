
# Bank Nifty Derivatives Analytics Dashboard — V2

## Features

- Current Nifty Bank constituent discovery from NSE
- BANKNIFTY index options
- Current constituent stock options
- Nearest / 2nd / 3rd expiry
- ATM ± N strikes
- CE/PE OI, OI change, volume, IV, LTP and price change
- Rule-based Long Buildup / Short Buildup / Short Covering / Long Unwinding / Neutral
- Overall PCR
- Strike-wise PCR
- OI charts
- OI-change charts
- OI heatmap
- OI-change heatmap
- Max Pain calculation for selected expiry
- Futures contracts
- Current Bank-stock snapshot comparison
- CSV downloads
- Optional auto refresh

## Windows setup

Open this folder in VS Code.

```powershell
py -m pip install -r requirements.txt
```

Then:

```powershell
streamlit run app.py
```

If `py` is unavailable:

```powershell
python -m pip install -r requirements.txt
streamlit run app.py
```

## If NSE returns 401/403/429

This project warms an NSE session and retries requests. NSE can still restrict automated requests.

Do not repeatedly press Refresh. Wait and retry later.

## Notes

- The stock comparison makes many NSE requests and may be rate-limited.
- Max Pain is calculated from the selected expiry's CE/PE OI.
- The premium number shown as LTP × volume is a turnover proxy, not a true traded premium value.
- OI labels are descriptive calculations, not trading recommendations.
- NSE's own option-chain page states that its displayed volume/OI are in contracts and that IV is reference information. Check NSE's current Terms of Use before redistributing NSE data.
