# 課程 App 專案規範（給 AI Coding Agent）

## 專案背景

- 這是彰師大地理系「地理資訊系統運用程式」學生的個人 App repo，使用者是正在學習 Python 與 GIS 程式設計的大學部學生。
- 用 [Solara](https://solara.dev/) 開發網頁 App，在 **GitHub Codespaces** 開發，之後部署到 HuggingFace Spaces（Docker）。
- 執行方式：`solara run app.py`，預設在 8765 埠。

## 檔案結構

- `app.py`：App 主程式。
- `data/`：App 使用的資料。**唯讀：禁止修改、覆寫、刪除、移動或重新命名。** 要換資料時，由我自己放檔案進來。
- `requirements.txt`：套件清單，**每個套件都要固定版本**（`套件==版本`）。
- `Dockerfile`：部署到 HuggingFace Spaces 用。
- `.devcontainer/`：Codespaces 的環境設定。

## 程式撰寫規則

1. 註解與介面文字一律使用繁體中文（台灣用語）。
2. 以初學者看得懂為原則：一個函式只做一件事，避免過長的鏈式呼叫。
3. 圖表用 Plotly（`solara.FigurePlotly`），不要用 matplotlib。部署環境沒有中文字型，matplotlib 的中文會變成方框。
4. 讀檔放在元件外面，不要每次操作都重新讀檔。
5. 讀 CSV 時，`sno`、`act` 這類代碼欄位要指定為字串（`dtype={"sno": str, "act": str}`）。
6. 需要新增套件時，先說明理由並取得我的同意，再寫進 `requirements.txt` 並固定版本。
7. **API 金鑰、token、密碼不得寫進程式碼或 commit。** 需要時從環境變數讀取（Codespaces secrets、HuggingFace Space Secrets）。

## 資料判讀原則

- 不要只憑欄位名稱猜測欄位的意義、單位或統計範圍。請先實際檢查資料內容，必要時查資料來源的官方說明，再列出你的判斷與依據；不確定時直接說不確定。
- 頁面上要標示資料來源與資料時間。

## 協作方式

- 新增或修改檔案前，先簡述計畫，並列出會動到哪些檔案。**只改我要求的檔案**，想順便修改其他檔案時，先問我。
- 執行安裝套件、刪除檔案或其他 shell 指令前，先說明這個指令做什麼。
- **不要自己執行 `git commit`、`git push`、`git reset`。** 改完後告訴我改了哪些檔案，由我看過 `git diff` 再自己 commit。
- 提出建議時附上理由，讓我能判斷要採納、拒絕或修改。
