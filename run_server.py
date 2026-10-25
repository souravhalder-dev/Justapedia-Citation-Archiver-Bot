"""Local server runner for Justapedia Archiver Bot API and UI."""

import uvicorn
from bot.logging_config import logger

if __name__ == "__main__":
    logger.info("Starting Justapedia Archiver Bot Server on http://127.0.0.1:8080 ...")
    uvicorn.run("api.app:app", host="127.0.0.1", port=8080, reload=False)
