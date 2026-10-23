# irc.farmOS.org

## Setup

Create the `config` directory and ensure it is owned by user `1000`.

```sh
mkdir -p config/weechat
chown -R 1000:1000 config
```

Run the `weechat` TUI interactively to create initial configuration.

```sh
docker compose run --rm weechat weechat
```

Quit the TUI.

```sh
/quit
```

## Usage

```sh
docker compose up -d
```
