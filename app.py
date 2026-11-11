import streamlit as st
import pandas as pd
import glob
from google import genai

st.set_page_config(page_title="弱点特化・資格演習アプリ", layout="wide")

# --- APIキーの設定（Streamlit Secrets から安全に取得） ---
# Streamlit Cloudの「Secrets」または手動入力からキーを取得
api_key = st.secrets.get("GEMINI_API_KEY", "")

if not api_key:
    # Secretsが未設定の場合の入力フォールバック
    api_key = st.sidebar.text_input("Gemini API Key", type="password")

client = genai.Client(api_key=api_key) if api_key else None

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
        if "正誤" in col or "判定" in col or "結果" in col:
            seigo_col = col
            break
            
    if seigo_col:
        weak_records = df[df[seigo_col].astype(str).str.contains("×|不正解|ミス|バツ|誤", na=False)]
        st.sidebar.success(f"正誤データを自動読込完了（苦手: {len(weak_records)} 件）")
    else:
        st.sidebar.warning("正誤列が見つかりません。全データから出題します。")
        weak_records = df

    # --- 2. 出題生成ボタン ---
    if st.button("🚨 苦手論点から新しい問題を生成する"):
        if not client:
            st.error("APIキーが設定されていません。")
        elif weak_records.empty:
            st.warning("出題対象のデータがありません。")
        else:
            with st.spinner("苦手論点を分析して出題を作成中..."):
                target = weak_records.sample(1).iloc[0]
                target_dict = target.to_dict()
                log_text = "\n".join([f"- {k}: {v}" for k, v in target_dict.items() if pd.notna(v)])
                
                prompt = f"""
あなたは国家資格試験（土地家屋調査士試験等）の専属講師です。
生徒の過去問正誤ログから、特に苦手としている論点・ミスしやすいポイントを突いた択一問題を1問作成してください。

【生徒の過去のつまずきデータ】
{log_text}

【問題作成の要件】
1. 本試験レベルのひっかけ（生徒が間違えた理由を踏まえた選択肢）を含めてください。
2. 5肢択一または正誤判定問題として出題してください。
3. この段階では「問題文と選択肢のみ」を出力してください（正解と解説は出力しないこと）。
4. 最後に「【問題文出力完了】」と書いて終了してください。
"""
                response = client.models.generate_content(
                    model="gemini-3.8-flash",
                    contents=prompt
                )
                
                st.session_state.current_question = response.text
                st.session_state.target_info = target_dict
                st.session_state.explanation = None
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
以下の問題に対して、生徒が「{user_answer}」と解答しました。
詳細な解説を作成してください。

【問題文】
{st.session_state.current_question}

【元になった弱点データ】
{st.session_state.target_info}

【解説の出力要件】
1. 正解と生徒の成否の判定
2. 各肢の詳しい解説（根拠条文・判例・計算のポイント）
3. 生徒が過去にミスした視点を踏まえた「見抜くためのアドバイス」
4. 📖 テキスト参照案内：手元のテキストで確認すべき「関連項目名」および「おおよその参照章・論点」
"""
            exp_response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=exp_prompt
            )
            st.session_state.explanation = exp_response.text

# --- 4. 解説表示 ---
if st.session_state.explanation:
    st.markdown("### 📖 解答・解説")
    st.write(st.session_state.explanation)
