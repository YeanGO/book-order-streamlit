
import pandas as pd
import streamlit as st
from datetime import datetime
from sqlalchemy import create_engine, text

st.set_page_config(page_title="書籍訂購（雲端資料庫版）", page_icon="📚", layout="centered")
st.title("📚 書籍訂購表單（多人雲端版）")

# ---- Database setup ----
# 將資料庫連線字串放在 .streamlit/secrets.toml 的 DB_URL
# 例：postgresql://user:password@host:5432/dbname
if "DB_URL" not in st.secrets:
    st.error("找不到 DB_URL。請在 .streamlit/secrets.toml 或雲端平台的 Secrets 設定 DB_URL。")
    st.stop()

DB_URL = st.secrets["DB_URL"]
engine = create_engine(DB_URL, pool_pre_ping=True)

def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                qty INTEGER NOT NULL CHECK (qty > 0),
                created_at TIMESTAMP NOT NULL
            );
        """))

def insert_order(name: str, qty: int):
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO orders (name, qty, created_at) VALUES (:n, :q, :t)"
        ), {"n": name, "q": int(qty), "t": datetime.now()})

def fetch_orders(limit: int = 200) -> pd.DataFrame:
    with engine.begin() as conn:
        df = pd.read_sql(text(
            "SELECT id, name, qty, created_at FROM orders ORDER BY id DESC LIMIT :lim"
        ), conn, params={"lim": limit})
    return df

# 初始化資料表
try:
    init_db()
except Exception as e:
    st.error(f"初始化資料庫失敗：{e}")
    st.stop()

# ---- Form ----
with st.form("order_form", clear_on_submit=True):
    name = st.text_input("訂購人姓名", max_chars=50, placeholder="請輸入姓名")
    qty = st.number_input("數量", min_value=1, step=1, value=1)
    submitted = st.form_submit_button("送出訂單")
    if submitted:
        if not name.strip():
            st.error("姓名不可為空白。")
        else:
            try:
                insert_order(name.strip(), qty)
                st.success("訂單已送出！")
            except Exception as e:
                st.error(f"寫入失敗：{e}")

st.subheader("最新訂單")
try:
    df = fetch_orders(limit=200)
    st.dataframe(df, use_container_width=True)
    st.download_button(
        "下載目前訂單（CSV）",
        df.to_csv(index=False).encode("utf-8-sig"),
        "orders.csv",
        "text/csv"
    )
except Exception as e:
    st.error(f"讀取失敗：{e}")

st.caption("資料儲存在你設定的 Postgres 資料庫中；請記得定期備份。")
