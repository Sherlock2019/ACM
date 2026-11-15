import os
import tempfile

# Tests must never pick up the user's saved UI LLM settings (a real, paid provider) or their .env key.
os.environ["AFM_LLM_SETTINGS_PATH"] = os.path.join(tempfile.mkdtemp(prefix="afm-test-"), "llm_settings.json")
os.environ["AFM_LLM_PROVIDER"] = "mock"
os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.engine.service import AFMService
from app.engine.usecases import UseCaseService
from app.main import create_app
from app.storage.db import Database

INV = "warehouse-demo"
WEB = "webapp-demo"
PLAY = "object-playground"
DEMO_GOAL = "Fulfill Order A while avoiding a shortage for Order B."
WEB_GOAL = "Change the application to port 9000 while keeping it accessible. Do not delete data. Ask me before making changes."
PLAY_GOAL = "Change Object A's value to 10 and show me what will happen."


@pytest.fixture
def svc(tmp_path):
    return AFMService(db=Database(tmp_path / "afm-test.db"))


@pytest.fixture
def ucs(svc):
    return UseCaseService(svc)


@pytest.fixture
def client(svc):
    return TestClient(create_app(svc))


@pytest.fixture
def demo_run(svc):
    return svc.assess(INV, DEMO_GOAL)


def store(svc, env=INV):
    return svc.env(env).store


def plan_of(run, plan_id):
    return next(a for a in run.assessments if a.plan.plan_id == plan_id)


def approve(svc, run, plan_id):
    a = plan_of(run, plan_id)
    return svc.decide(run.run_id, plan_id, "approve", a.plan_hash, run.environment_version)
