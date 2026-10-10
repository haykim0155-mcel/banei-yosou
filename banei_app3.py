import json
import os
import re
import glob
from datetime import datetime
import pandas as pd
import pypdf
import requests
from bs4 import BeautifulSoup
import streamlit as st

# パス定義
DIR_PRE = "data/pre"
DIR_TODAY = "data/today"
DIR_RESULT = "data/result"

PATH_JT = "master_jt.json"
PATH_ABIL = "master_abil.json"
PATH_COND = "master_cond.json"
PATH_HIST_BALANCE = "history_balance.json"
PATH_HIST_WINRATES = "history_winrates.json"

for d in [DIR_PRE, DIR_TODAY, DIR_RESULT]:
    os.makedirs(d, exist_ok=True)


def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return [] if "history_" in filepath else {}


def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_pre_path(date_str):
    return os.path.join(DIR_PRE, f"pre_data_{date_str}.json")


def get_today_path(date_str):
    return os.path.join(DIR_TODAY, f"today_data_{date_str}.json")


def get_result_path(date_str):
    return os.path.join(DIR_RESULT, f"result_data_{date_str}.json")

# =========================================================
# 水分量からマスタ参照キーを取得する関数（新日本語表記統一）
# =========================================================
def get_moisture_key(val):
    try:
        f_val = float(val)
    except (ValueError, TypeError):
        f_val = 1.0

    if f_val <= 0.9:
        return "極重"
    elif f_val <= 1.5:
        return "稍重"
    elif f_val <= 2.0:
        return "普通"
    elif f_val <= 3.0:
        return "稍軽"
    else:
        return "極軽"


# =========================================================
# 馬体重増減からマスタ参照キーを取得する関数
# =========================================================
def get_weight_key(val):
    try:
        w_val = int(val)
    except (ValueError, TypeError):
        w_val = 0

    if w_val >= 20:
        return "+20以上"
    elif w_val >= 10:
        return "+10台"
    elif w_val <= -10:
        return "-2桁"
    else:
        return "±1桁"

# =========================================================
# 💡 全データ一括自動更新エンジン（最終総合順位4頭BOX厳密計算＆JSON綺麗整形版）
# =========================================================
def update_all_data_from_results(target_date, moisture_str="1.0%"):
    clean_d = re.sub(r"\D", "", target_date)
    res_path = get_result_path(clean_d)
    pre_path = get_pre_path(clean_d)
    today_path = get_today_path(clean_d)

    if not os.path.exists(res_path):
        return (
            False,
            f"『result_data_{clean_d}.json』 が存在しません。結果を取得・保存してください。",
        )

    res_json = load_json(res_path)
    pre_json = load_json(pre_path)
    today_json = load_json(today_path)

    # 新3分割JSONの読み込み
    master_jt = load_json(PATH_JT)
    master_abil = load_json(PATH_ABIL)
    master_cond = load_json(PATH_COND)

    d_label = (
        f"{int(clean_d[4:6])}月{int(clean_d[6:])}日"
        if len(clean_d) == 8
        else clean_d
    )

    day_payouts = {
        "日付": d_label,
        "単勝": 0, "複勝": 0, "馬連": 0, "馬単": 0, "ワイド": 0, "3連複": 0, "3連単": 0,
    }

    day_winrates = {"日付": d_label, "水分": moisture_str}

    # 事前データ ＆ 当日確定データの統合マッピング作成
    pre_map = {}
    
    # 1. まず pre_data から基本情報（騎手・能力など）を取得
    if isinstance(pre_json, dict):
        for r_k, h_list in pre_json.items():
            pre_map[r_k] = {}
            if isinstance(h_list, list):
                for h in h_list:
                    if isinstance(h, dict) and "馬番" in h:
                        try:
                            h_no = int(float(h["馬番"]))
                            pre_map[r_k][h_no] = {
                                "騎手": str(h.get("騎手", "")).strip(),
                                "調教師": str(h.get("調教師", "")).strip(),
                                "脚質": str(h.get("脚質", "先行")).strip(),
                                "オッズ記号": str(h.get("オッズ記号", h.get("オッズ", "×"))).strip(),
                                "馬体重差": get_weight_key(h.get("増減", h.get("馬体重差", 0))),
                                "先行力": int(float(h.get("先行力", h.get("先行", 3)))),
                                "障害力": int(float(h.get("障害力", h.get("障害", 3)))),
                                "末脚力": int(float(h.get("末脚力", h.get("末脚", 3)))),
                                "軽馬場": int(float(h.get("軽馬場", 3))),
                                "重馬場": int(float(h.get("重馬場", 3))),
                            }
                        except Exception: pass

    # 2. 💡【重要】today_data に入っている「当日の確定オッズ記号・馬体重増減」で上書き補正
    if isinstance(today_json, dict):
        for r_k, h_list in today_json.items():
            if r_k not in pre_map:
                pre_map[r_k] = {}
            if isinstance(h_list, list):
                for h in h_list:
                    if isinstance(h, dict) and "馬番" in h:
                        try:
                            h_no = int(float(h["馬番"]))
                            if h_no not in pre_map[r_k]:
                                pre_map[r_k][h_no] = {
                                    "騎手": str(h.get("騎手", "")).strip(),
                                    "調教師": str(h.get("調教師", "")).strip(),
                                    "脚質": str(h.get("脚質", "先行")).strip(),
                                    "先行力": 3, "障害力": 3, "末脚力": 3, "軽馬場": 3, "重馬場": 3
                                }
                            
                            # 当日のオッズ記号と馬体重差を確実にセット
                            o_raw = str(h.get("オッズ記号", h.get("オッズマーク", h.get("オッズ印", h.get("オッズ", "-"))))).strip()
                            w_raw = h.get("増減", h.get("馬体重増減", h.get("馬体重差", 0)))
                            
                            if o_raw in ["◎", "○", "▲", "△", "×"]:
                                pre_map[r_k][h_no]["オッズ記号"] = o_raw
                            pre_map[r_k][h_no]["馬体重差"] = get_weight_key(w_raw)
                            if "脚質" in h and h["脚質"]:
                                pre_map[r_k][h_no]["脚質"] = str(h["脚質"]).strip()
                        except Exception: pass

    try:
        m_val = float(re.sub(r"[^\d.]", "", moisture_str))
        w_seg = get_moisture_key(m_val)
    except Exception:
        w_seg = "稍重"

    for r in range(1, 13):
        r_k = f"{r}R"
        r_info = res_json.get(r_k, {})
        t1_list = r_info.get("1着_list", [])
        t2_list = r_info.get("2着_list", [])
        t3_list = r_info.get("3着_list", [])

        # ---------------------------------------------------------
        # 💡 最終総合順位の上位4頭（BOX）を確実に抽出
        # ---------------------------------------------------------
        box_horses = []
        if isinstance(today_json, dict) and r_k in today_json:
            valid_horses = [
                x for x in today_json[r_k]
                if isinstance(x, dict) and "最終順位" in x and pd.notna(x["最終順位"])
            ]
            sorted_h = sorted(valid_horses, key=lambda x: int(float(x.get("最終順位", 99))))
            box_horses = [int(float(x["馬番"])) for x in sorted_h[:4] if "馬番" in x and pd.notna(x["馬番"])]

        # ---------------------------------------------------------
        # 💡 4頭BOX的中に基づく正確な収支計算（シート合計と完全一致）
        # ---------------------------------------------------------
        if box_horses and len(box_horses) == 4:
            # 1. 単勝
            for m_str, p_val in r_info.get("単勝", {}).items():
                if m_str.isdigit() and int(m_str) in box_horses:
                    day_payouts["単勝"] += p_val

            # 2. 複勝
            for item in r_info.get("複勝", []):
                if isinstance(item, dict):
                    m_num = item.get("馬番")
                    if m_num and int(m_num) in box_horses:
                        day_payouts["複勝"] += item.get("金額", 0)

            # 3. 馬連
            if t1_list and t2_list and (t1_list[0] in box_horses) and (t2_list[0] in box_horses):
                for item in r_info.get("馬連", []):
                    day_payouts["馬連"] += item.get("金額", 0) if isinstance(item, dict) else 0

            # 4. 馬単
            if t1_list and t2_list and (t1_list[0] in box_horses) and (t2_list[0] in box_horses):
                for item in r_info.get("馬単", []):
                    day_payouts["馬単"] += item.get("金額", 0) if isinstance(item, dict) else 0

            # 5. ワイド (辞書型・ハイフン文字列・配列の全パターンに完全対応)
            wide_data = r_info.get("ワイド", [])
            if isinstance(wide_data, dict):
                # パターンA: {"1-6": 460, "1-2": 290} のような辞書型
                for k_str, p_val in wide_data.items():
                    nums = [int(x) for x in re.findall(r"\d+", str(k_str))]
                    if len(nums) == 2 and nums[0] in box_horses and nums[1] in box_horses:
                        day_payouts["ワイド"] += p_val if isinstance(p_val, int) else p_val.get("金額", 0)
            elif isinstance(wide_data, list):
                # パターンB: [{"組合せ": [1, 6], "金額": 460}, ...] や [{"組合せ": "1-6", "金額": 460}]
                for item in wide_data:
                    if isinstance(item, dict):
                        combo = item.get("組合せ", item.get("組", item.get("馬番", [])))
                        nums = []
                        if isinstance(combo, list):
                            nums = [int(x) for x in combo if str(x).isdigit()]
                        elif isinstance(combo, str):
                            nums = [int(x) for x in re.findall(r"\d+", combo)]
                        
                        if len(nums) == 2 and nums[0] in box_horses and nums[1] in box_horses:
                            day_payouts["ワイド"] += item.get("金額", 0)

            # 6. 3連複
            if t1_list and t2_list and t3_list:
                if (t1_list[0] in box_horses) and (t2_list[0] in box_horses) and (t3_list[0] in box_horses):
                    for item in r_info.get("3連複", []):
                        day_payouts["3連複"] += item.get("金額", 0) if isinstance(item, dict) else 0

            # 7. 3連単
            if t1_list and t2_list and t3_list:
                if (t1_list[0] in box_horses) and (t2_list[0] in box_horses) and (t3_list[0] in box_horses):
                    for item in r_info.get("3連単", []):
                        day_payouts["3連単"] += item.get("金額", 0) if isinstance(item, dict) else 0

        # 実績加算（騎手・調教師・能力5指標・cond）
        sec_key = "前半(1~6R)" if r <= 6 else "後半(7~12R)"

        # 初回のみ日次保持用オブジェクトを初期化
        if "daily_stats" not in locals():
            daily_stats = {
                "日付": clean_d, "水分区分": w_seg,
                "jockey": {}, "trainer": {}, "abil": {},
                "cond": {w_seg: {"脚質": {}, "オッズ": {}, "馬体重": {}}}
            }

        # 💡 タブ1と100%数値を一致させるため today_data の出走馬をベースにループ
        r_today_list = today_json.get(r_k, []) if isinstance(today_json, dict) else []
        r_pre_ab = pre_json.get(r_k, []) if isinstance(pre_json, dict) else []

        # 馬番ごとの能力5指標マップを作成
        ab_map_r = {}
        if isinstance(r_pre_ab, list):
            for hb in r_pre_ab:
                if isinstance(hb, dict) and "馬番" in hb:
                    try:
                        h_no = int(float(hb["馬番"]))
                        ab_map_r[h_no] = hb
                    except Exception: pass

        if isinstance(r_today_list, list):
            for h_item in r_today_list:
                if not isinstance(h_item, dict): continue
                
                try:
                    h_num = int(float(h_item.get("馬番", 0)))
                except Exception:
                    h_num = 0
                
                h_name = str(h_item.get("馬名", "")).strip()
                
                # 確定着順判定（t1_list, t2_list, t3_list を直接参照してエラー回避）
                rank = 4
                if h_num in t1_list: rank = 1
                elif h_num in t2_list: rank = 2
                elif h_num in t3_list: rank = 3
                is_fukusho = 1 if rank in [1, 2, 3] else 0

                # 💡 『確定着順』が "-" (ハイフン) または未決定の除外馬を完全にスキップ判定
                confirm_rank = str(h_item.get("確定着順", h_item.get("着順", ""))).strip()
                is_cancelled = (confirm_rank == "-" or confirm_rank == "" or confirm_rank == "競走除外")

                if h_name and h_num > 0 and not is_cancelled:
                    j_name = str(h_item.get("騎手", "")).strip()
                    t_name = str(h_item.get("調教師", "")).strip()
                    s_val = str(h_item.get("脚質", "先行")).strip()
                    
                    # 💡 "-" (ハイフン/競走除外) も有効な値としてそのまま許容し、"×" へ勝手に変換させない
                    o_val = str(h_item.get("オッズ記号", h_item.get("オッズマーク", h_item.get("オッズ印", h_item.get("オッズ", "-"))))).strip()
                    if o_val not in ["◎", "○", "▲", "△", "×", "-"]:
                        o_val = "-"
                        
                    w_val = get_weight_key(h_item.get("増減", h_item.get("馬体重増減", h_item.get("馬体重差", 0))))

                    # 騎手・調教師（本日分のみカウント）
                    for entity_type, name in [("jockey", j_name), ("trainer", t_name)]:
                        if name:
                            st = daily_stats[entity_type].setdefault(name, {"1着": 0, "2着": 0, "3着": 0, "4着以下": 0, "通算勝数": 0})
                            if rank == 1: st["1着"] += 1; st["通算勝数"] += 1
                            elif rank == 2: st["2着"] += 1
                            elif rank == 3: st["3着"] += 1
                            else: st["4着以下"] += 1

                    # 能力5指標（事前データから参照）
                    ab_info = ab_map_r.get(h_num, {})
                    for ab_name in ["先行力", "障害力", "末脚力", "軽馬場", "重馬場"]:
                        try:
                            lv_val = str(int(float(ab_info.get(ab_name, h_item.get(ab_name, 3)))))
                        except Exception:
                            lv_val = "3"
                        ab_st = daily_stats["abil"].setdefault(ab_name, {}).setdefault(lv_val, {"総数": 0, "複勝": 0})
                        ab_st["総数"] += 1; ab_st["複勝"] += is_fukusho

                    # 条件別 cond（本日分のみカウント）
                    c_sec = daily_stats["cond"].setdefault(sec_key, {}).setdefault(w_seg, {"脚質": {}, "オッズ": {}, "馬体重": {}})
                    s_st = c_sec["脚質"].setdefault(s_val, {"総数": 0, "複勝": 0}); s_st["総数"] += 1; s_st["複勝"] += is_fukusho

                    # 💡 オッズ印が "◎", "○", "▲", "△", "×" の場合のみ加算し、"-" (取消・未設定) は集計から完全除外
                    if o_val in ["◎", "○", "▲", "△", "×"]:
                        o_st = c_sec["オッズ"].setdefault(o_val, {"総数": 0, "複勝": 0}); o_st["総数"] += 1; o_st["複勝"] += is_fukusho

                    w_st = c_sec["馬体重"].setdefault(w_val, {"総数": 0, "複勝": 0}); w_st["総数"] += 1; w_st["複勝"] += is_fukusho
 
        # 的中マーク判定
        if t1_list and box_horses:
            hit1 = any(h in box_horses for h in t1_list)
            hit2 = any(h in box_horses for h in t2_list) if t2_list else False
            hit3 = any(h in box_horses for h in t3_list) if t3_list else False
            if not hit1: day_winrates[r_k] = "×"
            elif hit1 and not hit2: day_winrates[r_k] = "△"
            elif hit1 and hit2 and not hit3: day_winrates[r_k] = "○"
            elif hit1 and hit2 and hit3: day_winrates[r_k] = "◎"
        else:
            day_winrates[r_k] = "-"
            
    # ---------------------------------------------------------
    # 🔄 3層統合＆前回繰り越し処理（次回用に 当日_ を 0 リセット）
    # ---------------------------------------------------------
    # 1. 騎手・調教師の統合・繰り越し
    for entity in ["jockey", "trainer"]:
        for name, st in master_jt[entity].items():
            st["前回_1着"] += st["当日_1着"]
            st["前回_2着"] += st["当日_2着"]
            st["前回_3着"] += st["当日_3着"]
            st["前回_4着以下"] += st["当日_4着以下"]
            st["前回_通算勝数"] += st["当日_通算勝数"]
            
            st["当日_1着"] = st["当日_2着"] = st["当日_3着"] = st["当日_4着以下"] = st["当日_通算勝数"] = 0
            
            r1, r2, r3, r4 = st["前回_1着"], st["前回_2着"], st["前回_3着"], st["前回_4着以下"]
            st["1着"], st["2着"], st["3着"], st["4着以下"] = r1, r2, r3, r4
            st["通算勝数"] = st["前回_通算勝数"]
            tot = r1 + r2 + r3 + r4
            fuk = r1 + r2 + r3
            st["総数"], st["3着内"] = tot, fuk
            st["勝率"] = round(r1 / tot, 3) if tot > 0 else 0.0
            st["連対率"] = round((r1 + r2) / tot, 3) if tot > 0 else 0.0
            st["複勝率"] = round(fuk / tot, 3) if tot > 0 else 0.250

    # 2. 能力5指標 & 条件別の統合・繰り越し
    def finalize_rates_and_carryover(node):
        if isinstance(node, dict):
            if "前回_総数" in node and "当日_総数" in node:
                node["前回_総数"] += node["当日_総数"]
                node["前回_複勝"] += node["当日_複勝"]
                node["当日_総数"] = 0
                node["当日_複勝"] = 0
                
                tot = node["前回_総数"]
                fuk = node["前回_複勝"]
                node["総数"] = tot
                node["複勝"] = fuk
                node["複勝率"] = round(fuk / tot, 4) if tot > 0 else 0.2000
            for k, v in node.items():
                finalize_rates_and_carryover(v)

    finalize_rates_and_carryover(master_abil)
    finalize_rates_and_carryover(master_cond)

    # ---------------------------------------------------------
    # 💡 基礎データ保護 ＆ 2度押し対応・当日上書き再構築エンジン
    # ---------------------------------------------------------
    # 1. 本日単体のログを data/daily/daily_stats_YYYYMMDD.json へ保存
    DIR_DAILY = "data/daily"
    os.makedirs(DIR_DAILY, exist_ok=True)
    daily_file = os.path.join(DIR_DAILY, f"daily_stats_{clean_d}.json")
    with open(daily_file, "w", encoding="utf-8") as f:
        json.dump(daily_stats, f, ensure_ascii=False, indent=2)

    # 2. マスタファイルの読み込み（10/4までのベースデータを含む）
    master_jt = load_json(PATH_JT)
    master_abil = load_json(PATH_ABIL)
    master_cond = load_json(PATH_COND)

    # 3. 重加算防止：すべての「当日_」項目をまず0リセット（前回_ は維持）
    for entity in ["jockey", "trainer"]:
        for name, st in master_jt.get(entity, {}).items():
            st["当日_1着"] = st["当日_2着"] = st["当日_3着"] = st["当日_4着以下"] = st["当日_通算勝数"] = 0

    def reset_today_only(node):
        if isinstance(node, dict):
            if "当日_総数" in node:
                node["当日_総数"] = 0
                node["当日_複勝"] = 0
            for k, v in node.items():
                reset_today_only(v)

    reset_today_only(master_abil)
    reset_today_only(master_cond)

    # 4. data/daily/ フォルダ内の全ファイルをスキャンし、過去分は「前回_」、当日分は「当日_」へ格納
    daily_files = sorted(glob.glob(os.path.join(DIR_DAILY, "daily_stats_*.json")))
    for df_path in daily_files:
        d_data = load_json(df_path)
        f_date = os.path.basename(df_path).replace("daily_stats_", "").replace(".json", "")
        
        # 処理対象の日付(clean_d)と一致する場合は「当日_」、過去日付なら「前回_」へ加算
        prefix = "当日_" if f_date == clean_d else "前回_"

        # A. 騎手・調教師
        for entity in ["jockey", "trainer"]:
            for name, st in d_data.get(entity, {}).items():
                if name in master_jt.get(entity, {}):
                    m_st = master_jt[entity][name]
                    m_st[f"{prefix}1着"] += st.get("1着", 0)
                    m_st[f"{prefix}2着"] += st.get("2着", 0)
                    m_st[f"{prefix}3着"] += st.get("3着", 0)
                    m_st[f"{prefix}4着以下"] += st.get("4着以下", 0)
                    m_st[f"{prefix}通算勝数"] += st.get("通算勝数", 0)

        # B. 能力5指標
        for ab_name, lvs in d_data.get("abil", {}).items():
            for lv_val, st in lvs.items():
                m_st = master_abil.setdefault(ab_name, {}).setdefault(lv_val, {"前回_総数": 0, "前回_複勝": 0, "当日_総数": 0, "当日_複勝": 0, "総数": 0, "複勝": 0, "複勝率": 0.2})
                m_st[f"{prefix}総数"] += st.get("総数", 0)
                m_st[f"{prefix}複勝"] += st.get("複勝", 0)

        # C. 条件別
        for sec_k, w_dict in d_data.get("cond", {}).items():
            for w_k, cat_dict in w_dict.items():
                for cat_k, items in cat_dict.items():
                    for item_k, st in items.items():
                        m_st = master_cond.setdefault(sec_k, {}).setdefault(w_k, {}).setdefault(cat_k, {}).setdefault(item_k, {"前回_総数": 0, "前回_複勝": 0, "当日_総数": 0, "当日_複勝": 0, "総数": 0, "複勝": 0, "複勝率": 0.2})
                        m_st[f"{prefix}総数"] += st.get("総数", 0)
                        m_st[f"{prefix}複勝"] += st.get("複勝", 0)

    # 5. 最終更新日の付与
    master_jt["最終更新日"] = clean_d
    master_abil["最終更新日"] = clean_d
    master_cond["最終更新日"] = clean_d

    # 6. 「前回_」＋「当日_」から「総数」と「率」を算出
    for entity in ["jockey", "trainer"]:
        for name, st in master_jt[entity].items():
            if isinstance(st, dict):
                r1 = st["前回_1着"] + st["当日_1着"]
                r2 = st["前回_2着"] + st["当日_2着"]
                r3 = st["前回_3着"] + st["当日_3着"]
                r4 = st["前回_4着以下"] + st["当日_4着以下"]
                st["1着"], st["2着"], st["3着"], st["4着以下"] = r1, r2, r3, r4
                st["通算勝数"] = st["前回_通算勝数"] + st["当日_通算勝数"]
                tot, fuk = r1 + r2 + r3 + r4, r1 + r2 + r3
                st["総数"], st["3着内"] = tot, fuk
                st["勝率"] = round(r1 / tot, 3) if tot > 0 else 0.0
                st["連対率"] = round((r1 + r2) / tot, 3) if tot > 0 else 0.0
                st["複勝率"] = round(fuk / tot, 3) if tot > 0 else 0.250

    def calc_node_rates(node):
        if isinstance(node, dict):
            if "前回_総数" in node and "当日_総数" in node:
                tot = node["Previous_Total"] = node["前回_総数"] + node["当日_総数"] if False else node["前回_総数"] + node["当日_総数"]
                fuk = node["前回_複勝"] + node["当日_複勝"]
                node["総数"], node["複勝"] = tot, fuk
                node["複勝率"] = round(fuk / tot, 4) if tot > 0 else 0.2000
            for k, v in node.items():
                if k != "最終更新日":
                    calc_node_rates(v)

    calc_node_rates(master_abil)
    calc_node_rates(master_cond)

    # 💡 人間が見やすい縦並びJSONフォーマットで保存するヘルパー関数
    def save_json_pretty(filepath, data):
        raw_str = json.dumps(data, ensure_ascii=False, indent=2)
        # 最下層（1項目1行）の折り返しを横1行に整形
        compact_str = re.sub(
            r'\{\s*\n\s*"前回_総数":\s*(\d+),\s*\n\s*"前回_複勝":\s*(\d+),\s*\n\s*"当日_総数":\s*(\d+),\s*\n\s*"当日_複勝":\s*(\d+),\s*\n\s*"総数":\s*(\d+),\s*\n\s*"複勝":\s*(\d+),\s*\n\s*"複勝率":\s*([\d\.]+)\s*\}',
            r'{"前回_総数": \1, "前回_複勝": \2, "当日_総数": \3, "当日_複勝": \4, "総数": \5, "複勝": \6, "複勝率": \7}',
            raw_str
        )
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(compact_str)

    # 1. 計算完了した3分割マスタを確実に書き出し保存
    save_json_pretty(PATH_JT, master_jt)
    save_json_pretty(PATH_ABIL, master_abil)
    save_json_pretty(PATH_COND, master_cond)

    # 2. 収支・勝率データの保存
    hist_balance = load_json(PATH_HIST_BALANCE)
    hist_balance = [row for row in hist_balance if str(row.get("日付")) != day_payouts["日付"]]
    hist_balance.insert(0, day_payouts)
    save_json_pretty(PATH_HIST_BALANCE, hist_balance)

    hist_winrates = load_json(PATH_HIST_WINRATES)
    hist_winrates = [row for row in hist_winrates if str(row.get("日付")) != day_winrates["日付"]]
    hist_winrates.insert(0, day_winrates)
    save_json_pretty(PATH_HIST_WINRATES, hist_winrates)

    return (
        True,
        f"日付『{d_label}』の結果を新3分割マスタ（3層繰り越し統合）へ確定反映・保存しました！",
    )


# =========================================================
# Yahoo!競馬 完全分離スクレイパー (枠複・他券種混入ゼロ版)
# =========================================================
def fetch_and_parse_full_results_web(date_str, kai_code="04"):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    parsed_results = {}
    progress_bar = st.progress(0)
    status_text = st.empty()

    # 2桁にフォーマット整形 (例: "4" -> "04", 4 -> "04")
    try:
        kai_str = f"{int(kai_code):02d}"
    except (ValueError, TypeError):
        kai_str = "04"

    for r in range(1, 13):
        status_text.text(
            f"⏳ {r}R / 12R の確定着順・全7券種払戻金をYahoo!競馬より精査取得中..."
        )
        r_dict = {
            "1着_list": [],
            "2着_list": [],
            "3着_list": [],
            "単勝": {},
            "複勝": [],
            "馬連": [],
            "馬単": [],
            "ワイド": [],
            "3連複": [],
            "3連単": [],
        }

        # 💡 帯広場コード "03" + 日次コード kai_str (例: "04") + レース番号
        # 例: 20261003 + 03 + 04 + 01 -> https://sports.yahoo.co.jp/keiba_local/race/result/20261003030401
        yahoo_url = f"https://sports.yahoo.co.jp/keiba_local/race/result/{date_str}03{kai_str}{r:02d}"

        try:
            res = requests.get(yahoo_url, headers=headers, timeout=5)
            res.encoding = "utf-8"
            soup = BeautifulSoup(res.text, "html.parser")

            tables = soup.find_all("table")
            
            # 1. 確定着順の取得
            result_tbl = None
            for tbl in tables:
                if "着順" in tbl.get_text():
                    result_tbl = tbl
                    break

            if result_tbl:
                for row in result_tbl.find_all("tr"):
                    cols = row.find_all(["td", "th"])
                    if len(cols) >= 3:
                        rank_txt = cols[0].get_text(strip=True)
                        horse_txt = (
                            cols[2].get_text(strip=True)
                            if cols[2].get_text(strip=True).isdigit()
                            else cols[1].get_text(strip=True)
                        )

                        if horse_txt.isdigit():
                            h_num = int(horse_txt)
                            if rank_txt == "1" and h_num not in r_dict["1着_list"]:
                                r_dict["1着_list"].append(h_num)
                            elif rank_txt == "2" and h_num not in r_dict["2着_list"]:
                                r_dict["2着_list"].append(h_num)
                            elif rank_txt == "3" and h_num not in r_dict["3着_list"]:
                                r_dict["3着_list"].append(h_num)

            # 2. 払戻金テーブルの解析 (ハイフン・矢印の有無で混入を厳格遮断)
            current_type = None
            for tbl in tables:
                tbl_txt = tbl.get_text()
                if "払戻金" not in tbl_txt and "単勝" not in tbl_txt:
                    continue

                for tr in tbl.find_all("tr"):
                    row_txt = tr.get_text(" ", strip=True)

                    if "単勝" in row_txt and "複勝" not in row_txt:
                        current_type = "単勝"
                    elif "複勝" in row_txt:
                        current_type = "複勝"
                    elif "馬複" in row_txt or "馬連" in row_txt:
                        current_type = "馬連"
                    elif "馬単" in row_txt:
                        current_type = "馬単"
                    elif "ワイド" in row_txt:
                        current_type = "ワイド"
                    elif "3連複" in row_txt or "３連複" in row_txt:
                        current_type = "3連複"
                    elif "3連単" in row_txt or "３連単" in row_txt:
                        current_type = "3連単"

                    pay_match = re.search(r"([\d,]+)\s*円", row_txt)
                    if not pay_match:
                        continue
                    p_val = int(pay_match.group(1).replace(",", ""))

                    # ハイフン/矢印を含む組番かどうかのチェック
                    has_connector = ("-" in row_txt) or ("→" in row_txt) or ("-" in row_txt)

                    nums = re.findall(r"\d+", row_txt)

                    # 単勝（コネクタなし＆数字1つ以上）
                    if current_type == "単勝" and not has_connector and len(nums) >= 1:
                        m_str = str(nums[0])
                        r_dict["単勝"][m_str] = p_val

                    # 複勝（コネクタなし＆数字1つ以上 ➔ 枠連等の誤入力を100%遮断）
                    elif current_type == "複勝" and not has_connector and len(nums) >= 1:
                        m_id = int(nums[0])
                        if len(r_dict["複勝"]) < 4 and not any(x["馬番"] == m_id for x in r_dict["複勝"]):
                            r_dict["複勝"].append({"馬番": m_id, "金額": p_val})

                    # 馬連
                    elif current_type == "馬連" and len(nums) >= 2:
                        p1, p2 = int(nums[0]), int(nums[1])
                        k = f"{min(p1, p2)}-{max(p1, p2)}"
                        r_dict["馬連"].append({"組": k, "金額": p_val})

                    # 馬単
                    elif current_type == "馬単" and len(nums) >= 2:
                        k = f"{nums[0]}-{nums[1]}"
                        r_dict["馬単"].append({"組": k, "金額": p_val})

                    # ワイド
                    elif current_type == "ワイド" and len(nums) >= 2:
                        p1, p2 = int(nums[0]), int(nums[1])
                        k = f"{min(p1, p2)}-{max(p1, p2)}"
                        r_dict["ワイド"].append({"組": k, "金額": p_val})

                    # 3連複
                    elif current_type == "3連複" and len(nums) >= 3:
                        s_nums = sorted([int(nums[0]), int(nums[1]), int(nums[2])])
                        k = f"{s_nums[0]}-{s_nums[1]}-{s_nums[2]}"
                        r_dict["3連複"].append({"組": k, "金額": p_val})

                    elif current_type == "3連単" and len(nums) >= 3:
                        k = f"{nums[0]}-{nums[1]}-{nums[2]}"
                        r_dict["3連単"].append({"組": k, "金額": p_val})

        except Exception:
            pass

        r_dict["1着"] = r_dict["1着_list"][0] if r_dict["1着_list"] else None
        r_dict["2着"] = r_dict["2着_list"][0] if r_dict["2着_list"] else None
        r_dict["3着"] = r_dict["3着_list"][0] if r_dict["3着_list"] else None

        parsed_results[f"{r}R"] = r_dict
        progress_bar.progress(r / 12)

    status_text.empty()
    progress_bar.empty()
    return parsed_results


# =========================================================
# 【画面3：更新・分析モード メイン処理】
# =========================================================
def show_screen3():
    st.markdown(
        """
        <style>
            .block-container { padding-top: 2rem !important; }
            .analysis-table { width: 100%; border-collapse: collapse; font-size: 15px; text-align: center; table-layout: fixed; }
            .analysis-table th, .analysis-table td { border: 1px solid #c0c0c0; padding: 5px 2px; }
            .analysis-header { background-color: #e3f2fd; font-weight: bold; }
            .label-col { background-color: #f5f5f5; font-weight: bold; text-align: center; }
            .blue-col { background-color: #e1f5fe !important; font-weight: bold; text-align: center; font-size: 15px !important; }
            .highlight-yellow { background-color: #fff9c4 !important; font-weight: bold; color: #333333; }
            .symbol-cell { font-size: 20px !important; font-weight: bold; }
        </style>
    """,
        unsafe_allow_html=True,
    )

    st.header("📈 更新・分析モード")

    tab_results, tab_ai, tab_master, tab_analysis, tab_winrates, tab_balance = (
        st.tabs(
            [
                "🏁 レース結果登録 ＆ BOX払戻計算",
                "🤖 AI勝敗・消し馬分析",
                "📄 騎手・調教師データ",
                "📊 各分類別実績データ",
                "🎯 レース別勝率データ",
                "💰 4頭BOX収支データ",
            ]
        )
    )

    # ---------------------------------------------------------
    # 【タブ1：レース結果登録 ＆ BOX払戻計算 ＆ 書き込み前確認マスター同期シート】
    # ---------------------------------------------------------
    with tab_results:
        st.subheader("🏁 レース結果取得 ＆ マスター書き込み前確認シート")

        # 💡 日付(1.2) : 開催日次(0.8) : 水分量(0.8) : ボタン(2.2) に幅を最適化
        col_d, col_k, col_m, col_b = st.columns([1.2, 0.8, 0.8, 2.2])
        
        with col_d:
            today_str = datetime.now().strftime("%Y%m%d")
            date_str = st.text_input(
                "対象日付 (YYYYMMDD)", value=today_str, max_chars=8, key="target_date_input_tab1"
            )
            date_clean = re.sub(r"\D", "", date_str)
            
        with col_k:
            kai_code = st.text_input(
                "開催日次", value="04", max_chars=2, key="kai_code_input_tab1"
            )
            
        with col_m:
            moisture_input = st.text_input("馬場水分量", value="1.0%", key="moisture_input_tab1")
            
        with col_b:
            st.markdown(
                "<div style='margin-top:28px;'></div>", unsafe_allow_html=True
            )
            if st.button(
                "🔍 Webから確定結果を取得してプレビュー表示（※まだ保存されません）",
                type="primary",
                use_container_width=True,
                key="fetch_web_btn_tab1"
            ):
                with st.spinner(
                    "全12R確定着順・払戻金・騎手/調教師/実績データの更新候補を計算取得中..."
                ):
                    # 💡 入力された kai_code を引数として渡す
                    fetched_res = fetch_and_parse_full_results_web(date_clean, kai_code=kai_code)
                    if fetched_res:
                        st.session_state["preview_date"] = date_clean
                        st.session_state["preview_moisture"] = moisture_input
                        st.session_state["preview_results"] = fetched_res
                        st.success(
                            "✅ Webから確定結果と更新用データを取得しました！画面下部で更新前データをご確認ください。"
                        )
                        st.rerun()
                    else:
                        st.error("レース結果の自動取得に失敗しました。")

        st.markdown("---")

        # =========================================================
        # 1. 基礎データ＆結果マッピング作成
        # =========================================================
        res_data = st.session_state.get("preview_results") or load_json(
            get_result_path(date_clean)
        )
        today_data = load_json(get_today_path(date_clean))
        pre_data = load_json(get_pre_path(date_clean))

        def safe_get_int(item, key_name, default_val=999):
            if not isinstance(item, dict):
                return default_val
            val = item.get(key_name)
            if val is None or pd.isna(val):
                return default_val
            try:
                return int(float(val))
            except Exception:
                return default_val

        # 着順マッピング results_map (1着=1, 2着=2, 3着=3, 着外=4)
        preview_res_dict = st.session_state.get("preview_results", res_data)
        results_map = {}
        if isinstance(preview_res_dict, dict):
            for r_i in range(1, 13):
                r_k = f"{r_i}R"
                r_obj = preview_res_dict.get(r_k, {})
                results_map[r_i] = {}
                if isinstance(r_obj, dict):
                    for h in r_obj.get("1着_list", []):
                        results_map[r_i][int(h)] = 1
                    for h in r_obj.get("2着_list", []):
                        results_map[r_i][int(h)] = 2
                    for h in r_obj.get("3着_list", []):
                        results_map[r_i][int(h)] = 3

                r_today_list = (
                    today_data.get(r_k, [])
                    if isinstance(today_data, dict)
                    else []
                )
                if isinstance(r_today_list, list):
                    for h_item in r_today_list:
                        h_no = safe_get_int(h_item, "馬番", 0)
                        if h_no > 0 and h_no not in results_map[r_i]:
                            results_map[r_i][h_no] = 4

        # =========================================================
        # 2. 当選金額・払戻詳細シート（メイン表示）
        # =========================================================
        mode_select = st.radio(
            "表示対象モード",
            ["全表示", "事前総合順位 上位4頭BOX", "最終総合順位 上位4頭BOX"],
            horizontal=True,
            key="mode_select_radio_tab1"
        )

        if isinstance(res_data, dict) and res_data:
            st.markdown(
                f"### 📊 『{date_clean}』 当選金額・払戻詳細シート ({mode_select})"
            )
            calc_rows = []
            tot_by_type = {
                "単勝": 0, "複勝1": 0, "複勝2": 0, "複勝3": 0,
                "馬連": 0, "馬単": 0, "ワイド1": 0, "ワイド2": 0, "ワイド3": 0,
                "3連複": 0, "3連単": 0,
            }
            for r in range(1, 13):
                r_k = f"{r}R"
                r_res = res_data.get(r_k, {})
                if not isinstance(r_res, dict):
                    r_res = {}

                t1_list = [int(x) for x in r_res.get("1着_list", []) if str(x).isdigit()]
                t2_list = [int(x) for x in r_res.get("2着_list", []) if str(x).isdigit()]
                t3_list = [int(x) for x in r_res.get("3着_list", []) if str(x).isdigit()]
                top1_str = ", ".join(map(str, t1_list)) or "-"
                top2_str = ", ".join(map(str, t2_list)) or "-"
                top3_str = ", ".join(map(str, t3_list)) or "-"

                box_nums = []
                is_all_display = "全表示" in mode_select
                if not is_all_display:
                    if "事前" in mode_select and isinstance(pre_data, dict):
                        h_list = pre_data.get(r_k, [])
                        sorted_h = sorted(h_list, key=lambda e: safe_get_int(e, "事前順位", 999))
                        box_nums = [safe_get_int(x, "馬番") for x in sorted_h[:4] if safe_get_int(x, "馬番") != 999]
                    elif "最終" in mode_select and isinstance(today_data, dict):
                        h_list = today_data.get(r_k, [])
                        sorted_h = sorted(h_list, key=lambda e: safe_get_int(e, "最終順位", 999))
                        box_nums = [safe_get_int(x, "馬番") for x in sorted_h[:4] if safe_get_int(x, "馬番") != 999]
                box_set = set(box_nums)

                hit_top1 = is_all_display or (len(t1_list) > 0 and any(m in box_set for m in t1_list))
                hit_top2 = is_all_display or (len(t2_list) > 0 and any(m in box_set for m in t2_list))
                hit_top3 = is_all_display or (len(t3_list) > 0 and any(m in box_set for m in t3_list))

                tan_pay = 0
                if hit_top1:
                    raw_tan = r_res.get("単勝", {})
                    if isinstance(raw_tan, dict):
                        tan_pay = sum(raw_tan.values())

                fuku_pays = [0, 0, 0]
                raw_fuku = r_res.get("複勝", [])
                if isinstance(raw_fuku, list):
                    for idx, item in enumerate(raw_fuku):
                        if isinstance(item, dict):
                            m_id = item.get("馬番")
                            p_val = item.get("金額", 0)
                            if is_all_display or (m_id and int(m_id) in box_set):
                                if idx < 3:
                                    fuku_pays[idx] += p_val
                                else:
                                    fuku_pays[2] += p_val

                uren_pay_sum = 0
                if hit_top1 and hit_top2:
                    raw_uren = r_res.get("馬連", [])
                    if isinstance(raw_uren, dict):
                        uren_pay_sum = sum(raw_uren.values())
                    elif isinstance(raw_uren, list):
                        for item in raw_uren:
                            uren_pay_sum += item.get("金額", 0) if isinstance(item, dict) else 0

                utan_pay_sum = 0
                if hit_top1 and hit_top2:
                    raw_utan = r_res.get("馬単", [])
                    if isinstance(raw_utan, dict):
                        utan_pay_sum = sum(raw_utan.values())
                    elif isinstance(raw_utan, list):
                        for item in raw_utan:
                            utan_pay_sum += item.get("金額", 0) if isinstance(item, dict) else 0

                wide_pays = [0, 0, 0]
                raw_wide = r_res.get("ワイド", [])
                items_wide = raw_wide.items() if isinstance(raw_wide, dict) else (raw_wide if isinstance(raw_wide, list) else [])
                for idx, item in enumerate(items_wide):
                    p_val = item[1] if isinstance(item, tuple) else (item.get("金額", 0) if isinstance(item, dict) else 0)
                    k_str = item[0] if isinstance(item, tuple) else (item.get("組", "") if isinstance(item, dict) else "")
                    m_pair = [int(x) for x in re.findall(r"\d+", str(k_str))]
                    if is_all_display or (len(m_pair) >= 2 and all(m in box_set for m in m_pair)):
                        if idx < 3:
                            wide_pays[idx] += p_val
                        else:
                            wide_pays[2] += p_val

                ren3f_pay_sum = 0
                if hit_top1 and hit_top2 and hit_top3:
                    raw_3f = r_res.get("3連複", [])
                    if isinstance(raw_3f, dict):
                        ren3f_pay_sum = sum(raw_3f.values())
                    elif isinstance(raw_3f, list):
                        for item in raw_3f:
                            ren3f_pay_sum += item.get("金額", 0) if isinstance(item, dict) else 0

                ren3t_pay_sum = 0
                if hit_top1 and hit_top2 and hit_top3:
                    raw_3t = r_res.get("3連単", [])
                    if isinstance(raw_3t, dict):
                        ren3t_pay_sum = sum(raw_3t.values())
                    elif isinstance(raw_3t, list):
                        for item in raw_3t:
                            ren3t_pay_sum += item.get("金額", 0) if isinstance(item, dict) else 0

                tot_by_type["単勝"] += tan_pay
                tot_by_type["複勝1"] += fuku_pays[0]
                tot_by_type["複勝2"] += fuku_pays[1]
                tot_by_type["複勝3"] += fuku_pays[2]
                tot_by_type["馬連"] += uren_pay_sum
                tot_by_type["馬単"] += utan_pay_sum
                tot_by_type["ワイド1"] += wide_pays[0]
                tot_by_type["ワイド2"] += wide_pays[1]
                tot_by_type["ワイド3"] += wide_pays[2]
                tot_by_type["3連複"] += ren3f_pay_sum
                tot_by_type["3連単"] += ren3t_pay_sum

                # 💡 新・段階別判定ロジック (1着軸条件)
                # 1着不的中 -> ×
                # 1着のみ的中 -> △
                # 1着&2着的中 -> ○
                # 1~3着全的中 -> ◎
                symbol_disp = "-"
                if "最終" in mode_select and box_set:
                    hit1 = any(m in box_set for m in t1_list) if t1_list else False
                    hit2 = any(m in box_set for m in t2_list) if t2_list else False
                    hit3 = any(m in box_set for m in t3_list) if t3_list else False

                    if not hit1:
                        symbol_disp = "×"
                    elif hit1 and not hit2:
                        symbol_disp = "△"
                    elif hit1 and hit2 and not hit3:
                        symbol_disp = "○"
                    elif hit1 and hit2 and hit3:
                        symbol_disp = "◎"

                calc_rows.append(
                    {
                        "R": r_k,
                        "1着": top1_str,
                        "2着": top2_str,
                        "3着": top3_str,
                        "4頭BOX": ",".join(map(str, box_nums)) if box_nums else "全頭",
                        "判定": symbol_disp,  # 👈 新設：4頭BOXと単勝の間に配置
                        "単勝": f"{tan_pay:,}円",
                        "複勝1": f"{fuku_pays[0]:,}円",
                        "複勝2": f"{fuku_pays[1]:,}円",
                        "複勝3": f"{fuku_pays[2]:,}円",
                        "馬連": f"{uren_pay_sum:,}円",
                        "馬単": f"{utan_pay_sum:,}円",
                        "ワイド1": f"{wide_pays[0]:,}円",
                        "ワイド2": f"{wide_pays[1]:,}円",
                        "ワイド3": f"{wide_pays[2]:,}円",
                        "3連複": f"{ren3f_pay_sum:,}円",
                        "3連単": f"{ren3t_pay_sum:,}円",
                    }
                )

            tot_fuku_sum = tot_by_type["複勝1"] + tot_by_type["複勝2"] + tot_by_type["複勝3"]
            tot_wide_sum = tot_by_type["ワイド1"] + tot_by_type["ワイド2"] + tot_by_type["ワイド3"]

            calc_rows.append(
                {
                    "R": "合計",
                    "1着": "-", "2着": "-", "3着": "-", "4頭BOX": "-",
                    "判定": "-",
                    "単勝": f"{tot_by_type['単勝']:,}円",
                    "複勝1": f"{tot_fuku_sum:,}円",
                    "複勝2": "-", "複勝3": "-",
                    "馬連": f"{tot_by_type['馬連']:,}円",
                    "馬単": f"{tot_by_type['馬単']:,}円",
                    "ワイド1": f"{tot_wide_sum:,}円",
                    "ワイド2": "-", "ワイド3": "-",
                    "3連複": f"{tot_by_type['3連複']:,}円",
                    "3連単": f"{tot_by_type['3連単']:,}円",
                }
            )

            df_disp = pd.DataFrame(calc_rows)

            def style_dataframe(df):
                def highlight_row(row):
                    styles = [""] * len(row)
                    box_str = row.get("4頭BOX", "")
                    if box_str and box_str != "全頭" and box_str != "-":
                        b_nums = [int(x) for x in re.findall(r"\d+", str(box_str))]
                        b_set = set(b_nums)
                        for col_name in ["1着", "2着", "3着"]:
                            if col_name in row:
                                col_idx = df.columns.get_loc(col_name)
                                val_str = str(row[col_name])
                                val_nums = [int(x) for x in re.findall(r"\d+", val_str)]
                                if val_nums and any(n in b_set for n in val_nums):
                                    styles[col_idx] = "background-color: #fff9c4; font-weight: bold;"
                    return styles
                return df.style.apply(highlight_row, axis=1)

            styled_df = style_dataframe(df_disp)
            st.dataframe(
                styled_df, hide_index=True, use_container_width=True, height=500
            )
        else:
            st.info(
                f"※ 『{date_clean}』 の確定結果データはまだ取得されていません。「取得ボタン」を押してください。"
            )

        st.markdown("---")

        # =========================================================
        # 3. 下部：確認画面エリア（1回のみ）
        # =========================================================
        st.subheader("📋 【確認画面】確定結果に伴うマスター更新プレビュー")

        is_preview = "preview_results" in st.session_state
        if is_preview:
            st.warning(
                "⚠️ 現在表示されている数値は【更新プレビュー】です。内容を確認し、問題なければ下の『確定更新』ボタンを押して保存してください。"
            )

        # 3-1. 騎手・調教師成績プレビュー
        col_j, col_t = st.columns(2)
        with col_j:
            st.markdown("#### 🏇 本日の騎手成績一覧（更新根拠）")
            jockey_stats = {}
            for r_idx in range(1, 13):
                r_k = f"{r_idx}R"
                r_data = today_data.get(r_k, []) if isinstance(today_data, dict) else []
                r_res = results_map.get(r_idx, {})
                if isinstance(r_data, list):
                    for item in r_data:
                        j_name = str(item.get("騎手", "")).strip()
                        h_num = safe_get_int(item, "馬番", 0)
                        rank = r_res.get(h_num)
                        if j_name and rank is not None and rank != 999:
                            if j_name not in jockey_stats:
                                jockey_stats[j_name] = [0, 0, 0, 0]
                            if rank == 1:
                                jockey_stats[j_name][0] += 1
                            elif rank == 2:
                                jockey_stats[j_name][1] += 1
                            elif rank == 3:
                                jockey_stats[j_name][2] += 1
                            else:
                                jockey_stats[j_name][3] += 1
            if jockey_stats:
                j_rows = []
                for j_name, s in jockey_stats.items():
                    tot = sum(s)
                    w3 = sum(s[:3])
                    rate = (w3 / tot * 100) if tot > 0 else 0.0
                    j_rows.append(
                        {
                            "騎手名": j_name,
                            "成績 (1-2-3-着外)": f"{s[0]} - {s[1]} - {s[2]} - {s[3]}",
                            "1着": s[0], "3着内": w3, "騎乗数": tot,
                            "本日複勝率": f"{rate:.1f}%",
                        }
                    )
                df_j_today = pd.DataFrame(j_rows).sort_values("1着", ascending=False)
                st.dataframe(df_j_today, hide_index=True, use_container_width=True, height=250)
            else:
                st.info("※ 本日の騎手成績データはまだ集計されていません。")

        with col_t:
            st.markdown("#### 👔 本日の調教師成績一覧（更新根拠）")
            trainer_stats = {}
            for r_idx in range(1, 13):
                r_k = f"{r_idx}R"
                r_data = today_data.get(r_k, []) if isinstance(today_data, dict) else []
                r_res = results_map.get(r_idx, {})
                if isinstance(r_data, list):
                    for item in r_data:
                        t_name = str(item.get("調教師", "")).strip()
                        h_num = safe_get_int(item, "馬番", 0)
                        rank = r_res.get(h_num)
                        if t_name and rank is not None and rank != 999:
                            if t_name not in trainer_stats:
                                trainer_stats[t_name] = [0, 0, 0, 0]
                            if rank == 1:
                                trainer_stats[t_name][0] += 1
                            elif rank == 2:
                                trainer_stats[t_name][1] += 1
                            elif rank == 3:
                                trainer_stats[t_name][2] += 1
                            else:
                                trainer_stats[t_name][3] += 1
            if trainer_stats:
                t_rows = []
                for t_name, s in trainer_stats.items():
                    tot = sum(s)
                    w3 = sum(s[:3])
                    rate = (w3 / tot * 100) if tot > 0 else 0.0
                    t_rows.append(
                        {
                            "調教師名": t_name,
                            "成績 (1-2-3-着外)": f"{s[0]} - {s[1]} - {s[2]} - {s[3]}",
                            "1着": s[0], "3着内": w3, "出走数": tot,
                            "本日複勝率": f"{rate:.1f}%",
                        }
                    )
                df_t_today = pd.DataFrame(t_rows).sort_values("1着", ascending=False)
                st.dataframe(df_t_today, hide_index=True, use_container_width=True, height=250)
            else:
                st.info("※ 本日の調教師成績データはまだ集計されていません。")

        st.markdown("---")

        # 3-2. 本日の分類別成績サマリー
        m_val_float = 1.0
        try:
            m_val_float = float(re.sub(r"[^\d.]", "", str(moisture_input or "1.0")))
        except Exception:
            m_val_float = 1.0

        target_water_key = get_moisture_key(m_val_float)

        st.markdown(f"#### 📊 本日の分類別実績サマリー（対象水分区分: **{target_water_key}**）")

        pre_ability_map = {}
        if isinstance(pre_data, dict):
            for r_k, h_list in pre_data.items():
                if isinstance(h_list, list):
                    pre_ability_map[r_k] = {}
                    for h in h_list:
                        if isinstance(h, dict):
                            h_no = safe_get_int(h, "馬番", 0)
                            if h_no > 0:
                                pre_ability_map[r_k][h_no] = {
                                    "先行力": safe_get_int(h, "先行力", safe_get_int(h, "先行", 3)),
                                    "障害力": safe_get_int(h, "障害力", safe_get_int(h, "障害", 3)),
                                    "末脚力": safe_get_int(h, "末脚力", safe_get_int(h, "末脚", 3)),
                                    "軽馬場": safe_get_int(h, "軽馬場", 3),
                                    "重馬場": safe_get_int(h, "重馬場", 3),
                                }

        flat_horse_results = []
        for r_idx in range(1, 13):
            r_k = f"{r_idx}R"
            r_data = today_data.get(r_k, []) if isinstance(today_data, dict) else []
            r_res = results_map.get(r_idx, {})
            r_pre_ab = pre_ability_map.get(r_k, {})

            if isinstance(r_data, list):
                for item in r_data:
                    h_num = safe_get_int(item, "馬番", 0)
                    h_name = str(item.get("馬名", "")).strip()
                    rank = r_res.get(h_num)

                    if h_name and rank is not None and rank != 999:
                        is_w3 = 1 if rank in [1, 2, 3] else 0
                        ab_info = r_pre_ab.get(h_num, {})
                        flat_horse_results.append(
                            {
                                "R": r_idx,
                                "is_zenhan": (r_idx <= 6),
                                "脚質": str(item.get("脚質", "先行")).strip(),
                                "オッズ記号": str(item.get("オッズ記号", "×")).strip(),
                                "馬体重増減": get_weight_key(item.get("増減", 0)),
                                "先行力": ab_info.get("先行力", 3),
                                "障害力": ab_info.get("障害力", 3),
                                "末脚力": ab_info.get("末脚力", 3),
                                "軽馬場": ab_info.get("軽馬場", 3),
                                "重馬場": ab_info.get("重馬場", 3),
                                "複勝": is_w3,
                            }
                        )

        def build_summary_rows(data_list, key_name, categories):
            rows = []
            for cat in categories:
                items = [x for x in data_list if x.get(key_name) == cat]
                tot = len(items)
                w3 = sum(x["複勝"] for x in items)
                rate = (w3 / tot * 100) if tot > 0 else 0.0
                rows.append({key_name: cat, "出走": tot, "複勝数": w3, "複勝率": f"{rate:.1f}%"})
            return pd.DataFrame(rows)

        col_s1, col_s2, col_s3, col_s4 = st.columns(4)

        with col_s1:
            st.markdown(f"**■ 脚質別 ({target_water_key})**")
            styles = ["逃げ", "先行", "差し", "追込"]
            st.caption("🔻 前半(1~6R)")
            st.dataframe(build_summary_rows([x for x in flat_horse_results if x["is_zenhan"]], "脚質", styles), hide_index=True, use_container_width=True, height=160)
            st.caption("🔻 後半(7~12R)")
            st.dataframe(build_summary_rows([x for x in flat_horse_results if not x["is_zenhan"]], "脚質", styles), hide_index=True, use_container_width=True, height=160)

        with col_s2:
            st.markdown(f"**■ オッズ印別 ({target_water_key})**")
            odds_list = ["◎", "○", "▲", "△", "×"]
            st.caption("🔻 前半(1~6R)")
            st.dataframe(build_summary_rows([x for x in flat_horse_results if x["is_zenhan"]], "オッズ記号", odds_list), hide_index=True, use_container_width=True, height=180)
            st.caption("🔻 後半(7~12R)")
            st.dataframe(build_summary_rows([x for x in flat_horse_results if not x["is_zenhan"]], "オッズ記号", odds_list), hide_index=True, use_container_width=True, height=180)

        with col_s3:
            st.markdown(f"**■ 馬体重増減別 ({target_water_key})**")
            weights = ["+20以上", "+10台", "±1桁", "-2桁"]
            st.caption("🔻 前半(1~6R)")
            st.dataframe(build_summary_rows([x for x in flat_horse_results if x["is_zenhan"]], "馬体重増減", weights), hide_index=True, use_container_width=True, height=160)
            st.caption("🔻 後半(7~12R)")
            st.dataframe(build_summary_rows([x for x in flat_horse_results if not x["is_zenhan"]], "馬体重増減", weights), hide_index=True, use_container_width=True, height=160)

        with col_s4:
            st.markdown("**■ 能力5指標別 (全R一括・1~5)**")
            ab_rows = []
            ab_names = ["先行力", "障害力", "末脚力", "軽馬場", "重馬場"]
            for ab_k in ab_names:
                for lv in range(1, 6):
                    items = [x for x in flat_horse_results if x.get(ab_k) == lv]
                    tot = len(items)
                    w3 = sum(x["複勝"] for x in items)
                    rate = (w3 / tot * 100) if tot > 0 else 0.0
                    ab_rows.append({"指標": ab_k, "Lv": f"{lv}", "出走": tot, "複勝数": w3, "複勝率": f"{rate:.1f}%"})
            st.dataframe(pd.DataFrame(ab_rows), hide_index=True, use_container_width=True, height=360)

        st.markdown("---")

        # 3-3. 2段階・確定処理ボタン (横並び配置)
        st.subheader("💾 確定データ保存 ＆ マスター更新実行")

        col_b1, col_b2 = st.columns(2)

        with col_b1:
            if st.button(
                "📄 ① 確定結果(result_data)のみ保存する",
                use_container_width=True,
                key="save_result_only_btn",
            ):
                p_date = st.session_state.get("preview_date", date_clean)
                p_res = st.session_state.get("preview_results") or res_data
                if p_res:
                    save_json(get_result_path(p_date), p_res)
                    st.success(f"✅ 『result_data_{p_date}.json』 に確定結果を保存しました！（※マスターはまだ更新されていません）")
                else:
                    st.error("保存する確定結果データがありません。")

        with col_b2:
            if st.button(
                "🚀 ② 各種マスターJSONを一括確定更新する",
                type="primary",
                use_container_width=True,
                key="update_all_masters_btn",
            ):
                p_date = st.session_state.get("preview_date", date_clean)
                p_moisture = st.session_state.get("preview_moisture", moisture_input)
                p_res = st.session_state.get("preview_results") or res_data

                if not os.path.exists(get_result_path(p_date)) and p_res:
                    save_json(get_result_path(p_date), p_res)

                with st.spinner("全マスター(騎手・調教師・実績・勝率・収支)へ確定反映中..."):
                    success, msg = update_all_data_from_results(p_date, p_moisture)
                    if success:
                        if "preview_results" in st.session_state:
                            del st.session_state["preview_results"]
                        if "preview_date" in st.session_state:
                            del st.session_state["preview_date"]
                        if "preview_moisture" in st.session_state:
                            del st.session_state["preview_moisture"]
                        st.success(f"🎉 確定更新完了！ {msg}")
                        st.rerun()
                    else:
                        st.warning(f"⚠️ {msg}")
                        
    # ---------------------------------------------------------
    # 【ブロック2：タブ2 AI勝敗・消し馬分析（動的集計版）】
    # ---------------------------------------------------------
    with tab_ai:
        st.subheader("🤖 AIデータ分析（累積マスタ動的算出エンジン）")

        # 新3分割JSONから安全に取得
        cur_jt = load_json(PATH_JT)
        j_data = cur_jt.get("jockey", {}) if isinstance(cur_jt, dict) else {}
        
        ability_data = load_json(PATH_ABIL)
        
        # --- 動的集計1：騎手複勝率 35% 以上の平均複勝率をリアルタイム算出 ---
        high_j_w3 = sum(
            [
                v.get("3着内", 0)
                for k, v in j_data.items()
                if isinstance(v, dict) and v.get("複勝率", 0) >= 0.35
            ]
        )
        high_j_tot = sum(
            [
                v.get("総数", 0)
                for k, v in j_data.items()
                if isinstance(v, dict) and v.get("複勝率", 0) >= 0.35
            ]
        )
        high_j_rate = (
            (high_j_w3 / high_j_tot * 100) if high_j_tot > 0 else 0.0
        )

        # --- 動的集計2：先行力最高評価(5)の平均複勝率をリアルタイム算出 ---
        senkou5 = ability_data.get("先行力", {}).get("5", {})
        senkou5_tot = senkou5.get("総数", 0)
        senkou5_w3 = senkou5.get("着内", senkou5.get("3着内", 0))
        senkou5_rate = (
            (senkou5_w3 / senkou5_tot * 100) if senkou5_tot > 0 else 0.0
        )

        col_ai1, col_ai2 = st.columns([1, 1])

        with col_ai1:
            st.markdown("#### ❌ AI検出：危険な消し馬（切り条件）")
            st.error("【条件1】近走評価 1〜2 ＆ オッズ記号 ×（30倍以上）")
            st.caption(
                "➔ 実走オッズ30倍以上の馬は、直近累積データにおいて消し推奨。"
            )
            st.error(
                "【条件2】前走クラス差 -0.2 ＆ 馬体重減 -2桁（-10kg以上）"
            )
            st.caption(
                "➔ クラス上位挑戦かつ大幅馬体重減の馬は、実績データ上消し推奨。"
            )

        with col_ai2:
            st.markdown("#### 🎯 AI検出：高確率・鉄板軸馬（動的計算結果）")
            st.success(
                "【条件1】事前順位 1位 ＆ 複勝率 35% 以上の主要騎手"
            )
            st.markdown(
                f"➔ 該当騎手の最新累積成績：<b>{high_j_tot:,}</b> 出走中 <b>{high_j_w3:,}</b> 回3着内（リアルタイム複勝率: <span style='color:#2e7d32; font-weight:bold;'>{high_j_rate:.1f}%</span>）",
                unsafe_allow_html=True,
            )

            st.success("【条件2】能力評価「先行力 5」該当馬")
            st.markdown(
                f"➔ 先行力5評価の最新累積成績：<b>{senkou5_tot:,}</b> 出走中 <b>{senkou5_w3:,}</b> 回3着内（リアルタイム複勝率: <span style='color:#2e7d32; font-weight:bold;'>{senkou5_rate:.1f}%</span>）",
                unsafe_allow_html=True,
            )

    # ---------------------------------------------------------
    # 【ブロック2：タブ3 騎手・調教師データ（RAW全項目表示版）】
    # ---------------------------------------------------------
    with tab_master:
        st.subheader("📄 騎手・調教師マスタデータ（master_jt.json）")
        cur_jt = load_json(PATH_JT)
        cur_j = cur_jt.get("jockey", {})
        cur_t = cur_jt.get("trainer", {})

        # RAWから全項目を動的取得してデータフレーム化する関数
        def build_master_df(data_dict, key_name):
            rows = []
            for k, v in data_dict.items():
                if isinstance(v, dict):
                    rows.append({
                        key_name: k,
                        "1着": v.get("1着", 0), "2着": v.get("2着", 0), "3着": v.get("3着", 0), "4着以下": v.get("4着以下", 0),
                        "総数": v.get("総数", 0), "3着内": v.get("3着内", 0),
                        "勝率": f"{v.get('勝率', 0.0):.3f}", "連対率": f"{v.get('連対率', 0.0):.3f}", "複勝率": f"{v.get('複勝率', 0.0):.3f}",
                        "通算勝数": v.get("通算勝数", 0),
                    })
            df = pd.DataFrame(rows)
            return df.sort_values(by="1着", ascending=False) if not df.empty else df

        df_j = build_master_df(cur_j, "騎手名")
        df_t = build_master_df(cur_t, "調教師名")

        st.markdown(f"### 🏇 登録騎手データ ({len(df_j)}名)")
        st.dataframe(df_j, hide_index=True, use_container_width=True, height=350)
        st.markdown("---")
        st.markdown(f"### 👔 登録調教師データ ({len(df_t)}名)")
        st.dataframe(df_t, hide_index=True, use_container_width=True, height=350)
            
    # ---------------------------------------------------------
    # 【ブロック3：タブ4 各分類別実績データ (新3分割JSON対応版)】
    # ---------------------------------------------------------
    with tab_analysis:
        st.subheader("📊 各分類別実績データ（傾向分析マスタ）")
        
        # 新ファイルからそれぞれ読み込み
        master_cond = load_json(PATH_COND)
        master_abil = load_json(PATH_ABIL)

        if not master_cond or not master_abil:
            st.warning(
                "⚠️ マスタファイル（master_cond.json / master_abil.json）が読み込めません。"
            )
        else:
            # 1. 前半(1~6R) vs 後半(7~12R) の比較表示
            col_zen, col_kou = st.columns(2)

            def build_compact_html(section_title, section_dict):
                html = f"<div style='border:1px solid #1565c0; border-radius:5px; padding:8px; margin-bottom:15px; background-color:#f8f9fa;'>"
                html += f"<h4 style='text-align:center; color:#1565c0; margin-top:0px; margin-bottom:8px;'>{section_title}</h4>"

                categories = ["脚質", "オッズ", "馬体重"]
                # 💡 水分ヘッダーを新しい日本語表記に統一
                water_headers = ["極重", "稍重", "普通", "稍軽", "極軽"]

                for cat in categories:
                    html += f"<table class='analysis-table' style='table-layout:fixed; width:100%; margin-bottom:10px; font-size:13px;'>"
                    html += f"<thead><tr class='analysis-header'><th style='width:25%;'>{cat}</th>"
                    for w in water_headers:
                        html += f"<th>{w}</th>"
                    html += "</tr></thead><tbody>"

                    # 💡 水分区分ごとのデータを集計・抽出
                    cat_data = {}
                    for w in water_headers:
                        nodes = section_dict.get(w, {}).get(cat, {})
                        for r_key, r_val in nodes.items():
                            rate = r_val.get("複勝率", 0.0) if isinstance(r_val, dict) else float(r_val)
                            cat_data.setdefault(r_key, {})[w] = rate

                    for row_key, rates in cat_data.items():
                        html += f"<tr><td class='label-col'>{row_key}</td>"
                        for w in water_headers:
                            rate = rates.get(w, 0.0)
                            html += f"<td>{rate:.3f}</td>"
                        html += "</tr>"
                    html += "</tbody></table>"
                html += "</div>"
                return html

            with col_zen:
                st.markdown(
                    build_compact_html(
                        "前半(1~6R)", master_cond.get("前半(1~6R)", {})
                    ),
                    unsafe_allow_html=True,
                )

            with col_kou:
                st.markdown(
                    build_compact_html(
                        "後半(7~12R)", master_cond.get("後半(7~12R)", {})
                    ),
                    unsafe_allow_html=True,
                )

            st.markdown("---")

            # 2. 能力5指標 サマリー表示
            st.markdown("### 🌟 能力5指標 評価別実績サマリー")

            abilities = ["先行力", "障害力", "末脚力", "軽馬場", "重馬場"]
            html_ab = "<div style='overflow-x:auto;'><table class='analysis-table' style='table-layout:fixed; min-width:1000px; font-size:13px;'>"

            # 最上段：タイトル行
            html_ab += "<thead><tr class='analysis-header'>"
            html_ab += "<th style='width:8%;' class='label-col'>項目</th>"
            for ab in abilities:
                html_ab += f"<th colspan='5' style='background-color:#bbdefb; color:#0d47a1; font-weight:bold;'>{ab}総数</th>"
            html_ab += "</tr>"

            # 2段目：指数値 (1 2 3 4 5)
            html_ab += "<tr class='analysis-header'><td class='label-col'>指数値</td>"
            for ab in abilities:
                for lv in range(1, 6):
                    html_ab += f"<td style='background-color:#e3f2fd;'><b>{lv}</b></td>"
            html_ab += "</tr></thead><tbody>"

            # 3段目：複勝率
            html_ab += "<tr><td class='label-col'>複勝率</td>"
            for ab in abilities:
                for lv in range(1, 6):
                    node = master_abil.get(ab, {}).get(str(lv), {})
                    rate = float(node.get("複勝率", 0.0))
                    html_ab += f"<td style='font-weight:bold; color:#1b5e20;'>{rate:.3f}</td>"
            html_ab += "</tr>"

            # 4段目：総数
            html_ab += "<tr><td class='label-col'>総数</td>"
            for ab in abilities:
                for lv in range(1, 6):
                    tot = master_abil.get(ab, {}).get(str(lv), {}).get("総数", 0)
                    html_ab += f"<td>{tot:,}</td>"
            html_ab += "</tr>"

            # 5段目：複勝
            html_ab += "<tr><td class='label-col'>複勝</td>"
            for ab in abilities:
                for lv in range(1, 6):
                    w3 = master_abil.get(ab, {}).get(str(lv), {}).get("複勝", 0)
                    html_ab += f"<td>{w3:,}</td>"
            html_ab += "</tr>"

            html_ab += "</tbody></table></div>"
            st.markdown(html_ab, unsafe_allow_html=True)
            
    # ---------------------------------------------------------
    # 【ブロック3：タブ5 レース別勝率データ (基準値判定・縦軸同期版)】
    # ---------------------------------------------------------
    with tab_winrates:
        st.subheader("🎯 レース別勝率データ ＆ 累積的中率集計（基準値判定版）")
        winrate_hist = load_json(PATH_HIST_WINRATES)

        total_days = len(winrate_hist) if winrate_hist else 0

        # 1R〜12R の確率算出 (単勝: △○◎ / ２連: ○◎ / ３連: ◎)
        calc_rates = {
            r: {"単勝": 0.0, "2連": 0.0, "3連": 0.0} for r in range(1, 13)
        }

        if total_days > 0:
            for r in range(1, 13):
                r_key = f"{r}R"
                
                # 💡 Excelの COUNTA (◎, ○, △, ▲, × の有効データが存在する件数) を取得
                valid_r_data = [
                    d.get(r_key) for d in winrate_hist 
                    if d.get(r_key) in ["◎", "○", "△", "▲", "×"]
                ]
                r_counta = len(valid_r_data)

                if r_counta > 0:
                    tan_hits = sum(1 for m in valid_r_data if m in ["◎", "○", "△", "▲"])
                    ren2_hits = sum(1 for m in valid_r_data if m in ["◎", "○"])
                    ren3_hits = sum(1 for m in valid_r_data if m in ["◎"])

                    calc_rates[r]["単勝"] = round(tan_hits / r_counta, 3)
                    calc_rates[r]["2連"] = round(ren2_hits / r_counta, 3)
                    calc_rates[r]["3連"] = round(ren3_hits / r_counta, 3)
                else:
                    calc_rates[r]["単勝"] = 0.0
                    calc_rates[r]["2連"] = 0.0
                    calc_rates[r]["3連"] = 0.0

        st.markdown(
            f"#### 📈 【1R〜12R レース別累積勝率サマリー】 (累積データ数: <b>{total_days}</b> 日分)",
            unsafe_allow_html=True,
        )

        html_sum_rates = """
        <table class='analysis-table' style='table-layout:fixed; width:100%;'>
            <thead>
                <tr class='analysis-header'>
                    <th style='width:12%;'>勝率区分</th>
                    <th style='width:8%;' class='blue-col'>基準値</th>
                    <th style='width:6.6%;'>1R</th><th style='width:6.6%;'>2R</th><th style='width:6.6%;'>3R</th><th style='width:6.6%;'>4R</th><th style='width:6.6%;'>5R</th><th style='width:6.6%;'>6R</th>
                    <th style='width:6.6%;'>7R</th><th style='width:6.6%;'>8R</th><th style='width:6.6%;'>9R</th><th style='width:6.6%;'>10R</th><th style='width:6.6%;'>11R</th><th style='width:6.6%;'>12R</th>
                </tr>
            </thead>
            <tbody>
        """

        rate_configs = [
            ("単勝勝率", "単勝", 0.750),
            ("２連勝率", "2連", 0.500),
            ("３連勝率", "3連", 0.250),
        ]

        for k_label, short_k, base_val in rate_configs:
            html_sum_rates += f"<tr><td class='label-col'>{k_label}</td>"
            html_sum_rates += f"<td class='blue-col'>{base_val:.3f}</td>"

            for r in range(1, 13):
                val = calc_rates[r][short_k]
                is_over = val > base_val
                bg_cls = "class='highlight-yellow'" if is_over else ""
                html_sum_rates += f"<td {bg_cls}>{val:.3f}</td>"
            html_sum_rates += "</tr>"

        html_sum_rates += (
            "</tbody></table><div style='margin-bottom:20px;'></div>"
        )
        st.markdown(html_sum_rates, unsafe_allow_html=True)

        st.markdown("#### 📜 日別的中マーク履歴")
        if winrate_hist:
            html_w_hist = """
            <table class='analysis-table' style='table-layout:fixed; width:100%;'>
                <thead>
                    <tr class='analysis-header'>
                        <th style='width:12%;' class='label-col'>日付</th>
                        <th style='width:8%;' class='blue-col'>水分</th>
                        <th style='width:6.6%;'>1R</th><th style='width:6.6%;'>2R</th><th style='width:6.6%;'>3R</th><th style='width:6.6%;'>4R</th><th style='width:6.6%;'>5R</th><th style='width:6.6%;'>6R</th>
                        <th style='width:6.6%;'>7R</th><th style='width:6.6%;'>8R</th><th style='width:6.6%;'>9R</th><th style='width:6.6%;'>10R</th><th style='width:6.6%;'>11R</th><th style='width:6.6%;'>12R</th>
                    </tr>
                </thead>
                <tbody>
            """

            for row in winrate_hist:
                html_w_hist += f"<tr><td class='label-col'>{row.get('日付','-')}</td><td class='blue-col'>{row.get('水分','-')}</td>"
                for r in range(1, 13):
                    sym = row.get(f"{r}R", "-")
                    if sym in ["◎", "○", "▲", "△"]:
                        html_w_hist += f"<td class='symbol-cell' style='color:#2e7d32;'>{sym}</td>"
                    elif sym in ["×", "X"]:
                        html_w_hist += f"<td class='symbol-cell' style='color:#c62828;'>{sym}</td>"
                    else:
                        html_w_hist += "<td style='color:#9e9e9e;'>-</td>"
                html_w_hist += "</tr>"
            html_w_hist += "</tbody></table>"
            st.markdown(html_w_hist, unsafe_allow_html=True)
        else:
            st.info("※ 日別の的中履歴データがまだありません。")

    # ---------------------------------------------------------
    # 【ブロック3：タブ6 4頭BOX累計損益管理表】
    # ---------------------------------------------------------
    with tab_balance:
        st.subheader("💰 4頭BOX 累計年間損益管理表")
        balance_hist = load_json(PATH_HIST_BALANCE)

        COSTS = {
            "単勝": 4800,
            "複勝": 4800,
            "馬連": 7200,
            "馬単": 14400,
            "ワイド": 7200,
            "3連複": 4800,
            "3连単": 28800,
            "3連単": 28800,
        }
        T_KEYS = [
            "単勝",
            "複勝",
            "馬連",
            "馬単",
            "ワイド",
            "3連複",
            "3連単",
        ]

        st.markdown("#### 📊 【全期間 累計損益サマリー（券種別）】")
        total_days = len(balance_hist) if balance_hist else 0

        summary_data = {
            t: {
                "黒字回数": 0,
                "費用": total_days * COSTS[t],
                "収益": 0,
                "差額": 0,
            }
            for t in T_KEYS
        }

        for row in balance_hist:
            for t in T_KEYS:
                payout = int(row.get(t, 0) or 0)
                cost = COSTS[t]
                summary_data[t]["収益"] += payout
                if payout >= cost:
                    summary_data[t]["黒字回数"] += 1

        for t in T_KEYS:
            summary_data[t]["差額"] = (
                summary_data[t]["収益"] - summary_data[t]["費用"]
            )

        html_sum_bal = "<table class='analysis-table'><thead><tr class='analysis-header'><th style='width:16%;'>項目</th>"
        for t in T_KEYS:
            html_sum_bal += f"<th>{t}</th>"
        html_sum_bal += "</tr></thead><tbody>"

        # 黒字回数行
        html_sum_bal += "<tr><td class='label-col'>黒字回数</td>"
        for t in T_KEYS:
            html_sum_bal += f"<td><b>{summary_data[t]['黒字回数']}</b> / {total_days}日</td>"
        html_sum_bal += "</tr>"

        # 費用行
        html_sum_bal += "<tr><td class='label-col'>費用</td>"
        for t in T_KEYS:
            html_sum_bal += f"<td>{summary_data[t]['費用']:,}円</td>"
        html_sum_bal += "</tr>"

        # 収益行
        html_sum_bal += "<tr><td class='label-col'>収益</td>"
        for t in T_KEYS:
            html_sum_bal += f"<td>{summary_data[t]['収益']:,}円</td>"
        html_sum_bal += "</tr>"

        # 差額行
        html_sum_bal += "<tr><td class='label-col'>差額</td>"
        for t in T_KEYS:
            diff = summary_data[t]["差額"]
            cls = (
                "style='color:#c62828; font-weight:bold;'"
                if diff < 0
                else "style='color:#2e7d32; font-weight:bold;'"
            )
            html_sum_bal += f"<td {cls}>{diff:,}円</td>"
        html_sum_bal += "</tr>"

        html_sum_bal += (
            "</tbody></table><div style='margin-bottom:20px;'></div>"
        )
        st.markdown(html_sum_bal, unsafe_allow_html=True)

        st.markdown("#### 📜 日別収支明細 (最新順)")
        if balance_hist:
            html_b_hist = "<table class='analysis-table'><tr class='analysis-header'><th style='width:16%;' class='label-col'>日付</th>"
            for t in T_KEYS:
                html_b_hist += f"<th>{t}</th>"
            html_b_hist += "</tr>"

            for row in balance_hist:
                d_label = row.get("日付", "-")
                html_b_hist += f"<tr><td class='label-col'>{d_label}</td>"
                for t_k in T_KEYS:
                    val = int(row.get(t_k, 0) or 0)
                    cost = COSTS.get(t_k, 0)
                    cls = (
                        "class='highlight-yellow'"
                        if val >= cost
                        else "style='color:#757575;'"
                    )
                    html_b_hist += f"<td {cls}>{val:,}円</td>"
                html_b_hist += "</tr>"
            html_b_hist += "</table>"
            st.markdown(html_b_hist, unsafe_allow_html=True)
        else:
            st.info("※ 日別の収支明細データがまだありません。")