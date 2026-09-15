"""Evaluation harness for the RAG pipeline.

Run this against a fixed set of question/expected-answer pairs to get a
repeatable quality score instead of eyeballing a demo. This is what you show
in an interview when asked 'how do you know your RAG isn't hallucinating?'

Usage:
    python eval/run_eval.py --dataset eval/golden_set.json --token YOUR_JWT
"""
import argparse
import json
import time

import httpx

GRADING_PROMPT = """You are grading whether a generated answer correctly addresses a question, \
given a reference answer. Respond with ONLY a number from 0 to 1, where 1 means fully correct \
and consistent with the reference, 0 means wrong or contradicts it.

Question: {question}
Reference answer: {reference}
Generated answer: {generated}

Score:"""


def load_dataset(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def call_api(base_url: str, token: str, question: str) -> dict:
    response = httpx.post(
        f"{base_url}/query",
        json={"question": question, "top_k": 5, "stream": False},
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def grade_with_llm(question: str, reference: str, generated: str, gemini_client) -> float:
    """Uses Gemini itself as a judge -- much cheaper than human grading and
    consistent enough to track quality regressions between prompt changes."""
    prompt = GRADING_PROMPT.format(question=question, reference=reference, generated=generated)

    for attempt in range(4):
        try:
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            return float(response.text.strip())
        except (ValueError, AttributeError):
            return 0.0
        except Exception as exc:  # noqa: BLE001 -- transient 503/overload from Gemini
            if attempt == 3:
                print(f"  (grading failed after retries: {exc})")
                return 0.0
            wait = 2**attempt
            print(f"  (grading hit a transient error, retrying in {wait}s...)")
            time.sleep(wait)
    return 0.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="eval/golden_set.json")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token", required=True)
    args = parser.parse_args()

    import os

    from google import genai

    judge = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    dataset = load_dataset(args.dataset)

    results = []
    for i, item in enumerate(dataset):
        if i > 0:
            time.sleep(15)  # stay under Gemini free tier's 5 requests/minute limit

        start = time.perf_counter()
        result = call_api(args.base_url, args.token, item["question"])
        latency_ms = (time.perf_counter() - start) * 1000
        score = grade_with_llm(item["question"], item["expected_answer"], result["answer"], judge)
        results.append(
            {
                "question": item["question"],
                "score": score,
                "latency_ms": round(latency_ms),
                "answer": result["answer"],
            }
        )
        print(f"[{score:.2f}] {item['question'][:60]}... ({round(latency_ms)}ms)")

    avg_score = sum(r["score"] for r in results) / len(results)
    avg_latency = sum(r["latency_ms"] for r in results) / len(results)
    print(f"\nAverage score: {avg_score:.2f} | Average latency: {avg_latency:.0f}ms")

    with open("eval/last_run.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()