"""
Script to test whether camera polling frequency affects error rate.

The idea is to take a series of exposures with a given camera, recording the time the camera fails.
"""
import os
import csv
import time
import threading
from contextlib import suppress
import numpy as np
from astropy import units as u
from astropy.time import Time

from pocs.utils import error
from pocs.utils import CountdownTimer
from pocs.camera.sdk import AbstractSDKCamera
from pocs.camera.libasi import ASIDriver
from pocs.utils import get_quantity_value
from pocs.utils.images import fits as fits_utils
from huntsman.pocs.utils.config import load_device_config

DEFAULT_POLLING_INTERVAL = 0.01


class Camera(AbstractSDKCamera):

    _driver = None  # Class variable to store the ASI driver interface
    _cameras = []  # Cache of camera string IDs
    _assigned_cameras = set()  # Camera string IDs already in use.
    _temp_image_filename = "/tmp/polltest.fits"

    def __init__(self, name='ZWO ASI Camera', gain=None, image_type=None,
                 polling_interval=DEFAULT_POLLING_INTERVAL, *args, **kwargs):
        """
        ZWO ASI Camera class

        Args:
            serial_number (str): camera serial number or user set ID (up to 8 bytes). See notes.
            gain (int, optional): gain setting, using camera's internal units. If not given
                the camera will use its current or default setting.
            image_type (str, optional): image format to use (one of 'RAW8', 'RAW16', 'RGB24'
                or 'Y8'). Default is to use 'RAW16' if supported by the camera, otherwise
                the camera's own default will be used.
            *args, **kwargs: additional arguments to be passed to the parent classes.

        Notes:
            ZWO ASI cameras don't have a 'port', they only have a non-deterministic integer
            camera_ID and, probably, an 8 byte serial number. Optionally they also have an
            8 byte ID that can be written to the camera firmware by the user (using ASICap,
            or pocs.camera.libasi.ASIDriver.set_ID()). The camera should be identified by
            its serial number or, if it doesn't have one, by the user set ID.
        """
        kwargs['readout_time'] = kwargs.get('readout_time', 0.1)
        kwargs['timeout'] = kwargs.get('timeout', 0.5)

        self._video_event = threading.Event()

        super().__init__(name, ASIDriver, *args, **kwargs)

        # Increase default temperature_tolerance for ZWO cameras because the
        # default value is too low for their temperature resolution.
        self.temperature_tolerance = kwargs.get('temperature_tolerance', 0.6 * u.Celsius)

        if gain:
            self.gain = gain

        if image_type:
            self.image_type = image_type
        else:
            # Take monochrome 12 bit raw images by default, if we can
            if 'RAW16' in self.properties['supported_video_format']:
                self.image_type = 'RAW16'

        self._polling_interval = polling_interval       # <---------- This is the different
        # Save the record somewhere it's easily accessible outside of docker
        self._record_filename = f"/var/huntsman/logs/polltest_{self._serial_number}.csv"

        self.logger.info('{} initialised'.format(self))

    def __del__(self):
        """ Attempt some clean up """
        with suppress(AttributeError):
            camera_ID = self._handle
            Camera._driver.close_camera(camera_ID)
            self.logger.debug("Closed ZWO camera {}".format(camera_ID))
        super().__del__()

    # Properties

    @property
    def image_type(self):
        """ Current camera image type, one of 'RAW8', 'RAW16', 'Y8', 'RGB24' """
        roi_format = Camera._driver.get_roi_format(self._handle)
        return roi_format['image_type']

    @image_type.setter
    def image_type(self, new_image_type):
        if new_image_type not in self.properties['supported_video_format']:
            msg = "Image type '{} not supported by {}".format(new_image_type, self.model)
            self.logger.error(msg)
            raise ValueError(msg)
        roi_format = self._driver.get_roi_format(self._handle)
        roi_format['image_type'] = new_image_type
        Camera._driver.set_roi_format(self._handle, **roi_format)

    @property
    def bit_depth(self):
        """ADC bit depth"""
        return self.properties['bit_depth']

    @property
    def temperature(self):
        """ Current temperature of the camera's image sensor """
        return self._control_getter('TEMPERATURE')[0]

    @property
    def target_temperature(self):
        """ Current value of the target temperature for the camera's image sensor cooling control.

        Can be set by assigning an astropy.units.Quantity
        """
        return self._control_getter('TARGET_TEMP')[0]

    @target_temperature.setter
    def target_temperature(self, target):
        if not isinstance(target, u.Quantity):
            target = target * u.Celsius
        self.logger.debug("Setting {} cooling set point to {}".format(self, target))
        self._control_setter('TARGET_TEMP', target)

    @property
    def cooling_enabled(self):
        """ Current status of the camera's image sensor cooling system (enabled/disabled) """
        return self._control_getter('COOLER_ON')[0]

    @cooling_enabled.setter
    def cooling_enabled(self, enable):
        self._control_setter('COOLER_ON', enable)

    @property
    def cooling_power(self):
        """ Current power level of the camera's image sensor cooling system (as a percentage). """
        return self._control_getter('COOLER_POWER_PERC')[0]

    @property
    def gain(self):
        """ Current value of the camera's gain setting in internal units.

        See `egain` for the corresponding electrons / ADU value.
        """
        return self._control_getter('GAIN')[0]

    @gain.setter
    def gain(self, gain):
        self._control_setter('GAIN', gain)
        self._refresh_info()  # This will update egain value in self.properties

    @property
    def egain(self):
        """ Image sensor gain in e-/ADU for the current gain, as reported by the camera."""
        return self.properties['e_per_adu']

    @property
    def is_exposing(self):
        """ True if an exposure is currently under way, otherwise False """
        return Camera._driver.get_exposure_status(self._handle) == "WORKING"

    # Methods

    def connect(self):
        """
        Connect to ZWO ASI camera.

        Gets 'camera_ID' (needed for all driver commands), camera properties and details
        of available camera commands/parameters.
        """
        self.logger.debug("Connecting to {}".format(self))
        self._refresh_info()
        self._handle = self.properties['camera_ID']
        self.model, _, _ = self.properties['name'].partition('(')
        if self.properties['has_cooler']:
            self._is_cooled_camera = True
        if self.properties['is_color_camera']:
            self._filter_type = self.properties['bayer_pattern']
        else:
            self._filter_type = 'M'  # Monochrome
        Camera._driver.open_camera(self._handle)
        Camera._driver.init_camera(self._handle)
        self._control_info = Camera._driver.get_control_caps(self._handle)
        self._info['control_info'] = self._control_info  # control info accessible via properties
        Camera._driver.disable_dark_subtract(self._handle)
        self._connected = True

    def start_video(self, seconds, filename_root, max_frames, image_type=None):
        if not isinstance(seconds, u.Quantity):
            seconds = seconds * u.second
        self._control_setter('EXPOSURE', seconds)
        if image_type:
            self.image_type = image_type

        roi_format = Camera._driver.get_roi_format(self._handle)
        width = int(get_quantity_value(roi_format['width'], unit=u.pixel))
        height = int(get_quantity_value(roi_format['height'], unit=u.pixel))
        image_type = roi_format['image_type']

        timeout = 2 * seconds + self._timeout * u.second

        video_args = (width,
                      height,
                      image_type,
                      timeout,
                      filename_root,
                      self.file_extension,
                      int(max_frames),
                      self._create_fits_header(seconds, dark=False))
        video_thread = threading.Thread(target=self._video_readout,
                                        args=video_args,
                                        daemon=True)

        Camera._driver.start_video_capture(self._handle)
        self._video_event.clear()
        video_thread.start()
        self.logger.debug("Video capture started on {}".format(self))

    def stop_video(self):
        self._video_event.set()
        Camera._driver.stop_video_capture(self._handle)
        self.logger.debug("Video capture stopped on {}".format(self))

    # Private methods

    def _video_readout(self,
                       width,
                       height,
                       image_type,
                       timeout,
                       filename_root,
                       file_extension,
                       max_frames,
                       header):

        start_time = time.monotonic()
        good_frames = 0
        bad_frames = 0

        # Calculate number of bits that have been used to pad the raw data to RAW16 format.
        if self.image_type == 'RAW16':
            pad_bits = 16 - int(get_quantity_value(self.bit_depth, u.bit))
        else:
            pad_bits = 0

        for frame_number in range(max_frames):
            if self._video_event.is_set():
                break
            # This call will block for up to timeout milliseconds waiting for a frame
            video_data = Camera._driver.get_video_data(self._handle,
                                                       width,
                                                       height,
                                                       image_type,
                                                       timeout)
            if video_data is not None:
                now = Time.now()
                header.set('DATE-OBS', now.fits, 'End of exposure + readout')
                filename = "{}_{:06d}.{}".format(filename_root, frame_number, file_extension)
                # Fix 'raw' data scaling by changing from zero padding of LSBs
                # to zero padding of MSBs.
                video_data = np.right_shift(video_data, pad_bits)
                fits_utils.write_fits(video_data, header, filename)
                good_frames += 1
            else:
                bad_frames += 1

        if frame_number == max_frames - 1:
            # No one callled stop_video() before max_frames so have to call it here
            self.stop_video()

        elapsed_time = (time.monotonic() - start_time) * u.second
        self.logger.debug("Captured {} of {} frames in {:.2f} ({:.2f} fps), {} frames lost".format(
            good_frames,
            max_frames,
            elapsed_time,
            get_quantity_value(good_frames / elapsed_time),
            bad_frames))

    def _start_exposure(self, seconds, filename, dark, header, *args, **kwargs):
        self._control_setter('EXPOSURE', seconds)
        roi_format = Camera._driver.get_roi_format(self._handle)
        Camera._driver.start_exposure(self._handle)
        readout_args = (filename,
                        roi_format['width'],
                        roi_format['height'],
                        header)
        return readout_args

    def _readout(self, filename, width, height, header):
        exposure_status = Camera._driver.get_exposure_status(self._handle)
        if exposure_status == 'SUCCESS':
            try:
                image_data = Camera._driver.get_exposure_data(self._handle,
                                                              width,
                                                              height,
                                                              self.image_type)
            except RuntimeError as err:
                raise error.PanError('Error getting image data from {}: {}'.format(self, err))
            else:
                # Fix 'raw' data scaling by changing from zero padding of LSBs
                # to zero padding of MSBs.
                if self.image_type == 'RAW16':
                    pad_bits = 16 - int(get_quantity_value(self.bit_depth, u.bit))
                    image_data = np.right_shift(image_data, pad_bits)

                fits_utils.write_fits(image_data,
                                      header,
                                      filename,
                                      self.logger)
        elif exposure_status == 'FAILED':
            raise error.PanError("Exposure failed on {}".format(self))
        elif exposure_status == 'IDLE':
            raise error.PanError("Exposure missing on {}".format(self))
        else:
            raise error.PanError("Unexpected exposure status on {}: '{}'".format(
                self, exposure_status))

    def _create_fits_header(self, seconds, dark):
        header = super()._create_fits_header(seconds, dark)
        header.set('CAM-GAIN', self.gain, 'Internal units')
        header.set('XPIXSZ', get_quantity_value(self.properties['pixel_size'], u.um), 'Microns')
        header.set('YPIXSZ', get_quantity_value(self.properties['pixel_size'], u.um), 'Microns')
        return header

    def _refresh_info(self):
        self._info = Camera._driver.get_camera_property(self._address)

    def _control_getter(self, control_type):
        if control_type in self._control_info:
            return Camera._driver.get_control_value(self._handle, control_type)
        else:
            raise error.NotSupported("{} has no '{}' parameter".format(self.model, control_type))

    def _control_setter(self, control_type, value):
        if control_type not in self._control_info:
            raise error.NotSupported("{} has no '{}' parameter".format(self.model, control_type))

        control_name = self._control_info[control_type]['name']
        if not self._control_info[control_type]['is_writable']:
            raise error.NotSupported("{} cannot set {} parameter'".format(
                self.model, control_name))

        if value != 'AUTO':
            # Check limits.
            max_value = self._control_info[control_type]['max_value']
            if value > max_value:
                msg = "Cannot set {} to {}, clipping to max value {}".format(
                    control_name, value, max_value)
                Camera._driver.set_control_value(self._handle, control_type, max_value)
                raise error.IllegalValue(msg)

            min_value = self._control_info[control_type]['min_value']
            if value < min_value:
                msg = "Cannot set {} to {}, clipping to min value {}".format(
                    control_name, value, min_value)
                Camera._driver.set_control_value(self._handle, control_type, min_value)
                raise error.IllegalValue(msg)
        else:
            if not self._control_info[control_type]['is_auto_supported']:
                msg = "{} cannot set {} to AUTO".format(self.model, control_name)
                raise error.IllegalValue(msg)

        Camera._driver.set_control_value(self._handle, control_type, value)

    def _poll_exposure(self, readout_args):
        """Override to include `self._polling_interval`."""
        print(f"Polling camera with {self._polling_interval}s interval.")
        timer = CountdownTimer(duration=self._timeout)
        try:
            while self.is_exposing:
                if timer.expired():
                    msg = "Timeout waiting for exposure on {} to complete".format(self)
                    raise error.Timeout(msg)
                time.sleep(self._polling_interval)  # <---------- This is different
        except (RuntimeError, error.PanError) as err:
            # Error returned by driver at some point while polling
            self.logger.error('Error while waiting for exposure on {}: {}'.format(self, err))
            raise err
        else:
            # Camera type specific readout function
            self._readout(*readout_args)
        finally:
            self._exposure_event.set()  # Make sure this gets set regardless of readout errors

    def take_exposure_series(self, max_exposures=1000, exposure_time=1*u.second,
                             filter_name="blank"):
        """
        Take a series of blocking exposues on the camera, each time deleting the resulting file. Do
        this max_exposures times, or until it breaks. Record the polling interval and final number
        of exposures.
        """
        # Move the filterwheel
        # self.filterwheel.move_to(filter_name)

        # Start the exposure series
        for exp_num in range(1, max_exposures+1):
            try:
                self.take_exposure(filename=self._temp_image_filename, seconds=exposure_time,
                                   blocking=True)
                os.remove(self._temp_image_filename)
            except (error.PanError, FileNotFoundError) as err:
                self.logger.info(f"Error on {self} after {exp_num} exposures with polling"
                                 f" interval={self._polling_interval}: {err}.")
                break
        print(f"Finished {exp_num} exposures.")

        # Log the number of exposures before error
        with open(self._record_filename, "a") as f:
            writer = csv.writer(f)
            writer.writerow([f"{self._polling_interval:0.3f}", f"{exp_num}"])

        return exp_num

    def take_exposure(self,
                      seconds=1.0 * u.second,
                      filename=None,
                      dark=False,
                      blocking=False,
                      *args,
                      **kwargs):
        """Take an exposure for given number of seconds and saves to provided filename.
        Args:
            seconds (u.second, optional): Length of exposure.
            filename (str, optional): Image is saved to this filename.
            dark (bool, optional): Exposure is a dark frame, default False. On cameras that support
                taking dark frames internally (by not opening a mechanical shutter) this will be
                done, for other cameras the light must be blocked by some other means. In either
                case setting dark to True will cause the `IMAGETYP` FITS header keyword to have
                value 'Dark Frame' instead of 'Light Frame'. Set dark to None to disable the
                `IMAGETYP` keyword entirely.
            blocking (bool, optional): If False (default) returns immediately after starting
                the exposure, if True will block until it completes.
        Returns:
            threading.Event: Event that will be set when exposure is complete.
        """
        assert self.is_connected, self.logger.error("Camera must be connected for take_exposure!")

        assert filename is not None, self.logger.error("Must pass filename for take_exposure")

        # Check that the camera (and subcomponents) is ready
        if not self.is_ready:
            # Work out why the camera isn't ready.
            current_readiness = self.readiness
            problems = []
            if not current_readiness.get('temperature_stable', True):
                problems.append("unstable temperature")

            for sub_name in self._subcomponent_names:
                if not current_readiness.get(sub_name, True):
                    problems.append(f"{sub_name} not ready")

            if not current_readiness['not_exposing']:
                problems.append("exposure in progress")

            problems_string = ", ".join(problems)
            msg = f"Attempt to start exposure on {self} while not ready: {problems_string}."
            raise error.PanError(msg)

        if not isinstance(seconds, u.Quantity):
            seconds = seconds * u.second

        self.logger.debug(f'Taking {seconds} exposure on {self.name}: {filename}')

        header = self._create_fits_header(seconds, dark)

        if not self._exposure_event.is_set():
            msg = f"Attempt to take exposure on {self} while one already in progress."
            raise error.PanError(msg)

        # Clear event now to prevent any other exposures starting before this one is finished.
        self._exposure_event.clear()

        try:
            # Camera type specific exposure set up and start
            readout_args = self._start_exposure(seconds, filename, dark, header, *args, *kwargs)
        except (RuntimeError, ValueError, error.PanError) as err:
            self._exposure_event.set()
            raise error.PanError("Error starting exposure on {}: {}".format(self, err))

        # Start polling thread that will call camera type specific _readout method when done
        readout_thread = threading.Timer(interval=get_quantity_value(seconds, unit=u.second)/2,
                                         function=self._poll_exposure,
                                         args=(readout_args,))
        readout_thread.start()

        if blocking:
            self.logger.debug("Blocking on exposure event for {}".format(self))
            self._exposure_event.wait()

        return self._exposure_event


if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--polling_interval', type=float, default=DEFAULT_POLLING_INTERVAL)
    parser.add_argument('--exposure_time', type=float, default=1)
    args = parser.parse_args()
    polling_interval = args.polling_interval
    exposure_time = args.exposure_time * u.second
    print(f"Polling interval: {polling_interval}s.")
    print(f"Exposure time: {exposure_time.value}s.")

    # serial_number = "3528420013090900"  # Pi8
    # polling_interval = DEFAULT_POLLING_INTERVAL
    config = load_device_config()["camera"]
    config["polling_interval"] = polling_interval

    # Create the camera
    camera = Camera(**config)

    # Enable cooling
    camera.cooling_enabled = True
    print("Waiting for camera cooling.")
    time.sleep(240)

    # Move to blank filter
    camera.filterwheel.move_to("blank", blocking=True)

    # Take the exposure series
    print("Starting exposures.")
    n_exposures = camera.take_exposure_series(exposure_time=exposure_time)
