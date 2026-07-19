# Build + host-unit-test environment for the FTM project.
#
# Scope: firmware builds and host unit tests ONLY. This image never touches the
# boards -- flashing and E2E run on the Windows host. See docs/CONTAINER.md.
#
# Pinned deliberately: floating to :latest would change the IDF version out from
# under the measurements recorded in docs/HARDWARE_FINDINGS.md.
FROM espressif/idf:v5.5.2

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8
ENV DEBIAN_FRONTEND=noninteractive

# Ruby is here so Ceedling never has to be installed on the developer's PC.
# gcovr/lcov for coverage. build-essential for the native (host) compiles that
# Ceedling and the ESP-IDF linux target both need.
RUN apt-get update -y && apt-get install -y --no-install-recommends \
        ruby-full \
        build-essential \
        gcovr \
        lcov \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN gem install --no-document ceedling

# Sourced by the entrypoint; also convenient for interactive shells.
RUN echo "source /opt/esp/idf/export.sh > /dev/null 2>&1" >> /etc/bash.bashrc

WORKDIR /project

COPY entrypoint.sh /usr/local/bin/ftm-entrypoint.sh
RUN chmod +x /usr/local/bin/ftm-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/ftm-entrypoint.sh"]
CMD ["bash"]
