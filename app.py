# app.py － 書籍訂購表單（多人雲端版＋CRUD＋統計）— 加速優化版
from datetime import datetime
from decimal import Decimal
from typing import List, Dict

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text, bindparam

# ---------------- 基本設定 ----------------
st.set_page_config(page_title="書籍訂購（多人雲端版）", page_icon="📚", layout="wide")
st.title("📚 書籍訂購表單（多人雲端版）")

# ---- 讀取資料庫連線（必填） ----
if "DB_URL" not in st.secrets:
    st.error("找不到 DB_URL。請在 .streamlit/secrets.toml 或雲端平台的 Secrets 設定 DB_URL。")
    st.stop()

DB_URL = st.secrets["DB_URL"]

@st.cache_resource
def get_engine():
    # pool_pre_ping 避免閒置連線失效；pool_recycle 讓長連線定期重建
    return create_engine(DB_URL, pool_pre_ping=True, pool_recycle=1800)

engine = get_engine()

# ---- 常數：書籍選單與價格 ----
BOOK_PRICES = {
    "python人工智慧": Decimal("450"),
    "python基礎學習課程": Decimal("300"),
}
OTHER_LABEL = "其他（自填）"

# ---------------- 資料層：初始化 & CRUD ----------------
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
        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS book_category TEXT;"))
        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS book_title TEXT;"))
        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS price NUMERIC(10,2);"))
        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS note TEXT;"))
        conn.execute(text("UPDATE orders SET price = 0 WHERE price IS NULL;"))
        conn.execute(text("UPDATE orders SET book_category = COALESCE(book_category,'(未填)') WHERE book_category IS NULL;"))
        conn.execute(text("UPDATE orders SET book_title = COALESCE(book_title,'(未填)') WHERE book_title IS NULL;"))

def insert_order(name: str, qty: int, book_category: str, book_title: str, price: Decimal, note: str | None):
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO orders (name, qty, created_at, book_category, book_title, price, note)
                VALUES (:n, :q, :t, :bc, :bt, :p, :note)
            """),
            {"n": name, "q": int(qty), "t": datetime.now(), "bc": book_category, "bt": book_title, "p": price, "note": note or ""}
        )

@st.cache_data(ttl=5)
def fetch_orders(limit: int = 500) -> pd.DataFrame:
    with engine.begin() as conn:
        df = pd.read_sql(
            text("""SELECT id, name, qty, book_category, book_title, price, note, created_at
                    FROM orders ORDER BY id DESC LIMIT :lim"""),
            conn, params={"lim": limit}
        )
    if df.empty:
        return pd.DataFrame(columns=["id","name","qty","book_category","book_title","price","note","created_at","amount"])
    # 型別轉換與金額
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0)
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0).astype(int)
    df["amount"] = (df["qty"] * df["price"]).astype(float)
    return df

def batch_apply(updates: List[Dict], delete_ids: List[int]):
    """一次交易內完成多筆更新與刪除"""
    with engine.begin() as conn:
        # 1) 更新數量
        if updates:
            conn.execute(
                text("UPDATE orders SET qty = :q WHERE id = :id"),
                updates  # executemany
            )
        # 2) 刪除（expanding IN）
        if delete_ids:
            stmt = text("DELETE FROM orders WHERE id IN :ids").bindparams(
                bindparam("ids", expanding=True)
            )
            conn.execute(stmt, {"ids": delete_ids})

# ---------------- 初始化 ----------------
try:
    init_db()
except Exception as e:
    st.error(f"初始化資料庫失敗：{e}")
    st.stop()

# =========================
# 建單區（使用 form，避免每次輸入都重跑）
# =========================
st.subheader("新增訂單")

with st.form("create_order_form", clear_on_submit=True):
    name = st.text_input("訂購人姓名", max_chars=50, placeholder="請輸入姓名")

    # 書籍選擇（radio，不用下拉）
    choice = st.radio("選擇書籍", list(BOOK_PRICES.keys()) + [OTHER_LABEL], horizontal=True)

    if choice == OTHER_LABEL:
        # 立刻顯示其他欄位（在 form 內不會造成多次 rerun）
        title = st.text_input("其他選項：書名", max_chars=100, placeholder="請輸入書名")
        other_price = st.number_input("其他選項：價格（數字）", min_value=0.0, step=1.0, value=0.0)
        price = Decimal(str(other_price))
        category = "其他選項"
    else:
        show_price = float(BOOK_PRICES[choice])
        st.number_input("單價（唯讀）", value=show_price, disabled=True)
        price = BOOK_PRICES[choice]
        title = choice
        category = choice

    qty = st.number_input("數量", min_value=1, step=1, value=1)
    note = st.text_area("備註（可留空）", max_chars=300, placeholder="可輸入備註…")

    submitted = st.form_submit_button("➕ 送出訂單", use_container_width=True)

if submitted:
    clean_name = (name or "").strip()
    if not clean_name:
        st.error("姓名不可為空白。")
    elif choice == OTHER_LABEL and (not title.strip() or price <= 0):
        st.error("請輸入『其他選項』的書名與正確價格（> 0）。")
    else:
        try:
            insert_order(clean_name, int(qty), category, title.strip(), price, note)
            st.success("訂單已送出！")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"寫入失敗：{e}")

st.divider()

# =========================
# 訂單列表（批次調整數量／批次刪除）
# =========================
st.subheader("訂單列表")
df = fetch_orders(limit=500)

if df.empty:
    st.info("目前沒有訂單。")
else:
    # 顯示用 DataFrame
    view_df = df[["id","created_at","name","book_category","book_title","price","qty","amount","note"]].copy()
    view_df["price"] = view_df["price"].astype(float)
    view_df["amount"] = view_df["amount"].astype(float)

    # 加一個刪除勾選欄
    view_df.insert(1, "刪除", False)

    edited = st.data_editor(
        view_df,
        use_container_width=True,
        height=420,
        num_rows="fixed",
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "刪除": st.column_config.CheckboxColumn("刪除"),
            "created_at": st.column_config.DatetimeColumn("建立時間", disabled=True),
            "name": st.column_config.TextColumn("訂購人", disabled=True),
            "book_category": st.column_config.TextColumn("類別", disabled=True),
            "book_title": st.column_config.TextColumn("書名", disabled=True),
            "price": st.column_config.NumberColumn("單價", step=1, disabled=True),
            "qty": st.column_config.NumberColumn("數量", step=1, min_value=1),
            "amount": st.column_config.NumberColumn("小計", disabled=True),
            "note": st.column_config.TextColumn("備註", disabled=True),
        },
        key="orders_editor"
    )

    # 計算「有變動的數量」與「需要刪除的 id」
    # 1) 刪除
    delete_ids = edited.loc[edited["刪除"] == True, "id"].astype(int).tolist()

    # 2) 數量變更（比對原始 df）
    merged = edited[["id","qty"]].merge(df[["id","qty"]], on="id", how="left", suffixes=("_new","_old"))
    changed = merged[merged["qty_new"].astype(int) != merged["qty_old"].astype(int)]
    updates = [{"id": int(row.id), "q": int(row.qty_new)} for row in changed.itertuples(index=False)]

    colA, colB = st.columns([1,3])
    with colA:
        apply_clicked = st.button("🚀 套用變更", type="primary", use_container_width=True)
    with colB:
        st.caption(f"待更新數量：{len(updates)}　|　待刪除筆數：{len(delete_ids)}")

    if apply_clicked:
        try:
            batch_apply(updates, delete_ids)
            st.success("已完成套用。重新載入最新資料…")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"套用失敗：{e}")

    st.divider()

    # ---- 統計 ----
    st.subheader("統計")
    agg = (
        df.groupby("book_title", dropna=False)
          .agg(數量合計=("qty", "sum"),
               總金額=("amount", "sum"))
          .reset_index()
          .sort_values("book_title")
    )
    agg["總金額"] = agg["總金額"].round(0).astype(int).astype(str)
    st.dataframe(agg, use_container_width=True)

    total_amount = float(df["amount"].sum())
    st.metric(label="全部書籍的總金額", value=f"{total_amount:.0f}")

    export_df = df.copy()
    export_df["price"] = export_df["price"].round(0).astype(int)
    export_df["amount"] = export_df["amount"].round(0).astype(int)
    st.download_button(
        "下載目前訂單（CSV）",
        export_df.to_csv(index=False).encode("utf-8-sig"),
        "orders.csv",
        "text/csv",
    )

st.caption("※ 定義價格：python人工智慧＝450、python基礎學習課程＝300；其他選項可自填書名與價格。")
