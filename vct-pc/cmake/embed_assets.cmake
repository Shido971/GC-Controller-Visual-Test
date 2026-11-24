# Generates <name>_png.c / <name>_png.h for every PNG in ASSET_DIR,
# mimicking devkitPro's bin2o output (plus a <name>_png_size symbol).
# Usage: cmake -DASSET_DIR=... -DOUT_DIR=... -P embed_assets.cmake
file(MAKE_DIRECTORY "${OUT_DIR}")
file(GLOB pngs "${ASSET_DIR}/*.png")
foreach(png ${pngs})
  get_filename_component(base "${png}" NAME_WE)
  set(sym "${base}_png")
  set(c_out "${OUT_DIR}/${sym}.c")
  set(h_out "${OUT_DIR}/${sym}.h")
  if(NOT EXISTS "${c_out}" OR "${png}" IS_NEWER_THAN "${c_out}")
    file(READ "${png}" hex HEX)
    string(LENGTH "${hex}" hexlen)
    math(EXPR size "${hexlen} / 2")
    string(REGEX REPLACE "([0-9a-f][0-9a-f])" "0x\\1," arr "${hex}")
    string(REGEX REPLACE "((0x..,){32})" "\\1\n" arr "${arr}")
    file(WRITE "${c_out}" "/* generated from ${base}.png */\n"
      "const unsigned char ${sym}[${size}] = {\n${arr}\n};\n"
      "const unsigned int ${sym}_size = ${size};\n")
    file(WRITE "${h_out}" "/* generated */\n#pragma once\n"
      "extern const unsigned char ${sym}[];\n"
      "extern const unsigned int ${sym}_size;\n")
  endif()
endforeach()
