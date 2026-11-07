# irc.farmOS.org

A website that archives conversations in the #farmOS IRC room. Our bot
(@farmBOT) joins the channel and logs every message, which you can browse and
search on [irc.farmOS.org](https://irc.farmOS.org).

## Prerequisites

[Ansible](https://www.ansible.com/) is used for provisioning the
`irc.farmos.org` server.

Install Ansible (and other dependencies) locally via `pipx`:

```sh
sudo apt-get install pipx
pipx install --include-deps ansible
```

## Setup

Create a Debian server and point the `irc.farmos.org` DNS A record at it.

Add your SSH key to the `root` user's `authorized_keys`.

```sh
ssh-copy-id root@irc.farmos.org
```

Create the local variables file and set the `farmBOT` irc.oftc.net user
password in it.

```sh
cp ansible/vars.yml.example ansible/vars.yml
vi ansible/vars.yml
```

Provision the server with Ansible.

```sh
ansible-playbook -i ansible/inventory.yml ansible/playbook.yml
```

## Usage

SSH into the server and start the stack.

```sh
ssh root@irc.farmos.org
cd /opt/irc.farmOS.org
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
