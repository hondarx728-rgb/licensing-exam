import streamlit as st
import pandas as pd
import glob
import time
from google import genai
from google.genai import types

st.set_page_config(page_title="弱点特化・資格演習アプリ", layout="wide")

# --- APIキーの設定（Streamlit Secrets から取得） ---
api_key = st.secrets.get("GEMINI_API_KEY", "")

if not api_key:
    api_key = st.sidebar.text_input("Gemini API Key", type="password")

client = genai.Client(api_key=api_key) if api_key else None

# 出力トークンのみを制限して素早く完結させる設定
fast_question_config = types.GenerateContentConfig(
    max_output_tokens=800,
    temperature=0.3
)

fast_explanation_config = types.GenerateContentConfig(
    max_output_tokens=1200,
    temperature=0.3
)

# 混雑時に順次切り替える軽量・高速モデルのリスト
LIGHT_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.6-flash"
]

def request_with_fallback(prompt, config):
    """503混雑時に即座に別モデルへフォールバックして即答させる関数"""
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
            # 503混雑や一時エラーの場合は間髪入れずに次のモデルへ切り替え
            time.sleep(0.5)
            continue
    raise last_error

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
            with st.spinner("出題を作成中（数秒で完了します）..."):
                target = weak_records.sample(1).iloc[0]
                target_dict = target.to_dict()
                log_text = "\n".join([f"- {k}: {v}" for k, v in target_dict.items() if pd.notna(v)])
                
                prompt = f"""
土地家屋調査士試験の択一問題を1問作成してください。

【弱点データ】
{log_text}

【要件】
1. つまずいた論点を突いた択一問題（5肢択一または正誤判定）。
2. 出力は「問題文と選択肢のみ」。正解や解説は一切含めないこと。
3. 簡潔に出力してください。
"""
                try:
                    q_text = request_with_fallback(prompt, fast_question_config)
                    st.session_state.current_question = q_text
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
        with st.spinner("解説を生成中..."):
            exp_prompt = f"""
以下の問題に対して生徒が「{user_answer}」と解答しました。簡潔に解説してください。

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
                exp_text = request_with_fallback(exp_prompt, fast_explanation_config)
                st.session_state.explanation = exp_text
            except Exception as e:
                st.error(f"解説生成エラー: {e}")

# --- 4. 解説表示 ---
if st.session_state.explanation:
    st.markdown("### 📖 解答・解説")
    st.write(st.session_state.explanation)
