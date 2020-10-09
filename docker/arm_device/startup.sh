#!/bin/sh
sudo chown -R ${PANUSER} /home/${PANUSER}/.ssh
sudo chown -R ${PANUSER} ${PANDIR}/logs
cd ${HUNTSMAN_POCS}
python setup.py develop
python ${HUNTSMAN_POCS}/scripts/run_device.py
