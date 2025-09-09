
# 書籍訂購（Streamlit + Postgres，多人版）

這是一個可直接部署到 **Streamlit Community Cloud** 的專案範例。表單包含「訂購人姓名、數量」，
送出後會寫入 **Postgres**（雲端或自家資料庫），支援多人同時使用且資料不會因 App 重啟而消失。

## 快速開始（本機測試）
1. 安裝套件
   ```bash
   pip install -r requirements.txt
   ```
2. 建立 `.streamlit/secrets.toml`
   ```toml
   DB_URL = "postgresql://user:password@host:5432/dbname"
   ```
3. 執行
   ```bash
   streamlit run app.py
   ```

## 部署到 Streamlit Community Cloud
1. 把本專案放到 GitHub（至少包含 `app.py`、`requirements.txt`）。
2. 到 https://streamlit.io/cloud 建立新 App，選取你的 GitHub repo。
3. 在 App 的 **Settings → Secrets** 貼上：
   ```toml
   DB_URL = "postgresql://user:password@host:5432/dbname"
   ```
4. 完成後即可取得網址分享給使用者。

## 建立雲端 Postgres 的方式（擇一）
- **Neon**（免費額度）：建立專案後，取得 `postgresql://...` 連線字串貼到 Secrets。
- **Railway/Render/Fly.io**：建立 Postgres 服務並取得連線字串。
- **公司自有 DB**：請網管提供內網/對外連線字串。

## 可選：Docker 自架
你也可以用 `docker-compose` 在一台機器上同時跑 Postgres + App：
```bash
docker compose up -d
```
啟動後瀏覽 `http://localhost:8501`。

## 結構
- `app.py`：Streamlit App（透過 SQLAlchemy 連 Postgres）
- `requirements.txt`：相依套件
- `.streamlit/secrets.toml`：機密設定（**不要 Commit 到 GitHub**）

## 常見問題
- **看不到資料？** 確認 DB_URL 正確，且 Security Group/防火牆允許連線。
- **多使用者同時寫入？** Postgres 天生支援併發，無需額外設定。
- **需要增加欄位（如書名、Email）？** 直接在 `CREATE TABLE` 與表單加欄位，並在 `INSERT` 語句中加入即可。
