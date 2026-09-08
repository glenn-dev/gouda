#!/bin/sh

set -eu

env_file=${1:-.env}

if [ ! -f "$env_file" ]; then
    echo "Error: .env is missing. Copy .env.example to .env and fill the required values." >&2
    exit 1
fi

missing=$(
    awk '
        BEGIN {
            required[1] = "DJANGO_SECRET_KEY"
            required[2] = "POSTGRES_PASSWORD"
        }
        {
            sub(/\r$/, "")
            for (idx = 1; idx <= 2; idx++) {
                key = required[idx]
                prefix = key "="
                if (index($0, prefix) == 1) {
                    value = substr($0, length(prefix) + 1)
                    gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
                    if (value == "\"\"" || value == "\047\047" || value ~ /^#/) {
                        value = ""
                    }
                    present[key] = (length(value) > 0)
                }
            }
        }
        END {
            separator = ""
            for (idx = 1; idx <= 2; idx++) {
                key = required[idx]
                if (!present[key]) {
                    printf "%s%s", separator, key
                    separator = ", "
                }
            }
        }
    ' "$env_file"
)

if [ -n "$missing" ]; then
    echo "Error: .env has missing or blank required values: $missing." >&2
    exit 1
fi

echo "Local environment check passed."
