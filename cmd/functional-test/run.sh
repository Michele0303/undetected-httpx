#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
comparison_dir=$(mktemp -d)
trap 'rm -rf "$comparison_dir"' EXIT

extension=
if [ "${1:-}" = "windows-latest" ]; then
    extension=.exe
fi

go build -o "$comparison_dir/functional-test$extension" .
go build -o "$comparison_dir/httpx_dev$extension" ../httpx
GOBIN="$comparison_dir" go install github.com/projectdiscovery/httpx/cmd/httpx@v1.12.0

# This optional suite contacts public websites; it is separate from local CI.
"$comparison_dir/functional-test$extension" \
    -main "$comparison_dir/httpx$extension" \
    -dev "$comparison_dir/httpx_dev$extension" \
    -testcases testcases.txt
