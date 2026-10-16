FROM golang:1.26-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /undetected-httpx ./cmd/undetected-httpx

FROM alpine:3.23
RUN apk add --no-cache ca-certificates && adduser -D -u 10001 scanner
COPY --from=build /undetected-httpx /usr/local/bin/undetected-httpx
COPY --from=build /src/LICENSE /src/LICENSE.md /usr/share/licenses/undetected-httpx/
USER scanner
WORKDIR /home/scanner
ENTRYPOINT ["undetected-httpx"]
