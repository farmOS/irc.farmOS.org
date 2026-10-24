# Start with a common Rust build environment.
FROM rust:trixie AS build

# Define the ircjournal version.
ARG IRCJOURNAL_REF=v0.2.0

# Install build dependencies and clone the source.
RUN apt-get update \
	&& apt-get install -y --no-install-recommends \
		build-essential \
		git \
		libssl-dev \
		npm \
		pkg-config \
		sassc \
	&& npm install -g typescript@4.4 \
	&& rm -rf /var/lib/apt/lists/* \
	&& git clone --depth 1 --branch ${IRCJOURNAL_REF} \
		https://github.com/zopieux/ircjournal.git /src

# Update the pinned time crate in the lock file.
# time 0.3.34 does not compile with modern rustc.
WORKDIR /src
RUN cargo update -p time --precise 0.3.36

# Build the watcher.
# SQLX_OFFLINE makes sqlx use the checked-in sqlx-data.json.
ENV SQLX_OFFLINE=1

# Build the workspace.
RUN cargo build --release

# Start a common runtime environment.
FROM debian:trixie-slim AS common

# Install runtime dependencies.
RUN apt-get update \
	&& apt-get install -y --no-install-recommends \
		ca-certificates \
		libssl3 \
	&& rm -rf /var/lib/apt/lists/*

# Set the working directory where ircjournal configuration will live.
WORKDIR /app

# Create the ircj-watch image.
FROM common AS ircj-watch
COPY --from=build /src/target/release/ircj-watch /usr/local/bin/ircj-watch
COPY ircj-watch.toml /app/ircj-watch.toml

# Create the ircj-serve image.
FROM common AS ircj-serve
COPY --from=build /src/target/release/ircj-serve /usr/local/bin/ircj-serve
