# src/api/test_client.py
import urllib.request
import json


def test_query_api():
    url = "http://localhost:8000/query"

    # The default API key from src/api/security.py
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer trustsql-secret-key",
    }

    # The payload matching our QueryRequest Pydantic model
    payload = {
        "question": "How many total orders are there?",
        "source_id": "olist",
        "chat_history": [],
    }

    print(f"Sending POST request to {url}...")
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )

    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
            print("\n✅ API Response Success!")
            print(f"Intent: {result.get('intent')}")
            print(f"SQL: {result.get('generated_sql')}")
            print(f"Final Answer: {result.get('final_answer')}")

            if result.get("dq_warnings"):
                print(f"DQ Warnings: {result.get('dq_warnings')}")

    except urllib.error.HTTPError as e:
        print(f"\n❌ HTTP Error: {e.code} - {e.reason}")
        print(e.read().decode("utf-8"))
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    test_query_api()
