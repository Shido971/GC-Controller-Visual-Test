# Visual Controller Test pour Android : SDL2 + sources partagées avec le portage PC.
cmake_minimum_required(VERSION 3.18)
project(vct_android C)

get_filename_component(REPO_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../../../.." ABSOLUTE)
set(VCTPC "${REPO_ROOT}/vct-pc")
set(SDL_SRC "${CMAKE_CURRENT_SOURCE_DIR}/SDL" CACHE PATH "Sources SDL2 (android/fetch_deps.sh)")
set(VCT_UPSTREAM "${CMAKE_CURRENT_SOURCE_DIR}/vct-upstream" CACHE PATH "Sources Wii de Visual Controller Test")

if(NOT EXISTS "${SDL_SRC}/CMakeLists.txt" OR NOT EXISTS "${VCT_UPSTREAM}/source/main.c")
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
