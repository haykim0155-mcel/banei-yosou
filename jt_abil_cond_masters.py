import os
import re
import json
import glob
import pandas as pd

# ファイル名定義
CSV_JT = "騎手調教師アップロード用.csv"
CSV_ANA = "脚質、オッズ、馬体重、各能力.csv"

FILE_ABIL = "master_abil.json"
FILE_JT = "master_jt.json"
FILE_COND = "master_cond.json"

def save_json_pretty(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def find_file(filename):
    search_paths = [
        filename,
        os.path.join("data", filename),
        os.path.join("data", "pre", filename),
        os.path.join("data", "result", filename),
    ]
    for p in search_paths:
        if os.path.exists(p):
            return p
    return None

def jt_abil_cond_masters():
    print("🔄 3分割マスタ（3層構造）の生成と騎手調教師(10/3・10/4分)の『前回』合算を開始します...")

    csv_jt_path = find_file(CSV_JT)
    csv_ana_path = find_file(CSV_ANA)

    if not csv_jt_path or not csv_ana_path:
        print(f"❌ エラー: CSVファイルが見つかりません。")
        return

    # ---------------------------------------------------------
    # 1. 騎手・調教師マスタ (master_jt.json) のCSV読み込み (9/28時点)
    # ---------------------------------------------------------
    df_jt = pd.read_csv(csv_jt_path)
    master_jt = {"jockey": {}, "trainer": {}}

    for idx, row in df_jt.iterrows():
        if idx <= 2: continue
        
        # 騎手
        j_name = str(row['Unnamed: 2']).strip() if pd.notna(row['Unnamed: 2']) else ""
        if j_name and j_name != "nan":
            try:
                r1 = int(float(row['Unnamed: 3']))
                r2 = int(float(row['Unnamed: 4']))
                r3 = int(float(row['Unnamed: 5']))
                r4 = int(float(row['Unnamed: 6']))
                tot = int(float(row['Unnamed: 7']))
                r1_tot = int(float(row['Unnamed: 10'])) if pd.notna(row['Unnamed: 10']) else r1
                
                master_jt["jockey"][j_name] = {
                    "前回_1着": r1, "前回_2着": r2, "前回_3着": r3, "前回_4着以下": r4, "前回_通算勝数": r1_tot,
                    "当日_1着": 0, "当日_2着": 0, "当日_3着": 0, "当日_4着以下": 0, "当日_通算勝数": 0,
                    "1着": r1, "2着": r2, "3着": r3, "4着以下": r4, "通算勝数": r1_tot,
                    "総数": tot, "3着内": r1 + r2 + r3,
                    "勝率": round(r1 / tot, 3) if tot > 0 else 0.0,
                    "連対率": round((r1 + r2) / tot, 3) if tot > 0 else 0.0,
                    "複勝率": round((r1 + r2 + r3) / tot, 3) if tot > 0 else 0.250
                }
            except Exception: pass

        # 調教師
        t_name = str(row['Unnamed: 14']).strip() if pd.notna(row['Unnamed: 14']) else ""
        if t_name and t_name != "nan":
            try:
                r1 = int(float(row['Unnamed: 15']))
                r2 = int(float(row['Unnamed: 16']))
                r3 = int(float(row['Unnamed: 17']))
                r4 = int(float(row['Unnamed: 18']))
                tot = int(float(row['Unnamed: 19']))
                r1_tot = int(float(row['Unnamed: 22'])) if pd.notna(row['Unnamed: 22']) else r1
                
                master_jt["trainer"][t_name] = {
                    "前回_1着": r1, "前回_2着": r2, "前回_3着": r3, "前回_4着以下": r4, "前回_通算勝数": r1_tot,
                    "当日_1着": 0, "当日_2着": 0, "当日_3着": 0, "当日_4着以下": 0, "当日_通算勝数": 0,
                    "1着": r1, "2着": r2, "3着": r3, "4着以下": r4, "通算勝数": r1_tot,
                    "総数": tot, "3着内": r1 + r2 + r3,
                    "勝率": round(r1 / tot, 3) if tot > 0 else 0.0,
                    "連対率": round((r1 + r2) / tot, 3) if tot > 0 else 0.0,
                    "複勝率": round((r1 + r2 + r3) / tot, 3) if tot > 0 else 0.250
                }
            except Exception: pass

    # 💡 騎手調教師データへ 10/3 (土) と 10/4 (日) の成績を『前回_』として合算
    res_search_patterns = [
        "result_data_*.json", os.path.join("data", "result_data_*.json"), os.path.join("data", "result", "result_data_*.json")
    ]
    res_files = list(set([f for p in res_search_patterns for f in glob.glob(p)]))

    for res_path in sorted(res_files):
        clean_d = re.sub(r"\D", "", os.path.basename(res_path))
        if clean_d in ["20261003", "20261004"]:
            pre_file_name = f"pre_data_{clean_d}.json"
            pre_path = find_file(pre_file_name)
            if pre_path and os.path.exists(pre_path):
                try:
                    with open(res_path, "r", encoding="utf-8") as rf: res_json = json.load(rf)
                    with open(pre_path, "r", encoding="utf-8") as pf: pre_json = json.load(pf)

                    pre_map = {}
                    if isinstance(pre_json, dict):
                        for r_k, h_list in pre_json.items():
                            if isinstance(h_list, list):
                                pre_map[r_k] = {
                                    int(h["馬番"]): {
                                        "騎手": h.get("騎手", ""),
                                        "調教師": h.get("調教師", "")
                                    }
                                    for h in h_list if isinstance(h, dict) and "馬番" in h and str(h["馬番"]).replace(".", "").isdigit()
                                }

                    for r in range(1, 13):
                        r_k = f"{r}R"
                        r_info = res_json.get(r_k, {})
                        t1_list = [int(x) for x in r_info.get("1着_list", []) if str(x).isdigit()]
                        t2_list = [int(x) for x in r_info.get("2着_list", []) if str(x).isdigit()]
                        t3_list = [int(x) for x in r_info.get("3着_list", []) if str(x).isdigit()]

                        r_pre = pre_map.get(r_k, {})
                        for h_num, h_info in r_pre.items():
                            j_name, t_name = h_info["騎手"], h_info["調教師"]
                            rank = 4
                            if h_num in t1_list: rank = 1
                            elif h_num in t2_list: rank = 2
                            elif h_num in t3_list: rank = 3

                            for entity_type, name in [("jockey", j_name), ("trainer", t_name)]:
                                if name and name in master_jt[entity_type]:
                                    st = master_jt[entity_type][name]
                                    if rank == 1:
                                        st["前回_1着"] += 1
                                        st["前回_通算勝数"] += 1
                                    elif rank == 2: st["前回_2着"] += 1
                                    elif rank == 3: st["前回_3着"] += 1
                                    else: st["前回_4着以下"] += 1

                    print(f" └ 日付『{clean_d}』の成績を騎手調教師の『前回_』データへ合算完了。")
                except Exception as e:
                    print(f"⚠️ {clean_d} 合算時エラー: {e}")

    # 騎手調教師の「合計値」と「各種率」を再計算
    for entity in ["jockey", "trainer"]:
        for name, st in master_jt[entity].items():
            st["1着"] = st["前回_1着"]
            st["2着"] = st["前回_2着"]
            st["3着"] = st["前回_3着"]
            st["4着以下"] = st["前回_4着以下"]
            st["通算勝数"] = st["前回_通算勝数"]
            tot = st["1着"] + st["2着"] + st["3着"] + st["4着以下"]
            fuk = st["1着"] + st["2着"] + st["3着"]
            st["総数"] = tot
            st["3着内"] = fuk
            st["勝率"] = round(st["1着"] / tot, 3) if tot > 0 else 0.0
            st["連対率"] = round((st["1着"] + st["2着"]) / tot, 3) if tot > 0 else 0.0
            st["複勝率"] = round(fuk / tot, 3) if tot > 0 else 0.250

    save_json_pretty(FILE_JT, master_jt)
    print(f"✅ {FILE_JT} を作成（土・日分加算済みで10/4日曜日時点に同期完了）。")

    # ---------------------------------------------------------
    # 2. 能力5指標マスタ (master_abil.json)
    # ---------------------------------------------------------
    df_ana = pd.read_csv(csv_ana_path)
    master_abil = {}
    ab_col_ranges = {
        "先行力": (1, 6), "障害力": (6, 11), "末脚力": (11, 16), "軽馬場": (16, 21), "重馬場": (21, 26)
    }
    for ab_name, (start_c, end_c) in ab_col_ranges.items():
        master_abil[ab_name] = {}
        for col_idx in range(start_c, end_c):
            try:
                lv_str = str(int(float(df_ana.iloc[0, col_idx])))
                tot = int(float(df_ana.iloc[2, col_idx]))
                fuk = int(float(df_ana.iloc[3, col_idx]))
                master_abil[ab_name][lv_str] = {
                    "前回_総数": tot, "前回_複勝": fuk,
                    "当日_総数": 0, "当日_複勝": 0,
                    "総数": tot, "複勝": fuk,
                    "複勝率": round(fuk / tot, 4) if tot > 0 else 0.2000
                }
            except Exception: pass

    save_json_pretty(FILE_ABIL, master_abil)
    print(f"✅ {FILE_ABIL} を作成しました（10/4日曜日時点）。")

    # ---------------------------------------------------------
    # 3. 条件別マスタ (master_cond.json)
    # ---------------------------------------------------------
    master_cond = {"前半(1~6R)": {}, "後半(7~12R)": {}}
    water_blocks = [
        ("極重", 12), ("稍重", 21), ("普通", 30), ("稍軽", 39), ("極軽", 48)
    ]

    for w_label, c_row in water_blocks:
        if c_row >= len(df_ana): continue
        
        z_dict = master_cond["前半(1~6R)"].setdefault(w_label, {"脚質": {}, "オッズ": {}, "馬体重": {}})
        k_dict = master_cond["後半(7~12R)"].setdefault(w_label, {"脚質": {}, "オッズ": {}, "馬体重": {}})

        # 1. 脚質
        styles = ["逃げ", "先行", "差し", "追込"]
        for idx, st in enumerate(styles):
            # 前半(1~6R)
            f_z = int(float(df_ana.iloc[c_row, idx]))        # A~D (複勝)
            t_z = int(float(df_ana.iloc[c_row, idx + 4]))    # E~H (総数)
            z_dict["脚質"][st] = {
                "前回_総数": t_z, "前回_複勝": f_z, "当日_総数": 0, "当日_複勝": 0,
                "総数": t_z, "複勝": f_z, "複勝率": round(f_z / t_z, 4) if t_z > 0 else 0.2000
            }
            # 後半(7~12R) ➔ AD~AG (複勝), AH~AK (総数)
            f_k = int(float(df_ana.iloc[c_row, idx + 29]))
            t_k = int(float(df_ana.iloc[c_row, idx + 33]))
            k_dict["脚質"][st] = {
                "前回_総数": t_k, "前回_複勝": f_k, "当日_総数": 0, "当日_複勝": 0,
                "総数": t_k, "複勝": f_k, "複勝率": round(f_k / t_k, 4) if t_k > 0 else 0.2000
            }

        # 2. オッズ
        odds_keys = ["◎", "○", "▲", "△", "×"]
        for idx, ok in enumerate(odds_keys):
            # 前半(1~6R)
            f_z = int(float(df_ana.iloc[c_row, idx + 9]))    # J~N (複勝)
            t_z = int(float(df_ana.iloc[c_row, idx + 14]))   # O~S (総数)
            z_dict["オッズ"][ok] = {
                "前回_総数": t_z, "前回_複勝": f_z, "当日_総数": 0, "当日_複勝": 0,
                "総数": t_z, "複勝": f_z, "複勝率": round(f_z / t_z, 4) if t_z > 0 else 0.2000
            }
            # 後半(7~12R) ➔ AM~AQ (複勝), AR~AV (総数)
            f_k = int(float(df_ana.iloc[c_row, idx + 38]))
            t_k = int(float(df_ana.iloc[c_row, idx + 43]))
            k_dict["オッズ"][ok] = {
                "前回_総数": t_k, "前回_複勝": f_k, "当日_総数": 0, "当日_複勝": 0,
                "総数": t_k, "複勝": f_k, "複勝率": round(f_k / t_k, 4) if t_k > 0 else 0.2000
            }

        # 3. 馬体重
        w_keys = ["+20以上", "+10台", "±1桁", "-2桁"]
        for idx, wk in enumerate(w_keys):
            # 前半(1~6R) ➔ U~X (総数), Y~AB (複勝)
            t_z = int(float(df_ana.iloc[c_row, idx + 20]))
            f_z = int(float(df_ana.iloc[c_row, idx + 24]))
            z_dict["馬体重"][wk] = {
                "前回_総数": t_z, "前回_複勝": f_z, "当日_総数": 0, "当日_複勝": 0,
                "総数": t_z, "複勝": f_z, "複勝率": round(f_z / t_z, 4) if t_z > 0 else 0.2000
            }
            # 後半(7~12R) ➔ AX~BA (総数), BB~BE (複勝)
            t_k = int(float(df_ana.iloc[c_row, idx + 49]))
            f_k = int(float(df_ana.iloc[c_row, idx + 53]))
            k_dict["馬体重"][wk] = {
                "前回_総数": t_k, "前回_複勝": f_k, "当日_総数": 0, "当日_複勝": 0,
                "総数": t_k, "複勝": f_k, "複勝率": round(f_k / t_k, 4) if t_k > 0 else 0.2000
            }

    save_json_pretty(FILE_COND, master_cond)
    print(f"✅ {FILE_COND} を作成しました（10/4日曜日時点）。")

    print("\n✨ 準備完了！ 3マスタ全てが【10月4日（日）終了時点】の数値で美しく同期されました！")

if __name__ == "__main__":
    jt_abil_cond_masters()