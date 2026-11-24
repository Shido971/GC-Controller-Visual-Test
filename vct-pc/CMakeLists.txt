cmake_minimum_required(VERSION 3.16)
project(VisualControllerTestPC C)

# ---------------------------------------------------------------------------
# Upstream Wii sources. By default the pinned upstream revision is downloaded;
# pass -DVCT_UPSTREAM_DIR=/path/to/VisualControllerTest to use a local copy.
# ---------------------------------------------------------------------------
set(VCT_UPSTREAM_REPO "https://github.com/mardy/VisualControllerTest" CACHE STRING "Upstream repository")
set(VCT_UPSTREAM_REF "e6482631b252b2a945965a036831036bf07ca5a5" CACHE STRING "Upstream commit/tag/branch")
set(VCT_UPSTREAM_DIR "" CACHE PATH "Local upstream checkout (skips download)")

if(VCT_UPSTREAM_DIR)
  set(UPSTREAM "${VCT_UPSTREAM_DIR}")
else()
  include(FetchContent)
  find_package(Git QUIET)
  if(GIT_FOUND)
    FetchContent_Declare(vct_upstream
      GIT_REPOSITORY "${VCT_UPSTREAM_REPO}.git"
      GIT_TAG "${VCT_UPSTREAM_REF}")
  else()
    FetchContent_Declare(vct_upstream
      URL "${VCT_UPSTREAM_REPO}/archive/${VCT_UPSTREAM_REF}.tar.gz")
  endif()
  FetchContent_GetProperties(vct_upstream)
  if(NOT vct_upstream_POPULATED)
    FetchContent_Populate(vct_upstream)
  endif()
  set(UPSTREAM "${vct_upstream_SOURCE_DIR}")
endif()

if(NOT EXISTS "${UPSTREAM}/source/main.c")
  message(FATAL_ERROR "Upstream sources not found in ${UPSTREAM}")
endif()
message(STATUS "Visual Controller Test upstream: ${UPSTREAM}")

# Embed PNG assets at configure time (equivalent of devkitPro bin2o)
set(GEN_DIR "${CMAKE_BINARY_DIR}/generated")
execute_process(COMMAND ${CMAKE_COMMAND} -DASSET_DIR=${UPSTREAM}/data -DOUT_DIR=${GEN_DIR}
                        -P ${CMAKE_CURRENT_SOURCE_DIR}/cmake/embed_assets.cmake
                RESULT_VARIABLE embed_rc)
if(NOT embed_rc EQUAL 0)
  message(FATAL_ERROR "Asset embedding failed")
endif()
file(GLOB ASSET_SOURCES "${GEN_DIR}/*.c")
include(${CMAKE_CURRENT_SOURCE_DIR}/cmake/fetch_stb.cmake)

# ---------------------------------------------------------------------------
# Dependencies: SDL2 + libusb-1.0
# ---------------------------------------------------------------------------
find_package(PkgConfig)
if(PKG_CONFIG_FOUND)
  pkg_check_modules(SDL2 IMPORTED_TARGET sdl2)
  pkg_check_modules(LIBUSB IMPORTED_TARGET libusb-1.0)
endif()
if(NOT SDL2_FOUND)
  find_package(SDL2 REQUIRED CONFIG)
endif()
if(NOT LIBUSB_FOUND)
  find_path(LIBUSB_INCLUDE_DIR libusb.h PATH_SUFFIXES libusb-1.0 REQUIRED)
  find_library(LIBUSB_LIBRARY NAMES usb-1.0 libusb-1.0 REQUIRED)
endif()

add_executable(vct_pc
  src/main_pc.c
  src/grrlib_sdl.c
  src/pad_pc.c
  "${UPSTREAM}/source/main.c"
  ${ASSET_SOURCES})
set_target_properties(vct_pc PROPERTIES OUTPUT_NAME "VisualControllerTest" C_STANDARD 11)
if(MINGW)
  # no console window; main() stays the entry point with MinGW
  set_target_properties(vct_pc PROPERTIES WIN32_EXECUTABLE ON)
endif()

target_include_directories(vct_pc PRIVATE compat src "${STB_INCLUDE_DIR}" "${GEN_DIR}")

# The upstream file is compiled untouched: its main() becomes vct_main(),
# and C99 inline semantics are relaxed the way devkitPPC's GCC accepted them.
set(RENAME_MAIN_H "${CMAKE_CURRENT_SOURCE_DIR}/compat/rename_main.h")
if(NOT MSVC)
  set_source_files_properties("${UPSTREAM}/source/main.c" PROPERTIES
    COMPILE_OPTIONS "-include;${RENAME_MAIN_H};-fgnu89-inline;-Wno-unused-variable;-Wno-unused-but-set-variable;-Wno-format;-Wno-int-conversion")
else()
  set_source_files_properties("${UPSTREAM}/source/main.c" PROPERTIES COMPILE_OPTIONS "/FI${RENAME_MAIN_H}")
  target_compile_definitions(vct_pc PRIVATE _USE_MATH_DEFINES _CRT_SECURE_NO_WARNINGS)
endif()

if(SDL2_FOUND AND TARGET PkgConfig::SDL2)
  target_link_libraries(vct_pc PRIVATE PkgConfig::SDL2)
else()
  target_link_libraries(vct_pc PRIVATE SDL2::SDL2)
endif()
if(TARGET PkgConfig::LIBUSB)
  target_link_libraries(vct_pc PRIVATE PkgConfig::LIBUSB)
else()
  target_include_directories(vct_pc PRIVATE ${LIBUSB_INCLUDE_DIR})
  target_link_libraries(vct_pc PRIVATE ${LIBUSB_LIBRARY})
endif()
if(NOT MSVC)
  target_link_libraries(vct_pc PRIVATE m)
endif()
if(MINGW)
  target_link_options(vct_pc PRIVATE -static-libgcc)
endif()

install(TARGETS vct_pc RUNTIME DESTINATION .)

# Unit test for the adapter report parser
enable_testing()
add_executable(test_adapter_proto tests/test_adapter_proto.c)
target_include_directories(test_adapter_proto PRIVATE compat src)
add_test(NAME adapter_proto COMMAND test_adapter_proto)
