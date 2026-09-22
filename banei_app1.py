import json
import os
import re
import time
from bs4 import BeautifulSoup
import pandas as pd
import pdfplumber
import requests
import streamlit as st
from datetime import datetime, timedelta


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
                "先行力": 3,
                "障害力": 3,
                "末脚": 3,
                "軽馬場": 3,
                "重馬場": 3,
            }

    # 1. netkeiba: 馬名・騎手・調教師
    NAME_FIXES = {"大河原和": "大河原和雄", "竹ケ原茉": "竹ケ原茉耶"}
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
                        horse_name = re.sub(
                            r"[^\w\u3040-\u30ff\u4e00-\u9fcf]",
                            "",
                            horse_name_raw,
                        )

                        j_raw = cols[6].get_text(strip=True)
                        t_raw = cols[7].get_text(strip=True)
                        jockey = (
                            j_raw.replace("◇", "")
                            .replace("▲", "")
                            .replace("★", "")
                            .replace("☆", "")
                            .strip()
                        )
                        trainer = (
                            t_raw.replace("ばんえい", "")
                            .replace("（ばんえい）", "")
                            .replace("(ばんえい)", "")
                            .replace("帯広", "")
                            .replace("（他）", "")
                            .split("（")[0]
                            .strip()
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
            matches = re.findall(
                r"【?(逃げ|先行|差し|追込)】?[:：\s]*([0-9,、\s]+)",
                res.text,
            )
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
        "A": 5,
        "B": 4,
        "C": 3,
        "D": 2,
        "E": 1,
        "ａ": 5,
        "ｂ": 4,
        "ｃ": 3,
        "ｄ": 2,
        "ｅ": 1,
        "a": 5,
        "b": 4,
        "c": 3,
        "d": 2,
        "e": 1,
        "Ａ": 5,
        "Ｂ": 4,
        "Ｃ": 3,
        "Ｄ": 2,
        "Ｅ": 1,
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
                            cells = [
                                str(c).strip() if c else "" for c in row
                            ]
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
                            ranks = [
                                SCORE_MAP[c] for c in cells if c in SCORE_MAP
                            ]
                            if h_num and ranks:
                                while len(ranks) < 5:
                                    ranks.append(3)
                                all_races_dict[race_no][h_num]["先行力"] = (
                                    ranks[0]
                                )
                                all_races_dict[race_no][h_num]["障害力"] = (
                                    ranks[1]
                                )
                                all_races_dict[race_no][h_num]["末脚"] = (
                                    ranks[2]
                                )
                                all_races_dict[race_no][h_num]["軽馬場"] = (
                                    ranks[3]
                                )
                                all_races_dict[race_no][h_num]["重馬場"] = (
                                    ranks[4]
                                )
                if os.path.exists(temp_pdf):
                    os.remove(temp_pdf)
        except Exception:
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)
        time.sleep(0.12)

    # 4. netkeiba: AI指数
    try:
        start_id = int(start_yoso_id)
        for race_no in range(1, 13):
            curr_id = start_id + (race_no - 1)
            url = f"https://dir.netkeiba.com/baneikeiba/yoso_detail.html?yoso_id={curr_id}"
            res = requests.get(url, headers=headers, timeout=10)
            html_text = res.content.decode("euc-jp", errors="ignore")
            all_floats = re.findall(r"\d{1,3}\.\d", html_text)
            target_scores = (
                all_floats[7:17] if len(all_floats) >= 16 else all_floats[:10]
            )
            for idx, score_str in enumerate(target_scores, start=1):
                if idx <= 10:
                    try:
                        all_races_dict[race_no][idx]["AI指数"] = float(
                            score_str
                        )
                    except Exception:
                        all_races_dict[race_no][idx]["AI指数"] = 0.0
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
            master = json.load(f)
    except Exception as e:
        st.error(f"master_data.json の読み込みエラー: {e}")
        return

    # --- サイドバー ---
    st.sidebar.subheader("🌐 外部データ自動取得")
    with st.sidebar.form("fetch_form"):
        # 開いた日の「翌日」を自動計算して初期表示
        tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y%m%d")
        date_str = st.text_input("開催日付 (YYYYMMDD)", value=tomorrow_str)

        # プレフィックスを空欄デフォルトに
        pdf_prefix = st.text_input(
            "能力PDFプレフィックス (英小文字2文字)", value="", max_chars=2
        ).lower()

        # YOSO_ID を空欄デフォルトに (テキスト入力形式に変更して空欄を許可)
        ai_start_id_str = st.text_input(
            "AI指数 1R目YOSO_ID (7桁数値)", value="", max_chars=7
        )
        # 数値変換用 (未入力の場合は 0 または None)
        ai_start_id = (
            int(ai_start_id_str)
            if ai_start_id_str.isdigit()
            else None
        )
        fetch_btn = st.form_submit_button("データ自動取得")

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
            "脚質補正 (%) [デフォルト70%]",
            min_value=0,
            max_value=200,
            value=70,
            step=10,
        )
        update_btn = st.form_submit_button("データ更新 (再計算)")

    moisture_key = get_moisture_key(moisture_val)

    # 【修正1】初期状態は馬番以外を完全な空欄状態に初期化
    if "fetched_data" not in st.session_state or fetch_btn:
        if fetch_btn:
            with st.spinner("全12レースのデータをWebサイト・PDFから取得中..."):
                st.session_state.fetched_data = fetch_all_pre_data(
                    date_str, pdf_prefix, ai_start_id
                )
                st.success("自動取得が完了しました！")
        else:
            st.session_state.fetched_data = {}
            for r in range(1, 13):
                st.session_state.fetched_data[r] = [
                    {
                        "馬番": i,
                        "馬名": "",
                        "脚質": "先行",
                        "騎手": "",
                        "調教師": "",
                        "AI指数": 0.0,
                        "先行力": 3,
                        "障害力": 3,
                        "末脚": 3,
                        "軽馬場": 3,
                        "重馬場": 3,
                    }
                    for i in range(1, 11)
                ]

    tabs = st.tabs([f"{r}R" for r in range(1, 13)])
    all_race_pre_data = {}
    summary_picks = {}

    # 【修正4】近走評価の選択肢をご指定の [0.5, 0.4, 0.3, 0.2, 0.1, 0.0] に変更
    KINSOU_OPTIONS = [0.5, 0.4, 0.3, 0.2, 0.1, 0.0]
    CLASS_OPTIONS = [0.2, 0.1, 0.0, -0.1, -0.2]

    for r_idx, tab in enumerate(tabs, start=1):
        with tab:
            df_base = pd.DataFrame(st.session_state.fetched_data[r_idx])

            col_input, col_table = st.columns([0.9, 4.1])

            with col_input:
                st.markdown("**補正入力**")
                input_df = pd.DataFrame(
                    {
                        "馬番": range(1, 11),
                        "近走評価": [0.0] * 10,  # デフォルト0.0
                        "前走クラス差": [0.0] * 10,
                    }
                )
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
                    key=f"editor_input_{r_idx}",
                    use_container_width=True,
                )

            df_merged = pd.merge(df_base, edited_inputs, on="馬番")

            # --- 計算処理 ---
            def calc_pre_scores(row):
                if not str(row["馬名"]).strip():
                    return pd.Series([None, None, None, None, None, True])

                half_key = "zenhan" if r_idx <= 6 else "kouhan"

                raw_p_kyakushitsu = (
                    master[half_key]["kyakushitsu"]
                    .get(row["脚質"], {})
                    .get(moisture_key, 0.25)
                )

                p_kyakushitsu = raw_p_kyakushitsu * (kyakushitsu_adj / 100.0)

                p_jockey = master["jockey"].get(row["騎手"], 0.25)
                p_trainer = master["trainer"].get(row["調教師"], 0.25)

                p_senkou = master["ability"]["先行力"].get(
                    str(row["先行力"]), 0.20
                )
                p_shougai = master["ability"]["障害力"].get(
                    str(row["障害力"]), 0.20
                )
                p_sueashi = master["ability"]["末脚"].get(
                    str(row["末脚"]), 0.20
                )
                p_kei = master["ability"]["軽馬場"].get(
                    str(row["軽馬場"]), 0.20
                )
                p_juu = master["ability"]["重馬場"].get(
                    str(row["重馬場"]), 0.20
                )

                ability_product_200 = (
                    p_senkou * p_shougai * p_sueashi * p_kei * p_juu
                ) * 200.0
                ai_val = float(row["AI指数"]) / 100.0

                pre_total = (
                    p_kyakushitsu
                    + p_jockey
                    + p_trainer
                    + ai_val
                    + ability_product_200
                    + row["近走評価"]
                    + row["前走クラス差"]
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
                        html_code += f"<td class='text-center'>{row['近走評価']:.1f}</td>"
                        html_code += f"<td class='text-center'>{row['前走クラス差']:.1f}</td>"
                        html_code += f"<td class='text-center'>{row['脚質複勝率']:.3f}</td>"
                        html_code += f"<td class='text-center'>{row['騎手複勝率']:.3f}</td>"
                        html_code += f"<td class='text-center'>{row['調教師複勝率']:.3f}</td>"
                        html_code += f"<td class='text-center'>{row['能力総合']:.3f}</td>"

                        if show_ability:
                            html_code += f"<td class='text-center'>{row['先行力']}</td>"
                            html_code += f"<td class='text-center'>{row['障害力']}</td>"
                            html_code += f"<td class='text-center'>{row['末脚']}</td>"
                            html_code += f"<td class='text-center'>{row['軽馬場']}</td>"
                            html_code += f"<td class='text-center'>{row['重馬場']}</td>"

                        html_code += "</tr>"

                html_code += "</tbody></table>"
                st.markdown(html_code, unsafe_allow_html=True)

            all_race_pre_data[f"{r_idx}R"] = df_merged.to_dict(orient="records")

    # --- アクションエリア ---
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

    # 【修正2&3】保存先日付を動的指定＆同名ファイル上書き注意表示
    with col_save:
        save_target_date = st.text_input(
            "保存するファイルの日付 (YYYYMMDD)",
            value=date_str,
            key="save_date_input",
        )
        
        # 👈 【変更1】 data/pre フォルダ配下に保存先パスを指定
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
            # 👈 【変更2】 修正後のパス (save_filename) で保存
            with open(save_filename, "w", encoding="utf-8") as f:
                json.dump(all_race_pre_data, f, ensure_ascii=False, indent=2)
            st.success(
                f"事前予想データを 『{save_filename}』 に保存しました！ 当日予想モードへ引き継げます。"
            )