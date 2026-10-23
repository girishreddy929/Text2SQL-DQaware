"""Run:  python -m src.common.list_models
Lists the Gemini models your API key can use (names change often)."""

from google import genai

from config.settings import get_settings


def main() -> None:
    client = genai.Client(api_key=get_settings().google_api_key.get_secret_value())
    rows = []
    for m in client.models.list():
        actions = list(getattr(m, "supported_actions", None) or [])
        rows.append((m.name, actions))

    print(f"Total models visible: {len(rows)}\n")

    print("--- chat models (generateContent) with 'flash' in the name ---")
    chat = [
        n for n, a in sorted(rows) if "generateContent" in a and "flash" in n.lower()
    ]
    print("\n".join(chat) if chat else "(none found; see full list below)")

    print("\n--- embedding models ---")
    emb = [(n, a) for n, a in sorted(rows) if "embed" in n.lower()]
    for n, a in emb:
        print(n, a)
    if not emb:
        print("(none found; see full list below)")

    if not chat or not emb:
        print("\n--- full list ---")
        for n, a in sorted(rows):
            print(n, a)


if __name__ == "__main__":
    main()
