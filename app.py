import streamlit as st
import pandas as pd
import glob
import time
from google import genai
from google.genai import types

st.set_page_config(page_title="弱点特化・資格演習アプリ", layout="wide")

# --- APIキーの設定（Streamlit Secrets から安全に取得） ---
api_key = st.secrets.get("GEMINI_API_KEY", "")

if not api_key:
    api_key = st.sidebar.text_input("Gemini API Key", type="password")

client = genai.Client(api_key=api_key) if api_key else None

# 高速応答用の設定（思考プロセスを最小化し、最大トークンを制限）
fast_question_config = types.GenerateContentConfig(
    max_output_tokens=1000,
    thinking_config=types.ThinkingConfig(thinking_budget=0)
)

fast_explanation_config = types.GenerateContentConfig(
    max_output_tokens=1500,
    thinking_config=types.ThinkingConfig(thinking_budget=0)
)

def generate_fast(prompt, config):
    """高速にテキストを生成する関数"""
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=config
            )
            return response.text
        except Exception as e:
            if attempt == 0 and "503" in str(e):
                time.sleep(1)
                continue
            raise e

if "current_question" not in st.session_state:
    st.session_state.current_question = None
if "explanation" not in st.session_state:
    st.session_state.explanation = None

st.title("📝 弱点集中・演習アプリ")

# --- 1. CSVの自動検出・読み込み ---
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
        st.sidebar.success(f"正誤データを自動読込完了（判定列: {seigo_col} / 苦手: {len(weak_records)} 件）")
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
            with st.spinner("出題作成中（約5〜10秒）..."):
                target = weak_records.sample(1).iloc[0]
                target_dict = target.to_dict()
                log_text = "\n".join([f"- {k}: {v}" for k, v in target_dict.items() if pd.notna(v)])
                
                prompt = f"""
国家資格（土地家屋調査士）の択一問題を1問作成してください。

【弱点データ】
{log_text}

【要件】
1. 生徒がつまずいた論点を突いた、本試験レベルのひっかけを含む問題（5肢択一または正誤判定）。
2. 出力は「問題文と選択肢のみ」。正解や解説は一切含めないこと。
3. 簡潔かつ迅速に出力してください。
"""
                try:
                    question_text = generate_fast(prompt, fast_question_config)
                    st.session_state.current_question = question_text
                    st.session_state.target_info = target_dict
                    st.session_state.explanation = None
                except Exception as e:
                    st.error(f"問題生成エラー: {e}")
else:
    st.warning("リポジトリ内にCSVファイルが見つかりません。")

# --- 3. 出題画面 ---
if st.session_state.current_question:
    st.markdown("### 📋 演習問題")
    field = st.session_state.target_info.get('主な出題分野', st.session_state.target_info.get('種別', ''))
    year = st.session_state.target_info.get('年度', '')
    st.info(f"対象論点: {field}（関連: {year}）")
    st.write(st.session_state.current_question)
    
    st.write("---")
    user_answer = st.text_input("あなたの解答（例: 肢3、○、× など）:")
    
    if st.button("解答を提出して解説を見る"):
        with st.spinner("解説生成中（約5〜10秒）..."):
            exp_prompt = f"""
以下の問題に対して生徒が「{user_answer}」と解答しました。要点を絞って解説してください。

【問題文】
{st.session_state.current_question}

【元データ】
{st.session_state.target_info}

【解説要件】
1. 正解と合否判定
2. 各肢の簡潔な解説（条文・判例根拠）
3. ミスを防ぐ着眼点アドバイス
4. 確認すべき参考テキスト項目
"""
            try:
                exp_text = generate_fast(exp_prompt, fast_explanation_config)
                st.session_state.explanation = exp_text
            except Exception as e:
                st.error(f"解説生成エラー: {e}")

# --- 4. 解説表示 ---
if st.session_state.explanation:
    st.markdown("### 📖 解答・解説")
    st.write(st.session_state.explanation)
