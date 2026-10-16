"""Print model IDs available to your key (pick Nemotron IDs from here; check function-calling support in the docs)."""
import os

from .config import DEFAULT_BASE_URL, load_dotenv


def main():
    load_dotenv()
    if not os.environ.get("NEBIUS_API_KEY"):
        raise SystemExit("NEBIUS_API_KEY is not set (put it in .env or the environment)")
    from openai import OpenAI
    client = OpenAI(base_url=os.environ.get("NEBIUS_BASE_URL", DEFAULT_BASE_URL),
                    api_key=os.environ["NEBIUS_API_KEY"])
    ids = sorted(m.id for m in client.models.list())
    for i in ids:
        if "nemotron" in i.lower() or "nvidia" in i.lower():
            print("*", i)
        else:
            print(" ", i)


if __name__ == "__main__":
    main()
