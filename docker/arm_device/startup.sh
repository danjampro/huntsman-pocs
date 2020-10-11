#!/bin/sh
sudo chown -R ${PANUSER} /home/${PANUSER}/.ssh
sudo chown -R ${PANUSER} ${PANDIR}
cd ${HUNTSMAN_POCS}
python setup.py develop
python scripts/run_device.py
