#!/usr/bin/env bash
# Compila MapMap con la misma receta que usa su CI de GitHub Actions
# (Qt 6.8.0 win64_mingw + MinGW 13.1.0), añadiendo el módulo httpserver
# para que se active el servidor MCP (HAVE_MCP).
#
#   Uso:  bash build-mapmap.sh [-j N]
set -euo pipefail

QT_ROOT="/c/Qt/6.8.0/mingw_64"
MINGW_ROOT="/c/Qt/Tools/mingw1310_64"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/mapmap"
JOBS="${1:-4}"; JOBS="${JOBS#-j}"

for d in "$QT_ROOT" "$MINGW_ROOT" "$SRC_DIR"; do
  [ -d "$d" ] || { echo "FALTA: $d" >&2; exit 1; }
done

export PATH="$QT_ROOT/bin:$MINGW_ROOT/bin:$PATH"

echo "== Qt:     $(qmake -query QT_VERSION)"
echo "== Compil: $(g++ --version | head -1)"
echo "== Fuente: $SRC_DIR"

# qtHaveModule(httpserver) decide si se compila el servidor MCP.
if [ -f "$QT_ROOT/lib/libQt6HttpServer.a" ] || [ -f "$QT_ROOT/lib/Qt6HttpServer.prl" ]; then
  echo "== MCP:    modulo httpserver presente -> servidor MCP ACTIVADO"
else
  echo "== MCP:    httpserver NO instalado -> se compilara SIN MCP" >&2
fi

cd "$SRC_DIR"
qmake mapmap.pro CONFIG+=release
mingw32-make -j"$JOBS"

echo
echo "== Empaquetando dependencias de Qt junto al .exe"
windeployqt --release --no-system-d3d-compiler "MapMap/MapMap.exe"

echo
echo "LISTO -> $SRC_DIR/MapMap/MapMap.exe"
