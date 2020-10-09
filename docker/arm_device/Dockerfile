#==============================================================================
# Dockerfile for an ARM Huntsman device.
#==============================================================================

# This can be replaced with the official POCS docker image in future...
FROM raspbian/jessie:latest

# Build args
ARG panuser=huntsman
ARG pocs_branch=develop
ARG pocs_url=https://github.com/panoptes/POCS.git
ARG conda_path=/home/${panuser}/berryconda3
ARG conda_script=Berryconda3-2.0.0-Linux-armv7l.sh
ARG conda_url=https://github.com/jjhelmus/berryconda/releases/download/v2.0.0/${conda_script}

# Environment variables
ENV PANUSER=${panuser}
ENV PANDIR=/var/${PANUSER}
ENV DEBIAN_FRONTEND=noninteractive
ENV POCS=${PANDIR}/POCS
ENV PAWS=${PANDIR}/PAWS
ENV HUNTSMAN_POCS=${PANDIR}/huntsman-pocs

# Add the huntsman user
RUN useradd -m -d /home/$PANUSER $PANUSER && \
    mkdir $PANDIR && \
    chown $PANUSER $PANDIR && \
    echo dialout plugdev netdev users input spi i2c gpio | xargs -n 1 groupadd -f && \
    usermod -a -G dialout,plugdev,netdev,users,input,spi,i2c,gpio,sudo huntsman && \
    # Install packages
    apt-get -y upgrade && \
    apt-get update && \
    apt-get -y dist-upgrade && \
    apt-get -y install bzip2 git gcc sshfs sudo vim && \
    # Allow sudo without password
    echo "$PANUSER ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

# Install Berryconda as PANUSER
USER ${PANUSER}
RUN cd ${PANDIR} && \
    wget ${conda_url} && \
    chmod +x ${conda_script} && \
    ./${conda_script} -b -p ${conda_path}

USER root
RUN ln -s ${conda_path}/bin/conda /usr/local/bin/ && \
    ln -s ${conda_path}/bin/python3.6 /usr/local/bin/python && \
    ln -s ${conda_path}/bin/pip /usr/local/bin/ && \
    # Install python deps
    pip install --upgrade pip && \
    pip install setuptools --upgrade && \
    conda install astropy matplotlib requests scipy && \
    pip install netifaces pyro4 pyyaml pyserial pymongo && \
    # Install POCS
    mkdir -p ${PANDIR}/logs && \
    cd ${PANDIR} && \
    git clone ${pocs_url} && \
    cd ${POCS} && \
    git fetch origin ${pocs_branch} && \
    git checkout -t origin/${pocs_branch} && \
    python setup.py develop --no-deps && \
    # Setup permissions for PANUSER
    chmod 1777 /tmp && \
    chown -R ${PANUSER} ${PANDIR} && \
    chown -R ${PANUSER} /home/${PANUSER}

#==============================================================================

ADD docker/arm_device/startup.sh .
CMD ["sh", "./startup.sh"]
