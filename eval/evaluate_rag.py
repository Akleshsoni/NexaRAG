"""Measure the RAG pipeline on a fixed question set (nothing here is hard-coded results).

Metrics
  Retrieval  : Hit@1/3/5 and MRR over in-scope questions. A returned source counts as
               relevant if it contains the question's `evidence` phrase.
  Routing    : abstention accuracy on out-of-scope questions (no document sources
               returned -> the system answered with general AI), and false-abstain rate
               on in-scope questions.
  Answers    : keyword coverage (are the expected terms in the answer?) and, with
               --judge, an LLM-as-judge faithfulness score from Gemini.
  Latency    : mean / p50 / p95 of the API's own latency_ms.

Setup: upload eval/sample_docs/cs_notes.pdf to the account you evaluate with and wait
until it is "ready" (use a dedicated account so other documents don't interfere).

Usage (from the project folder, with the stack running):
    docker compose exec api python eval/evaluate_rag.py --base-url http://localhost:8000 \
        --email you@example.com --password '...'
    # or: --token <JWT>;  add --judge for the Gemini faithfulness score
"""
import argparse
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

import httpx

DEFAULT_SET = Path(__file__).with_name("rag_eval_set.json")

JUDGE_PROMPT = """You are grading a RAG answer. Score from 0 to 1:
1 = the answer is correct for the question AND every claim is supported by the SOURCES;
0.5 = partly correct or partly unsupported; 0 = wrong, unsupported, or contradicts the sources.
Reply with ONLY the number.

QUESTION: {q}
SOURCES:
{sources}

ANSWER: {a}

SCORE:"""


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def login(client: httpx.Client, email: str, password: str) -> str:
    r = client.post("/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def ask(client: httpx.Client, headers: dict, question: str, retries: int = 4) -> dict | None:
    for attempt in range(retries):
        r = client.post("/query", headers=headers, json={"question": question, "top_k": 5, "stream": False})
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 502, 503):
            wait = 20 * (attempt + 1)
            print(f"   ... HTTP {r.status_code} ({r.json().get('detail', '')[:60]}); retry in {wait}s")
            time.sleep(wait)
            continue
        print(f"   ... HTTP {r.status_code}: {r.text[:120]}")
        return None
    return None


def judge(question: str, answer: str, sources: list[dict]) -> float | None:
    try:
        from google import genai

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        src = "\n".join(f"[{i + 1}] {s['text'][:600]}" for i, s in enumerate(sources)) or "(none)"
        out = client.models.generate_content(
            model=os.getenv("LLM_MODEL", "gemini-2.5-flash"),
            contents=JUDGE_PROMPT.format(q=question, sources=src, a=answer),
        )
        return max(0.0, min(1.0, float((out.text or "").strip())))
    except Exception as exc:  # noqa: BLE001
        print(f"   ... judge failed ({type(exc).__name__})")
        return None


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:5.1f}%  ({n}/{d})" if d else "n/a"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--token")
    ap.add_argument("--email")
    ap.add_argument("--password")
    ap.add_argument("--dataset", default=str(DEFAULT_SET))
    ap.add_argument("--delay", type=float, default=2.5, help="seconds between requests (rate limit is 30/min)")
    ap.add_argument("--judge", action="store_true", help="add Gemini faithfulness scoring (uses quota)")
    ap.add_argument("--out", default="eval/last_report.json")
    args = ap.parse_args()

    data = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    with httpx.Client(base_url=args.base_url, timeout=90) as client:
        token = args.token or (login(client, args.email, args.password) if args.email else None)
        if not token:
            print("Provide --token or --email/--password")
            return 2
        headers = {"Authorization": f"Bearer {token}"}

        rows, hit_ranks = [], []
        for i, item in enumerate(data["in_scope"], 1):
            print(f"[in-scope {i}/{len(data['in_scope'])}] {item['question']}")
            res = ask(client, headers, item["question"])
            time.sleep(args.delay)
            if res is None:
                rows.append({**item, "error": True})
                continue
            evidence = norm(item["evidence"])
            rank = next((r for r, s in enumerate(res["sources"], 1) if evidence in norm(s["text"])), None)
            answer = res["answer"]
            kws = item["answer_keywords"]
            coverage = sum(k in norm(answer) for k in kws) / len(kws)
            row = {
                "question": item["question"], "lang": item.get("lang", "en"), "rank": rank,
                "mode": res.get("mode"), "n_sources": len(res["sources"]),
                "keyword_coverage": coverage, "latency_ms": res["latency_ms"], "answer": answer,
            }
            if args.judge:
                row["faithfulness"] = judge(item["question"], answer, res["sources"])
                time.sleep(4)
            rows.append(row)
            hit_ranks.append(rank)

        neg_rows = []
        for i, item in enumerate(data["out_of_scope"], 1):
            print(f"[out-of-scope {i}/{len(data['out_of_scope'])}] {item['question']}")
            res = ask(client, headers, item["question"])
            time.sleep(args.delay)
            if res is None:
                neg_rows.append({"question": item["question"], "error": True})
                continue
            neg_rows.append({
                "question": item["question"], "mode": res.get("mode"), "n_sources": len(res["sources"]),
                "abstained": not res["sources"], "latency_ms": res["latency_ms"],
            })

    ok = [r for r in rows if not r.get("error")]
    n = len(ok)
    n_neg = len([r for r in neg_rows if not r.get("error")])
    ranks = [r["rank"] for r in ok]

    def hit(k: int) -> int:
        return sum(1 for r in ranks if r is not None and r <= k)

    mrr = sum(1 / r for r in ranks if r) / n if n else 0.0
    lat = sorted(r["latency_ms"] for r in ok + [x for x in neg_rows if not x.get("error")])
    p = lambda q: lat[min(len(lat) - 1, int(q * len(lat)))] if lat else 0  # noqa: E731
    faith = [r["faithfulness"] for r in ok if r.get("faithfulness") is not None]

    print("\n" + "=" * 62)
    print(" NexaRAG evaluation report")
    print("=" * 62)
    print(f" In-scope questions answered : {n}/{len(data['in_scope'])}    Out-of-scope: {n_neg}/{len(data['out_of_scope'])}")
    print("\n Retrieval (in-scope)")
    for k in (1, 3, 5):
        print(f"   Hit@{k}      : {pct(hit(k), n)}")
    print(f"   MRR        : {mrr:.3f}")
    print(f"   False abstain (no sources for an in-scope question): {pct(sum(1 for r in ok if r['n_sources'] == 0), n)}")
    print("\n Routing (out-of-scope should return NO document sources)")
    print(f"   Abstention : {pct(sum(1 for r in neg_rows if r.get('abstained')), n_neg)}")
    print("\n Answers (in-scope)")
    if n:
        print(f"   Keyword coverage (mean)   : {statistics.mean(r['keyword_coverage'] for r in ok):.3f}")
        print(f"   All keywords present      : {pct(sum(r['keyword_coverage'] == 1 for r in ok), n)}")
    if faith:
        print(f"   Faithfulness (Gemini judge): {statistics.mean(faith):.3f}  over {len(faith)} answers")
    else:
        print("   Faithfulness (Gemini judge): not run (use --judge)")
    hing = [r for r in ok if r["lang"] == "hinglish"]
    if hing:
        print(f"   Hinglish questions         : {sum(1 for r in hing if r['rank'])}/{len(hing)} retrieved the right passage")
    print(f"\n Latency (API latency_ms): mean {statistics.mean(lat) if lat else 0:.0f} ms | p50 {p(0.5)} | p95 {p(0.95)}")
    print("\n Limitations")
    print("   - Small, single-document set (cs_notes.pdf); results do not generalise to other corpora.")
    print("   - Relevance = contains an evidence phrase, a coarse proxy for 'the right passage'.")
    print("   - Keyword coverage rewards mentioning terms; it cannot detect wrong reasoning.")
    print("   - The Gemini judge is itself an LLM (non-deterministic, may be lenient) and sees the same sources.")
    print("   - Repeating a run can hit the 30-minute answer cache, which makes latency look better.")
    print("   - Abstention depends on RETRIEVAL_MIN_SCORE; tune it with this script rather than by guesswork.")

    Path(args.out).write_text(
        json.dumps({"in_scope": rows, "out_of_scope": neg_rows}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n Full per-question results: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
