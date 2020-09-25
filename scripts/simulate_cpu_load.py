"""Simple program to take up CPU and some RAM."""

from multiprocessing import Pool
import numpy as np


def func(x):
    while True:
        data = np.random.normal(0, 1, shape=(5500, 2500))
        data = data * data


if __name__ == "__main__":

    with Pool(4) as pool:
        pool.map(func, [_ for _ in range(4)])
