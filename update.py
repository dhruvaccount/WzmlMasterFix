"""
WZML-X Update Script

Handles runtime updates from upstream Git repository.
Can be run standalone: python update.py
"""

import os
import sys
import logging
from subprocess import run as srun, call as scall

logging.basicConfig(
    format="[%(asctime)s] [%(levelname)s] - %(message)s",
    datefmt="%d-%b-%y %I:%M:%S %p",
    level=logging.INFO,
)
logger = logging.getLogger("wzml.update")


def main():
    logger.info("=" * 50)
    logger.info("WZML-X Update Check")
    logger.info("=" * 50)

    try:
        from config import get_config

        config = get_config()
        config.load_all()
    except Exception as e:
        logger.error(f"Config load error: {e}")
        sys.exit(1)

    telegram_config = config.telegram
    database_config = config.database

    if not telegram_config.BOT_TOKEN:
        logger.error("BOT_TOKEN not configured!")
        sys.exit(1)

    bot_id = telegram_config.BOT_TOKEN.split(":")[0]

    upstream_repo = os.environ.get("UPSTREAM_REPO", "")
    upstream_branch = os.environ.get("UPSTREAM_BRANCH", "wzv3")
    update_pkgs = os.environ.get("UPDATE_PKGS", "True")

    if database_config.DATABASE_URL:
        try:
            from pymongo import MongoClient
            from pymongo.server_api import ServerApi

            conn = MongoClient(
                database_config.DATABASE_URL, server_api=ServerApi("1")
            )
            db = conn.wzmlx

            deploy_config = db.settings.deployConfig.find_one(
                {"_id": bot_id}, {"_id": 0}
            )
            stored_config = db.settings.config.find_one({"_id": bot_id})

            if stored_config:
                upstream_repo = stored_config.get("UPSTREAM_REPO", upstream_repo)
                upstream_branch = stored_config.get(
                    "UPSTREAM_BRANCH", upstream_branch
                )
                update_pkgs = stored_config.get("UPDATE_PKGS", update_pkgs)

            conn.close()
            logger.info("Loaded config from database")
        except Exception as e:
            logger.warning(f"Database config error: {e}")

    if upstream_repo:
        logger.info(f"Upstream repo: {upstream_repo}")
        logger.info(f"Upstream branch: {upstream_branch}")

        if os.path.exists(".git"):
            srun(["rm", "-rf", ".git"], shell=True)

        git_cmd = f"""
git init -q
&& git config --global user.email update@wzml-x
&& git config --global user.name WZML-X
&& git add .
&& git commit -sm update -q
&& git remote add origin {upstream_repo}
&& git fetch origin -q
&& git reset --hard origin/{upstream_branch} -q
"""
        result = srun([git_cmd], shell=True)

        if result.returncode == 0:
            logger.info("Successfully updated from upstream!")
        else:
            logger.error("Update failed! Check upstream repo/branch")

        repo = upstream_repo.split("/")
        upstream_repo = f"https://github.com/{repo[-2]}/{repo[-1]}"
        logger.info(f"UPSTREAM_REPO: {upstream_repo} | UPSTREAM_BRANCH: {upstream_branch}")

    if update_pkgs and str(update_pkgs).lower() == "true":
        logger.info("Updating Python packages...")
        scall("uv pip install -U -r requirements.txt", shell=True)
        logger.info("Packages updated!")

    logger.info("=" * 50)
    logger.info("Update complete!")
    logger.info("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Interrupted")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)