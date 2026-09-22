import json
import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
import pandas as pd
import requests
import streamlit as st

# ---------------------------------------------------------
# フォルダ構造の自動定義とパス取得関数
# ---------------------------------------------------------
DIR_PRE = "data/pre"
DIR_TODAY = "data/today"
DIR_RESULT = "data/result"
for d in [DIR_PRE, DIR_TODAY, DIR_RESULT]:
    os.makedirs(d, exist_ok=True)


def get_pre_path(date_str):
    p = os.path.join(DIR_PRE, f"pre_data_{date_str}.json")
    return (
        p
        if os.path.exists(p) or not os.path.exists(f"pre_data_{date_str}.json")
        else f"pre_data_{date_str}.json"
    )


def get_today_path(date_str):
    p = os.path.join(DIR_TODAY, f"today_data_{date_str}.json")
    return (
        p
        if os.path.exists(p) or not os.path.exists(f"today_data_{date_str}.json")
        else f"today_data_{date_str}.json"
    )


# =========================================================
# 水分量キー判定
# =========================================================
def get_moisture_key(val):
    if val <= 0.9:
        return "~0.9"
    elif val <= 1.5:
        return "~1.5"
    elif val <= 2.0:
        return "~2"
    elif val <= 3.0:
        return "~3"
    else:
        return "3.1~"


# =========================================================
# オッズ数値から記号への変換
# =========================================================
def convert_odds_to_symbol(odds_val):
    try:
        val = float(odds_val)
        if 1.0 <= val <= 5.0:
            return "◎"
        elif 5.1 <= val <= 10.0:
            return "○"
        elif 10.1 <= val <= 20.0:
            return "▲"
        elif 20.1 <= val <= 30.0:
            return "△"
        elif val >= 30.1:
            return "×"
        else:
            return ""
    except ValueError:
        return ""


# =========================================================
# 馬体増減数値からマスタキーへの変換
# =========================================================
def get_weight_key(weight_diff_val):
    try:
        val = int(re.sub(r"[^\d-]", "", str(weight_diff_val)))
        if val >= 20:
            return "+20以上"
        elif 10 <= val <= 19:
            return "+10台"
        elif -9 <= val <= 9:
            return "±1桁"
        else:
            return "-2桁"
    except Exception:
        return "±1桁"


# =========================================================
# レース別過去的中率データ＆基準超え判定
# =========================================================
def get_race_winrate_info(race_num):
    rates = {
        1: {"単勝": 75.6, "2連": 53.7, "3連": 30.5},
        2: {"単勝": 68.3, "2連": 46.3, "3連": 15.9},
        3: {"単勝": 65.9, "2連": 42.7, "3連": 19.5},
        4: {"単勝": 69.1, "2連": 40.7, "3連": 17.3},
        5: {"単勝": 85.2, "2連": 59.3, "3連": 33.3},
        6: {"単勝": 71.6, "2連": 45.7, "3連": 23.5},
        7: {"単勝": 80.2, "2連": 55.6, "3連": 32.1},
        8: {"単勝": 70.4, "2連": 49.4, "3連": 22.2},
        9: {"単勝": 75.6, "2連": 51.2, "3連": 23.2},
        10: {"単勝": 84.1, "2連": 56.1, "3連": 32.9},
        11: {"単勝": 78.0, "2連": 43.9, "3連": 20.7},
        12: {"単勝": 70.7, "2連": 50.0, "3連": 25.6},
    }
    r = rates.get(race_num, {"単勝": 75.0, "2連": 50.0, "3連": 25.0})

    tan_bg = (
        "background-color: #fff9c4; font-weight: bold; border: 1px solid #fbc02d;"
        if r["単勝"] > 75.0
        else ""
    )
    ren2_bg = (
        "background-color: #fff9c4; font-weight: bold; border: 1px solid #fbc02d;"
        if r["2連"] > 50.0
        else ""
    )
    ren3_bg = (
        "background-color: #fff9c4; font-weight: bold; border: 1px solid #fbc02d;"
        if r["3連"] > 25.0
        else ""
    )

    return r, tan_bg, ren2_bg, ren3_bg


# =========================================================
# 本日の騎手成績集計関数（data/result フォルダ最優先検索）
# =========================================================
def get_today_jockey_stats(date_str):
    jockey_stats = {}

    # 1. data/result フォルダ内のパスを最優先指定
    res_file = os.path.join(DIR_RESULT, f"result_data_{date_str}.json")
    if not os.path.exists(res_file):
        # 2. 直下の旧ファイルパスをフォールバック指定
        res_file = f"result_data_{date_str}.json"

    if os.path.exists(res_file):
        try:
            with open(res_file, "r", encoding="utf-8") as f:
                res_data = json.load(f)

            # pre_data も data/pre を正しく参照
            pre_file = get_pre_path(date_str)
            pre_jockey_map = {}
            if os.path.exists(pre_file):
                with open(pre_file, "r", encoding="utf-8") as pf:
                    p_data = json.load(pf)
                for r_k, h_list in p_data.items():
                    pre_jockey_map[r_k] = {
                        int(h["馬番"]): h.get("騎手", "")
                        for h in h_list
                        if "馬番" in h
                    }

            for r_k, r_info in res_data.items():
                top1 = r_info.get("1着")
                top2 = r_info.get("2着")
                top3 = r_info.get("3着")
                j_map = pre_jockey_map.get(r_k, {})

                for h_num, j_name in j_map.items():
                    if not j_name:
                        continue
                    if j_name not in jockey_stats:
                        jockey_stats[j_name] = {
                            "1着": 0,
                            "2着": 0,
                            "3着": 0,
                            "4着以下": 0,
                        }

                    if top1 is not None:
                        if h_num == top1:
                            jockey_stats[j_name]["1着"] += 1
                        elif h_num == top2:
                            jockey_stats[j_name]["2着"] += 1
                        elif h_num == top3:
                            jockey_stats[j_name]["3着"] += 1
                        else:
                            jockey_stats[j_name]["4着以下"] += 1
        except Exception:
            pass

    result_list = []
    for j_name, stat in jockey_stats.items():
        tot = stat["1着"] + stat["2着"] + stat["3着"] + stat["4着以下"]
        win_rate = (stat["1着"] / tot * 100) if tot > 0 else 0.0
        fuku_rate = (
            ((stat["1着"] + stat["2着"] + stat["3着"]) / tot * 100)
            if tot > 0
            else 0.0
        )

        formatted_score = (
            f"{stat['1着']} － {stat['2着']} － {stat['3着']} － {stat['4着以下']}"
        )
        result_list.append(
            {
                "騎手名": j_name,
                "本日成績 (1着-2着-3着-4着以下)": formatted_score,
                "出走数": tot,
                "1着数": stat["1着"],
                "2着数": stat["2着"],
                "3着数": stat["3着"],
                "4着以下数": stat["4着以下"],
                "勝率": f"{win_rate:.1f}%",
                "複勝率": f"{fuku_rate:.1f}%",
            }
        )

    df_res = pd.DataFrame(result_list)
    if not df_res.empty:
        df_res = df_res.sort_values(by="1着数", ascending=False)
    return df_res

# =========================================================
# 当日オッズ・馬体重増減の自動取得
# =========================================================
def fetch_realtime_odds_weight(date_str, race_no):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
    }
    race_id = f"{date_str[:4]}65{date_str[4:]}{race_no:02d}"
    url_shutuba = f"https://nar.netkeiba.com/race/shutuba.html?race_id={race_id}"

    odds_weight_dict = {}

    try:
        NAME_FIXES = {"大河原和": "大河原和雄", "竹ケ原茉": "竹ケ原茉耶"}

        res_s = requests.get(url_shutuba, headers=headers, timeout=10)
        res_s.encoding = (
            res_s.apparent_encoding if res_s.apparent_encoding else "utf-8"
        )
        soup_s = BeautifulSoup(res_s.text, "html.parser")

        rows = soup_s.find_all("tr")

        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 8:
                c_txts = [c.get_text(strip=True) for c in cols]

                horse_num = None
                for idx in [1, 0, 2]:
                    if idx < len(c_txts) and c_txts[idx].isdigit():
                        val = int(c_txts[idx])
                        if (
                            1 <= val <= 12
                            and len(c_txts) > 3
                            and not c_txts[3].isdigit()
                        ):
                            horse_num = val
                            break

                if horse_num is not None:
                    row_text = "".join(c_txts)
                    is_canceled = (
                        "取消" in row_text or "除外" in row_text or "取" in row_text
                    )

                    jockey, trainer = "", ""
                    if len(cols) >= 7:
                        j_raw = re.sub(
                            r"[◇▲★☆]", "", cols[6].get_text(strip=True)
                        ).strip()
                        jockey = NAME_FIXES.get(j_raw, j_raw)

                    if len(cols) >= 8:
                        t_raw = (
                            cols[7]
                            .get_text(strip=True)
                            .replace("ばんえい", "")
                            .replace("（ばんえい）", "")
                            .replace("(ばんえい)", "")
                            .replace("帯広", "")
                            .split("（")[0]
                            .strip()
                        )
                        trainer = NAME_FIXES.get(t_raw, t_raw)

                    weight_diff = "0"
                    weight_match = re.search(r"\(([-+±]?\d+)\)", row_text)
                    if weight_match:
                        raw_w = weight_match.group(1)
                        weight_diff = raw_w.replace("+", "").replace("±", "")

                    odds_val_num = 999.0
                    odds_symbol = ""
                    pop_rank = "-"

                    for txt in reversed(c_txts):
                        if odds_val_num == 999.0:
                            o_match = re.search(r"^(\d+\.\d+)$", txt)
                            if o_match:
                                try:
                                    odds_val_num = float(o_match.group(1))
                                    odds_symbol = convert_odds_to_symbol(
                                        odds_val_num
                                    )
                                except ValueError:
                                    pass

                        if pop_rank == "-":
                            p_match = re.search(r"^(\d+)$", txt)
                            if p_match:
                                p_val = int(p_match.group(1))
                                if 1 <= p_val <= 12:
                                    # 人気は「○人気」ではなく数字のみ（例: "1"）で格納（表示も枠幅35pxに最適化）
                                    pop_rank = str(p_val)

                    odds_weight_dict[horse_num] = {
                        "騎手": jockey,
                        "調教師": trainer,
                        "オッズ数値": odds_val_num,
                        "オッズ記号": odds_symbol,
                        "人気": pop_rank,
                        "増減": weight_diff,
                        "取消": is_canceled,
                    }

    except Exception as e:
        st.error(f"{race_no}R の直前データ取得時にエラーが発生しました: {e}")

    return odds_weight_dict


# =========================================================
# 画面2：当日予想モード メイン処理
# =========================================================
def show_screen2():
    st.markdown(
        """
        <style>
            .block-container { padding-top: 3rem !important; }
            div[data-testid="stDataEditor"] {
                margin-top: 22px !important;
            }
            div[data-testid="stDataEditor"] td, div[data-testid="stDataEditor"] th {
                height: 38px !important;
                padding: 4px 4px !important;
                font-size: 15px !important;
            }
            .custom-table { width: 100%; border-collapse: collapse; font-size: 16px; }
            .custom-table th { background-color: #f0f2f6; border: 1px solid #d0d7de; height: 38px; padding: 2px; text-align: center; font-weight: bold; line-height: 1.1; font-size: 13px; }
            .custom-table td { border: 1px solid #e1e4e8; height: 34px; padding: 1px; font-size: 15px; }
            .text-left { text-align: left; }
            .text-center { text-align: center; }
            .highlight-row { background-color: #fff9c4; font-weight: bold; }
            .cancel-row { background-color: #eeeeee; color: #9e9e9e; }
            .red-header { background-color: #ef9a9a !important; color: #000000; }
            .red-col { background-color: #ffcdd2 !important; color: #000000; font-weight: bold; text-align: center; font-size: 16px; }
            .pink-header { background-color: #f48fb1 !important; color: #000000; }
            .pink-col { background-color: #f8bbd0 !important; font-weight: bold; text-align: center; font-size: 16px; }
        </style>
    """,
        unsafe_allow_html=True,
    )

    st.header("☀️ 当日予想モード")

    # --- 1. master_data.json の読み込み ---
    master = {}
    try:
        with open("master_data.json", "r", encoding="utf-8") as f:
            master = json.load(f)
    except Exception as e:
        st.error(f"master_data.json の読み込みエラー: {e}")
        return

    # --- 2. サイドバーの日付入力 ＆ パス取得 ---
    st.sidebar.subheader("📂 予想データのロード")
    today_str = datetime.now().strftime("%Y%m%d")

    raw_date = st.sidebar.text_input(
        "開催日付 (YYYYMMDD)", value=today_str, max_chars=8
    )

    date_str = re.sub(r"\D", "", raw_date)
    pre_filename = get_pre_path(date_str)
    today_filename = get_today_path(date_str)

    # --- 3. 事前予想データの存在チェック ＆ 読み込み ---
    if not os.path.exists(pre_filename):
        st.warning(
            f"予想データ 『{pre_filename}』 が見つかりません。先に「事前予想モード」でデータを保存してください。"
        )
        return

    try:
        with open(pre_filename, "r", encoding="utf-8") as f:
            pre_data_loaded = json.load(f)
    except Exception as e:
        st.error(f"データの読み込みエラー: {e}")
        return

    # --- 4. 当日保存データ (today_data) の復元 ＆ サイドバーメッセージ判定 ---
    today_data_loaded = {}
    if os.path.exists(today_filename):
        try:
            with open(today_filename, "r", encoding="utf-8") as tf:
                today_data_loaded = json.load(tf)
            # today_data が読めた場合は、青メッセージのみ表示
            st.sidebar.info(
                f"✅ 保存済みの当日データ 『{os.path.basename(today_filename)}』 を復元しました！"
            )
        except Exception:
            today_data_loaded = {}
            st.sidebar.success(
                f"『{os.path.basename(pre_filename)}』 を読み込みました"
            )
    else:
        # today_data がまだ無い時だけ緑メッセージを表示
        st.sidebar.success(
            f"『{os.path.basename(pre_filename)}』 を読み込みました"
        )

    st.sidebar.markdown("---")
    st.sidebar.subheader("🔗 画面の分離表示")
    st.sidebar.link_button(
        "📈 更新・分析モードを別タブで開く",
        "http://localhost:8501",
        use_container_width=True,
    )
    st.sidebar.caption(
        "※別タブで開くことで、当日予想モードの入力状態を保持したまま分析・結果登録ができます。"
    )

    if "screen2_moisture_val" not in st.session_state:
        st.session_state.screen2_moisture_val = 1.0

    updated_moisture = st.sidebar.number_input(
        "現在の馬場水分量 (%)",
        min_value=0.0,
        max_value=10.0,
        value=st.session_state.screen2_moisture_val,
        step=0.1,
        format="%.1f",
        key="screen2_moisture_input",
    )
    st.session_state.screen2_moisture_val = updated_moisture
    moisture_key = get_moisture_key(updated_moisture)

    # ご指定通り脚質・オッズ補正のデフォルト値を 70% に設定
    if "screen2_odds_adj_val" not in st.session_state:
        st.session_state.screen2_odds_adj_val = 70

    odds_adj = st.sidebar.number_input(
        "オッズ補正 (%) [10%刻み]",
        min_value=0,
        max_value=200,
        value=st.session_state.screen2_odds_adj_val,
        step=10,
        key="screen2_odds_adj_input",
    )
    st.session_state.screen2_odds_adj_val = odds_adj

    if "screen2_weight_adj_val" not in st.session_state:
        st.session_state.screen2_weight_adj_val = 100

    weight_adj = st.sidebar.number_input(
        "馬体重補正 (%) [10%刻み]",
        min_value=0,
        max_value=200,
        value=st.session_state.screen2_weight_adj_val,
        step=10,
        key="screen2_weight_adj_input",
    )
    st.session_state.screen2_weight_adj_val = weight_adj

    if "today_live_data" not in st.session_state:
        st.session_state.today_live_data = {r: {} for r in range(1, 13)}

    SELECT_PADDOCK_OPTIONS = [0.2, 0.1, 0.0, -0.1, -0.2]
    SELECT_BUY_MARKS = ["-", "◎", "○", "▲", "△", "×"]

    tabs = st.tabs([f"{r}R" for r in range(1, 13)])

    for r_idx, tab in enumerate(tabs, start=1):
        with tab:
            r_key = f"{r_idx}R"

            race_pre_list = pre_data_loaded.get(r_key, [])
            if not race_pre_list:
                st.info("このレースの事前データが存在しません。")
                continue

            df_pre = pd.DataFrame(race_pre_list)

            # 💡 保存済み today_data からのオッズ・人気・パドック値の完全復元マップを作成
            saved_r_data = today_data_loaded.get(r_key, [])
            saved_map = {
                int(item["馬番"]): item for item in saved_r_data
            } if saved_r_data else {}

            # 直前データの統合（保存済みデータがある場合はそちらを最優先復元！）
            live_dict = st.session_state.today_live_data.get(r_idx, {})

            def merge_live_info(row):
                h_num = int(row["馬番"])
                saved_item = saved_map.get(h_num, {})

                # 1. 画面上で最新取得ボタンを押したデータがあれば最優先
                if h_num in live_dict:
                    info = live_dict[h_num]
                    j_name = info["騎手"] if info["騎手"] else row.get("騎手", "")
                    t_name = info["調教師"] if info["調教師"] else row.get("調教師", "")
                    return pd.Series(
                        [
                            info["オッズ数値"],
                            info["オッズ記号"],
                            info["人気"],
                            info["増減"],
                            j_name,
                            t_name,
                            info["取消"],
                        ]
                    )
                # 2. メモリに無くても、ファイル (today_data) に保存されていれば完全に復元！
                elif saved_item:
                    o_sym = saved_item.get("オッズ記号", "")
                    pop_r = str(saved_item.get("人気", "-"))
                    w_diff = str(saved_item.get("増減", "0"))
                    j_name = saved_item.get("騎手", row.get("騎手", ""))
                    t_name = saved_item.get("調教師", row.get("調教師", ""))
                    return pd.Series(
                        [
                            999.0, # ダミー数値
                            o_sym,
                            pop_r,
                            w_diff,
                            j_name,
                            t_name,
                            False,
                        ]
                    )
                # 3. 未保存・未取得の場合の初期値
                return pd.Series(
                    [
                        999.0,
                        "",
                        "-",
                        "0",
                        row.get("騎手", ""),
                        row.get("調教師", ""),
                        False,
                    ]
                )

            df_pre[
                ["オッズ数値", "オッズ記号", "人気", "増減", "騎手", "調教師", "取消"]
            ] = df_pre.apply(merge_live_info, axis=1)

            # AI判定
            jiku_horses, keshi_horses = [], []
            for _, h_row in df_pre.iterrows():
                h_num = h_row.get("馬番")
                h_name = h_row.get("馬名")
                p_rank = h_row.get("事前順位")
                j_rate = float(h_row.get("騎手複勝率", 0.0))
                kyakushitsu = str(h_row.get("脚質", ""))
                kinso = float(h_row.get("近走評価", 3.0))
                o_sym = str(h_row.get("オッズ記号", ""))

                if (p_rank == 1 and j_rate >= 0.35) or (
                    kyakushitsu == "逃げ"
                    and r_idx >= 7
                    and updated_moisture >= 2.0
                ):
                    jiku_horses.append(f"{h_num}番 {h_name}")

                if kinso <= 2.0 and o_sym == "×":
                    keshi_horses.append(f"{h_num}番 {h_name}")

            jiku_text = ", ".join(jiku_horses) if jiku_horses else "なし"
            keshi_text = ", ".join(keshi_horses) if keshi_horses else "なし"

            st.markdown(
                f"""
                <div style="background-color: #f1f8e9; border: 1px solid #c8e6c9; padding: 6px 12px; border-radius: 5px; margin-bottom: 10px; font-size: 14px;">
                    🤖 <b>AI分析判定</b>&nbsp;&nbsp;|&nbsp;&nbsp;
                    🎯 <b>鉄板軸馬:</b> <span style="color: #2e7d32; font-weight: bold;">{jiku_text}</span> &nbsp;&nbsp;|&nbsp;&nbsp;
                    ❌ <b>危険な消し馬:</b> <span style="color: #c62828; font-weight: bold;">{keshi_text}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            r_rates, tan_bg, ren2_bg, ren3_bg = get_race_winrate_info(r_idx)
            html_rate_box = f"""
            <div style="background-color: #f8f9fa; border: 1px solid #e0e0e0; padding: 8px 12px; border-radius: 5px; margin-bottom: 12px; font-size: 14px;">
                🎯 <b>【{r_idx}R 当日予想的中率データ】</b>&nbsp;&nbsp;&nbsp;&nbsp;
                単勝的中率(△): <span style="{tan_bg} padding:2px 8px; border-radius:3px;">{r_rates['単勝']}%</span> &nbsp;|&nbsp;
                2連勝率(○): <span style="{ren2_bg} padding:2px 8px; border-radius:3px;">{r_rates['2連']}%</span> &nbsp;|&nbsp;
                3連勝率(◎): <span style="{ren3_bg} padding:2px 8px; border-radius:3px;">{r_rates['3連']}%</span>
                <span style="font-size:11px; color:#666; margin-left:10px;">（※黄色枠：基準勝率オーバー）</span>
            </div>
            """
            st.markdown(html_rate_box, unsafe_allow_html=True)

            with st.expander(
                f"🏇 本日（{date_str}）の騎手リアルタイム成績 (○－○－○－○) を確認する"
            ):
                if st.button(
                    f"🔄 {date_str} の騎手成績を集計",
                    key=f"btn_jockey_stat_{r_idx}",
                ):
                    with st.spinner("確定レース結果から騎手成績を集計中..."):
                        df_j_stats = get_today_jockey_stats(date_str)
                        if not df_j_stats.empty:
                            st.session_state[f"df_jockeys_{date_str}"] = (
                                df_j_stats
                            )
                            st.success(
                                f"『{date_str}』 の騎手成績を集計しました！"
                            )
                        else:
                            st.warning(
                                f"※『result_data_{date_str}.json』 が見つかりません。"
                            )

                if f"df_jockeys_{date_str}" in st.session_state:
                    st.dataframe(
                        st.session_state[f"df_jockeys_{date_str}"],
                        hide_index=True,
                        use_container_width=True,
                    )

            col_btn, col_info = st.columns([1.8, 2.2])
            with col_btn:
                if st.button(
                    f"🔄 {r_idx}R の最新オッズ・馬体重を取得",
                    key=f"btn_fetch_{r_idx}",
                    type="primary",
                ):
                    with st.spinner("直前データを自動取得中..."):
                        fetched_live = fetch_realtime_odds_weight(
                            date_str, r_idx
                        )
                        st.session_state.today_live_data[r_idx] = fetched_live
                        st.success(f"{r_idx}R の最新データを更新しました！")
                        st.rerun()

            col_input, col_table = st.columns([0.9, 4.1])

            with col_input:
                st.markdown("**購入検討 / パドック**")

                # 💡 保存済み today_data があれば、検討マークとパドック値を自動復元！
                saved_r_data = today_data_loaded.get(r_key, [])
                saved_map = {
                    int(item["馬番"]): item for item in saved_r_data
                } if saved_r_data else {}

                init_buys = [
                    saved_map.get(h, {}).get("検討", "-") for h in range(1, 11)
                ]
                init_paddocks = [
                    float(saved_map.get(h, {}).get("パドック値", 0.0))
                    for h in range(1, 11)
                ]

                paddock_df = pd.DataFrame(
                    {
                        "検討": init_buys,
                        "馬番": range(1, 11),
                        "パドック": init_paddocks,
                    }
                )
                edited_paddock = st.data_editor(
                    paddock_df,
                    column_config={
                        "検討": st.column_config.SelectboxColumn(
                            "検討",
                            options=SELECT_BUY_MARKS,
                            width="extra-small",
                            required=True,
                        ),
                        "馬番": st.column_config.NumberColumn(
                            "馬番", width="extra-small"
                        ),
                        "パドック": st.column_config.SelectboxColumn(
                            "パドック",
                            options=SELECT_PADDOCK_OPTIONS,
                            width="small",
                            required=True,
                        ),
                    },
                    disabled=["馬番"],
                    hide_index=True,
                    height=390,
                    key=f"editor_paddock_{r_idx}",
                    use_container_width=True,
                )

            df_final = pd.merge(df_pre, edited_paddock, on="馬番")

            def calc_final_score(row):
                if not str(row["馬名"]).strip() or row.get("取消", False):
                    return pd.Series(
                        [None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, True]
                    )

                half_key = "zenhan" if r_idx <= 6 else "kouhan"

                pre_score = (
                    float(row["事前総合評価"])
                    if row["事前総合評価"] is not None
                    else 0.0
                )

                pre_jockey_rate = float(row.get("騎手複勝率", 0.25))
                today_jockey_name = row["騎手"]

                j_master_val = master.get("jockey", {}).get(
                    today_jockey_name, 0.25
                )
                if isinstance(j_master_val, dict):
                    today_jockey_rate = float(j_master_val.get("val", 0.25))
                else:
                    today_jockey_rate = float(j_master_val)

                adjusted_pre_score = (
                    pre_score - pre_jockey_rate + today_jockey_rate
                )

                odds_sym = str(row["オッズ記号"]).strip()
                odds_target = master[half_key]["odds"].get(odds_sym, 0.15)
                if isinstance(odds_target, dict):
                    raw_p_odds = float(odds_target.get(moisture_key, 0.15))
                else:
                    raw_p_odds = float(odds_target)
                p_odds = raw_p_odds * (odds_adj / 100.0)

                w_key = get_weight_key(row["増減"])
                weight_target = master[half_key]["weight"].get(w_key, 0.25)
                if isinstance(weight_target, dict):
                    raw_p_weight = float(weight_target.get(moisture_key, 0.25))
                else:
                    raw_p_weight = float(weight_target)
                p_weight = raw_p_weight * (weight_adj / 100.0)

                paddock_val = float(row["パドック"])

                final_total = (
                    adjusted_pre_score + p_odds + p_weight + paddock_val
                )

                p_kyakushitsu = float(row.get("脚質複勝率", 0.0))
                p_trainer = float(row.get("調教師複勝率", 0.0))
                p_ability = float(row.get("能力総合", 0.0))

                return pd.Series(
                    [
                        final_total,
                        p_kyakushitsu,
                        today_jockey_rate,
                        p_trainer,
                        p_ability,
                        p_odds,
                        p_weight,
                        paddock_val,
                        False,
                    ]
                )

            df_final[
                [
                    "最終総合評価",
                    "脚質複勝率",
                    "騎手複勝率",
                    "調教師複勝率",
                    "能力総合",
                    "オッズ指数",
                    "馬体重指数",
                    "パドック値",
                    "空欄馬",
                ]
            ] = df_final.apply(calc_final_score, axis=1)

            df_valid = df_final[~df_final["空欄馬"]].copy()
            if not df_valid.empty:
                df_final.loc[~df_final["空欄馬"], "最終順位"] = (
                    df_valid["最終総合評価"]
                    .rank(ascending=False, method="min")
                    .astype(int)
                )
            else:
                df_final["最終順位"] = None

            with col_table:
                st.markdown(
                    f"**事前総合評価 ＆ 当日更新結果** (水分量: `{moisture_key}`)"
                )

                # ご指定のカラム幅指定：最終総合/事前総合=45px, ｵｯｽﾞﾏｰｸ/人気/ﾊﾟﾄﾞｯｸ/脚質=35px, 半角カタカナ表記
                html_code = """
                <table class="custom-table">
                    <thead>
                        <tr>
                            <th style="width:25px;">検討</th>
                            <th style="width:25px;">馬番</th>
                            <th style="width:110px;">馬名</th>
                            <th class="red-header" style="width:30px;">最終<br>順位</th>
                            <th class="red-header" style="width:45px;">最終<br>総合</th>
                            <th class="pink-header" style="width:30px;">事前<br>順位</th>
                            <th class="pink-header" style="width:45px;">事前<br>総合</th>
                            <th style="width:35px;">ｵｯｽﾞ<br>指数</th>
                            <th style="width:35px;">馬体重<br>指数</th>
                            <th style="width:35px;">ｵｯｽﾞ<br>ﾏｰｸ</th>
                            <th style="width:35px;">人気</th>
                            <th style="width:35px;">馬体重<br>増減</th>
                            <th style="width:35px;">ﾊﾟﾄﾞｯｸ</th>
                            <th style="width:35px;">脚質</th>
                            <th style="width:75px;">騎手</th>
                            <th style="width:75px;">調教師</th>
                        </tr>
                    </thead><tbody>
                """

                df_sorted = df_final.sort_values("馬番")
                for _, row in df_sorted.iterrows():
                    if row["空欄馬"]:
                        status_str = "取消" if row.get("取消", False) else ""
                        html_code += "<tr class='cancel-row'>"
                        html_code += f"<td class='text-center'>{row.get('検討','-')}</td>"
                        html_code += f"<td class='text-center'>{row['馬番']}</td>"
                        html_code += f"<td class='text-left'>{row['馬名']} {status_str}</td>"
                        html_code += "<td class='text-center'>-</td><td class='text-center'>-</td><td class='text-center'>-</td><td class='text-center'>-</td>"
                        html_code += "<td class='text-center'>-</td><td class='text-center'>-</td><td class='text-center'>-</td><td class='text-center'>-</td><td class='text-center'>-</td><td class='text-center'>-</td>"
                        html_code += "<td></td><td></td><td></td>"
                        html_code += "</tr>"
                    else:
                        row_class = (
                            "highlight-row"
                            if (
                                row["最終順位"] is not None
                                and row["最終順位"] <= 4
                            )
                            else ""
                        )
                        p_rank_str = (
                            int(row["事前順位"])
                            if row["事前順位"] is not None
                            else "-"
                        )
                        pre_score_str = (
                            f"{float(row['事前総合評価']):.3f}"
                            if row["事前総合評価"] is not None
                            else "-"
                        )

                        html_code += f"<tr class='{row_class}'>"
                        html_code += f"<td class='text-center' style='font-weight:bold; color:#d81b60;'>{row['検討']}</td>"
                        html_code += f"<td class='text-center'>{row['馬番']}</td>"
                        html_code += f"<td class='text-left' style='font-size:12px; white-space:nowrap;'>{row['馬名']}</td>"

                        html_code += f"<td class='red-col'>{int(row['最終順位'])}</td>"
                        html_code += f"<td class='red-col'>{row['最終総合評価']:.3f}</td>"
                        html_code += f"<td class='text-center'>{p_rank_str}</td>"
                        html_code += f"<td class='pink-col'>{pre_score_str}</td>"
                        html_code += f"<td class='text-center'>{row['オッズ指数']:.3f}</td>"
                        html_code += f"<td class='text-center'>{row['馬体重指数']:.3f}</td>"

                        html_code += f"<td class='text-center' style='font-size:20px; font-weight:bold; color:#d81b60;'>{row['オッズ記号']}</td>"
                        html_code += f"<td class='text-center' style='font-size:14px;'>{row['人気']}</td>"
                        html_code += f"<td class='text-center'>{row['増減']}</td>"
                        html_code += f"<td class='text-center'>{row['パドック値']:.1f}</td>"

                        html_code += f"<td class='text-center' style='white-space:nowrap;'>{row['脚質']}</td>"
                        html_code += f"<td class='text-left' style='white-space:nowrap;'>{row['騎手']}</td>"
                        html_code += f"<td class='text-left' style='white-space:nowrap;'>{row['調教師']}</td>"
                        html_code += "</tr>"

                html_code += "</tbody></table>"
                st.markdown(html_code, unsafe_allow_html=True)

            # 保存ボタン処理
            st.markdown("---")
            save_status_key = f"saved_status_{date_str}_{r_idx}R"

            col_save1, col_save2 = st.columns([2.5, 1.5])
            with col_save1:
                if st.button(
                    f"💾 {r_idx}R のパドック評価・直前予想結果を保存",
                    key=f"btn_save_today_{r_idx}",
                    type="primary",
                ):
                    today_save_filename = get_today_path(date_str)
                    today_store = {}
                    if os.path.exists(today_save_filename):
                        try:
                            with open(
                                today_save_filename, "r", encoding="utf-8"
                            ) as f:
                                today_store = json.load(f)
                        except Exception:
                            today_store = {}

                    save_cols = [
                        "馬番",
                        "馬名",
                        "検討",
                        "パドック値",
                        "最終順位",
                        "最終総合評価",
                        "事前順位",
                        "事前総合評価",
                        "オッズ記号",
                        "人気",
                        "増減",
                        "脚質",
                        "騎手",
                        "調教師",
                    ]
                    existing_save_cols = [
                        c for c in save_cols if c in df_final.columns
                    ]

                    today_store[r_key] = df_final[
                        existing_save_cols
                    ].to_dict(orient="records")

                    with open(
                        today_save_filename, "w", encoding="utf-8"
                    ) as f:
                        json.dump(today_store, f, ensure_ascii=False, indent=2)

                    now_time = datetime.now().strftime("%H:%M:%S")
                    st.session_state[save_status_key] = now_time
                    st.success(
                        f"『{os.path.basename(today_save_filename)}』 へ {r_idx}R を保存しました！"
                    )
                    st.rerun()

            with col_save2:
                if save_status_key in st.session_state:
                    st.markdown(
                        f"<div style='background-color:#e8f5e9; border:1px solid #81c784; padding:6px 10px; border-radius:5px; color:#2e7d32; font-weight:bold; font-size:14px; text-align:center;'>✅ 保存済み ({st.session_state[save_status_key]})</div>",
                        unsafe_allow_html=True,
                    )
                elif os.path.exists(today_filename):
                    st.markdown(
                        "<div style='background-color:#e8f5e9; border:1px solid #81c784; padding:6px 10px; border-radius:5px; color:#2e7d32; font-weight:bold; font-size:14px; text-align:center;'>✅ 保存済み (復元データ)</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        "<div style='color:#9e9e9e; font-size:13px; padding:8px;'>⚪ 未保存</div>",
                        unsafe_allow_html=True,
                    )

            st.markdown("---")
            show_pre_details = st.checkbox(
                "👁️ 前日予想の計算内訳データ（脚質複勝率・騎手複勝率・能力5指標など）を表示",
                key=f"check_pre_details_{r_idx}",
            )

            if show_pre_details:
                st.subheader(f"📋 {r_idx}R 事前予想データ内訳")
                display_cols = [
                    "馬番",
                    "馬名",
                    "事前総合評価",
                    "事前順位",
                    "脚質",
                    "騎手",
                    "調教師",
                    "近走評価",
                    "前走クラス差",
                    "脚質複勝率",
                    "騎手複勝率",
                    "調教師複勝率",
                    "能力総合",
                ]
                existing_cols = [c for c in display_cols if c in df_pre.columns]
                st.dataframe(
                    df_pre[existing_cols],
                    hide_index=True,
                    use_container_width=True,
                )