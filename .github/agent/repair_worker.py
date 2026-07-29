from pathlib import Path
import re

path = Path("backend/amodb/jobs/saas_worker_safe.py")
worker = path.read_text(encoding="utf-8")
worker = re.sub(r"(?m)^logger = logging\.getLogger\(__name__\)\n?", "", worker)
worker, count = re.subn(
    r"def _worker_id\(\) -> str:[\s\S]*?\n\ndef _record_worker_heartbeat",
    "def _worker_id() -> str:\n"
    "    return os.getenv(\"SAAS_WORKER_ID\") or f\"{socket.gethostname()}:{os.getpid()}\"\n\n\n"
    "def _record_worker_heartbeat",
    worker,
    count=1,
)
if count != 1:
    raise RuntimeError("safe worker identity block was not found")
anchor = "from amodb.database import WriteSessionLocal, close_session_safely\n"
if "logger = logging.getLogger(__name__)" not in worker:
    if anchor not in worker:
        raise RuntimeError("safe worker import anchor was not found")
    worker = worker.replace(anchor, anchor + "\n\nlogger = logging.getLogger(__name__)\n", 1)
path.write_text(worker, encoding="utf-8")
