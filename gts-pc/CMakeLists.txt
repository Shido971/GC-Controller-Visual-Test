cmake_minimum_required(VERSION 3.16)
project(GTSPC C)

# ---------------------------------------------------------------------------
# GCC Test Suite (GTS) by greenwave-1 - GPL-3.0.
# The upstream sources are compiled unmodified, as the GameCube build (HW_DOL),
# on top of a small libogc compatibility layer (compat/ + src/) and the
# adapter/SDL input layer shared with the Visual Controller Test port.
# ---------------------------------------------------------------------------
set(GTS_UPSTREAM_REPO "https://github.com/greenwave-1/GTS" CACHE STRING "Upstream repository")
set(GTS_UPSTREAM_REF "9d72278e4114dc31a238f47a2e2d863ade7bf948" CACHE STRING "Upstream commit/tag/branch")
set(GTS_UPSTREAM_DIR "" CACHE PATH "Local upstream checkout (skips download)")

get_filename_component(VCTPC "${CMAKE_CURRENT_SOURCE_DIR}/../vct-pc" ABSOLUTE)

if(GTS_UPSTREAM_DIR)
  set(UPSTREAM "${GTS_UPSTREAM_DIR}")
else()
  include(FetchContent)
  find_package(Git QUIET)
  if(GIT_FOUND)
    FetchContent_Declare(gts_upstream GIT_REPOSITORY "${GTS_UPSTREAM_REPO}.git" GIT_TAG "${GTS_UPSTREAM_REF}")
  else()
    FetchContent_Declare(gts_upstream URL "${GTS_UPSTREAM_REPO}/archive/${GTS_UPSTREAM_REF}.tar.gz")
  endif()
  FetchContent_GetProperties(gts_upstream)
  if(NOT gts_upstream_POPULATED)
    FetchContent_Populate(gts_upstream)
  endif()
  set(UPSTREAM "${gts_upstream_SOURCE_DIR}")
endif()
if(NOT EXISTS "${UPSTREAM}/source/main.c")
  message(FATAL_ERROR "GTS sources not found in ${UPSTREAM}")
endif()
message(STATUS "GTS upstream: ${UPSTREAM}")

# Textures (replaces devkitPro's gxtexconv / TPL)
set(GEN_DIR "${CMAKE_BINARY_DIR}/generated")
execute_process(COMMAND ${CMAKE_COMMAND} -DSCF=${UPSTREAM}/textures/textures.scf -DOUT_DIR=${GEN_DIR}
                        -P ${CMAKE_CURRENT_SOURCE_DIR}/cmake/embed_textures.cmake
                RESULT_VARIABLE tex_rc)
if(NOT tex_rc EQUAL 0)
  message(FATAL_ERROR "Texture embedding failed")
endif()

include(${VCTPC}/cmake/fetch_stb.cmake)

# Upstream sources (network logging is Wii-only: not built)
file(GLOB GTS_SOURCES "${UPSTREAM}/source/*.c" "${UPSTREAM}/source/submenu/*.c" "${UPSTREAM}/source/util/*.c")
list(FILTER GTS_SOURCES EXCLUDE REGEX "/util/logging\\.c$")

# Dependencies: SDL2 + libusb-1.0 (same logic as vct-pc)
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

add_executable(gts_pc
  src/gts_main_pc.c
  src/gx_sdl.c
  src/gts_sys.c
  ${VCTPC}/src/pad_pc.c
  ${GEN_DIR}/textures_pack.c
  ${GTS_SOURCES})
set_target_properties(gts_pc PROPERTIES OUTPUT_NAME "GTS" C_STANDARD 23 C_EXTENSIONS ON)
if(MINGW)
  set_target_properties(gts_pc PROPERTIES WIN32_EXECUTABLE ON)
  target_link_options(gts_pc PRIVATE -static-libgcc)
endif()

# order matters: our libogc headers first
target_include_directories(gts_pc PRIVATE
  compat ${VCTPC}/compat ${VCTPC}/src "${STB_INCLUDE_DIR}" "${GEN_DIR}" "${UPSTREAM}/include")
string(SUBSTRING "${GTS_UPSTREAM_REF}" 0 7 _gts_short)
target_compile_definitions(gts_pc PRIVATE HW_DOL "BUILD_DATE=\"PC-${_gts_short}\"")

if(NOT MSVC)
  set(GTS_FLAGS "-include;${CMAKE_CURRENT_SOURCE_DIR}/compat/gts_prelude.h;-Wno-unused-variable;-Wno-unused-but-set-variable;-Wno-format;-Wno-int-conversion;-Wno-incompatible-pointer-types;-Wno-unused-function")
  set_source_files_properties(${GTS_SOURCES} PROPERTIES COMPILE_OPTIONS "${GTS_FLAGS}")
else()
  message(FATAL_ERROR "GTS PC port: use GCC/Clang (MSYS2 on Windows)")
endif()

if(TARGET PkgConfig::SDL2)
  target_link_libraries(gts_pc PRIVATE PkgConfig::SDL2)
else()
  target_link_libraries(gts_pc PRIVATE SDL2::SDL2)
endif()
if(TARGET PkgConfig::LIBUSB)
  target_link_libraries(gts_pc PRIVATE PkgConfig::LIBUSB)
else()
  target_include_directories(gts_pc PRIVATE ${LIBUSB_INCLUDE_DIR})
  target_link_libraries(gts_pc PRIVATE ${LIBUSB_LIBRARY})
endif()
target_link_libraries(gts_pc PRIVATE m)

install(TARGETS gts_pc RUNTIME DESTINATION .)
