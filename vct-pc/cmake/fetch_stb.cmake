# stb_image.h (domaine public) : copie locale dans third_party/ si présente,
# sinon téléchargement d'une révision figée, vérifiée par SHA-256.
set(STB_COMMIT "6b5799bae8a1fe3792691ef4b72ae26434c3e799")
set(STB_SHA256 "dfc2aadda6295f67f677587773f25e5bf8c8ad427ed0db7c518525c91e72e020")
get_filename_component(_vct_root "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
if(EXISTS "${_vct_root}/third_party/stb_image.h")
  set(STB_INCLUDE_DIR "${_vct_root}/third_party")
else()
  set(STB_INCLUDE_DIR "${CMAKE_BINARY_DIR}/stb")
  if(NOT EXISTS "${STB_INCLUDE_DIR}/stb_image.h")
    file(DOWNLOAD "https://raw.githubusercontent.com/nothings/stb/${STB_COMMIT}/stb_image.h"
         "${STB_INCLUDE_DIR}/stb_image.h"
         EXPECTED_HASH SHA256=${STB_SHA256} TLS_VERIFY ON STATUS _st)
    list(GET _st 0 _code)
    if(NOT _code EQUAL 0)
      message(FATAL_ERROR "Téléchargement de stb_image.h impossible : ${_st}")
    endif()
  endif()
endif()
