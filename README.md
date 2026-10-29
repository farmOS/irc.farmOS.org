# irc.farmOS.org

A website that archives conversations in the #farmOS IRC room. Our bot
(@farmBOT) joins the channel and logs every message, which you can browse and
search on [irc.farmOS.org](https://irc.farmOS.org).

## Setup

Create a Debian server and point the `irc.farmos.org` DNS A record at it.

Add your SSH key to the `root` user's `authorized_keys`.

```sh
ssh-copy-id root@irc.farmos.org
```

Provision the server with Ansible.

```sh
ansible-playbook -i ansible/inventory.yml ansible/playbook.yml
```

SSH into the server.

```sh
ssh root@irc.farmos.org
```

Create the `config` and `logs` directories and ensure they are owned by user
`1000`.

```sh
cd /opt/irc.farmOS.org
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

## History

The #farmOS IRC room was created in 2014. Our faithful bot (@farmBOT) has been
logging it from the beginning.

- **2014** - The #farmOS IRC room is created on Freenode and the @farmBOT user
  begins logging via the Drupal [Bot](https://www.drupal.org/project/bot)
  module.
- **2018** - The #farmOS Matrix room is created and bridged to the IRC room so
  that @farmBOT can continue its job.
- **2021** - The IRC room moves from Freenode to Libera.chat
  (`irc.libera.chat`).
- **2024** - The IRC room moves to OFTC (`irc.oftc.net`).
- **2026** - The bot and website are rewritten from scratch. WeeChat runs in
  a Docker container as the IRC client and writes log files, which
  [ircjournal](https://github.com/zopieux/ircjournal) makes browsable and
  searchable on the web.

Thank you @farmBOT for your many years of dedicated service!
