"""
Script to test whether camera polling frequency affects error rate.

The idea is to take a series of exposures with a given camera, recording the time the camera fails.
"""
import os
import csv
import time
from astropy import units as u

from pocs.utils import error
from pocs.utils import CountdownTimer
from pocs.camera.zwo import Camera as ZWOCamera
from pocs.camera.libasi import ASIDriver


DEFAULT_POLLING_INTERVAL = 0.01


class Camera(ZWOCamera):
    """

    """
    _driver = ZWOCamera._driver
    _temp_image_filename = "/tmp/tempdata.fits"

    def __init__(self, polling_interval=DEFAULT_POLLING_INTERVAL, **kwargs):
        super().__init__(**kwargs)
        self._polling_interval = polling_interval
        # Save the record somewhere it's easily accessible outside of docker
        self._record_filename = os.path.join(self.config["directories"]["images"],
                                             f"polltest_{self._serial_number}.csv")

    def _poll_exposure(self, readout_args):
        """Override to include `self._polling_interval`."""
        timer = CountdownTimer(duration=self._timeout)
        try:
            while self.is_exposing:
                if timer.expired():
                    msg = "Timeout waiting for exposure on {} to complete".format(self)
                    raise error.Timeout(msg)
                time.sleep(self._polling_interval)  # <---------- This is the only difference
        except (RuntimeError, error.PanError) as err:
            # Error returned by driver at some point while polling
            self.logger.error('Error while waiting for exposure on {}: {}'.format(self, err))
            raise err
        else:
            # Camera type specific readout function
            self._readout(*readout_args)
        finally:
            self._exposure_event.set()  # Make sure this gets set regardless of readout errors

    def take_exposure_series(self, max_exposures=100, exposure_time=1*u.second,
                             filter_name="blank"):
        """
        Take a series of blocking exposues on the camera, each time deleting the resulting file. Do
        this max_exposures times, or until it breaks. Record the polling interval and final number
        of exposures.
        """
        # Move the filterwheel
        self.filterwheel.move_to(filter_name)

        # Start the exposure series
        for exp_num in range(1, max_exposures+1):
            try:
                self.take_exposure(filename=self._temp_image_filename, exposure_time=exposure_time,
                                   blocking=True)
                os.remove(self._temp_image_filename)
            except error.PanError as err:
                self.logger.info(f"Error on {self} after {exp_num} exposures with polling"
                                 f" interval={self._polling_interval}: {err}.")
                break

        # Log the number of exposures before error
        with open(self._record_filename, "a") as f:
            writer = csv.writer(f)
            writer.writerow([f"{self._polling_interval:0.3f}", f"{exp_num}"])


if __name__ == "__main__":

    serial_number = "361d420013090900"  # Pi1
    polling_interval = DEFAULT_POLLING_INTERVAL

    # Create the camera
    camera = Camera(serial_number=serial_number, polling_interval=polling_interval)

    # Take the exposure series
    camera.take_exposure_series()
