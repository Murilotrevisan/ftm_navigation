# L1b -- ESP-IDF `linux` target host tests over components/services/ ONLY.
#
# Runs in the container: `.\tools\dev.ps1 test-host` (docs/CONTAINER.md).
#
# Why IDF's own build rather than a second Ceedling project: services/ lives
# inside the IDF component system, so testing it through that build exercises
# the real component dependency graph and the real Kconfig wiring, including
# the role-strategy source selection a standalone Ceedling project cannot see
# (docs/TESTING.md §2).
#
# The division rule: services/ belongs here, domain/ belongs to
# tests/host_ceedling/. Never test a module in both.
cmake_minimum_required(VERSION 3.16)

set(EXTRA_COMPONENT_DIRS
    "${CMAKE_CURRENT_LIST_DIR}/../../components/domain"
    "${CMAKE_CURRENT_LIST_DIR}/../../components/services"
)

# Only what the tests need. The firmware components are not pulled in: this
# binary is a native executable, and dragging in the Wi-Fi stack would defeat
# the point of a host test.
set(COMPONENTS main domain services unity)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(host_idf_tests)
