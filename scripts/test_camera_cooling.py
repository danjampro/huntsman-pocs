import time
import numpy as np
import matplotlib.pyplot as plt
from astropy import units as u
from pocs.camera.zwo import Camera


if __name__ == "__main__":

    time_max = 360
    time_interval = 2
    time_cool = 60
    time_nocool = time_max - 60
    image_filename = "test_camera_cooling.png"
    serial_number = "1815420013090900"
    port = "/dev/ttyUSB0"

    # Create camera
    camera = Camera(serial_number=serial_number, port=port)
    camera.cooling_enabled = False

    # Prepare containers
    times = np.arange(0, time_max, time_interval)
    temperatures = np.zeros_like(times, dtype="float")

    # Log temperatures
    for i, t in enumerate(times):

        # Activate cooling once
        if (t >= time_cool) and (t < time_nocool) and not (camera.cooling_enabled):
            print("Activating camera cooling.")
            camera.cooling_enabled = True

        # Deactivate cooling once
        if (t >= time_nocool) and camera.cooling_enabled:
            print("Deactivating camera cooling.")
            camera.cooling_enabled = False

        temperatures[i] = camera.temperature.to_value(u.Celsius)
        time.sleep(time_interval)

    # Deactivate camera cooling
    print("Deactivating camera cooling.")
    camera.cooling_enabled = False

    plt.figure()
    plt.plot(times, temperatures, 'k-')
    plt.xlabel("Time [s]")
    plt.ylabel("Temperature [degrees Celsius]")
    ylim = plt.ylim()
    plt.plot([time_cool, time_cool], ylim, "b-", label="Cooling Activated")
    plt.plot([time_nocool, time_nocool], ylim, "r-", label="Cooling Deactivated")
    plt.ylim(ylim)
    plt.legend(loc="best")
    plt.show(block=False)

    plt.savefig(image_filename, dpi=150, bbox_inches="tight")
