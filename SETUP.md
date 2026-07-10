# 部署教學:讓系統每天自動運行(免費、不用開電腦)

從零開始約 15 分鐘。完成後,每個交易日收盤後(台北時間早上約 5:35)系統自動研究、寫日誌、更新儀表板網頁。

> **隱私須知**:GitHub 免費方案中,「儀表板網址(GitHub Pages)」只有**公開(Public)repo** 才能使用 — 公開代表網路上任何人都能看到 repo 內所有檔案。建議做法:**公開 repo + 示範持倉**(不放真實金額),真實損益請 Claude 在對話裡私下幫你計算;若改用**私人(Private)repo** 則持倉完全保密,但沒有網址,看面板改成從 repo 下載 `docs/index.html` 或請 Claude 更新側邊欄 artifact。repo 隨時可在 Settings 底部 Change visibility 切換公開/私人。

## 步驟 0:註冊 GitHub(已有帳號跳過)

1. 開 [github.com](https://github.com) → 右上 **Sign up**。
2. 輸入 Email → 設密碼 → 取一個使用者名稱(它會出現在儀表板網址:`https://使用者名稱.github.io/ai-stock-advisor/`)。
3. 完成人機驗證 → 收信輸入驗證碼。個人化問題可一路 **Skip**,方案選 **Free**。

## 步驟 1:建立儲存庫(repo)

1. 登入後右上角 **+** → **New repository**。
2. Repository name 填 `ai-stock-advisor`。
3. 選 **Public**(要有儀表板網址;搭配示範持倉)或 **Private**(完全私密、無網址)。
4. 其他選項都不動 → **Create repository**。

## 步驟 2:上傳程式

1. 建立後的頁面中間,點藍字 **uploading an existing file**。
2. 打開 Finder → `Investment Agent/ai-stock-advisor`,**Cmd+A 全選**資料夾內容,拖進網頁虛線框。
3. 等檔案清單出現(advisor、config、docs、journal、output、README.md、run.py…)→ 按綠色 **Commit changes**。
4. 看不到 `.gitignore` 是正常的(Mac 隱藏檔),不影響運作。

## 步驟 3:建立自動排程檔(關鍵)

1. repo 首頁 → **Add file** → **Create new file**。
2. 檔名欄輸入:`.github/workflows/daily.yml`(打到 `/` 會自動變成資料夾,繼續打完)。
3. 用 Mac「文字編輯」打開資料夾裡的 `github-workflow-daily.yml`,全選複製 → 貼到網頁編輯框。
4. 右上 **Commit changes...** → 再按 **Commit changes**。

## 步驟 4:允許 Actions 寫回結果

1. repo → **Settings** → 左側 **Actions → General**。
2. 拉到最底 **Workflow permissions** → 選 **Read and write permissions** → **Save**。

## 步驟 5:開啟儀表板網址(Public repo 限定)

1. Settings → 左側 **Pages**。
2. Branch 選 `main`、資料夾選 **/docs** → **Save**。
3. 幾分鐘後網址生效:`https://你的使用者名稱.github.io/ai-stock-advisor/`(手機瀏覽器開啟後「加入主畫面」,用起來就像 App)。

## 步驟 6:手動觸發第一次執行

1. 上排 **Actions** 分頁 → 若出現提示,按 **I understand my workflows, go ahead and enable them**。
2. 左側 **每日投資研究** → 右側 **Run workflow** ▾ → 綠色 **Run workflow**。
3. 約 2~3 分鐘出現綠色勾勾 → 重新整理儀表板:示範資料已變成真實美股行情。

之後每個交易日自動執行。失敗(紅叉)通常是資料源暫時限流,按 **Re-run** 或隔天自動恢復。

## 步驟 7:換成你的資料

- **觀察清單**:repo 網頁編輯 `config/watchlist.json`(鉛筆圖示線上改)。
- **持倉**:公開 repo 建議持續用示範持倉;真實持倉貼給 Claude,在對話裡私下幫你算損益與風控。私人 repo 則可直接把真實持倉寫進 `config/portfolio.json`(記得刪掉 `"_示範": true`)。

## 常見問題

**Q:會自動下單嗎?** 不會。系統只產生建議與紀錄,錢永遠在你的券商帳戶、由你操作。

**Q:要 API 金鑰嗎?** 不用。Yahoo Finance(備援 Stooq)與 Google News RSS 全部免費免金鑰。

**Q:額度夠嗎?** 公開 repo 的 Actions 完全免費;私人 repo 每月 2,000 分鐘免費額度,本系統每天約用 2~3 分鐘,綽綽有餘。

**Q:想調整?** 停損、部位上限、買賣門檻都在 `config/settings.json`;不確定怎麼改,問 Claude。
