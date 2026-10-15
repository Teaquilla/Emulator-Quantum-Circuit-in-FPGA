"""Print model IDs available to your key (pick Nemotron IDs from here; check function-calling support in the docs)."""
from .config import DEFAULT_BASE_URL
import os


def main():
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
