import streamlit as st
import pandas as pd
import time
from google import genai

st.set_page_config(page_title="弱点特化・資格演習アプリ", layout="wide")

# --- 初期設定 ---
api_key = st.sidebar.text_input("Gemini API Key", type="password")
client = genai.Client(api_key=api_key) if api_key else None

if "current_question" not in st.session_state:
    st.session_state.current_question = None
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "elapsed_time" not in st.session_state:
    st.session_state.elapsed_time = None

st.title("⏱️ 弱点集中・タイマー演習アプリ")

# --- 1. 正誤表CSVの読み込み ---
csv_file = st.sidebar.file_uploader("正誤表CSVをアップロード", type=["csv"])

if csv_file:
    try:
        df = pd.read_csv(csv_file, encoding="utf-8")
    except UnicodeDecodeError:
        csv_file.seek(0)
        df = pd.read_csv(csv_file, encoding="cp932")
    
    # 列名の前後の空白や改行をきれいに除去
    df.columns = [str(c).strip().replace("\n", "").replace("\r", "") for c in df.columns]
    st.sidebar.success("CSV読み込み完了！")
    
    # 「正誤」列の探索
    seigo_col = None
    for col in df.columns:
        if "正誤" in col or "判定" in col or "結果" in col:
            seigo_col = col
            break
            
    if seigo_col:
        # 不正解（×、不正解、ミス、誤り等）が含まれる行を抽出
        weak_records = df[df[seigo_col].astype(str).str.contains("×|不正解|ミス|バツ|誤|×", na=False)]
        st.sidebar.write(f"抽出された苦手レコード数: {len(weak_records)} 件")
    else:
        st.sidebar.warning("⚠️ 正誤列が自動判定できませんでした。全データから出題します。")
        weak_records = df

    # --- 2. 出題生成ボタン ---
    if st.button("🚨 苦手意識から新しい問題を生成する"):
        if not client:
            st.error("左のサイドバーにGemini API Keyを入力してください。")
        elif weak_records.empty:
            st.warning("出題対象のデータが見つかりませんでした。")
        else:
            with st.spinner("過去のミス傾向を分析して出題中..."):
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
                # モデル名を最新の gemini-3.8-flash に更新
                response = client.models.generate_content(
                    model="gemini-3.8-flash",
                    contents=prompt
                )
                
                st.session_state.current_question = response.text
                st.session_state.target_info = target_dict
                st.session_state.start_time = time.time()
                st.session_state.elapsed_time = None
                st.session_state.explanation = None

# --- 3. 出題画面 & タイマー計測 ---
if st.session_state.current_question:
    st.markdown("### 📝 演習問題")
    field = st.session_state.target_info.get('主な出題分野', st.session_state.target_info.get('種別', ''))
    year = st.session_state.target_info.get('年度', '')
    st.info(f"出題元分野: {field}（関連: {year}）")
    st.write(st.session_state.current_question)
    
    st.write("---")
    user_answer = st.text_input("あなたの解答（例: 肢3、○、× など）:")
    
    if st.button("解答を提出して解説を見る"):
        st.session_state.elapsed_time = round(time.time() - st.session_state.start_time, 1)
        
        with st.spinner("解説を作成中..."):
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
            # モデル名を最新の gemini-3.8-flash に更新
            exp_response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=exp_prompt
            )
            st.session_state.explanation = exp_response.text

# --- 4. 結果・タイム・解説表示 ---
if st.session_state.get("elapsed_time") is not None:
    mins = int(st.session_state.elapsed_time // 60)
    secs = int(st.session_state.elapsed_time % 60)
    
    st.success(f"⏱️ **解答所要時間**: {mins}分 {secs}秒 ({st.session_state.elapsed_time}秒)")
    if st.session_state.elapsed_time > 150:
        st.warning("⚠️ 2分30秒を超えています。本試験ペースに注意してください。")
    
    st.markdown("### 📖 解答・解説")
    st.write(st.session_state.explanation)