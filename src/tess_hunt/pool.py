"""Process pools for the stages."""

import multiprocessing
from concurrent.futures import ProcessPoolExecutor


def process_pool(workers: int) -> ProcessPoolExecutor:
    # Forking a parent that has started threads (astroquery, numba) can deadlock a child; spawn starts
    # clean and passes os.environ, so TESS_HUNT_DATA reaches every worker.
    return ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"))
