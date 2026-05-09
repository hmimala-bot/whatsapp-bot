import logging
import sys


def _build_logger(name: str) -> logging.Logger:
    log = logging.getLogger(name)
    log.setLevel(logging.INFO)
    if not log.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        log.addHandler(handler)
    return log


logger = _build_logger("hammam_ai")
