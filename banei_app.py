import banei_app1
import banei_app2
import banei_app3  # 追加
import streamlit as st

st.set_page_config(page_title="ばんえい競馬予想アプリ", layout="wide")

mode = st.sidebar.radio(
    "モード選択",
    ["事前予想モード", "当日予想モード", "更新・分析モード"],
)

if mode == "事前予想モード":
    banei_app1.show_screen1()
elif mode == "当日予想モード":
    banei_app2.show_screen2()
elif mode == "更新・分析モード":
    banei_app3.show_screen3()