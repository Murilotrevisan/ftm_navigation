# L2 -- on-target Unity test app (ESP32-C3).
#
# Kept as the TEMPLATE for every later L2 suite (drivers/peripherals/wifi in
# Phase 3), and used by the L3 E2E harness as the known-good app it flashes to
# both boards.
#
# Build:  .\tools\dev.ps1 target-build         (container)
# Flash:  .\tools\dev.ps1 flash responder      (Windows venv)
cmake_minimum_required(VERSION 3.16)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(ftm_target_smoke)
