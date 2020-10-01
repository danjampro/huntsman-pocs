"""
Simple script to connect to cameras and use them to take exposures.
"""
import os
import time
import argparse
from contextlib import suppress
from huntsman.pocs.utils import load_config
from huntsman.pocs.camera import create_cameras_from_config


def take_exposure(cameras, config, exptime=15, max_wait=30):
    """
    Take a blocking exposure on all the cameras.
    """
    # output_dir = os.path.join(config["directories"]["images"], "zwo_testing")
    output_dir = "/home/huntsman/zwo_testing"  # Don't write over network as it takes too long
    with suppress(FileExistsError):
        os.mkdir(output_dir)
    events = []
    filenames = []
    # Start for the exposures
    for i, camera in enumerate(cameras.values()):
        filename = os.path.join(output_dir, f"test_{i}.fits")
        filenames.append(filename)
        with suppress(FileNotFoundError):
            os.remove(filename)
        events.append(camera.take_exposure(filename=filename, seconds=exptime, blocking=False))
    # Wait for exposures
    timer = 0
    while not all([e.is_set() for e in events]):
        print("Waiting for exposures...")
        if timer > exptime + max_wait:
            raise RuntimeError("Timeout!")
        timer += 1
        time.sleep(1)
    # Clean-up files
    for filename in filenames:
        with suppress(FileNotFoundError):
            os.remove(filename)


def prepare_cameras(cameras):
    """
    Cool cameras and prepare FWs.
    """
    for camera in cameras.values():
        camera.cooling_enabled = True
        camera.filterwheel.move_to("blank", blocking=False)
    while not all([c.is_ready for c in cameras.values()]):
        print("Waiting for cameras...")
        time.sleep(5)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('--exposure_time', default=1)

    args = parser.parse_args()
    exposure_time = float(args.exposure_time)

    config = load_config()

    # Create the cameras
    cameras = create_cameras_from_config(config=config)
    prepare_cameras(cameras)

    # Start the exposure sequence
    while True:
        take_exposure(cameras, config, exptime=exposure_time)
