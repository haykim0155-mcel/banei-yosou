import json
import os
import re
import time
from bs4 import BeautifulSoup
import pandas as pd
import pdfplumber
import requests
import streamlit as st
import unicodedata
from datetime import datetime, timedelta

# =========================================================
# 保存用ファイルパスを取得する関数
# =========================================================
def get_pre_path(date_str):
    DIR_PRE = "data/pre"
    os.makedirs(DIR_PRE, exist_ok=True)
    clean_d = re.sub(r"\D", "", date_str)
    return os.path.join(DIR_PRE, f"pre_data_{clean_d}.json")

# =========================================================
# 水分量からマスタ参照キーを取得する関数
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
# 💡 騎手・調教師の表記ゆれ（5文字名・ケ/ヶ・空白等）を完全抽出するマスタ参照関数
# =========================================================
def get_master_rate(name, master_dict, default_val=0.25):
    if not name or pd.isna(name):
        return default_val
    
    # 1. カッコ除去、空白除去、ケ/ヶ統一
    clean_name = str(name).strip().replace(" ", "").replace(" ", "").replace("ヶ", "ケ")
    clean_name = re.sub(r"[（\(].*?[）\)]", "", clean_name)
    
    # 2. Unicode正規化（分離型「芳」などの異体字や特殊文字を標準文字に統一）
    clean_name = unicodedata.normalize('NFKC', clean_name)
    clean_name = re.sub(r"[^\w]", "", clean_name)
    
    if not clean_name:
        return default_val

    # 3. 完全一致チェック
    if clean_name in master_dict:
        val = master_dict[clean_name]
        return float(val.get("複勝率", val.get("val", default_val))) if isinstance(val, dict) else float(val)
    
    # 4. 前方・部分一致チェック（「森芳」や「大河原」など2〜3文字での柔軟マッチング）
    for k, val in master_dict.items():
        clean_k = str(k).strip().replace(" ", "").replace(" ", "").replace("ヶ", "ケ")
        clean_k = re.sub(r"[（\(].*?[）\)]", "", clean_k)
        clean_k = unicodedata.normalize('NFKC', clean_k)
        clean_k = re.sub(r"[^\w]", "", clean_k)
        
        if clean_k == clean_name or clean_k.startswith(clean_name[:2]) or clean_name.startswith(clean_k[:2]):
            return float(val.get("複勝率", val.get("val", default_val))) if isinstance(val, dict) else float(val)
            
    return default_val

# =========================================================
# 自動データ取得・統合処理関数
# =========================================================
def fetch_all_pre_data(date_str, pdf_prefix, start_yoso_id):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
    }
    all_races_dict = {r: {} for r in range(1, 13)}

    for r in range(1, 13):
        for h in range(1, 11):
            all_races_dict[r][h] = {
                "馬番": h,
                "馬名": "",
                "脚質": "先行",
                "騎手": "",
                "調教師": "",
                "AI指数": 0.0,
                "近走評価": 0.0,
                "前走クラス差": 0.0,
                "先行力": 3,
                "障害力": 3,
                "末脚力": 3,
                "軽馬場": 3,
                "重馬場": 3,
            }

    # 1. netkeiba: 馬名・騎手・調教師
    NAME_FIXES = {
        "大河原和": "大河原和雄", "大河原": "大河原和雄",
        "竹ケ原茉": "竹ケ原茉耶", "竹ヶ原茉": "竹ケ原茉耶", "竹ヶ原": "竹ケ原茉耶"
    }
    for race_no in range(1, 13):
        race_id = f"{date_str[:4]}65{date_str[4:]}{race_no:02d}"
        url = f"https://nar.netkeiba.com/race/shutuba.html?race_id={race_id}"
        try:
            res = requests.get(url, headers=headers, timeout=10)
            res.encoding = res.apparent_encoding
            soup = BeautifulSoup(res.text, "html.parser")
            for row in soup.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) >= 8 and cols[1].get_text(strip=True).isdigit():
                    num = int(cols[1].get_text(strip=True))
                    if 1 <= num <= 10:
                        horse_name_raw = cols[3].get_text(strip=True)
                        horse_name = re.sub(r"[^\w\u3040-\u30ff\u4e00-\u9fcf]", "", horse_name_raw)

                        j_raw = cols[6].get_text(strip=True)
                        t_raw = cols[7].get_text(strip=True)
                        jockey = (
                            j_raw.replace("◇", "").replace("▲", "").replace("★", "").replace("☆", "").strip()
                        )
                        trainer = (
                            t_raw.replace("ばんえい", "").replace("（ばんえい）", "").replace("(ばんえい)", "")
                            .replace("帯広", "").replace("（他）", "").split("（")[0].strip()
                        )
                        jockey = NAME_FIXES.get(jockey, jockey)
                        trainer = NAME_FIXES.get(trainer, trainer)

                        all_races_dict[race_no][num]["馬名"] = horse_name
                        all_races_dict[race_no][num]["騎手"] = jockey
                        all_races_dict[race_no][num]["調教師"] = trainer
        except Exception:
            pass
        time.sleep(0.12)

    # 2. がんばれ地方競馬: 脚質
    headers_gb = {
        "User-Agent": headers["User-Agent"],
        "Referer": "http://ganbare-chihoukeiba.info/",
    }
    for race_no in range(1, 13):
        race_str = f"{race_no:02d}"
        url = f"http://ganbare-chihoukeiba.info/obihiro/index_detail.php?p_date={date_str}&p_race={race_str}"
        try:
            res = requests.get(url, headers=headers_gb, timeout=10)
            res.encoding = "cp932"
            matches = re.findall(r"【?(逃げ|先行|差し|追込)】?[:：\s]*([0-9,、\s]+)", res.text)
            for style_name, numbers_str in matches:
                for num_str in re.findall(r"\d+", numbers_str):
                    num = int(num_str)
                    if 1 <= num <= 10:
                        all_races_dict[race_no][num]["脚質"] = style_name
        except Exception:
            pass
        time.sleep(0.12)

    # 3. ねっとばんばPDF: 能力評価
    SCORE_MAP = {
        "A": 5, "B": 4, "C": 3, "D": 2, "E": 1,
        "ａ": 5, "ｂ": 4, "ｃ": 3, "ｄ": 2, "ｅ": 1,
        "a": 5, "b": 4, "c": 3, "d": 2, "e": 1,
        "Ａ": 5, "Ｂ": 4, "Ｃ": 3, "Ｄ": 2, "Ｅ": 1,
    }
    for race_no in range(1, 13):
        race_str = f"{race_no:02d}"
        clean_prefix = str(pdf_prefix).lower().strip()
        pdf_url = f"https://net-banba.com/rakuten/{clean_prefix}{date_str}{race_str}.pdf"
        temp_pdf = f"temp_{race_str}.pdf"
        try:
            res = requests.get(pdf_url, headers=headers, timeout=10)
            if res.status_code == 200:
                with open(temp_pdf, "wb") as f:
                    f.write(res.content)
                with pdfplumber.open(temp_pdf) as pdf:
                    for table in pdf.pages[0].extract_tables():
                        for row in table:
                            cells = [str(c).strip() if c else "" for c in row]
                            if len(cells) < 3:
                                continue
                            h_num = None
                            if cells[1].isdigit() and 1 <= int(cells[1]) <= 10:
                                h_num = int(cells[1])
                            else:
                                for c in cells[:3]:
                                    if c.isdigit() and 1 <= int(c) <= 10:
                                        h_num = int(c)
                                        break
                            ranks = [SCORE_MAP[c] for c in cells if c in SCORE_MAP]
                            if h_num and ranks:
                                while len(ranks) < 5:
                                    ranks.append(3)
                                all_races_dict[race_no][h_num]["先行力"] = ranks[0]
                                all_races_dict[race_no][h_num]["障害力"] = ranks[1]
                                all_races_dict[race_no][h_num]["末脚力"] = ranks[2]
                                all_races_dict[race_no][h_num]["軽馬場"] = ranks[3]
                                all_races_dict[race_no][h_num]["重馬場"] = ranks[4]
                if os.path.exists(temp_pdf):
                    os.remove(temp_pdf)
        except Exception:
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)
        time.sleep(0.12)

    # 4. netkeiba: AI指数
    try:
        if start_yoso_id:
            start_id = int(start_yoso_id)
            for race_no in range(1, 13):
                curr_id = start_id + (race_no - 1)
                url = f"https://dir.netkeiba.com/baneikeiba/yoso_detail.html?yoso_id={curr_id}"
                res = requests.get(url, headers=headers, timeout=10)
                html_text = res.content.decode("euc-jp", errors="ignore")

                soup_ai = BeautifulSoup(html_text, "html.parser")
                clean_text = soup_ai.get_text()
                all_floats = re.findall(r"\d{1,3}\.\d", clean_text)

                target_scores = []
                for val_str in all_floats:
                    try:
                        v = float(val_str)
                        if 10.0 <= v <= 999.0:
                            target_scores.append(v)
                    except ValueError:
                        pass

                if len(target_scores) > 10:
                    target_scores = target_scores[-10:]

                for idx, score_val in enumerate(target_scores, start=1):
                    if idx <= 10:
                        all_races_dict[race_no][idx]["AI指数"] = score_val

                time.sleep(0.12)
    except Exception:
        pass

    result_data = {}
    for r in range(1, 13):
        result_data[r] = [all_races_dict[r][h] for h in range(1, 11)]

    return result_data


# =========================================================
# 画面1：メイン表示処理
# =========================================================
def show_screen1():
    st.markdown(
        """
        <style>
            .block-container { padding-top: 3rem !important; }
        </style>
    """,
        unsafe_allow_html=True,
    )

    st.header("事前予想モード")

    try:
        with open("master_data.json", "r", encoding="utf-8") as f:
            master_data = json.load(f)
        with open("master_analysis.json", "r", encoding="utf-8") as f:
            master_analysis = json.load(f)

        # master 変数に master_analysis.json と master_data.json の情報を完全統合
        master = master_analysis.copy() if isinstance(master_analysis, dict) else {}
        if isinstance(master_data, dict):
            master["jockey"] = master_data.get("jockey", {})
            master["trainer"] = master_data.get("trainer", {})
    except Exception as e:
        st.error(f"マスタファイルの読み込みエラー: {e}")
        return

    # --- サイドバー ---
    st.sidebar.subheader("🌐 外部データ自動取得")
    
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y%m%d")
    date_str_raw = st.sidebar.text_input(
        "開催日付 (YYYYMMDD)", 
        value=tomorrow_str,
        key="pre_date_input_main"
    )
    date_str = re.sub(r"\D", "", date_str_raw)
    date_clean = date_str
    pre_save_path = get_pre_path(date_clean)

    with st.sidebar.form("fetch_form"):
        pdf_prefix = st.text_input(
            "能力PDFプレフィックス (英小文字2文字)", value="", max_chars=2
        ).lower()
        ai_start_id_str = st.text_input(
            "AI指数 1R目YOSO_ID (7桁数値)", value="", max_chars=7
        )
        ai_start_id = (
            int(ai_start_id_str) if ai_start_id_str.isdigit() else None
        )
        fetch_btn = st.form_submit_button("データ自動取得")

    load_btn = False
    if os.path.exists(pre_save_path):
        st.sidebar.info(f"📄 『pre_data_{date_clean}.json』 が検出されました")
        load_btn = st.sidebar.button("📁 指定日付の保存データを読み込む", use_container_width=True, type="primary")
    else:
        st.sidebar.caption(f"※ pre_data_{date_clean}.json は存在しません")

    st.sidebar.markdown("---")
    st.sidebar.subheader("⚙️ リアルタイム計算設定")
    with st.sidebar.form("calc_form"):
        moisture_val = st.number_input(
            "当日の想定馬場水分量 (%)",
            min_value=0.0,
            max_value=10.0,
            value=1.0,
            step=0.1,
            format="%.1f",
        )
        kyakushitsu_adj = st.number_input(
            "脚質補正 (%) [デフォルト10%]",
            min_value=0,
            max_value=200,
            value=30,
            step=10,
        )
        update_btn = st.form_submit_button("データ更新 (再計算)")

    moisture_key = get_moisture_key(moisture_val)

    if "fetched_data" not in st.session_state or fetch_btn or load_btn:
        st.session_state.current_pre_date = date_clean
        if fetch_btn:
            with st.spinner("全12レースのデータをWebサイト・PDFから取得中..."):
                new_fetched = fetch_all_pre_data(
                    date_clean, pdf_prefix, ai_start_id
                )
                # 💡 自動取得時も既存の入力補正（近走評価・前走クラス差）を保持
                if "fetched_data" in st.session_state:
                    old_data = st.session_state.fetched_data
                    for r_i in range(1, 13):
                        if r_i in old_data and r_i in new_fetched:
                            old_r_map = {h["馬番"]: h for h in old_data[r_i]}
                            for h_item in new_fetched[r_i]:
                                h_num = h_item["馬番"]
                                if h_num in old_r_map:
                                    h_item["近走評価"] = old_r_map[h_num].get("近走評価", 0.0)
                                    h_item["前走クラス差"] = old_r_map[h_num].get("前走クラス差", 0.0)
                
                st.session_state.fetched_data = new_fetched
                st.success("自動取得が完了しました！（※入力済みの補正値は保持されています）")
        elif load_btn and os.path.exists(pre_save_path):
            try:
                with open(pre_save_path, "r", encoding="utf-8") as pf:
                    saved_json = json.load(pf)
                loaded_dict = {}
                for r in range(1, 13):
                    r_str_key = f"{r}R"
                    if r_str_key in saved_json:
                        loaded_dict[r] = saved_json[r_str_key]
                    elif str(r) in saved_json:
                        loaded_dict[r] = saved_json[str(r)]
                    elif r in saved_json:
                        loaded_dict[r] = saved_json[r]
                    else:
                        loaded_dict[r] = []
                st.session_state.fetched_data = loaded_dict
                st.success(f"『pre_data_{date_clean}.json』 を正常に読み込みました！")
            except Exception as e:
                st.error(f"保存データの読み込みエラー: {e}")
        elif "fetched_data" not in st.session_state:
            st.session_state.fetched_data = {
                r: [{"馬番": i, "馬名": "", "脚質": "先行", "騎手": "", "調教師": "", "AI指数": 0.0, "近走評価": 0.0, "前走クラス差": 0.0, "先行力": 3, "障害力": 3, "末脚力": 3, "軽馬場": 3, "重馬場": 3} for i in range(1, 11)]
                for r in range(1, 13)
            }

    tabs = st.tabs([f"{r}R" for r in range(1, 13)])
    all_race_pre_data = {}
    summary_picks = {}

    KINSOU_OPTIONS = [0.5, 0.4, 0.3, 0.2, 0.1, 0.0]
    CLASS_OPTIONS = [0.2, 0.1, 0.0, -0.1, -0.2]

    for r_idx, tab in enumerate(tabs, start=1):
        with tab:
            df_base = pd.DataFrame(st.session_state.fetched_data[r_idx])

            col_input, col_table = st.columns([0.9, 4.1])

            with col_input:
                st.markdown("**補正入力**")
                
                # 💡 保存済み・ロード済みのデータを確実に10頭分抽出
                kinsou_init = []
                class_init = []
                
                r_list = st.session_state.fetched_data.get(r_idx, [])
                r_map = {int(x["馬番"]): x for x in r_list if isinstance(x, dict) and "馬番" in x}
                
                for h in range(1, 11):
                    h_info = r_map.get(h, {})
                    k_val = h_info.get("近走評価", 0.0)
                    c_val = h_info.get("前走クラス差", 0.0)
                    try:
                        kinsou_init.append(float(k_val) if k_val is not None and not pd.isna(k_val) else 0.0)
                    except Exception:
                        kinsou_init.append(0.0)
                    try:
                        class_init.append(float(c_val) if c_val is not None and not pd.isna(c_val) else 0.0)
                    except Exception:
                        class_init.append(0.0)

                input_df = pd.DataFrame(
                    {
                        "馬番": range(1, 11),
                        "近走評価": kinsou_init,
                        "前走クラス差": class_init,
                    }
                )
                
                # 💡 1つ目の st.data_editor（ここだけに絞り込む）
                edited_inputs = st.data_editor(
                    input_df,
                    column_config={
                        "馬番": st.column_config.NumberColumn(
                            "馬番", width="extra-small"
                        ),
                        "近走評価": st.column_config.SelectboxColumn(
                            "近走評価",
                            options=KINSOU_OPTIONS,
                            width="small",
                            required=True,
                        ),
                        "前走クラス差": st.column_config.SelectboxColumn(
                            "前走クラス差",
                            options=CLASS_OPTIONS,
                            width="small",
                            required=True,
                        ),
                    },
                    disabled=["馬番"],
                    hide_index=True,
                    height=390,
                    key=f"editor_input_single_r_{r_idx}",
                    use_container_width=True,
                )

                # 💡 編集内容を即時反映（2R以降のデータ保持）
                for _, ed_row in edited_inputs.iterrows():
                    h_num = int(ed_row["馬番"])
                    if h_num in r_map:
                        r_map[h_num]["近走評価"] = float(ed_row["近走評価"])
                        r_map[h_num]["前走クラス差"] = float(ed_row["前走クラス差"])

            # 💡 入力値を確実に反映するため既存の補正列を削除してから結合
            df_base_clean = df_base.drop(columns=["近走評価", "前走クラス差"], errors="ignore")
            df_merged = pd.merge(df_base_clean, edited_inputs, on="馬番")

            def calc_pre_scores(row):
                if not str(row["馬名"]).strip():
                    return pd.Series([None, None, None, None, None, True])

                half_key = "前半(1~6R)" if r_idx <= 6 else "後半(7~12R)"
                s_name = str(row["脚質"]).strip()

                # ---------------------------------------------------------
                # 1. 脚質複勝率の取得（JSON構造: [half_key]["脚質"][s_name][moisture_key]["複勝率"]）
                # ---------------------------------------------------------
                raw_p_kyakushitsu = 0.25
                try:
                    style_node = (
                        master.get(half_key, {})
                        .get("脚質", {})
                        .get(s_name, {})
                        .get(moisture_key, {})
                    )
                    if isinstance(style_node, dict):
                        raw_p_kyakushitsu = float(
                            style_node.get("複勝率", style_node.get("率", 0.25))
                        )
                    elif isinstance(style_node, (int, float)):
                        raw_p_kyakushitsu = float(style_node)
                except Exception:
                    raw_p_kyakushitsu = 0.25

                # 脚質補正値の適用
                p_kyakushitsu = (
                    raw_p_kyakushitsu * (kyakushitsu_adj / 100.0)
                    if kyakushitsu_adj != 100
                    else raw_p_kyakushitsu
                )

                # ---------------------------------------------------------
                # 2. 騎手・調教師 複勝率取得
                # ---------------------------------------------------------
                p_jockey = get_master_rate(
                    row["騎手"], master.get("jockey", {}), 0.25
                )
                p_trainer = get_master_rate(
                    row["調教師"], master.get("trainer", {}), 0.25
                )

                # ---------------------------------------------------------
                # 3. 能力5指標 (JSON構造: ["能力5指標"][cat][str(val)]["複勝率"])
                # ---------------------------------------------------------
                ability_master = master.get("能力5指標", {})

                def get_ab_rate(cat_name, val):
                    try:
                        node = (
                            ability_master.get(cat_name, {})
                            .get(str(int(float(val))), {})
                        )
                        if isinstance(node, dict):
                            return float(node.get("複勝率", 0.20))
                        return float(node)
                    except Exception:
                        return 0.20

                p_senkou = get_ab_rate(
                    "先行力", row.get("先行力", row.get("先行", 3))
                )
                p_shougai = get_ab_rate(
                    "障害力", row.get("障害力", row.get("障害", 3))
                )
                p_sueashi = get_ab_rate(
                    "末脚力", row.get("末脚力", row.get("末脚", 3))
                )
                p_kei = get_ab_rate("軽馬場", row.get("軽馬場", 3))
                p_juu = get_ab_rate("重馬場", row.get("重馬場", 3))

                ability_product_200 = (
                    p_senkou * p_shougai * p_sueashi * p_kei * p_juu
                ) * 200.0
                ai_val = float(row["AI指数"]) / 100.0

                kinsou_val = float(row.get("近走評価", 0.0) or 0.0)
                class_val = float(row.get("前走クラス差", 0.0) or 0.0)

                pre_total = (
                    p_kyakushitsu
                    + p_jockey
                    + p_trainer
                    + ai_val
                    + ability_product_200
                    + kinsou_val
                    + class_val
                )
                return pd.Series(
                    [
                        p_kyakushitsu,
                        p_jockey,
                        p_trainer,
                        ability_product_200,
                        pre_total,
                        False,
                    ]
                )

            df_merged[
                [
                    "脚質複勝率",
                    "騎手複勝率",
                    "調教師複勝率",
                    "能力総合",
                    "事前総合評価",
                    "空欄馬",
                ]
            ] = df_merged.apply(calc_pre_scores, axis=1)

            df_valid = df_merged[~df_merged["空欄馬"]].copy()
            if not df_valid.empty:
                df_merged.loc[~df_merged["空欄馬"], "事前順位"] = (
                    df_valid["事前総合評価"]
                    .rank(ascending=False, method="min")
                    .astype(int)
                )
            else:
                df_merged["事前順位"] = None

            valid_top5 = df_merged[~df_merged["空欄馬"]].sort_values(
                "事前順位"
            )
            top_5_horses = valid_top5["馬番"].head(5).tolist()
            while len(top_5_horses) < 5:
                top_5_horses.append("-")
            summary_picks[f"{r_idx}R"] = top_5_horses

            with col_table:
                col_title, col_check = st.columns([2.5, 1.5])
                with col_title:
                    adj_str = (
                        f" (脚質補正: {kyakushitsu_adj}%)"
                        if kyakushitsu_adj != 100
                        else ""
                    )
                    st.markdown(
                        f"**事前総合評価** (水分量: `{moisture_key}`){adj_str}"
                    )
                with col_check:
                    show_ability = st.checkbox(
                        "能力5項目を右側に表示", key=f"check_ability_{r_idx}"
                    )

                html_code = """
                <style>
                    .custom-table { width: 100%; border-collapse: collapse; font-size: 15px; }
                    .custom-table th { 
                        background-color: #f0f2f6; 
                        border: 1px solid #d0d7de; 
                        height: 34px !important; 
                        padding: 1px 1px; 
                        text-align: center; 
                        font-weight: bold; 
                        line-height: 1.1; 
                        box-sizing: border-box;
                    }
                    .custom-table td { 
                        border: 1px solid #e1e4e8; 
                        height: 34px !important; 
                        padding: 1px 1px; 
                        box-sizing: border-box;
                    }
                    .text-left { text-align: left; }
                    .text-center { text-align: center; }
                    .highlight-row { background-color: #fff9c4; font-weight: bold; }
                    .pink-header { background-color: #f48fb1 !important; color: #000000; }
                    .pink-col { background-color: #f8bbd0 !important; color: #000000; font-weight: bold; text-align: center; }
                </style>
                <table class="custom-table">
                    <thead>
                        <tr>
                            <th style="width:30px;">馬番</th>
                            <th style="width:140px;">馬名</th>
                            <th class="pink-header" style="width:80px;">事前<br>総合評価</th>
                            <th class="pink-header" style="width:40px;">事前<br>順位</th>
                            <th>脚質</th>
                            <th>騎手</th>
                            <th>調教師</th>
                            <th>AI指数</th>
                            <th>近走<br>評価</th>
                            <th>前走<br>クラス差</th>
                            <th>脚質<br>複勝率</th>
                            <th>騎手<br>複勝率</th>
                            <th>調教師<br>複勝率</th>
                            <th>能力<br>総合</th>
                """
                if show_ability:
                    html_code += "<th>先行</th><th>障害</th><th>末脚</th><th>軽馬</th><th>重馬</th>"
                html_code += "</tr></thead><tbody>"

                df_sorted = df_merged.sort_values("馬番")
                for _, row in df_sorted.iterrows():
                    if row["空欄馬"]:
                        html_code += "<tr>"
                        html_code += (
                            f"<td class='text-center'>{row['馬番']}</td>"
                        )
                        html_code += "<td></td><td class='text-center'>-</td><td class='text-center'>-</td>"
                        html_code += "<td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>"
                        if show_ability:
                            html_code += (
                                "<td></td><td></td><td></td><td></td><td></td>"
                            )
                        html_code += "</tr>"
                    else:
                        row_class = (
                            "highlight-row"
                            if (
                                row["事前順位"] is not None
                                and row["事前順位"] <= 4
                            )
                            else ""
                        )
                        kinsou_disp = float(row.get("近走評価", 0.0) or 0.0)
                        class_disp = float(row.get("前走クラス差", 0.0) or 0.0)

                        html_code += f"<tr class='{row_class}'>"
                        html_code += (
                            f"<td class='text-center'>{row['馬番']}</td>"
                        )
                        html_code += f"<td class='text-left' style='font-size:13px; white-space:nowrap;'>{row['馬名']}</td>"
                        html_code += f"<td class='pink-col'>{row['事前総合評価']:.3f}</td>"
                        html_code += f"<td class='pink-col'>{int(row['事前順位'])}</td>"
                        html_code += f"<td class='text-left'>{row['脚質']}</td>"
                        html_code += (
                            f"<td class='text-left'>{row['騎手']}</td>"
                        )
                        html_code += f"<td class='text-left'>{row['調教師']}</td>"
                        html_code += f"<td class='text-center'>{float(row['AI指数']):.1f}</td>"
                        html_code += f"<td class='text-center'>{kinsou_disp:.1f}</td>"
                        html_code += f"<td class='text-center'>{class_disp:.1f}</td>"
                        html_code += f"<td class='text-center'>{row['脚質複勝率']:.3f}</td>"
                        html_code += f"<td class='text-center'>{row['騎手複勝率']:.3f}</td>"
                        html_code += f"<td class='text-center'>{row['調教師複勝率']:.3f}</td>"
                        html_code += f"<td class='text-center'>{row['能力総合']:.3f}</td>"

                        if show_ability:
                            html_code += f"<td class='text-center'>{row['先行力']}</td>"
                            html_code += f"<td class='text-center'>{row['障害力']}</td>"
                            html_code += f"<td class='text-center'>{row['末脚力']}</td>"
                            html_code += f"<td class='text-center'>{row['軽馬場']}</td>"
                            html_code += f"<td class='text-center'>{row['重馬場']}</td>"

                        html_code += "</tr>"

                html_code += "</tbody></table>"
                st.markdown(html_code, unsafe_allow_html=True)

            all_race_pre_data[f"{r_idx}R"] = df_merged.to_dict(orient="records")

    st.markdown("---")

    pdf_html_content = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: sans-serif; text-align: center; }}
            table {{ width: 100%; max-width: 500px; border-collapse: collapse; margin: 15px auto; font-size: 16px; }}
            th, td {{ border: 1px solid #000; padding: 8px 4px; text-align: center; height: 28px; }}
            .blank-row {{ height: 32px; background-color: #ffffff; }}
        </style>
    </head>
    <body>
        <h3>事前予想サマリー (1〜5位)</h3>
        <table>
            <tbody>
    """
    for r in range(1, 13):
        r_key = f"{r}R"
        picks = summary_picks.get(r_key, ["-", "-", "-", "-", "-"])
        pdf_html_content += f"""
            <tr>
                <td style="width:20%;"><b>{picks[0]}</b></td>
                <td style="width:20%;"><b>{picks[1]}</b></td>
                <td style="width:20%;"><b>{picks[2]}</b></td>
                <td style="width:20%;"><b>{picks[3]}</b></td>
                <td style="width:20%;"><b>{picks[4]}</b></td>
            </tr>
            <tr class="blank-row">
                <td></td><td></td><td></td><td></td><td></td>
            </tr>
        """
    pdf_html_content += "</tbody></table></body></html>"

    col_dl, col_save = st.columns([1, 1])

    with col_dl:
        st.download_button(
            label="📄 事前予想サマリー（結果記入枠付き）をダウンロード",
            data=pdf_html_content,
            file_name=f"事前予想サマリー_{date_str}.html",
            mime="text/html",
            use_container_width=True,
            type="primary",
        )

    with col_save:
        save_target_date = st.text_input(
            "保存するファイルの日付 (YYYYMMDD)",
            value=date_str,
            key="save_date_input",
        )
        
        DIR_PRE = "data/pre"
        os.makedirs(DIR_PRE, exist_ok=True)
        save_filename = os.path.join(DIR_PRE, f"pre_data_{save_target_date}.json")

        if os.path.exists(save_filename):
            st.caption(
                f"⚠️ 『{save_filename}』 は既に存在します（保存すると上書きされます）"
            )

        if st.button(
            f"💾 『{os.path.basename(save_filename)}』 にデータを保存",
            use_container_width=True,
        ):
            with open(save_filename, "w", encoding="utf-8") as f:
                json.dump(all_race_pre_data, f, ensure_ascii=False, indent=2)
            st.success(
                f"事前予想データを 『{save_filename}』 に保存しました！ 当日予想モードへ引き継げます。"
            )