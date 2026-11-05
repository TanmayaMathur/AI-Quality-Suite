import json

import pytest

from app.config import Settings
from app.contracts import Generation, Passage, Source
from app.pipeline import Pipeline


class FixtureRetriever:
    def __init__(self):
        self.passages = [
            Passage(
                Source(document_id="bridge", chunk_id="bridge-1", relevance_score=0.87),
                "The Harbor Bridge uses Ethernet and supports 24 sensors.",
            ),
            Passage(
                Source(document_id="relay", chunk_id="relay-1", relevance_score=0.76),
                "The Drift Relay operates on 2.4 GHz Wi-Fi.",
            ),
        ]
        self.query = None

    def retrieve(self, query):
        self.query = query
        return self.passages

    def ready(self):
        return None


class FixtureGenerator:
    def __init__(self):
        self.reply = "The Harbor Bridge uses Ethernet [1]."
        self.user = None
        self.system = None

    def ready(self):
        return None

    def generate(self, system, user):
        self.system = system
        self.user = json.loads(user)
        return Generation(self.reply, 120, 15)


@pytest.fixture
def pipeline():
    return Pipeline(FixtureRetriever(), FixtureGenerator(), Settings(_env_file=None))
