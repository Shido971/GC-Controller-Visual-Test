# Replaces devkitPro's gxtexconv: reads textures.scf and generates
#  - textures.h      : one #define per texture id (same order as the .scf)
#  - textures_tpl.h  : the "TPL" symbols GTS expects
#  - textures_pack.c : the PNG files embedded as byte arrays
# Usage: cmake -DSCF=.../textures.scf -DOUT_DIR=... -P embed_textures.cmake
get_filename_component(TEXDIR "${SCF}" DIRECTORY)
file(STRINGS "${SCF}" lines)
set(idx 0)
set(defs "")
set(arrays "")
set(ptrs "")
set(sizes "")
file(MAKE_DIRECTORY "${OUT_DIR}")
foreach(line IN LISTS lines)
  if(line MATCHES "^<filepath=\"([^\"]+)\" +id=\"([^\"]+)\"")
    set(fp "${CMAKE_MATCH_1}")
    set(id "${CMAKE_MATCH_2}")
    file(READ "${TEXDIR}/${fp}" hex HEX)
    string(LENGTH "${hex}" hexlen)
    math(EXPR size "${hexlen} / 2")
    string(REGEX REPLACE "([0-9a-f][0-9a-f])" "0x\\1," arr "${hex}")
    string(REGEX REPLACE "((0x..,){32})" "\\1\n" arr "${arr}")
    string(APPEND defs "#define ${id} ${idx}\n")
    string(APPEND arrays "static const unsigned char tex_${idx}[${size}] = {\n${arr}\n};\n")
    string(APPEND ptrs "  tex_${idx},\n")
    string(APPEND sizes "  ${size},\n")
    math(EXPR idx "${idx} + 1")
  endif()
endforeach()
file(WRITE "${OUT_DIR}/textures.h" "/* generated from textures.scf */\n#pragma once\n${defs}#define textures_count ${idx}\n")
file(WRITE "${OUT_DIR}/textures_tpl.h" "/* generated */\n#pragma once\nextern const unsigned char textures_tpl[];\nextern const unsigned int textures_tpl_size;\n")
file(WRITE "${OUT_DIR}/textures_pack.c"
  "/* generated from textures.scf */\n${arrays}"
  "const unsigned char *const gts_tex_png[] = {\n${ptrs}};\n"
  "const unsigned int gts_tex_png_size[] = {\n${sizes}};\n"
  "const int gts_tex_count = ${idx};\n"
  "const unsigned char textures_tpl[1] = { 0 };\nconst unsigned int textures_tpl_size = 1;\n")
