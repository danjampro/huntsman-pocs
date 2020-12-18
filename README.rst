=============
huntsman-pocs
=============

|Python Tests| |Docker CI| |codecov| |astropy|

Usage of commissioning branch
=============================

- Fork this repository/branch
- Clone the branch onto the control computer
- Make changes to `huntsman-pocs` on this branch
- Make changes to `panoptes-pocs` on any branch you like
- Run `bash ${HUNTSMAN_POCS}/scripts/build-pocs-image.sh` to build a new `pocs` image (not necessary if you have not changed any `pocs` code).
- Push your changes to *your own* github fork of this branch (you will need to set up docker GH secrets - see discussion on Slack or ask someone).
- The `huntsman-pocs` image will build in the cloud. Check it works in the `Actions` tab.
- Once it is ready, `cd /var/huntsman/huntsman-pocs/docker` on the control and do `docker-compose pull`
- Reboot the pis
- ???
- PROFIT!


