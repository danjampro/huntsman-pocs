#==============================================================================
# Dockerfile for a distributed Huntsman camera.
#==============================================================================

FROM huntsmanarray/arm_device:interim

# ZWO camera & EFW libraries
ADD scripts/install_asi_libs.sh .
RUN ./install_asi_libs.sh
