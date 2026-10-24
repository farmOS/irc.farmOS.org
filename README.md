# irc.farmOS.org

A website that archives conversations in the #farmOS IRC room. Our bot
(@farmBOT) joins the channel and logs every message, which you can browse and
search on [irc.farmOS.org](https://irc.farmOS.org).

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
/set logger.file.time_format %F %T
/set logger.file.path /logs
/set logger.file.flush_delay 0
```

Configure the IRC server connection (replace `<password>` with the `farmBOT`
irc.oftc.net user password).

```sh
/server add oftc irc.oftc.net/6697 -autoconnect
/set irc.server.oftc.nicks farmBOT
/set irc.server.oftc.command /msg NickServ IDENTIFY <password> 
/set irc.server.oftc.autojoin #farmOS
/set irc.server.oftc.autorejoin on
```

Hide the IRC client name and version when quitting.

```sh
/set irc.ctcp.version ""
```

Quit the TUI.

```sh
/quit
```

## Usage

```sh
docker compose up -d
```
