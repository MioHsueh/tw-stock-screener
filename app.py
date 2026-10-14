import time
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="台股量縮均線糾結選股", page_icon="📉", layout="wide")

st.title("📉 台股量縮 × 均線糾結選股")
st.caption("掃描台股上市＋上櫃｜收盤後日線篩選｜資料由外部行情來源取得，不會產生假造報價")

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def get_stock_universe():
    """Fetch stock master data and exclude financial sector by category/name."""
    response = requests.get(
        FINMIND_URL,
        params={"dataset": "TaiwanStockInfo"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") not in (200, "200", None):
        raise RuntimeError(f"股票清單來源回應錯誤：{payload}")

    df = pd.DataFrame(payload.get("data", []))
    if df.empty or "stock_id" not in df.columns:
        raise RuntimeError("股票清單來源沒有回傳可用資料。")

    df["stock_id"] = df["stock_id"].astype(str).str.strip()
    df = df[df["stock_id"].str.fullmatch(r"\d{4}", na=False)].copy()

    if "stock_name" not in df.columns:
        df["stock_name"] = ""
    if "industry_category" not in df.columns:
        df["industry_category"] = ""
    df["stock_name"] = df["stock_name"].fillna("").astype(str)
    df["industry_category"] = df["industry_category"].fillna("").astype(str)

    finance_category = df["industry_category"].str.contains(
        r"金融|銀行|保險|證券|期貨|票券|金控", case=False, regex=True, na=False
    )
    finance_name = df["stock_name"].str.contains(
        r"金融|金控|銀行|證券|期貨|票券|產險|壽險|保險", case=False, regex=True, na=False
    )
    df = df[~(finance_category | finance_name)].copy()
    df = df.drop_duplicates(subset=["stock_id"], keep="last")
    return df[["stock_id", "stock_name", "industry_category"]].sort_values("stock_id").reset_index(drop=True)


def download_history(stock_ids, period="3mo", chunk_size=25, progress=None):
    """
    Download Taiwan daily bars in small batches. Tries .TW and .TWO separately
    per batch to reduce yfinance MultiIndex ambiguity and request burst size.
    """
    histories = []
    total_chunks = max(1, (len(stock_ids) + chunk_size - 1) // chunk_size)

    for chunk_no, start in enumerate(range(0, len(stock_ids), chunk_size), start=1):
        chunk = stock_ids[start:start + chunk_size]
        ticker_map = {}
        for sid in chunk:
            ticker_map[sid] = [f"{sid}.TW", f"{sid}.TWO"]

        tickers = [t for pair in ticker_map.values() for t in pair]
        try:
            data = yf.download(
                tickers=tickers,
                period=period,
                interval="1d",
                auto_adjust=False,
                group_by="ticker",
                progress=False,
                threads=False,
                timeout=30,
            )
        except Exception:
            data = pd.DataFrame()

        if not data.empty and isinstance(data.columns, pd.MultiIndex):
            available = set(data.columns.get_level_values(0))
            for sid, candidates in ticker_map.items():
                for ticker in candidates:
                    if ticker not in available:
                        continue
                    try:
                        one = data[ticker].copy()
                        one = one.dropna(subset=["Close", "Volume"], how="any")
                        if len(one) >= 60:
                            one["stock_id"] = sid
                            one["ticker"] = ticker
                            histories.append(one)
                            break
                    except Exception:
                        continue

        elif not data.empty and len(chunk) == 1:
            one = data.dropna(subset=["Close", "Volume"], how="any")
            if len(one) >= 60:
                one["stock_id"] = chunk[0]
                one["ticker"] = chunk[0] + ".TW"
                histories.append(one)

        if progress:
            progress.progress(
                min(chunk_no / total_chunks, 1.0),
                text=f"下載行情中：第 {chunk_no}/{total_chunks} 批",
            )
        time.sleep(0.2)

    return histories


def evaluate_stock(
    hist,
    stock_name,
    volume_ratio_limit,
    ma_spread_limit,
    min_volume_lots,
    volume_unit,
):
    hist = hist.copy().sort_index()
    hist = hist[~hist.index.duplicated(keep="last")]
    hist["Close"] = pd.to_numeric(hist["Close"], errors="coerce")
    hist["Volume"] = pd.to_numeric(hist["Volume"], errors="coerce")
    hist = hist.dropna(subset=["Close", "Volume"])

    # Need 60 daily closes for MA60 and 20 complete previous sessions for volume average.
    if len(hist) < 61:
        return None

    latest = hist.iloc[-1]
    previous_20 = hist["Volume"].iloc[-21:-1]
    if len(previous_20) != 20:
        return None

    close = float(latest["Close"])
    volume_shares = float(latest["Volume"])
    avg20_shares = float(previous_20.mean())
    if close <= 0 or avg20_shares <= 0:
        return None

    # Minimum volume threshold: 1 lot = 1,000 shares.
    if volume_shares / 1000 < min_volume_lots:
        return None

    ma5 = float(hist["Close"].rolling(5).mean().iloc[-1])
    ma10 = float(hist["Close"].rolling(10).mean().iloc[-1])
    ma20 = float(hist["Close"].rolling(20).mean().iloc[-1])
    ma60 = float(hist["Close"].rolling(60).mean().iloc[-1])
    # Tangle is defined using MA5, MA10 and MA20 only.
    mas_tangle = [ma5, ma10, ma20]
    if any(pd.isna(value) for value in [ma5, ma10, ma20, ma60]):
        return None

    volume_ratio_pct = volume_shares / avg20_shares * 100
    spread_pct = (max(mas_tangle) - min(mas_tangle)) / close * 100
    if volume_ratio_pct > volume_ratio_limit or spread_pct > ma_spread_limit:
        return None

    volume_label = f"成交量({volume_unit})"
    avg_label = f"前20日均量({volume_unit})"
    divisor = 1000 if volume_unit == "張" else 1

    return {
        "股票代號": str(latest.get("stock_id", "")),
        "股票名稱": stock_name,
        "資料日期": pd.Timestamp(hist.index[-1]).strftime("%Y-%m-%d"),
        "收盤價": close,
        volume_label: volume_shares / divisor,
        avg_label: avg20_shares / divisor,
        "量比(%)": volume_ratio_pct,
        "MA5": ma5,
        "MA10": ma10,
        "MA20": ma20,
        "MA60": ma60,
        "均線糾結幅度(%)": spread_pct,
        "行情代碼": str(latest.get("ticker", "")),
    }


with st.sidebar:
    st.header("篩選設定")
    volume_ratio_limit = st.number_input(
        "成交量上限（前20日均量的 %）",
        min_value=1.0, max_value=100.0, value=20.0, step=1.0,
        help="設定 20 代表最新交易日成交量不得超過前 20 個交易日平均成交量的 20%。",
    )
    ma_spread_limit = st.number_input(
        "均線糾結幅度上限（%）",
        min_value=0.1, max_value=20.0, value=6.0, step=0.5,
    )
    min_volume_lots = st.number_input(
        "最低當日成交量（張）",
        min_value=0, max_value=1000000, value=1000, step=100,
        help="只保留最新交易日成交量至少達到此張數的股票；1 張 = 1,000 股。",
    )
    period_label = st.selectbox(
        "歷史資料下載範圍",
        ["1 個月", "2 個月", "3 個月（建議）", "6 個月"],
        index=2,
    )
    period = {
        "1 個月": "1mo",
        "2 個月": "2mo",
        "3 個月（建議）": "3mo",
        "6 個月": "6mo",
    }[period_label]
    volume_unit = st.radio("成交量顯示單位", ["張", "股"], index=0)
    scan_choice = st.selectbox(
        "掃描數量（測試用）",
        ["全部符合清單的股票", "前 100 檔（測試）", "前 300 檔（測試）"],
        index=0,
        help="第一次可選前 100 檔測試；正式掃描選全部。",
    )
    run_scan = st.button("🔎 開始掃描", type="primary", use_container_width=True)

st.info(
    f"篩選規則：排除金融類股；最新交易日成交量至少 {min_volume_lots:,.0f} 張，"
    f"且不超過前 20 個交易日平均成交量的 {volume_ratio_limit:.0f}%；"
    f"MA5 > MA10；MA5、MA10、MA20、MA60 的最大值與最小值之差 "
    f"÷ 最新收盤價 ≤ {ma_spread_limit:.1f}%。"
)
st.caption(
    "資料來源：FinMind 公開股票清單 + Yahoo Finance 日線歷史行情。"
    "第三方資料可能延遲、缺漏或限流；本工具不是即時報價服務。"
)

if "scan_results" not in st.session_state:
    st.session_state.scan_results = None
if "scan_error" not in st.session_state:
    st.session_state.scan_error = None

if run_scan:
    st.session_state.scan_results = None
    st.session_state.scan_error = None
    try:
        with st.spinner("取得上市櫃股票清單…"):
            universe = get_stock_universe()

        if scan_choice == "前 100 檔（測試）":
            universe = universe.head(100)
        elif scan_choice == "前 300 檔（測試）":
            universe = universe.head(300)

        st.write(
            f"股票清單（已排除金融類股）共 {len(universe):,} 檔，"
            "開始下載日線資料。全市場掃描可能需要數分鐘。"
        )
        progress = st.progress(0, text="準備下載行情…")
        stock_ids = universe["stock_id"].tolist()
        names = dict(zip(universe["stock_id"], universe["stock_name"]))
        histories = download_history(stock_ids, period=period, progress=progress)

        rows = []
        for hist in histories:
            sid = str(hist["stock_id"].iloc[0])
            ticker = str(hist["ticker"].iloc[0])
            hist = hist.drop(columns=["stock_id", "ticker"], errors="ignore")
            # Attach ticker as a column for the result date/metadata, without affecting calculations.
            hist["ticker"] = ticker
            row = evaluate_stock(
                hist,
                names.get(sid, ""),
                volume_ratio_limit,
                ma_spread_limit,
                min_volume_lots,
                volume_unit,
            )
            if row:
                row["股票代號"] = sid
                row["行情代碼"] = ticker
                rows.append(row)

        result = pd.DataFrame(rows)
        if not result.empty:
            result = result.sort_values(
                ["量比(%)", "均線糾結幅度(%)"], ascending=[True, True]
            ).reset_index(drop=True)

        st.session_state.scan_results = result
        st.session_state.scan_meta = {
            "universe_count": len(universe),
            "history_count": len(histories),
            "run_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "period": period_label,
        }
    except Exception as exc:
        st.session_state.scan_error = str(exc)

if st.session_state.scan_error:
    st.error("掃描失敗。可能是網路、資料來源格式或請求限制造成。")
    st.code(st.session_state.scan_error)
    st.markdown("請稍後重試；若持續失敗，可先選「前 100 檔（測試）」確認資料連線。")

if st.session_state.scan_results is not None:
    result = st.session_state.scan_results
    meta = st.session_state.get("scan_meta", {})
    c1, c2, c3 = st.columns(3)
    c1.metric("符合條件", f"{len(result):,} 檔")
    c2.metric("成功取得歷史行情", f"{meta.get('history_count', 0):,} 檔")
    c3.metric("掃描時間", meta.get("run_time", "—"))

    st.caption(
        f"股票清單（已排除金融類股）共 {meta.get('universe_count', 0):,} 檔；"
        f"資料期間：{meta.get('period', '—')}。"
        "若成功取得行情的股票數明顯少於清單數，結果可能不完整。"
    )

    if result.empty:
        st.warning("這次沒有找到符合條件的股票。這是實際篩選結果，不會以示意資料補上。")
    else:
        display = result.drop(columns=["行情代碼"], errors="ignore").copy()
        numeric_formats = {
            "收盤價": "{:.2f}",
            f"成交量({volume_unit})": "{:,.0f}",
            f"前20日均量({volume_unit})": "{:,.0f}",
            "量比(%)": "{:.2f}%",
            "MA5": "{:.2f}",
            "MA10": "{:.2f}",
            "MA20": "{:.2f}",
            "MA60": "{:.2f}",
            "均線糾結幅度(%)": "{:.2f}%",
        }
        st.dataframe(
            display.style.format(numeric_formats, na_rep="—"),
            use_container_width=True,
            hide_index=True,
        )
        csv_data = display.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            "⬇️ 下載 CSV",
            data=csv_data,
            file_name="台股量縮均線糾結選股.csv",
            mime="text/csv",
        )
        st.caption(
            "量比 = 最新交易日成交量 ÷ 前20個交易日均量；"
            "均線糾結幅度 = (MA5、MA10、MA20 的最高值 − 最低值) ÷ 最新收盤價。"
        )
else:
    st.subheader("使用方式")
    st.markdown(
        """
        1. 左側可以調整量縮上限、均線糾結幅度、最低成交量及歷史資料期間。
        2. 建議選「3 個月」，以便計算 MA60 及前 20 日均量。
        3. 第一次可選「前 100 檔（測試）」確認資料連線。
        4. 確認成功後選擇「全部符合清單的股票」再按「開始掃描」。
        5. 結果可以直接查看或下載 CSV。

        建議在台股收盤後執行；盤中最新日線可能尚未完成。
        """
    )
