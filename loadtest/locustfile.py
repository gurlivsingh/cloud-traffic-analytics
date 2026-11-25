"""Load test - shows CPU rising in CloudWatch (and Auto Scaling, if you set it up).

    pip install locust
    locust -f loadtest/locustfile.py --host http://<EC2-public-IP> --headless -u 100 -r 10 -t 2m
"""
import random

from locust import HttpUser, between, task


class DashboardUser(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self):
        self.locs = [l["id"] for l in self.client.get("/api/locations").json()] or [1]

    @task(3)
    def overview(self):
        self.client.get("/api/locations")
        self.client.get("/api/summary")

    @task(2)
    def prediction(self):
        self.client.get(f"/api/predictions?location={random.choice(self.locs)}", name="/api/predictions")

    @task(1)
    def patterns(self):   # heaviest call: aggregates every stored hour of one location
        self.client.get(f"/api/patterns?location={random.choice(self.locs)}", name="/api/patterns")

    @task(1)
    def traffic(self):
        self.client.get(f"/api/traffic?location={random.choice(self.locs)}", name="/api/traffic")
