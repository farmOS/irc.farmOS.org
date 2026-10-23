# irc.farmOS.org

## Setup

Create the `config` and `logs` directories and ensure they are owned by user
`1000`.

```sh
mkdir -p config/weechat logs
chown -R 1000:1000 config logs
```

Run the `weechat` TUI interactively to create initial configuration.

```sh
docker compose run --rm weechat weechat
```

Configure the logger.

```sh
/set logger.file.path /logs
```

Quit the TUI.

```sh
/quit
```

## Usage

```sh
docker compose up -d
```
