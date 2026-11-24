# Visual Controller Test pour Android : SDL2 + sources partagées avec le portage PC.
cmake_minimum_required(VERSION 3.18)
project(vct_android C)

get_filename_component(REPO_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../../../.." ABSOLUTE)
set(VCTPC "${REPO_ROOT}/vct-pc")
set(SDL_SRC "${CMAKE_CURRENT_SOURCE_DIR}/SDL" CACHE PATH "Sources SDL2 (android/fetch_deps.sh)")
set(VCT_UPSTREAM "${CMAKE_CURRENT_SOURCE_DIR}/vct-upstream" CACHE PATH "Sources Wii de Visual Controller Test")
set(GTS_UPSTREAM "${CMAKE_CURRENT_SOURCE_DIR}/gts-upstream" CACHE PATH "Sources de GTS (GCC Test Suite)")
set(GTSPC "${REPO_ROOT}/gts-pc")

if(NOT EXISTS "${SDL_SRC}/CMakeLists.txt" OR NOT EXISTS "${VCT_UPSTREAM}/source/main.c" OR NOT EXISTS "${GTS_UPSTREAM}/source/main.c")
  message(FATAL_ERROR "Dépendances absentes : lance d'abord android/fetch_deps.sh")
endif()

# SDL2 en bibliothèque partagée (libSDL2.so, chargée par SDLActivity)
set(SDL_SHARED ON CACHE BOOL "" FORCE)
set(SDL_STATIC OFF CACHE BOOL "" FORCE)
set(SDL_TEST OFF CACHE BOOL "" FORCE)
add_subdirectory("${SDL_SRC}" SDL2-build)

# Images du jeu intégrées au binaire (comme bin2o de devkitPro)
set(GEN_DIR "${CMAKE_BINARY_DIR}/generated")
execute_process(COMMAND ${CMAKE_COMMAND} -DASSET_DIR=${VCT_UPSTREAM}/data -DOUT_DIR=${GEN_DIR}
                        -P ${VCTPC}/cmake/embed_assets.cmake
                RESULT_VARIABLE embed_rc)
if(NOT embed_rc EQUAL 0)
  message(FATAL_ERROR "Intégration des images impossible")
endif()
file(GLOB ASSET_SOURCES "${GEN_DIR}/*.c")
include(${VCTPC}/cmake/fetch_stb.cmake)

add_library(vct SHARED
  ${VCTPC}/src/main_pc.c
  ${VCTPC}/src/grrlib_sdl.c
  ${VCTPC}/src/pad_pc.c
  ${VCTPC}/src/vct_jni.c
  ${VCT_UPSTREAM}/source/main.c
  ${ASSET_SOURCES})
set_target_properties(vct PROPERTIES C_STANDARD 11)
target_compile_definitions(vct PRIVATE VCT_NO_LIBUSB)
target_include_directories(vct PRIVATE ${VCTPC}/compat ${VCTPC}/src ${STB_INCLUDE_DIR} ${GEN_DIR})
# main.c d'origine compilé tel quel : son main() devient vct_main()
set_source_files_properties(${VCT_UPSTREAM}/source/main.c PROPERTIES
  COMPILE_DEFINITIONS "main=vct_main"
  COMPILE_OPTIONS "-fgnu89-inline;-Wno-unused-variable;-Wno-unused-but-set-variable;-Wno-format;-Wno-int-conversion;-Wno-implicit-function-declaration")
target_link_libraries(vct PRIVATE SDL2 log m)

# ---------------------------------------------------------------------------
# GTS (GCC Test Suite, greenwave-1, GPL-3.0) : sources d'origine non modifiées
# ---------------------------------------------------------------------------
set(GTS_GEN "${CMAKE_BINARY_DIR}/gts-generated")
execute_process(COMMAND ${CMAKE_COMMAND} -DSCF=${GTS_UPSTREAM}/textures/textures.scf -DOUT_DIR=${GTS_GEN}
                        -P ${GTSPC}/cmake/embed_textures.cmake
                RESULT_VARIABLE gts_tex_rc)
if(NOT gts_tex_rc EQUAL 0)
  message(FATAL_ERROR "Intégration des textures GTS impossible")
endif()
file(GLOB GTS_SOURCES "${GTS_UPSTREAM}/source/*.c" "${GTS_UPSTREAM}/source/submenu/*.c" "${GTS_UPSTREAM}/source/util/*.c")
list(FILTER GTS_SOURCES EXCLUDE REGEX "/util/logging\\.c$")

add_library(gts SHARED
  ${GTSPC}/src/gts_main_pc.c
  ${GTSPC}/src/gx_sdl.c
  ${GTSPC}/src/gts_sys.c
  ${VCTPC}/src/pad_pc.c
  ${VCTPC}/src/vct_jni.c
  ${GTS_GEN}/textures_pack.c
  ${GTS_SOURCES})
set_target_properties(gts PROPERTIES C_STANDARD 23 C_EXTENSIONS ON)
target_compile_definitions(gts PRIVATE VCT_NO_LIBUSB HW_DOL "BUILD_DATE=\"Android\"")
target_include_directories(gts PRIVATE ${GTSPC}/compat ${VCTPC}/compat ${VCTPC}/src ${STB_INCLUDE_DIR} ${GTS_GEN} ${GTS_UPSTREAM}/include)
set_source_files_properties(${GTS_SOURCES} PROPERTIES COMPILE_OPTIONS
  "-include;${GTSPC}/compat/gts_prelude.h;-Wno-unused-variable;-Wno-unused-but-set-variable;-Wno-format;-Wno-int-conversion;-Wno-incompatible-pointer-types;-Wno-unused-function;-Wno-implicit-function-declaration")
target_link_libraries(gts PRIVATE SDL2 log m)
