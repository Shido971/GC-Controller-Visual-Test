#!/usr/bin/env bash
# Récupère les dépendances natives de l'appli Android :
#  - SDL2 (sources + classes Java SDLActivity)
#  - sources Wii de Visual Controller Test
set -euo pipefail
cd "$(dirname "$0")"

SDL_TAG="${SDL_TAG:-release-2.30.9}"
VCT_REPO="${VCT_REPO:-https://github.com/mardy/VisualControllerTest}"
VCT_REF="${VCT_REF:-e6482631b252b2a945965a036831036bf07ca5a5}"
GTS_REPO="${GTS_REPO:-https://github.com/greenwave-1/GTS}"
GTS_REF="${GTS_REF:-9d72278e4114dc31a238f47a2e2d863ade7bf948}"
CPP=app/src/main/cpp
JAVA=app/src/main/java/org/libsdl/app

if [ ! -f "$CPP/SDL/CMakeLists.txt" ]; then
  echo "== SDL2 $SDL_TAG"
  git clone --quiet --depth 1 --branch "$SDL_TAG" https://github.com/libsdl-org/SDL "$CPP/SDL"
fi
mkdir -p "$JAVA"
cp "$CPP"/SDL/android-project/app/src/main/java/org/libsdl/app/*.java "$JAVA/"

if [ ! -f "$CPP/vct-upstream/source/main.c" ]; then
  echo "== Visual Controller Test $VCT_REF"
  rm -rf "$CPP/vct-upstream"
  git init --quiet "$CPP/vct-upstream"
  git -C "$CPP/vct-upstream" fetch --quiet --depth 1 "$VCT_REPO" "$VCT_REF"
  git -C "$CPP/vct-upstream" checkout --quiet FETCH_HEAD
fi
if [ ! -f "$CPP/gts-upstream/source/main.c" ]; then
  echo "== GTS $GTS_REF"
  rm -rf "$CPP/gts-upstream"
  git init --quiet "$CPP/gts-upstream"
  git -C "$CPP/gts-upstream" fetch --quiet --depth 1 "$GTS_REPO" "$GTS_REF"
  git -C "$CPP/gts-upstream" checkout --quiet FETCH_HEAD
fi
echo "Dépendances prêtes."
