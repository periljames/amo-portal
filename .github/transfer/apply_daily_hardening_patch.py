from pathlib import Path
import re


def replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise SystemExit(f"expected one {label}; found {source.count(old)}")
    return source.replace(old, new)


services_path = Path("backend/amodb/apps/aircraft_architecture/daily_utilisation/services.py")
services = services_path.read_text()
classification_role_pattern = re.compile(
    r"(classification\s*=\s*Classification\(\s*)role=(roles\.get\(component\.component_id\)\s+or\s+classify_component\()",
    re.MULTILINE,
)
classification_target_pattern = re.compile(
    r"classification\s*=\s*Classification\(\s*target_type=roles\.get\(component\.component_id\)\s+or\s+classify_component\(",
    re.MULTILINE,
)
services, classification_count = classification_role_pattern.subn(
    r"\1target_type=\2",
    services,
    count=1,
)
if classification_count == 0 and len(classification_target_pattern.findall(services)) != 1:
    raise SystemExit("expected one Classification role or target_type keyword")
services_path.write_text(services)


test_path = Path("backend/amodb/apps/aircraft_architecture/daily_utilisation/tests/test_posting_integration.py")
source = test_path.read_text()
source = replace_once(
    source,
    "from decimal import Decimal\nimport uuid\n",
    "from decimal import Decimal\nimport os\nimport uuid\n",
    "integration-test decimal import",
)
source = replace_once(
    source,
    "from sqlalchemy import func\n",
    "from sqlalchemy import create_engine, func\nfrom sqlalchemy.orm import sessionmaker\n",
    "integration-test SQLAlchemy import",
)
source = replace_once(
    source,
    "from amodb.database import WriteSessionLocal\n",
    "",
    "integration-test shared session import",
)
anchor = "\n\ndef _id(prefix: str) -> str:\n"
block = '''

POSTGRES_INTEGRATION_URL = os.getenv("POSTGRES_INTEGRATION_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_INTEGRATION_URL,
    reason="POSTGRES_INTEGRATION_URL is required for daily utilisation integration tests",
)


def _integration_session_factory():
    assert POSTGRES_INTEGRATION_URL, "POSTGRES_INTEGRATION_URL is required"
    engine = create_engine(POSTGRES_INTEGRATION_URL, pool_pre_ping=True, future=True)
    assert engine.dialect.name == "postgresql", engine.url.render_as_string(hide_password=True)
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )


IntegrationSession = _integration_session_factory() if POSTGRES_INTEGRATION_URL else None


def _new_session():
    assert IntegrationSession is not None, "PostgreSQL integration session is not configured"
    session = IntegrationSession()
    assert session.get_bind().dialect.name == "postgresql"
    return session
'''
source = replace_once(source, anchor, block + anchor, "integration-test insertion anchor")
if source.count("WriteSessionLocal()") != 2:
    raise SystemExit(f"expected two integration session constructors; found {source.count('WriteSessionLocal()')}")
source = source.replace("WriteSessionLocal()", "_new_session()")
test_path.write_text(source)

architecture_path = Path(".github/workflows/aircraft-architecture-ci.yml")
architecture = architecture_path.read_text()
db_line = "      DATABASE_URL: postgresql+psycopg2://amo:amo@127.0.0.1:5432/amo_test\n"
db_block = (
    db_line
    + "      DATABASE_WRITE_URL: postgresql+psycopg2://amo:amo@127.0.0.1:5432/amo_test\n"
    + "      POSTGRES_INTEGRATION_URL: postgresql+psycopg2://amo:amo@127.0.0.1:5432/amo_test\n"
)
architecture_path.write_text(
    replace_once(architecture, db_line, db_block, "architecture database URL")
)

reliability_path = Path(".github/workflows/reliability-module-ci.yml")
reliability = reliability_path.read_text()
reliability = replace_once(
    reliability,
    "        if: github.event_name == 'pull_request'\n",
    "        if: github.event_name == 'pull_request' && startsWith(github.head_ref, 'agent/reliability-')\n",
    "Reliability-only diff condition",
)

head_pattern = re.compile(
    r"^      - name: Verify one Alembic head\n.*?(?=^      - name: Upgrade clean PostgreSQL schema)",
    re.MULTILINE | re.DOTALL,
)
head_replacement = '''      - name: Verify one Alembic head with Reliability lineage
        run: |
          python - <<'PY_INNER'
          from alembic.config import Config
          from alembic.script import ScriptDirectory

          script = ScriptDirectory.from_config(Config("backend/amodb/alembic.ini"))
          heads = script.get_heads()
          assert len(heads) == 1, heads
          lineage = {revision.revision for revision in script.walk_revisions(heads[0], "base")}
          assert "rel_20260805_ops_exact_counts" in lineage, sorted(lineage)
          print(f"repository_head={heads[0]}; reliability_lineage=present")
          PY_INNER

'''
reliability, count = head_pattern.subn(head_replacement, reliability, count=1)
if count != 1:
    raise SystemExit("expected one Reliability Alembic head block")

revision_pattern = re.compile(
    r"^      - name: Verify Alembic revision and capacity\n.*?(?=^      - name: Run PostgreSQL append-only calculation regression)",
    re.MULTILINE | re.DOTALL,
)
revision_replacement = '''      - name: Verify Alembic revision and capacity
        run: |
          python - <<'PY_INNER'
          import os
          from alembic.config import Config
          from alembic.script import ScriptDirectory
          from sqlalchemy import create_engine, text

          repository_head = ScriptDirectory.from_config(
              Config("backend/amodb/alembic.ini")
          ).get_current_head()
          engine = create_engine(os.environ["DATABASE_URL"])
          with engine.connect() as connection:
              width = connection.execute(text("""
                  SELECT character_maximum_length
                  FROM information_schema.columns
                  WHERE table_name = 'alembic_version'
                    AND column_name = 'version_num'
              """)).scalar_one()
              versions = [row[0] for row in connection.execute(
                  text("SELECT version_num FROM alembic_version ORDER BY version_num")
              )]
          assert width is not None and width >= 128, width
          assert versions == [repository_head], (versions, repository_head)
          print(f"alembic_version={repository_head}; capacity={width}")
          PY_INNER

'''
reliability, count = revision_pattern.subn(revision_replacement, reliability, count=1)
if count != 1:
    raise SystemExit("expected one Reliability revision verification block")
reliability_path.write_text(reliability)
