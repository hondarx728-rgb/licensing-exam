import streamlit as st
import pandas as pd
import glob
import json
import re
import time
from google import genai
from google.genai import types

st.set_page_config(page_title="弱点特化・資格演習アプリ", layout="wide")

# --- APIキーの設定 ---
api_key = st.secrets.get("GEMINI_API_KEY", "")
if not api_key:
    api_key = st.sidebar.text_input("Gemini API Key", type="password")

client = genai.Client(api_key=api_key) if api_key else None

fast_config = types.GenerateContentConfig(
    max_output_tokens=1500,
    temperature=0.2
)

LIGHT_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.6-flash"
]

def request_with_fallback(prompt, config):
    last_error = None
    for model_name in LIGHT_MODELS:
        try:
            res = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )
            if res and res.text:
                return res.text
        except Exception as e:
            last_error = e
            time.sleep(0.5)
            continue
    raise last_error

# セッション状態の初期化
if "quiz_data" not in st.session_state:
    st.session_state.quiz_data = None
if "answered" not in st.session_state:
    st.session_state.answered = False

st.title("📝 弱点集中・演習アプリ")

# --- 1. CSV読み込み ---
csv_files = glob.glob("*.csv")
df = None

if csv_files:
    target_csv = csv_files[0]
    try:
        df = pd.read_csv(target_csv, encoding="utf-8")
    except Exception:
        try:
            df = pd.read_csv(target_csv, encoding="cp932")
        except Exception as e:
            st.error(f"CSV読み込みエラー: {e}")

if df is not None:
    df.columns = [str(c).strip().replace("\n", "").replace("\r", "") for c in df.columns]
    
    seigo_col = None
    for col in df.columns:
        if any(k in str(col) for k in ["正誤", "判定", "結果", "成否", "正解"]):
            seigo_col = col
            break
    if not seigo_col:
        for col in df.columns:
            if df[col].astype(str).str.contains("×|不正解|ミス|バツ|誤", na=False).any():
                seigo_col = col
                break
            
    if seigo_col:
        weak_records = df[df[seigo_col].astype(str).str.contains("×|不正解|ミス|バツ|誤", na=False)]
        st.sidebar.success(f"正誤データ自動読込完了（判定列: {seigo_col} / 苦手: {len(weak_records)} 件）")
    else:
        st.sidebar.warning("正誤列が見つかりません。全データから出題します。")
        weak_records = df

    # --- 2. 出題生成ボタン ---
    if st.button("🚨 苦手論点から新しい問題を生成する"):
        if not client or not api_key:
            st.error("APIキーが設定されていません。StreamlitのSecrets設定を確認してください。")
        elif weak_records.empty:
            st.warning("出題対象のデータがありません。")
        else:
            with st.spinner("出題を作成中（数秒）..."):
                target = weak_records.sample(1).iloc[0]
                target_dict = target.to_dict()
                log_text = "\n".join([f"- {k}: {v}" for k, v in target_dict.items() if pd.notna(v)])
                
                prompt = f"""
土地家屋調査士試験の択一問題を1問作成してください。
必ず以下のJSONフォーマットのみを出力してください（Markdownのバッククォート不要）。

【弱点データ】
{log_text}

【出力JSONフォーマット】
{{
  "question": "問題文および肢1〜5の記述",
  "correct_answer": 2,
  "explanation": "各肢の解説、条文根拠、ミスを防ぐアドバイス、確認すべき参考テキスト論点"
}}
※ "correct_answer" は正解の肢番号（1〜5の半角数値）を入れてください。
"""
                try:
                    res_raw = request_with_fallback(prompt, fast_config)
                    # JSON部分を抽出
                    json_str = res_raw.strip()
                    if "```" in json_str:
                        json_str = re.search(r"\{.*\}", json_str, re.DOTALL).group(0)
                    quiz_json = json.loads(json_str)
                    
                    st.session_state.quiz_data = quiz_json
                    st.session_state.target_info = target_dict
                    st.session_state.answered = False
                except Exception as e:
                    st.error(f"問題生成エラー: {e}")
else:
    st.warning("リポジトリ内にCSVファイルが見つかりません。")

# --- 3. 出題と解答 ---
if st.session_state.quiz_data:
    st.markdown("### 📋 演習問題")
    field = st.session_state.target_info.get('主な出題分野', st.session_state.target_info.get('種別', ''))
    year = st.session_state.target_info.get('年度', '')
    st.info(f"対象論点: {field}（関連: {year}）")
    
    st.markdown(st.session_state.quiz_data.get("question", ""))
    st.write("---")
    
    # スマホで押しやすいラジオボタン選択
    user_choice = st.radio("解答を選択してください:", [1, 2, 3, 4, 5], format_func=lambda x: f"肢 {x}", horizontal=True)
    
    if st.button("解答を確定する"):
        st.session_state.answered = True
        st.session_state.user_choice = user_choice

# --- 4. 結果判定と解説表示 ---
if st.session_state.quiz_data and st.session_state.answered:
    correct = int(st.session_state.quiz_data.get("correct_answer", 0))
    chosen = st.session_state.user_choice
    
    st.write("---")
    # プログラムで確実に成否を判定
    if chosen == correct:
        st.success(f"🎉 **正解です！（あなたの解答: 肢{chosen} / 正解: 肢{correct}）**")
    else:
        st.error(f"❌ **不正解です…（あなたの解答: 肢{chosen} / 正解: 肢{correct}）**")
        
    st.markdown("### 📖 解説・着眼点アドバイス")
    st.write(st.session_state.quiz_data.get("explanation", ""))
