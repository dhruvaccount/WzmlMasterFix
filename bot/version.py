from subprocess import run as srun

from bot.helper.ext_utils.bot_utils import new_task, sync_to_async

_git_hash = ""
_repo_url = ""
_commit_message = ""
_commit_time = ""


async def _run_git(args):
    proc = await sync_to_async(srun, args, capture_output=True, text=True, timeout=5)
    return proc.stdout.strip()


@new_task
async def _init_git_info():
    global _git_hash, _repo_url, _commit_message, _commit_time
    try:
        _git_hash = await _run_git(["git", "rev-parse", "--short", "HEAD"])
    except Exception:
        _git_hash = "unknown"
    try:
        url = await _run_git(["git", "remote", "get-url", "origin"])
        if url.startswith("https://") and "@" in url:
            url = "https://" + url.split("@", 1)[1]
        _repo_url = url.rstrip(".git")
    except Exception:
        _repo_url = ""
    try:
        _commit_message = await _run_git(
            ["git", "log", "-1", "--format=%s"]
        )
    except Exception:
        _commit_message = ""
    try:
        _commit_time = await _run_git(
            ["git", "log", "-1", "--format=%ci"]
        )
    except Exception:
        _commit_time = ""


_init_git_info()


def get_commit_hash():
    return _git_hash or "unknown"


def get_commit_url():
    h = get_commit_hash()
    if _repo_url and h != "unknown":
        return f"{_repo_url}/commit/{h}"
    return ""


def get_commit_message():
    return _commit_message or ""


def get_commit_time():
    return _commit_time or ""


def get_version() -> str:
    """
    Returns the version details. Do not Interfere with this !

    :return: The version details in the format 'vMAJOR.MINOR.PATCH-STATE'
    :rtype: str
    """
    MAJOR = "3"
    MINOR = "1"
    PATCH = "7"
    STATE = "x"
    return f"v{MAJOR}.{MINOR}.{PATCH}-{STATE}"


if __name__ == "__main__":
    print(get_version())
