# app.py － 書籍訂購表單（多人雲端版＋CRUD＋統計）
from datetime import datetime
from decimal import Decimal
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

st.set_page_config(page_title="書籍訂購（多人雲端版）", page_icon="📚", layout="centered")
st.title("📚 書籍訂購表單（多人雲端版）")

# ---- 讀取資料庫連線（必填） ----
if "DB_URL" not in st.secrets:
    st.error("找不到 DB_URL。請在 .streamlit/secrets.toml 或雲端平台的 Secrets 設定 DB_URL。")
    st.stop()

DB_URL = st.secrets["DB_URL"]
engine = create_engine(DB_URL, pool_pre_ping=True)

# ---- 常數：書籍選單與價格 ----
BOOK_CHOICES = {
    "python人工智慧": Decimal("450"),
    "python基礎學習課程": Decimal("300"),
    "其他選項（自填）": None,  # 其他選項需填書名與價格
}

# ---- DB 初始化與欄位升級（可重複執行，安全） ----
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
        # 逐一補欄位（Postgres 支援 IF NOT EXISTS）
        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS book_category TEXT;"))
        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS book_title TEXT;"))
        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS price NUMERIC(10,2);"))
        conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS note TEXT;"))
        # 針對舊資料若 price 為 NULL，先填 0 以避免運算問題
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

def fetch_orders(limit: int = 500) -> pd.DataFrame:
    with engine.begin() as conn:
        df = pd.read_sql(
            text("""SELECT id, name, qty, book_category, book_title, price, note, created_at
                    FROM orders ORDER BY id DESC LIMIT :lim"""),
            conn, params={"lim": limit}
        )
    # 計算每筆金額
    if not df.empty:
        df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0)
        df["amount"] = df["qty"] * df["price"]
    else:
        for col in ["amount"]:
            df[col] = []
    return df

def update_qty(order_id: int, new_qty: int):
    if new_qty < 1:
        new_qty = 1
    with engine.begin() as conn:
        conn.execute(text("UPDATE orders SET qty = :q WHERE id = :id"), {"q": int(new_qty), "id": int(order_id)})

def delete_order(order_id: int):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM orders WHERE id = :id"), {"id": int(order_id)})

# ---- 初始化 ----
try:
    init_db()
except Exception as e:
    st.error(f"初始化資料庫失敗：{e}")
    st.stop()

# ---- 建單表單 ----
with st.form("order_form", clear_on_submit=True, border=True):
    st.subheader("新增訂單")
    name = st.text_input("訂購人姓名", max_chars=50, placeholder="請輸入姓名")
    category = st.selectbox("選擇書籍", list(BOOK_CHOICES.keys()))
    other_title = ""
    other_price = Decimal("0")

    if category == "其他選項（自填）":
        other_title = st.text_input("其他選項：書名", max_chars=100, placeholder="請輸入書名")
        other_price_str = st.text_input("其他選項：價格（數字）", value="0")
        # 轉數字並檢查
        try:
            other_price = Decimal(other_price_str)
        except Exception:
            other_price = Decimal("0")
        if other_price <= 0:
            st.caption("⚠️ 其他選項價格需為正數。")

    qty = st.number_input("數量", min_value=1, step=1, value=1)
    note = st.text_area("備註（可留空）", max_chars=300, placeholder="可輸入備註…")
    submitted = st.form_submit_button("送出訂單")

    if submitted:
        clean_name = name.strip()
        if not clean_name:
            st.error("姓名不可為空白。")
        else:
            # 決定書名與價格
            if category == "其他選項（自填）":
                title = other_title.strip()
                price = other_price
                if not title:
                    st.error("請輸入『其他選項』的書名。")
                elif price <= 0:
                    st.error("請輸入正確的『其他選項』價格（> 0）。")
                else:
                    try:
                        insert_order(clean_name, qty, "其他選項", title, price, note)
                        st.success("訂單已送出！")
                    except Exception as e:
                        st.error(f"寫入失敗：{e}")
            else:
                title = category  # 直接以選單名稱當作書名
                price = BOOK_CHOICES[category]
                try:
                    insert_order(clean_name, qty, category, title, price, note)
                    st.success("訂單已送出！")
                except Exception as e:
                    st.error(f"寫入失敗：{e}")

st.divider()

# ---- 訂單列表（可刪除、調整數量） ----
st.subheader("訂單列表")
df = fetch_orders(limit=500)

if df.empty:
    st.info("目前沒有訂單。")
else:
    # 逐列呈現，提供「數量調整」與「刪除」
    for _, row in df.iterrows():
        col1, col2, col3, col4, col5, col6, col7 = st.columns([2, 2, 3, 2, 2, 3, 2])
        with col1:
            st.text(f"#{int(row['id'])}")
            st.caption(row["created_at"])
        with col2:
            st.text(row["name"])
            st.caption(row["book_category"])
        with col3:
            st.text(row["book_title"])
            st.caption(f"單價：{Decimal(row['price']):.0f}")
        with col4:
            # 調整數量
            new_qty = st.number_input(
                "數量", min_value=1, step=1, value=int(row["qty"]),
                key=f"qty_{int(row['id'])}", label_visibility="collapsed"
            )
        with col5:
            if st.button("更新數量", key=f"upd_{int(row['id'])}"):
                try:
                    update_qty(int(row["id"]), int(new_qty))
                    st.success("已更新")
                    st.experimental_rerun()
                except Exception as e:
                    st.error(f"更新失敗：{e}")
        with col6:
            st.text(f"小計：{Decimal(row['amount']):.0f}")
            if str(row.get("note", "")).strip():
                st.caption(f"備註：{row['note']}")
        with col7:
            if st.button("🗑 刪除", key=f"del_{int(row['id'])}"):
                try:
                    delete_order(int(row["id"]))
                    st.success("已刪除")
                    st.experimental_rerun()
                except Exception as e:
                    st.error(f"刪除失敗：{e}")

    st.divider()

    # ---- 統計：各書籍數量與金額、以及總金額 ----
    st.subheader("統計")
    # by title
    agg = (
        df.groupby("book_title", dropna=False)
          .agg(數量合計=("qty", "sum"),
               總金額=("amount", "sum"))
          .reset_index()
          .sort_values("book_title")
    )
    # 顯示金額為整數（若你要顯示到小數可改 .2f）
    agg["總金額"] = agg["總金額"].apply(lambda x: f"{Decimal(x):.0f}")
    st.dataframe(agg, use_container_width=True)

    total_amount = Decimal(df["amount"].sum())
    st.metric(label="全部書籍的總金額", value=f"{total_amount:.0f}")

    # 下載目前訂單
    export_df = df.copy()
    export_df["price"] = export_df["price"].apply(lambda x: f"{Decimal(x):.0f}")
    export_df["amount"] = export_df["amount"].apply(lambda x: f"{Decimal(x):.0f}")
    st.download_button(
        "下載目前訂單（CSV）",
        export_df.to_csv(index=False).encode("utf-8-sig"),
        "orders.csv",
        "text/csv",
    )

st.caption("※ 定義價格：python人工智慧＝450、python基礎學習課程＝300；其他選項需自填書名與價格。")
