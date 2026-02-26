import logging
from pythonjsonlogger import jsonlogger


def setup_logging(level: str = "INFO"):
    root = logging.getLogger()
    root.setLevel(level)
    # Avoid adding multiple handlers if already configured
    if any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        return root
    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)
    root.addHandler(handler)
    return root

