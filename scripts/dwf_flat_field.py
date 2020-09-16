from pocs.mount import create_mount_from_config
from pocs.scheduler import create_scheduler_from_config
from huntsman.pocs.camera import create_cameras_from_config
from huntsman.pocs.observatory import HuntsmanObservatory
from huntsman.pocs.utils import load_config


def take_flat_field(cam_name, filter_name, exposure_time, focus_position):
    """
    Take a single flat field exposure and an associated dark frame for a given camera.
    We use observatory methods to get consistent FITS headers.
    """
    # Create cameras
    config = load_config()
    cameras = create_cameras_from_config(config=config)
    scheduler = create_scheduler_from_config(config=config)
    mount = create_mount_from_config(config=config)
    mount.initialize()

    # Setup the camera
    camera = cameras[cam_name]
    camera.filterwheel.move_to(filter_name)
    camera.focuser.move_to(focus_position)

    # Create observatory
    simulators = ['weather', 'mount', 'power', 'night']
    observatory = HuntsmanObservatory(scheduler=scheduler, simulators=simulators, mount=mount)
    observatory.add_camera(cam_name, camera)

    # Make the observation and define FITS headers
    observation = observatory._create_flat_field_observation()
    fits_headers = observatory.get_standard_headers(observation=observation)

    # Prepare cameras (make sure temperature is stable etc)
    observatory.prepare_cameras()

    # Take the flat field, including an ET-matched dark frame
    exptimes = {cam_name: exposure_time}
    observatory._take_flat_observation(exptimes, observation, fits_headers=fits_headers,
                                       dark=False)
    camera.filterwheel.move_to("blank")
    observatory._take_flat_observation(exptimes, observation, fits_headers=fits_headers,
                                       dark=True)
