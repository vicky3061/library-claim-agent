from dotenv import load_dotenv
from google import genai

CANDIDATES = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-3-flash-preview",
]


def main():
    load_dotenv()
    client = genai.Client()
    for model in CANDIDATES:
        try:
            r = client.models.generate_content(model=model, contents="Reply with OK")
            print(f"{model:25s} -> OK ({r.text.strip()[:20]})")
        except Exception as e:
            print(f"{model:25s} -> FAIL {str(e)[:70]}")


if __name__ == "__main__":
    main()