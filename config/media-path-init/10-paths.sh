#!/bin/sh
set -eu
# Compatibility paths resolve through one mount, enabling cross-directory links.
for pair in downloads:downloads movies:movies tv:tvshows; do
    alias=/${pair%%:*}
    target=/data/${pair#*:}
    if [ -L "$alias" ]; then
        [ "$(readlink "$alias")" = "$target" ] || exit 1
    else
        if [ -d "$alias" ]; then rmdir "$alias"; fi
        ln -s "$target" "$alias"
    fi
done
