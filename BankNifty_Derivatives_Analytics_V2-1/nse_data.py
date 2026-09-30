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
        # NSE needs cookies, without this 401/404 comes
        try:
            self.s.get(self.BASE + "/", timeout=15)
            time.sleep(0.5)
            self.s.get(self.BASE + "/option-chain", timeout=15)
            time.sleep(0.5)
        except:
            pass

    def get(self, path, params=None, attempts=4):
        last = None
        for n in range(attempts):
            try:
                r = self.s.get(self.BASE + path, params=params, timeout=25)
                if r.status_code in (401, 403, 429):
                    last = RuntimeError(f"NSE HTTP {r.status_code} - blocked")
                    self.warm()
                    time.sleep(2 + n*2)
                    continue
                if r.status_code == 404:
                    # For 404 we should not retry same, return None to try other endpoint
                    raise requests.HTTPError(f"404 for {path} {params}", response=r)
                r.raise_for_status()
                return r.json()
            except requests.HTTPError as he:
                # 404 is final for this endpoint
                raise he
            except Exception as e:
                last = e
                time.sleep(1+n)
        raise last or RuntimeError("NSE request failed")

    def get_banknifty_constituents(self):
        try:
            data = self.get("/api/equity-stockIndices", params={"index": "NIFTY BANK"})
            res=[]
            for row in data.get("data", []):
                sym=row.get("symbol")
                if sym and sym.upper() not in ("NIFTY BANK","BANKNIFTY"):
                    if sym not in res:
                        res.append(sym)
            if res:
                return res
        except:
            pass
        return ["HDFCBANK","ICICIBANK","SBIN","KOTAKBANK","AXISBANK","INDUSINDBK","BANDHANBNK","FEDERALBNK","IDFCFIRSTB","AUBANK","PNB","BANKBARODA"]

    def get_option_chain(self, symbol, is_index=False, expiry=None):
        """
        New NSE v3 logic (working 2025-26):
        1. /api/option-chain-contract-info?symbol=BANKNIFTY gives expiries
        2. /api/option-chain-v3?type=Indices&symbol=BANKNIFTY&expiryDate=DD-MMM-YYYY
        """
        errors=[]
        # Try 1: v3 without expiry (returns nearest)
        try:
            params = {"type": "Indices" if is_index else "Equities", "symbol": symbol}
            if expiry:
                params["expiryDate"] = expiry
            payload = self.get("/api/option-chain-v3", params=params)
            if payload.get("records", {}).get("data"):
                return payload
        except Exception as e:
            errors.append(f"v3 no-expiry failed: {e}")

        # Try 2: get contract info then try each expiry
        try:
            contract = self.get("/api/option-chain-contract-info", params={"symbol": symbol})
            # contract structure varies
            expiries = contract.get("expiryDates") or contract.get("records", {}).get("expiryDates") or []
            # if no expiry provided, try first expiry
            target_expiries = [expiry] if expiry else expiries[:1]
            for exp in target_expiries:
                try:
                    params = {"type": "Indices" if is_index else "Equities", "symbol": symbol, "expiryDate": exp}
                    payload = self.get("/api/option-chain-v3", params=params)
                    if payload.get("records", {}).get("data"):
                        return payload
                except Exception as inner:
                    errors.append(f"v3 with {exp} failed: {inner}")
                    continue
        except Exception as e:
            errors.append(f"contract-info failed: {e}")

        # Try 3: old endpoints (will 404 but we try)
        try:
            if is_index:
                return self.get("/api/option-chain-indices", params={"symbol": symbol})
            else:
                return self.get("/api/option-chain-equities", params={"symbol": symbol})
        except Exception as e:
            errors.append(f"old api failed: {e}")

        # If all fail, raise with full log
        raise RuntimeError("NSE blocked all endpoints. Details: " + " | ".join(errors) + ". NSE session cookies expired - wait 2-3 min then click Load again. Do not spam refresh.")

    def get_derivative_quote(self, symbol):
        return self.get("/api/quote-derivative", params={"symbol": symbol})

    def parse_futures(self, payload):
        rows=[]
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
        wanted=["symbol","expiryDate","lastPrice","change","pChange","openInterest","changeinOpenInterest","totalTradedVolume","underlyingValue","instrumentType"]
        out=pd.DataFrame(rows)
        for c in wanted:
            if c not in out.columns:
                out[c]=None
        return out[wanted].drop_duplicates().reset_index(drop=True)
