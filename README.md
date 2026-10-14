# 台股量縮均線糾結選股網站

## 篩選條件
- 市場：台股上市＋上櫃（股票清單由 FinMind 公開資料取得）
- 排除金融類股（依來源產業分類欄位及名稱關鍵字排除）
- 最新交易日成交量至少 1,000 張（1 張 = 1,000 股）
- 最新交易日成交量至少 1,000 張，且 <= 前 20 個交易日平均成交量（不含最新交易日）的 10%
- MA5 > MA10
- MA5、MA10、MA20、MA60 的最大值與最小值之差，除以最新收盤價，<= 3%
- 顯示股票代號、名稱、資料日期、收盤價、成交量、前20日均量、量比、MA5/MA10/MA20/MA60、均線糾結幅度
- 可下載 CSV

## 重要資料說明
- 股票清單：FinMind 公開 API 的 `TaiwanStockInfo` 資料集。
- 歷史行情：Yahoo Finance 日線資料（透過 yfinance）。
- 本程式不內建假報價，也不會用示意資料填補空結果。
- 第三方行情可能延遲、缺漏、格式變動或限流；全市場掃描時，請留意畫面顯示的「成功取得歷史行情」數量。如果遠低於股票清單數，結果可能不完整。
- 建議收盤後掃描。程式以最新可取得的日線為基準；盤中執行時，最新日線可能尚未收盤。
- Yahoo Finance 的台股成交量通常以「股」提供；介面預設換算成「張」（1 張 = 1,000 股）。
- 金融股排除仰賴來源產業分類與名稱關鍵字，資料源若分類不完整，仍建議核對名單。
- 本工具是依規則篩選的輔助工具，不構成投資建議。

## Windows 安裝與啟動
1. 安裝 Python 3.11 或更新版本： https://www.python.org/downloads/
2. 將 `app.py` 與 `requirements.txt` 放在同一個資料夾。
3. 在該資料夾開啟命令提示字元（CMD）或 PowerShell。
4. 建議先建立虛擬環境：

   ```powershell
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

   若 PowerShell 阻擋啟用腳本，也可直接使用：

   ```powershell
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   .venv\Scripts\python.exe -m streamlit run app.py
   ```

5. 安裝套件：

   ```powershell
   python -m pip install -r requirements.txt
   ```

6. 啟動網站：

   ```powershell
   python -m streamlit run app.py
   ```

7. 瀏覽器開啟終端機顯示的網址，通常是 `http://localhost:8501`。
8. 第一次建議在左側選「前 100 檔（測試）」；確認成功後，再切換成「全部符合清單的股票」。

## macOS
在終端機進入資料夾後執行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## 常見問題
- **掃描失敗／被限流：** 等待一段時間再試，先用前 100 檔測試。全市場會向行情來源發出多批請求，可能花數分鐘。
- **符合條件 0 檔：** 這是實際篩選結果，不代表程式故障；可查看成交量與均線門檻是否符合你的策略。
- **有些股票沒有資料：** 新上市、歷史資料不足、代碼不存在、資料來源未涵蓋或來源暫時失敗，都可能造成缺漏。
- **想讓手機從外網開啟：** 目前是本機網站，只能在執行程式的電腦上直接開啟。若要外網使用，需另行部署到雲端並評估資料來源條款、資安及費用。


## 歷史資料範圍
介面可選 1、2 或 3 個月。由於策略仍需要 MA60 與前 20 個交易日均量，若只下載 1 個月資料，部分股票會因歷史資料不足而無法計算；建議選 3 個月。
