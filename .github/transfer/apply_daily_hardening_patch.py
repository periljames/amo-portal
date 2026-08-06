from pathlib import Path
import re


def replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise SystemExit(f"expected one {label}; found {source.count(old)}")
    return source.replace(old, new)


def ensure_fixture_component_kind(
    source: str,
    position_prefix: str,
    component_kind: str,
) -> str:
    pattern = re.compile(
        rf'(?m)^(?P<indent>[ \t]*)position="(?P<position>{re.escape(position_prefix)}-\d+)",'
    )
    matches = list(pattern.finditer(source))
    if not matches:
        raise SystemExit(
            f"expected at least one {component_kind} fixture position with prefix {position_prefix}"
        )

    result: list[str] = []
    cursor = 0
    inserted = 0
    accepted = 0
    for match in matches:
        constructor_start = source.rfind("FleetComponent(", 0, match.start())
        if constructor_start < 0:
            raise SystemExit(
                f"could not locate FleetComponent constructor for {match.group('position')}"
            )
        constructor_prefix = source[constructor_start:match.start()]
        existing = re.search(
            r'(?m)^\s*component_kind\s*=\s*["\'](?P<kind>[A-Z_]+)["\']\s*,',
            constructor_prefix,
        )

        result.append(source[cursor:match.start()])
        if existing:
            if existing.group("kind") != component_kind:
                raise SystemExit(
                    f"fixture {match.group('position')} has component_kind="
                    f"{existing.group('kind')}, expected {component_kind}"
                )
            accepted += 1
        else:
            result.append(
                f'{match.group("indent")}component_kind="{component_kind}",\n'
            )
            inserted += 1
        result.append(source[match.start():match.end()])
        cursor = match.end()

    result.append(source[cursor:])
    print(
        f"{component_kind} fixture roles: inserted={inserted}; already_correct={accepted}"
    )
    return "".join(result)


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
if classification_count == 0:
    target_count = len(classification_target_pattern.findall(services))
    if target_count == 1:
        pass
    elif target_count == 0 and "Classification" not in services and "classify_component" not in services:
        print("classification keyword correction is not applicable to this reviewed bundle")
    else:
        lines = services.splitlines()
        contexts = []
        for index, line in enumerate(lines):
            if "Classification" in line or "classify_component" in line:
                start = max(0, index - 4)
                end = min(len(lines), index + 10)
                contexts.append(
                    f"lines {start + 1}-{end}:\n"
                    + "\n".join(f"{line_number + 1}: {lines[line_number]}" for line_number in range(start, end))
                )
        detail = "\n---\n".join(contexts[:8]) or "no Classification/classify_component context found"
        raise SystemExit(
            f"ambiguous Classification correction state: target_count={target_count}\n" + detail
        )
services_path.write_text(services)


migration_path = Path(
    "backend/amodb/alembic/versions/aircraft_arch_20260805_daily_utilisation.py"
)
migration = migration_path.read_text()
payload_hash_pattern = re.compile(
    r'(sa\.Column\(\s*["\']payload_hash["\']\s*,\s*)sa\.String\(\)(\s*,)',
    re.MULTILINE,
)
migration, payload_hash_count = payload_hash_pattern.subn(
    r"\1sa.String(length=64)\2",
    migration,
    count=1,
)
if payload_hash_count == 0:
    corrected_payload_hash_pattern = re.compile(
        r'sa\.Column\(\s*["\']payload_hash["\']\s*,\s*sa\.String\(\s*(?:length\s*=\s*)?64\s*\)',
        re.MULTILINE,
    )
    if len(corrected_payload_hash_pattern.findall(migration)) != 1:
        raise SystemExit("expected exactly one bounded payload_hash column")
migration_path.write_text(migration)


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
source = ensure_fixture_component_kind(source, "ENG", "ENGINE")
source = ensure_fixture_component_kind(source, "PROP", "PROPELLER")
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
