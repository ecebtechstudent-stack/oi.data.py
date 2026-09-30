import time
import requests
import pandas as pd


class NSEClient:
    BASE = "https://www.nseindia.com"

    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/option-chain",
            "Connection": "keep-alive",
        })
        self.warm()

    def warm(self):
        for path in ["/", "/option-chain"]:
            try:
                self.s.get(self.BASE + path, timeout=15)
            except:
                pass

    def get(self, path, params=None, attempts=3):
        last = None
        for n in range(attempts):
            try:
                r = self.s.get(self.BASE + path, params=params, timeout=25)
                if r.status_code in (401, 403, 429):
                    last = RuntimeError(f"NSE HTTP {r.status_code} - blocked/rate-limited")
                    self.warm()
                    time.sleep(2 + n*2)
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last = e
                time.sleep(1+n)
        raise last or RuntimeError("NSE request failed")

    def get_banknifty_constituents(self):
        try:
            data = self.get("/api/equity-stockIndices", params={"index": "NIFTY BANK"})
            result = []
            for row in data.get("data", []):
                sym = row.get("symbol")
                if sym and sym.upper() not in ("NIFTY BANK","BANKNIFTY"):
                    if sym not in result:
                        result.append(sym)
            if result:
                return result
        except:
            pass
        return ["HDFCBANK","ICICIBANK","SBIN","KOTAKBANK","AXISBANK","INDUSINDBK","BANDHANBNK","FEDERALBNK","IDFCFIRSTB","AUBANK"]

    def get_option_chain(self, symbol, is_index=False, expiry=None):
        # STEP 1: Try new v3 API - this is the current working API as of 2025-2026
        # NSE flow: contract-info gives expiries, v3 gives chain for expiry
        try:
            if expiry:
                # Direct v3 call with expiry
                params = {"type": "Indices" if is_index else "Equities", "symbol": symbol, "expiryDate": expiry}
                payload = self.get("/api/option-chain-v3", params=params)
                if payload.get("records", {}).get("data"):
                    return payload
            else:
                # Get expiries first then chain - more reliable
                try:
                    contract = self.get("/api/option-chain-contract-info", params={"symbol": symbol})
                    # contract info contains expiry list, but we still need chain
                except:
                    pass
                # try v3 without expiry - NSE returns nearest expiry
                params = {"type": "Indices" if is_index else "Equities", "symbol": symbol}
                payload = self.get("/api/option-chain-v3", params=params)
                if payload.get("records", {}).get("data"):
                    return payload
        except Exception as e:
            # v3 failed, will try old as fallback for error message
            last_v3 = e

        # STEP 2: Old APIs - now return 404 (kept only to show clear error)
        try:
            if is_index:
                return self.get("/api/option-chain-indices", params={"symbol": symbol})
            else:
                return self.get("/api/option-chain-equities", params={"symbol": symbol})
        except Exception as old_e:
            raise RuntimeError(f"NSE API 404 fixed needed: Use v3 endpoint. Tried /api/option-chain-v3?type={'Indices' if is_index else 'Equities'}&symbol={symbol}. Old endpoint error: {old_e}")

    def get_derivative_quote(self, symbol):
        return self.get("/api/quote-derivative", params={"symbol": symbol})

    def parse_futures(self, payload):
        rows = []
        def walk(x):
            if isinstance(x, dict):
                if x.get("instrumentType") in ("FUTIDX","FUTSTK"):
                    rows.append(x)
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(payload)
        if not rows:
            return pd.DataFrame()
        wanted = ["symbol","expiryDate","lastPrice","change","pChange","openInterest","changeinOpenInterest","totalTradedVolume","underlyingValue","instrumentType"]
        out = pd.DataFrame(rows)
        for c in wanted:
            if c not in out.columns:
                out[c]=None
        return out[wanted].drop_duplicates().reset_index(drop=True)
