import logging
from pythonjsonlogger import jsonlogger


def setup_logging(level: str = "INFO"):
    logger = logging.getLogger()
    logger.setLevel(level)
    logHandler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    logHandler.setFormatter(formatter)
    logger.addHandler(logHandler)
    return logger

