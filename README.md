---
title: YouBike 空站觀察
emoji: 🚲
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# 臺北 YouBike 空站觀察

> 上面 `---` 之間的設定是給 HuggingFace Spaces 讀的（W5 部署時使用），請保留。

115-1 地理資訊系統運用程式的 App 範本。選擇時段與空站門檻，查看臺北各區的 YouBike 空站比例。

## App 用途

（HW4：用你自己的話寫這個 App 能回答什麼問題）

## 資料

| 項目 | 內容 |
|---|---|
| 來源 | 臺北市資料大平臺「YouBike2.0 臺北市公共自行車即時資訊」 |
| 網址 | `https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json` |
| 授權 | 政府資料開放授權條款－第 1 版（使用時須註明來源） |
| 資料時間 | 2026-09-25（五）12:28、17:58、23:28 三個時段的快照 |
| 檔案 | `data/youbike_sample.csv` |

（HW4：換成你自己 HW3 的資料後，更新這張表）

`app.py` 需要的欄位：`時段`、`sno`、`sarea`、`act`、`available_rent_bikes`。

## 在 Codespaces 執行

1. 在 repo 頁面按 **Code → Codespaces → Create codespace on main**。
2. 等環境建好（第一次約 2–3 分鐘，會自動安裝 `requirements.txt` 的套件）。
3. 在終端機輸入：

   ```bash
   solara run app.py
   ```

4. 右下角出現提示時，按 **Open in Browser**；或到「連接埠」分頁，開啟 8765 埠。

## 修改之後

```bash
git status          # 哪些檔案被改了？
git diff            # 改了哪幾行？
git add app.py      # 只加入你確認過的檔案
git commit -m "說明你改了什麼"
git push
```

**agent 改完之後，一定先看 `git diff` 再 commit。**

## 授權

- **程式碼**（`app.py`、`Dockerfile` 等）：MIT License，見 [`LICENSE`](LICENSE)。可以自由使用、修改、公開，請保留 `LICENSE` 檔。
- **資料**（`data/youbike_sample.csv`）：取自臺北市資料大平臺，依政府資料開放授權條款－第 1 版使用，不適用 MIT。換成自己的資料後，請在上方「資料」表格寫明來源與授權。
