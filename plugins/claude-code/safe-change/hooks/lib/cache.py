"""Per-table session cache backed by temp files.

All state lives under /tmp/mc_safe_change_*. No external dependencies.
Cleans up naturally on reboot.

Impact check gate uses three states:
  absent -> injected (instruction sent, waiting for completion)
  injected -> verified (MC_IMPACT_CHECK_COMPLETE marker found in transcript)
"""
import hashlib
import json
import os
import re
import time

CACHE_DIR = "/tmp"
_FILE_PERMISSIONS = 0o600  # Owner read/write only
_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
IC_PREFIX = "mc_safe_change_ic_"
MG_PREFIX = "mc_safe_change_mg_"
TURN_PREFIX = "mc_safe_change_turn_"
PENDING_PREFIX = "mc_safe_change_pending_"
DBT_CONFIG_PREFIX = "mc_safe_change_dbt_config_"
CLEANUP_MARKER = "mc_safe_change_last_cleanup"

ALL_PREFIXES = (IC_PREFIX, MG_PREFIX, TURN_PREFIX, PENDING_PREFIX, DBT_CONFIG_PREFIX)
STALE_THRESHOLD_SECONDS = 6 * 3600  # 6 hours — covers long sessions, cleans between days

# dbt_project.yml defaults per https://docs.getdbt.com/reference/project-configs
DBT_DEFAULT_PATHS = {
    "model-paths": ["models"],
    "macro-paths": ["macros"],
    "snapshot-paths": ["snapshots"],
    "seed-paths": ["seeds"],
    "analysis-paths": ["analyses"],
}


def _write_secure(path: str, content: str) -> None:
    """Write content to path and restrict permissions to owner-only."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _FILE_PERMISSIONS)
    try:
        os.write(fd, content.encode())
    finally:
        os.close(fd)


def _append_secure(path: str, content: str) -> None:
    """Append content to path, creating with restricted permissions if needed."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, _FILE_PERMISSIONS)
    try:
        os.write(fd, content.encode())
    finally:
        os.close(fd)


def _validate_session_id(session_id: str) -> str:
    """Validate session_id is alphanumeric with dashes/underscores only."""
    if not _SESSION_ID_RE.match(session_id):
        raise ValueError(f"Invalid session_id: {session_id!r}")
    return session_id


def _w4_path(table_name: str) -> str:
    return os.path.join(CACHE_DIR, f"{IC_PREFIX}{table_name}")


def _turn_path(session_id: str) -> str:
    return os.path.join(CACHE_DIR, f"{TURN_PREFIX}{_validate_session_id(session_id)}")


def _pending_path(session_id: str) -> str:
    return os.path.join(CACHE_DIR, f"{PENDING_PREFIX}{_validate_session_id(session_id)}")


# --- Impact check three-state marker ---

def get_impact_check_state(table_name: str) -> str | None:
    """Returns None, 'injected', or 'verified'."""
    path = _w4_path(table_name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return data.get("state")
    except (json.JSONDecodeError, OSError):
        return None


def mark_impact_check_injected(table_name: str) -> None:
    path = _w4_path(table_name)
    _write_secure(path, json.dumps({"state": "injected", "timestamp": time.time()}))


def mark_impact_check_verified(table_name: str) -> None:
    path = _w4_path(table_name)
    # Preserve timestamp from injection
    timestamp = time.time()
    try:
        with open(path, "r") as f:
            data = json.load(f)
            timestamp = data.get("timestamp", timestamp)
    except (json.JSONDecodeError, OSError):
        pass
    _write_secure(path, json.dumps({"state": "verified", "timestamp": timestamp}))


def get_impact_check_age_seconds(table_name: str) -> float:
    path = _w4_path(table_name)
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return time.time() - data.get("timestamp", time.time())
    except (json.JSONDecodeError, OSError):
        return 0.0


# --- Monitor coverage gap marker ---

def _mg_path(table_name: str) -> str:
    return os.path.join(CACHE_DIR, f"{MG_PREFIX}{table_name}")


def has_monitor_gap(table_name: str) -> bool:
    return os.path.exists(_mg_path(table_name))


def mark_monitor_gap(table_name: str) -> None:
    _write_secure(_mg_path(table_name), str(time.time()))


# --- Turn-level edit accumulator ---

def get_edited_tables(session_id: str) -> list[str]:
    path = _turn_path(session_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            tables = [line.strip() for line in f if line.strip()]
        return list(dict.fromkeys(tables))  # deduplicate, preserve order
    except OSError:
        return []


def add_edited_table(session_id: str, table_name: str) -> None:
    existing = get_edited_tables(session_id)
    if table_name in existing:
        return
    path = _turn_path(session_id)
    _append_secure(path, table_name + "\n")


def clear_edited_tables(session_id: str) -> None:
    path = _turn_path(session_id)
    if os.path.exists(path):
        os.remove(path)


# --- Pending validation ---

def move_to_pending_validation(session_id: str) -> None:
    tables = get_edited_tables(session_id)
    if tables:
        existing = get_pending_validation_tables(session_id)
        merged = list(dict.fromkeys(existing + tables))  # deduplicate, preserve order
        path = _pending_path(session_id)
        _write_secure(path, "".join(t + "\n" for t in merged))
    clear_edited_tables(session_id)


def get_pending_validation_tables(session_id: str) -> list[str]:
    path = _pending_path(session_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            return [line.strip() for line in f if line.strip()]
    except OSError:
        return []


def clear_pending_validation(session_id: str) -> None:
    path = _pending_path(session_id)
    if os.path.exists(path):
        os.remove(path)


# --- dbt project config cache ---

def _find_dbt_project_yml(file_path: str) -> str | None:
    """Walk up from file_path to find dbt_project.yml."""
    directory = os.path.dirname(os.path.abspath(file_path))
    while True:
        candidate = os.path.join(directory, "dbt_project.yml")
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent


def _dbt_config_cache_path(project_yml_path: str) -> str:
    """Stable cache path for a given dbt_project.yml location."""
    key = hashlib.md5(project_yml_path.encode()).hexdigest()[:12]
    return os.path.join(CACHE_DIR, f"{DBT_CONFIG_PREFIX}{key}")


def _parse_dbt_project_paths(project_yml_path: str) -> dict:
    """Parse path configs from dbt_project.yml without importing PyYAML.

    Only extracts top-level keys like 'model-paths: [...]'. Handles both
    YAML list syntax forms:
      model-paths: ['models', 'other']
      model-paths:
        - models
        - other
    """
    result = {}
    try:
        with open(project_yml_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError):
        return result

    current_key = None
    for line in lines:
        stripped = line.strip()
        # Check for inline list: key: ['a', 'b'] or key: [a, b]
        for key in DBT_DEFAULT_PATHS:
            if stripped.startswith(f"{key}:"):
                value_part = stripped[len(key) + 1:].strip()
                if value_part.startswith("["):
                    # Inline list — parse items between [ ]
                    inner = value_part.strip("[]")
                    items = [
                        item.strip().strip("'\"")
                        for item in inner.split(",")
                        if item.strip()
                    ]
                    if items:
                        result[key] = items
                    current_key = None
                elif not value_part or value_part == "":
                    # Block list follows on next lines
                    current_key = key
                    result[key] = []
                break
        else:
            # Check for block list continuation: - item
            if current_key and stripped.startswith("- "):
                item = stripped[2:].strip().strip("'\"")
                if item:
                    result.setdefault(current_key, []).append(item)
            elif current_key and not stripped.startswith("#") and stripped:
                # Non-list, non-comment line — end of block list
                current_key = None

    return result


def get_dbt_paths(file_path: str) -> dict:
    """Get dbt project paths for the project containing file_path.

    Returns dict with keys: model-paths, macro-paths, snapshot-paths,
    seed-paths, analysis-paths. Uses cached result if dbt_project.yml
    hasn't changed (same mtime).

    Returns defaults if no dbt_project.yml found.
    """
    project_yml = _find_dbt_project_yml(file_path)
    if not project_yml:
        return dict(DBT_DEFAULT_PATHS)

    cache_path = _dbt_config_cache_path(project_yml)
    mtime = os.path.getmtime(project_yml)

    # Check cache
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                cached = json.load(f)
            if cached.get("mtime") == mtime:
                return cached.get("paths", dict(DBT_DEFAULT_PATHS))
        except (json.JSONDecodeError, OSError):
            pass

    # Parse and cache
    parsed = _parse_dbt_project_paths(project_yml)
    paths = dict(DBT_DEFAULT_PATHS)
    paths.update(parsed)

    try:
        _write_secure(cache_path, json.dumps({"mtime": mtime, "paths": paths}))
    except OSError:
        pass

    return paths


# --- Lazy cleanup ---

def cleanup_stale_cache() -> None:
    """Remove mc_safe_change_* files older than STALE_THRESHOLD_SECONDS.

    Runs at most once per hour (tracked via CLEANUP_MARKER file).
    Call from any hook — it short-circuits quickly if cleanup ran recently.
    """
    marker_path = os.path.join(CACHE_DIR, CLEANUP_MARKER)
    now = time.time()

    # Check if cleanup ran recently (within 1 hour)
    if os.path.exists(marker_path):
        try:
            marker_mtime = os.path.getmtime(marker_path)
            if now - marker_mtime < 3600:
                return
        except OSError:
            pass

    # Touch marker first to prevent concurrent cleanup
    try:
        _write_secure(marker_path, str(now))
    except OSError:
        return

    # Scan /tmp for our files and remove stale ones
    try:
        for filename in os.listdir(CACHE_DIR):
            if not any(filename.startswith(prefix) for prefix in ALL_PREFIXES):
                continue
            filepath = os.path.join(CACHE_DIR, filename)
            try:
                file_mtime = os.path.getmtime(filepath)
                if now - file_mtime > STALE_THRESHOLD_SECONDS:
                    os.remove(filepath)
            except OSError:
                continue
    except OSError:
        pass
