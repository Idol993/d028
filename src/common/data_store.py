import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from hashlib import sha256

from .config_loader import ConfigLoader


class DataStore:
    def __init__(self):
        self.config = ConfigLoader()
        base_path = self.config.get("storage.base_path", "./data")
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

        self.audit_path = self.base_path / "audit_logs"
        self.report_path = self.base_path / "reports"
        self.release_path = self.base_path / "releases"
        self.drill_path = self.base_path / "drills"

        for p in [self.audit_path, self.report_path, self.release_path, self.drill_path]:
            p.mkdir(exist_ok=True)

    def _compute_hash(self, data: Dict[str, Any]) -> str:
        sorted_data = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return sha256(sorted_data.encode("utf-8")).hexdigest()

    def save_release_record(self, release_id: str, record: Dict[str, Any]) -> str:
        record["release_id"] = release_id
        record["saved_at"] = datetime.now().isoformat()
        record["hash"] = self._compute_hash({k: v for k, v in record.items() if k != "hash"})

        file_path = self.release_path / f"{release_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        return str(file_path)

    def get_release_record(self, release_id: str) -> Optional[Dict[str, Any]]:
        file_path = self.release_path / f"{release_id}.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def list_release_records(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        records = []
        for file_path in sorted(self.release_path.glob("*.json"), reverse=True):
            with open(file_path, "r", encoding="utf-8") as f:
                record = json.load(f)
                if self._match_filters(record, filters):
                    records.append(record)
        return records

    def _match_filters(self, record: Dict[str, Any], filters: Optional[Dict[str, Any]]) -> bool:
        if not filters:
            return True
        for key, value in filters.items():
            if key not in record:
                return False
            if isinstance(value, list):
                if record[key] not in value:
                    return False
            elif record[key] != value:
                return False
        return True

    def save_audit_log(self, audit_entry: Dict[str, Any]) -> str:
        audit_entry["timestamp"] = audit_entry.get("timestamp", datetime.now().isoformat())
        audit_entry["hash"] = self._compute_hash({k: v for k, v in audit_entry.items() if k != "hash"})

        date_str = datetime.now().strftime("%Y%m%d")
        file_path = self.audit_path / f"audit_{date_str}.jsonl"

        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")

        return str(file_path)

    def query_audit_logs(self, start_time: Optional[str] = None,
                         end_time: Optional[str] = None,
                         operation: Optional[str] = None,
                         operator: Optional[str] = None) -> List[Dict[str, Any]]:
        results = []
        for file_path in sorted(self.audit_path.glob("audit_*.jsonl")):
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if self._audit_match(entry, start_time, end_time, operation, operator):
                            results.append(entry)
                    except json.JSONDecodeError:
                        continue
        return sorted(results, key=lambda x: x.get("timestamp", ""))

    def _audit_match(self, entry: Dict[str, Any], start_time: Optional[str],
                     end_time: Optional[str], operation: Optional[str],
                     operator: Optional[str]) -> bool:
        ts = entry.get("timestamp", "")
        if start_time and ts < start_time:
            return False
        if end_time and ts > end_time:
            return False
        if operation and entry.get("operation") != operation:
            return False
        if operator and entry.get("operator") != operator:
            return False
        return True

    def save_drill_record(self, drill_id: str, record: Dict[str, Any]) -> str:
        record["drill_id"] = drill_id
        record["saved_at"] = datetime.now().isoformat()

        file_path = self.drill_path / f"{drill_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        return str(file_path)

    def list_drill_records(self) -> List[Dict[str, Any]]:
        records = []
        for file_path in sorted(self.drill_path.glob("*.json"), reverse=True):
            with open(file_path, "r", encoding="utf-8") as f:
                records.append(json.load(f))
        return records

    def save_report(self, report_name: str, report_data: Any) -> str:
        file_path = self.report_path / report_name
        if isinstance(report_data, (dict, list)):
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
        else:
            with open(file_path, "wb") as f:
                f.write(report_data if isinstance(report_data, bytes) else str(report_data).encode("utf-8"))
        return str(file_path)
