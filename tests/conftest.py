"""ACM test fixtures: MLM frames built from committed CoNLL-U, no parser model needed."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from splm.config import Config
from splm.language.packs import LanguagePackRegistry
from splm.linguistic.conllu import parse_conllu
from splm.linguistic.morphology import MorphologyEngine
from splm.linguistic.semantic_roles import SemanticRoleEngine
from splm.phrase.builder import PhraseFrameBuilder
from splm.phrase.schema import UniversalPhraseFrame

from acm.engine import ConsequenceEngine
from acm.schema import ConsequenceReport

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def builder() -> PhraseFrameBuilder:
    config = Config.load(apply_env=False, overrides={"app.lexicon.auto_download": False})
    registry = LanguagePackRegistry(config.language_packs_dir)
    return PhraseFrameBuilder(
        registry,
        morphology=MorphologyEngine(registry),
        semantic_roles=SemanticRoleEngine(registry),
    )


@pytest.fixture(scope="session")
def frame_for(builder: PhraseFrameBuilder) -> Callable[..., UniversalPhraseFrame]:
    cache: dict[str, dict] = {}

    def build(text: str, language: str = "en") -> UniversalPhraseFrame:
        if language not in cache:
            path = FIXTURE_DIR / f"{language}.conllu"
            if not path.is_file():
                pytest.skip(f"no ACM fixture for {language}; run scripts/make_fixtures.py")
            document = parse_conllu(path.read_text(encoding="utf-8"), language)
            cache[language] = {s.text.strip(): s for s in document.sentences}
        sentence = cache[language].get(text.strip())
        if sentence is None:
            pytest.skip(f"sentence not in the {language} ACM fixture: {text!r}")
        return builder.build(sentence)

    return build


@pytest.fixture(scope="session")
def engine() -> ConsequenceEngine:
    return ConsequenceEngine()


@pytest.fixture(scope="session")
def predict(engine, frame_for) -> Callable[..., ConsequenceReport]:
    """predict("context 1", "context 2", ..., "action") -> report."""

    def run(*texts: str, language: str = "en") -> ConsequenceReport:
        return engine.predict([frame_for(t, language) for t in texts], language=language)

    return run
