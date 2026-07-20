# The following lines of boilerplate have to be in your project's CMakeLists
# in this exact order for cmake to work correctly
cmake_minimum_required(VERSION 3.16)

# This bench is for the project's ESP32-C3 fleet, but callers may override it.
if(NOT DEFINED IDF_TARGET)
    set(IDF_TARGET "esp32c3")
endif()

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
# "Trim" the build. Include the minimal set of components, main, and anything it depends on.
idf_build_set_property(MINIMAL_BUILD ON)
project(ftm_measurement)
