# app/streamlit_app.py
import streamlit as st
import requests
import pandas as pd
import time

# API Configuration
API_URL = "http://localhost:8000"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": "Bearer trustsql-secret-key",
}

st.set_page_config(page_title="TrustSQL", page_icon="🔍", layout="wide")

st.title("🔍 TrustSQL: DQ-Aware Data Assistant")
st.markdown(
    "Ask questions about your data in plain English. I will write the SQL, fetch the data, and warn you about any data quality issues."
)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "is_processing" not in st.session_state:
    st.session_state.is_processing = False


def submit_feedback(score: int, msg_index: int):
    """Sends feedback to the API and marks it as submitted in the UI."""
    assistant_msg = st.session_state.messages[msg_index]
    user_msg = st.session_state.messages[msg_index - 1]

    payload = {
        "question": user_msg["content"],
        "source_id": "olist",
        "generated_sql": assistant_msg["sql"],
        "tables_used": assistant_msg.get("tables_used", []),
        "feedback_score": score,
    }

    try:
        requests.post(f"{API_URL}/feedback", json=payload, headers=HEADERS)
        st.session_state.messages[msg_index]["feedback_submitted"] = True
        if score > 0:
            st.toast("✅ Saved to Semantic Cache!")
        else:
            st.toast("Feedback recorded. We will improve!")
    except Exception as e:
        st.error(f"Failed to submit feedback: {e}")


# Display chat history
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        if msg.get("data"):
            st.dataframe(pd.DataFrame(msg["data"]))

        if msg.get("dq_warnings"):
            with st.expander("⚠️ Data Quality Warnings"):
                for warning in msg["dq_warnings"]:
                    st.warning(warning, icon="⚠️")

        if msg.get("sql"):
            with st.expander("💻 View Generated SQL"):
                st.code(msg["sql"], language="sql")

        # Show feedback buttons ONLY for the latest assistant message if it has SQL
        if (
            msg["role"] == "assistant"
            and msg.get("sql")
            and not msg.get("feedback_submitted")
        ):
            if i == len(st.session_state.messages) - 1:
                st.write("Was this answer helpful?")
                col1, col2, _ = st.columns([1, 1, 8])
                with col1:
                    # Disable button if a new query is currently running
                    st.button(
                        "👍 Yes",
                        on_click=submit_feedback,
                        args=(1, i),
                        disabled=st.session_state.is_processing,
                    )
                with col2:
                    st.button(
                        "👎 No",
                        on_click=submit_feedback,
                        args=(-1, i),
                        disabled=st.session_state.is_processing,
                    )

# Chat input
if prompt := st.chat_input(
    "Ask a question (e.g., 'What is the total revenue by category?')",
    disabled=st.session_state.is_processing,
):
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Lock the UI
    st.session_state.is_processing = True

    with st.chat_message("assistant"):
        success = False

        with st.status("Thinking...", expanded=True) as status:
            st.write("Analyzing intent and checking semantic cache...")

            payload = {
                "question": prompt,
                "source_id": "olist",
                "chat_history": [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages[:-1]
                ],
            }

            try:
                time.sleep(0.5)
                st.write("Retrieving schema and ontology context...")

                response = requests.post(
                    f"{API_URL}/query", json=payload, headers=HEADERS
                )
                response.raise_for_status()
                result = response.json()

                st.write("Generating and validating SQL...")
                time.sleep(0.5)
                st.write("Executing query and checking Data Quality...")

                status.update(
                    label="Finished processing!", state="complete", expanded=False
                )
                success = True

            except requests.exceptions.RequestException as e:
                status.update(label="Error occurred", state="error", expanded=True)
                st.error(f"Failed to connect to TrustSQL API: {e}")

        if success:
            raw_answer = result.get("final_answer", "No answer generated.")
            sql = result.get("generated_sql")
            data = result.get("execution_result", [])
            warnings = result.get("dq_warnings", [])
            tables_used = result.get("selected_tables", [])
            cache_hit = result.get("cache_hit", False)

            if data:
                ui_answer = f"Here are the results for your query ({len(data)} rows):"
            else:
                ui_answer = raw_answer

            if cache_hit:
                ui_answer = "⚡ *(Answered from Semantic Cache)*\n\n" + ui_answer

            st.markdown(ui_answer)

            if data:
                st.dataframe(pd.DataFrame(data))

            if warnings:
                with st.expander("⚠️ Data Quality Warnings"):
                    for w in warnings:
                        st.warning(w, icon="⚠️")

            if sql:
                with st.expander("💻 View Generated SQL"):
                    st.code(sql, language="sql")

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": ui_answer,
                    "sql": sql,
                    "data": data,
                    "dq_warnings": warnings,
                    "tables_used": tables_used,
                    "feedback_submitted": False,
                }
            )

        # Unlock the UI and rerun to show the new buttons
        st.session_state.is_processing = False
        st.rerun()
