"""Load test:  pip install locust

    LOCUST_EMAIL=you@example.com LOCUST_PASSWORD=... \
    locust -f locustfile.py --host http://localhost:8080 --headless -u 10 -r 2 -t 2m --csv load

Note: per-user rate limits (RATE_LIMIT_*_RPM) apply. All simulated users share one account
here, so raise those limits in .env for a throughput test or you will mostly measure 429s.
Record the numbers Locust prints (requests/s, p50/p95/p99, failure rate) -- do not estimate them.
"""
import os
import random

from locust import HttpUser, between, task

QUESTIONS = [
    "What is the time complexity of searching a balanced binary search tree?",
    "What principle does a stack follow?",
    "What are the main queue operations?",
    "Which data structure does BFS use?",
    "What is the worst-case time complexity of quick sort?",
]


class NexaUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        r = self.client.post(
            "/auth/login",
            json={"email": os.environ["LOCUST_EMAIL"], "password": os.environ["LOCUST_PASSWORD"]},
            name="/auth/login",
        )
        self.headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    @task(5)
    def rag_query(self):
        self.client.post("/query", json={"question": random.choice(QUESTIONS)}, headers=self.headers, name="/query")

    @task(2)
    def list_documents(self):
        self.client.get("/documents?page=1&limit=10", headers=self.headers, name="/documents")

    @task(2)
    def stats(self):
        self.client.get("/stats", headers=self.headers, name="/stats")

    @task(1)
    def history(self):
        self.client.get("/queries?page=1&limit=10", headers=self.headers, name="/queries")

    @task(1)
    def health(self):
        self.client.get("/health", name="/health")
