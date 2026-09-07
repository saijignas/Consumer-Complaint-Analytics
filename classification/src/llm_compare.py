"""Head-to-head: the TF-IDF+LogReg baseline vs. zero-shot LLM
classification, on the *same* held-out rows (a stratified sample of the
baseline's test set, since free-tier rate limits make calling the LLM on
the full test set impractical).

This is deliberately not "which is more accurate" in isolation -- it's
accuracy, latency, and output reliability (does the model actually return
one of the 6 valid categories) together, because in a real system all
three decide which approach you'd actually ship.

Requires an API key: set GROQ_API_KEY (provider=groq) or GEMINI_API_KEY
(provider=gemini) as an environment variable. Never hardcode a key here.
"""
import os
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).parent.parent
TABLE_DIR = ROOT / "results" / "tables"

PRODUCTS = [
    "Credit card",
    "Mortgage",
    "Checking or savings account",
    "Student loan",
    "Vehicle loan or lease",
    "Money transfer, virtual currency, or money service",
]
PER_CATEGORY_SAMPLE = 40  # 40 x 6 = 240 held-out rows sent to the LLM
RANDOM_STATE = 42

if os.environ.get("LLM_PROVIDER"):
    PROVIDER = os.environ["LLM_PROVIDER"].lower()
elif os.environ.get("GEMINI_API_KEY"):
    PROVIDER = "gemini"
else:
    PROVIDER = "groq"
GROQ_MODEL = "llama-3.1-8b-instant"
# gemini-3.6-flash (newest flagship) has a 20-requests/day free quota --
# discovered by hitting it. gemini-3.5-flash-lite has a much higher free
# daily quota (500/day) but repeated testing tonight exhausted that too --
# each model has its own separate daily quota bucket on the same key, so
# gemini-3.1-flash-lite (untouched tonight) is used instead.
GEMINI_MODEL = "gemini-3.1-flash-lite"
CALL_DELAY_S = 3.0
MAX_RETRIES = 3

# A plain requests.post() per call opens a fresh TCP+TLS connection every
# time -- observed tonight to add ~20s/call overhead (likely AV/endpoint
# security inspecting each new short-lived HTTPS connection from a script
# process), while ad-hoc curl calls to the same endpoint stayed under 1.2s.
# A shared Session reuses one keep-alive connection across all calls.
SESSION = requests.Session()


def build_prompt(narrative):
    options = "\n".join(f"- {p}" for p in PRODUCTS)
    return (
        "Classify this consumer complaint into exactly one of these categories. "
        "Reply with only the category name, nothing else.\n\n"
        f"Categories:\n{options}\n\n"
        f"Complaint:\n{narrative}\n\n"
        "Category:"
    )


def call_groq(prompt):
    key = os.environ["GROQ_API_KEY"]
    resp = SESSION.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 30,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def call_gemini(prompt):
    # Auth via header, not ?key=... in the URL -- a query-string key can
    # end up embedded in exception messages (e.g. requests' own
    # HTTPError/ConnectionError text includes the full URL) and get
    # logged or saved somewhere it shouldn't be.
    key = os.environ["GEMINI_API_KEY"]
    resp = SESSION.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        headers={"x-goog-api-key": key},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=30,
    )
    resp.raise_for_status()
    parts = resp.json()["candidates"][0]["content"]["parts"]
    return next(p["text"] for p in parts if "text" in p)


def call_llm(prompt):
    if PROVIDER == "groq":
        return call_groq(prompt)
    if PROVIDER == "gemini":
        return call_gemini(prompt)
    raise ValueError(f"Unknown LLM_PROVIDER={PROVIDER!r}")


def _scrub(text):
    # Defense in depth: never let any API key value reach saved output,
    # even via an error message from a code path that isn't call_gemini.
    for env_var in ("GEMINI_API_KEY", "GROQ_API_KEY"):
        key = os.environ.get(env_var)
        if key:
            text = text.replace(key, "[REDACTED]")
    return text


def call_llm_with_retry(prompt):
    # Retries on 429 (rate limit) AND on timeout/connection errors --
    # observed tonight to be transient (some calls take 15s+ then
    # succeed on retry), not a hard failure worth giving up on immediately.
    for attempt in range(MAX_RETRIES):
        try:
            return call_llm(prompt), None
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 429 and attempt < MAX_RETRIES - 1:
                time.sleep(CALL_DELAY_S * (attempt + 2))
                continue
            return "", _scrub(str(e))
        except (requests.Timeout, requests.ConnectionError) as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(CALL_DELAY_S)
                continue
            return "", _scrub(str(e))
        except Exception as e:
            return "", _scrub(str(e))
    return "", "max retries exceeded"


def parse_category(raw_text):
    text = raw_text.strip().lower()
    for p in PRODUCTS:
        if p.lower() in text:
            return p
    return None  # unparseable -- counted, not silently dropped


def main():
    test_df = pd.read_csv(TABLE_DIR / "test_set_with_baseline_preds.csv")
    parts = [
        g.sample(min(PER_CATEGORY_SAMPLE, len(g)), random_state=RANDOM_STATE)
        for _, g in test_df.groupby("true_product")
    ]
    sample = pd.concat(parts, ignore_index=True)
    print(f"Calling {PROVIDER} on {len(sample)} held-out complaints...")

    results = []
    for i, row in sample.iterrows():
        prompt = build_prompt(row["narrative"])
        start = time.time()
        raw, error = call_llm_with_retry(prompt)
        latency = time.time() - start
        pred = parse_category(raw) if not error else None
        results.append({
            "complaint_id": row["complaint_id"],
            "true_product": row["true_product"],
            "baseline_pred": row["baseline_pred"],
            "llm_raw_output": raw,
            "llm_pred": pred,
            "latency_s": latency,
            "error": error,
        })
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(sample)}")
        time.sleep(CALL_DELAY_S)

    out = pd.DataFrame(results)
    out.to_csv(TABLE_DIR / "llm_comparison_results.csv", index=False)

    unparseable = out["llm_pred"].isna().sum()
    parseable = out[out["llm_pred"].notna()]
    llm_acc = (parseable["llm_pred"] == parseable["true_product"]).mean()
    baseline_acc_same_rows = (out["baseline_pred"] == out["true_product"]).mean()

    print(f"\nOn the same {len(out)} held-out rows:")
    print(f"  Baseline (TF-IDF + LogReg) accuracy: {baseline_acc_same_rows:.3f}")
    print(f"  LLM ({PROVIDER}) accuracy (parseable only): {llm_acc:.3f}")
    print(f"  LLM unparseable outputs: {unparseable}/{len(out)}")
    print(f"  LLM mean latency: {out['latency_s'].mean():.2f}s/call "
          f"(baseline: sub-millisecond/call, already-trained)")

    with open(TABLE_DIR / "llm_comparison_summary.txt", "w") as f:
        f.write(f"provider={PROVIDER}\n")
        f.write(f"n_rows={len(out)}\n")
        f.write(f"baseline_acc={baseline_acc_same_rows:.4f}\n")
        f.write(f"llm_acc_parseable_only={llm_acc:.4f}\n")
        f.write(f"llm_unparseable={unparseable}\n")
        f.write(f"llm_mean_latency_s={out['latency_s'].mean():.3f}\n")


if __name__ == "__main__":
    main()
